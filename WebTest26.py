#!/usr/bin/env python3
"""WebTest26 - client input/timing evidence for the CHAIN web UI.

Drives the real page in headless Chrome with real DOM key events (the ?selftest=1
harness): Enter starts a run, arrow keys aim, ball keys respect stock, Space fires,
mid-playback keys are swallowed (exactly one shot consumed), playback completes and
applies the score, help opens/closes, Q quits with a run code, and the code resumes
to the same board. Results are posted back to the server (CHAIN_SELFTEST=1) and
checked here. Skips cleanly if no Chrome/Chromium binary is present.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TMP = tempfile.mkdtemp(prefix="chainweb26-")
os.environ["CHAIN_BEST_FILE"] = os.path.join(TMP, "best.txt")
os.environ["CHAIN_MARATHON_FILE"] = os.path.join(TMP, "marathon.txt")
os.environ["CHAIN_TOUR_FILE"] = os.path.join(TMP, "tour.txt")
os.environ["CHAIN_LONG_TOUR_FILE"] = os.path.join(TMP, "longtour.txt")
os.environ["CHAIN_SESSION_FILE"] = os.path.join(TMP, "session.json")
# the long tour legs need the unlocked state: a completed tour record
open(os.environ["CHAIN_TOUR_FILE"], "w").write("9,100")
os.environ["CHAIN_SELFTEST"] = "1"

import ChainWeb as W

Fails = []

def Check(name, ok):
    print(("ok  " if ok else "FAIL") + " " + name)
    if not ok:
        Fails.append(name)

CHROME = None
for cand in ("google-chrome", "chromium", "chromium-browser"):
    path = shutil.which(cand)
    if path:
        CHROME = path
        break

if not CHROME:
    print("SKIP: no chrome/chromium binary available - client selftest not run")
    sys.exit(0)

SERVER = W.make_server(0)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
url = "http://127.0.0.1:" + str(SERVER.server_address[1]) + "/?k=" + W.TOKEN + "&selftest=1"
proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                         "--window-size=1366,768", "--virtual-time-budget=120000", "--dump-dom", url],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
deadline = time.time() + 90
while time.time() < deadline:
    if SERVER.session.selftest is not None:
        break
    time.sleep(0.5)
proc.terminate()
SERVER.shutdown()

lines = SERVER.session.selftest
Check("client selftest reported back within 90s", lines is not None)
if lines:
    for line in lines:
        print("   " + line)
    bad = [l for l in lines if l.startswith("FAIL")]
    Check("no client-side failures", not bad)
    import re as _re
    _m = _re.match(r"checks (\d+) complete$", lines[-1]) if lines else None
    Check("selftest ran to completion (terminal marker)", bool(_m) and int(_m.group(1)) == len(lines) - 1)
print("FAILS", len(Fails))
sys.exit(1 if Fails else 0)
