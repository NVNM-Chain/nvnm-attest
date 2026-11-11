"""Keep a bot running for every source in sources/, on one machine.

Each run pulls the kit, so sources merged to main show up. Then, for every source with no bot on this machine,
it makes a wallet (fleet-<NAME>, funded from the faucet), makes the source's registry once, and starts its bot
in the background. A bot you started yourself counts as running, so the fleet never starts a second copy. Bots
keep running between runs, and the next run starts again any bot that stopped.

Run it every hour. On a Mac, --install does that with launchd:
  python3.12 scripts/fleet.py --install                # now, then every hour and at login
  python3.12 scripts/fleet.py --status                 # what runs, with registry links
  python3.12 scripts/fleet.py --skip hyperliquid_mids  # stop that source's fleet bot and leave it off
  python3.12 scripts/fleet.py --uninstall              # no more hourly runs; bots keep running

Local files: fleet/state.json (each source's registry, skipped sources), fleet/logs/<NAME>.log (each bot's
output) and fleet/fleet.log (the hourly runs).
"""
import argparse
import fcntl
import json
import os
import platform
import plistlib
import signal
import subprocess
import sys
import time
from pathlib import Path

import nvnm
from attest_bot import load_source

SOURCES = nvnm.KIT_DIR / "sources"
FLEET_DIR = nvnm.KIT_DIR / "fleet"
STATE = FLEET_DIR / "state.json"
LOGS = FLEET_DIR / "logs"
LABEL = "io.nvnmchain.attest-fleet"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
FUNDER_AMOUNT = 5  # nUSD a --funder wallet sends to a new bot when the faucet says no (~1,400 anchors)


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"registries": {}, "skip": []}


def save_state(state):
    FLEET_DIR.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))


def source_files():
    return sorted(p for p in SOURCES.glob("*.py") if not p.name.startswith("_"))


def running_bots():
    """Every attest_bot.py process on this machine, whoever started it: {source stem: (pid, wallet)}."""
    out = subprocess.run(["ps", "-ax", "-o", "pid=,command="], capture_output=True, text=True).stdout
    bots = {}
    for line in out.splitlines():
        pid, _, command = line.strip().partition(" ")
        args = command.split()
        if not any(arg.endswith("attest_bot.py") for arg in args) or "--dry-run" in args:
            continue
        opts = dict(zip(args, args[1:]))
        if "--source" in opts:
            bots[Path(opts["--source"]).stem] = (int(pid), opts.get("--wallet", ""))
    return bots


def description(src):
    if getattr(src, "DESCRIPTION", ""):
        return src.DESCRIPTION
    lines = (src.__doc__ or "").strip().splitlines()
    return lines[0] if lines else src.NAME


def fund(w3, address, funder, faucet_open):
    """Give a new wallet nUSD: the faucet first, then the --funder wallet. Returns (funded, faucet_open).

    After a faucet refusal the run stops asking it: its limit is 1 request per IP per hour.
    """
    if faucet_open:
        try:
            res = nvnm.request_faucet(address)
            print(f"  faucet sent {res.get('amount')} nUSD: {nvnm.tx_link(res['txHash'])}")
            return nvnm.wait_for_nusd(w3, address, timeout=60) > 0, True
        except nvnm.FaucetError as e:
            print(f"  faucet: {e}")
            faucet_open = False
    if funder:
        token = nvnm.nusd(w3)
        tx, _, _ = nvnm.send(w3, nvnm.load_account(funder), token.functions.transfer(address, int(FUNDER_AMOUNT * 1e6)))
        print(f"  {funder} sent {FUNDER_AMOUNT} nUSD: {nvnm.tx_link(tx)}")
        return nvnm.wait_for_nusd(w3, address, timeout=60) > 0, faucet_open
    return False, faucet_open


def start(w3, path, state, funder, faucet_open):
    """Wallet, nUSD, registry, bot: each step is skipped when it's already done. Returns faucet_open."""
    src = load_source(path)
    wallet = f"fleet-{src.NAME}"
    if not nvnm.wallet_path(wallet).exists():
        nvnm.create_wallet(wallet)
        print(f"  new wallet {wallet}")
    acct = nvnm.load_account(wallet)
    if nvnm.nusd_balance(w3, acct.address) <= 0:
        funded, faucet_open = fund(w3, acct.address, funder, faucet_open)
        if not funded:
            print(f"  {acct.address} has no nUSD yet. The next run tries again.")
            return faucet_open
    rid = state["registries"].get(path.stem)
    if rid is None:
        rid, _, _ = nvnm.create_registry(w3, acct, src.NAME, description(src), {"kit": nvnm.KIT_VERSION})
        state["registries"][path.stem] = rid
        save_state(state)
        print(f"  new registry {rid}: {nvnm.EXPLORER}/anchoring/{rid}")
    LOGS.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "NVNM_PRIVATE_KEY"}
    env["PYTHONUNBUFFERED"] = "1"
    log_path = LOGS / f"{src.NAME}.log"
    with open(log_path, "a") as log:
        proc = subprocess.Popen(
            [sys.executable, str(nvnm.KIT_DIR / "scripts" / "attest_bot.py"),
             "--wallet", wallet, "--registry", str(rid), "--source", str(path)],
            cwd=nvnm.KIT_DIR, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)  # its own session: it outlives this run and the launchd job
    print(f"  started, pid {proc.pid}, log {log_path}")
    return faucet_open


def pull():
    r = subprocess.run(["git", "-C", str(nvnm.KIT_DIR), "pull", "--ff-only", "--quiet"], capture_output=True, text=True)
    if r.returncode:
        print(f"git pull failed, so this run uses the sources already here: {(r.stderr or r.stdout).strip()}")


def show(state):
    bots = running_bots()
    for path in source_files():
        stem, rid = path.stem, state["registries"].get(path.stem)
        if stem in state["skip"]:
            what = "skipped"
        elif stem in bots:
            pid, wallet = bots[stem]
            what = f"running, pid {pid}, wallet {wallet}"
        else:
            what = "not running"
        link = f"  {nvnm.EXPLORER}/anchoring/{rid}" if rid is not None else ""
        print(f"{stem:<28} {what}{link}")


def skip(state, name):
    stem = Path(name).stem
    if stem not in state["skip"]:
        state["skip"].append(stem)
        save_state(state)
    pid, wallet = running_bots().get(stem, (None, ""))
    if pid and wallet.startswith("fleet-"):
        os.kill(pid, signal.SIGINT)  # like Ctrl-C, so the bot releases its wallet on the way out
        print(f"{stem}: stopped its bot (pid {pid}) and skipped it from now on.")
    elif pid:
        print(f"{stem}: skipped from now on. Its bot (pid {pid}, wallet {wallet}) isn't the fleet's, so it keeps running.")
    else:
        print(f"{stem}: skipped from now on.")


def unskip(state, name):
    stem = Path(name).stem
    if stem in state["skip"]:
        state["skip"].remove(stem)
        save_state(state)
    print(f"{stem}: the next run starts it.")


def install(funder):
    run = [sys.executable, str(Path(__file__).resolve())] + (["--funder", funder] if funder else [])
    if platform.system() != "Darwin":
        line = f"0 * * * * cd {nvnm.KIT_DIR} && {' '.join(run)} >> {FLEET_DIR / 'fleet.log'} 2>&1"
        raise SystemExit(f"--install uses launchd, which is macOS only. Elsewhere add this line with crontab -e:\n{line}")
    FLEET_DIR.mkdir(exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": run,
        "WorkingDirectory": str(nvnm.KIT_DIR),
        "StartInterval": 3600,
        "RunAtLoad": True,
        "AbandonProcessGroup": True,  # the bots it starts keep running after each hourly run ends
        "StandardOutPath": str(FLEET_DIR / "fleet.log"),
        "StandardErrorPath": str(FLEET_DIR / "fleet.log"),
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin", "PYTHONUNBUFFERED": "1"},
    }))
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(PLIST)], capture_output=True)  # an older install, if any
    r = subprocess.run(["launchctl", "bootstrap", domain, str(PLIST)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"launchctl couldn't load {PLIST}: {r.stderr.strip()}")
    print(f"Installed. The fleet runs now, then every hour and at login. Its log: {FLEET_DIR / 'fleet.log'}")
    print("See what runs: python3.12 scripts/fleet.py --status")


def uninstall():
    if PLIST.exists():
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST)], capture_output=True)
        PLIST.unlink()
    print("Uninstalled: no more hourly runs. Running bots keep going; stop one with --skip <source>.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--funder", help="a funded wallet that pays new bots when the faucet says no")
    p.add_argument("--no-pull", action="store_true", help="don't git pull first")
    p.add_argument("--status", action="store_true", help="show what runs and change nothing")
    p.add_argument("--skip", metavar="SOURCE", help="stop that source's fleet bot and don't start it again")
    p.add_argument("--unskip", metavar="SOURCE", help="start that source again from the next run")
    p.add_argument("--install", action="store_true", help="run the fleet now, then every hour (macOS launchd)")
    p.add_argument("--uninstall", action="store_true", help="stop the hourly runs; running bots keep going")
    a = p.parse_args()

    if platform.system() == "Darwin" and sys.executable.startswith("/usr/bin/"):
        raise SystemExit("macOS's built-in python3 can't reach the network (its TLS is too old). "
                         "Run this with Homebrew's: brew install python@3.12, then python3.12 scripts/fleet.py")
    if os.getenv("NVNM_PRIVATE_KEY"):
        raise SystemExit("Unset NVNM_PRIVATE_KEY first: the fleet gives every bot its own wallet.")
    if a.install:
        return install(a.funder)
    if a.uninstall:
        return uninstall()
    state = load_state()
    if a.status:
        return show(state)
    if a.skip:
        return skip(state, a.skip)
    if a.unskip:
        return unskip(state, a.unskip)

    FLEET_DIR.mkdir(exist_ok=True)
    lock = open(FLEET_DIR / "lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another fleet run is still going. This one stops.")
    print(f"--- fleet run {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    if not a.no_pull:
        pull()
    bots = running_bots()
    todo = [path for path in source_files() if path.stem not in state["skip"] and path.stem not in bots]
    if todo:
        w3 = nvnm.connect()
        faucet_open = True
        for path in todo:
            print(f"{path.stem}: no bot running")
            try:
                faucet_open = start(w3, path, state, a.funder, faucet_open)
            except (Exception, SystemExit) as e:  # one broken source must not stop the others
                print(f"  couldn't start it: {e}")
    show(state)


if __name__ == "__main__":
    main()
