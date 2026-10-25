#!/usr/bin/env python3
"""TourTest26 - the tour (ChainDemo.py + ChainWeb.py).

The tour is a fixed nine-board ladder (TourSeeds) under its own quota/shot
pressure curve (TourQuotas/TourShotLimits): one failed board ends the tour,
clearing all nine completes it. Pins the curated table and curve, CH25T code
round-trips and rejections, tour records (ChainTour.txt), measured per-board
difficulty of the nine actual boards under their actual quotas/limits,
full-tour Policy-bot simulation bounds, the localhost web tour flows, and the
terminal tour loop through a real pseudo-terminal. Asserts and exits non-zero
on failure.

Simulation caveat (kept distinct from the pins): bot clear rates are a policy
proxy, not human difficulty proof. Across the simulation trials only the bot's
aim policy randomness varies - the nine boards, quotas, shot limits and draft
offers are fixed by the table, so the spread measures the bot, not the tour's
variety.
"""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request

Here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, Here)

TMP = tempfile.mkdtemp(prefix="chaintour-")
os.environ["CHAIN_BEST_FILE"] = os.path.join(TMP, "best.txt")
os.environ["CHAIN_MARATHON_FILE"] = os.path.join(TMP, "marathon.txt")
os.environ["CHAIN_TOUR_FILE"] = os.path.join(TMP, "tour.txt")
os.environ["CHAIN_LONG_TOUR_FILE"] = os.path.join(TMP, "longtour.txt")
os.environ["CHAIN_SESSION_FILE"] = os.path.join(TMP, "session.json")

import random
import ChainDemo as E

Fails = []
def Check(name, ok):
    print(("ok  " if ok else "FAIL") + " " + name)
    if not ok:
        Fails.append(name)

# the policy bot from ChainTest15 (shared difficulty yardstick)
BotSrc = open(os.path.join(Here, "ChainTest15.py")).read().split("bad = collections.Counter()")[0]
BotG = {"__file__": os.path.join(Here, "ChainTest15.py")}
exec(compile(BotSrc, "ChainTest15.py", "exec"), BotG)
Policy, BotKind = BotG["Policy"], BotG["Kind"]

# --- 1. the curated table and pressure curve --------------------------------
Check("nine tour boards", E.TourLength == 9 and len(E.TourSeeds) == 9)
Check("tour seed table pinned", E.TourSeeds == (30005, 30056, 30002, 30007, 30015, 30008, 30014, 30021, 30006))
Check("tour quota curve pinned", E.TourQuotas == (9, 10, 10, 11, 11, 12, 12, 12, 12))
Check("tour shot curve pinned", E.TourShotLimits == (8, 8, 7, 7, 7, 6, 6, 6, 5))
families = [E.Board(s).Style.split(" ")[0] for s in E.TourSeeds]
Check("family order is the measured easy-to-hard ramp",
      families == ["zigzag", "pinwheel", "columns", "hourglass", "towers", "cross", "spiral", "bowl", "rings"])
board1 = E.TourBoard(1, {})
Check("tour board 1 wiring", board1.Seed == 30005 and board1.Quota == 9 and board1.Limit == 8
      and board1.Credit == board1.Total - 9 and board1.Stock == {"r": 0, "x": 0, "s": 0})
board9 = E.TourBoard(9, {"r": 2, "x": 1})
Check("tour board 9 wiring + satchel stock", board9.Quota == 12 and board9.Limit == 5
      and board9.Credit == board9.Total - 12 and board9.Stock == {"r": 2, "x": 1, "s": 0})
hashes = [E.TourBoard(k, {}).Hash() for k in range(1, 10)]
# the curated boards under tour pressure (quota/limit/stock fold into the hash, as with marathon boards)
Check("tour board hashes pinned", hashes == ["9bc41d12", "99f5489b", "7dd773ce", "50897f22", "c85e06e1",
                                             "5da9ee95", "db6e4884", "f438b1b4", "6ac57132"] and len(set(hashes)) == 9)

# --- 2. CH25T codes ----------------------------------------------------------
st0 = E.RunState(0, tour=True)
b0 = E.Attach(E.TourBoard(1, st0.Satchel), st0)
Check("empty tour code", st0.Code(b0) == "CH25T--")
r0 = E.ParseRunCodeFull("CH25T--")
Check("tour code parses to the tour arm", r0 == (0, [], [[]], False, False, False, False, True, False))
Check("run arm reports no tour", E.ParseRunCodeFull("CH24R-40001-9.10.10--4.3.15")[7] is False)
Check("marathon arm reports no tour", E.ParseRunCodeFull("CH23M-40003--38r.2")[7] is False)

rng = random.Random(90007)
stT = E.RunState(0, tour=True)
bT = E.Attach(E.TourBoard(1, stT.Satchel), stT)
while True:
    while not bT.Over():
        left = bT.Limit + bT.Extra - len(bT.Log)
        aim, hit = Policy(bT, rng)
        bT.Play(aim, None, BotKind(bT, hit, left))
    if not bT.Won():
        break
    stT.Boards.append(bT)
    offer = E.RunOffer(stT.Run, stT.K)
    pick = offer[0] if offer else "0"
    stT.Picks.append(pick)
    stT.Satchel[pick] = stT.Satchel.get(pick, 0) + 1
    stT.K += 1
    bT = E.Attach(E.TourBoard(stT.K, stT.Satchel), stT)
midCode = stT.Code(bT)
Check("scripted tour fell mid-ladder", stT.K == 6 and midCode.startswith("CH25T-xsrxs-"))
stR, bR = E.ResumeRun(midCode)
Check("tour code resumes to the same board", stR.Tour and stR.K == 6 and bR.Hash() == bT.Hash()
      and bR.Score == bT.Score and stR.Satchel == stT.Satchel and stR.Picks == stT.Picks)
Check("resumed tour re-emits the same code", stR.Code(bR) == midCode)
Check("resumed tour board is the curated board 6", bR.Seed == E.TourSeeds[5] and bR.Quota == 12 and bR.Limit == 6)
# a mid-board code with no pick yet is legitimate (quit codes end open mid-board)
wst, wb = E.ResumeRun("CH25T--1")
rst = E.RunState(0, tour=True)
ref = E.Attach(E.TourBoard(1, rst.Satchel), rst)
ref.Play(1, None, "n")
Check("mid-board tour code resumes to play", wst.Tour and not wb.Won() and not wb.Over() and wst.K == 1
      and wb.Score == ref.Score and wb.Hash() == ref.Hash())
for bad in ("CH25T-x-", "CH25T-xs-", "CH24T--", "CH25T--1/2/3/4/5/6/7/8/9/10",
            "CH25T-xsrxsrxsx-", "CH25M-0--"):
    try:
        E.ParseRunCode(bad)
        ok = False
    except ValueError:
        ok = True
    Check("rejects " + bad, ok)

# --- 3. tour records ---------------------------------------------------------
tourPath = os.environ["CHAIN_TOUR_FILE"]
best, isNew, saved = E.RecordTourBest(5, 12345)
Check("first tour record saves", isNew and saved and best == (5, 12345))
Check("tour record file holds boards,total", open(tourPath).read().strip() == "5,12345")

# HUD progress label: tour boards name the tour and its length (Screen.Frame, headless)
scr = E.Screen(True, 0)
hudB = E.Attach(E.TourBoard(1, {}), E.RunState(0, tour=True))
hudFrame = "\n".join(scr.Frame(hudB, 0, False))
Check("tour hud shows tour progress", "Tour board 1/9" in hudFrame)
runB = E.Attach(E.RunBoard(0, 1, {}, False, False, None, None), E.RunState(0))
runFrame = "\n".join(scr.Frame(runB, 0, False))
Check("run hud still shows run progress", " Board 1/3" in runFrame)

def PlayTourBoards(rngSeed, count):
    st = E.RunState(0, tour=True)
    b = E.Attach(E.TourBoard(1, st.Satchel), st)
    rng = random.Random(rngSeed)
    while True:
        while not b.Over():
            left = b.Limit + b.Extra - len(b.Log)
            a, hit = Policy(b, rng)
            b.Play(a, None, BotKind(b, hit, left))
        if not b.Won() or len(st.Boards) + 1 >= count:
            return st, b
        st.Boards.append(b)
        offer = E.RunOffer(st.Run, st.K)
        pick = offer[0] if offer else "0"
        st.Picks.append(pick)
        if pick != "0":
            st.Satchel[pick] = st.Satchel.get(pick, 0) + 1
        st.K += 1
        b = E.Attach(E.TourBoard(st.K, st.Satchel), st)

mSt, mB = PlayTourBoards(90001, 3)
midTxt = chr(10).join(scr.Frame(mB, 0, False, None, "", True))
Check("mid-tour win offers the upgrade pick, not last board",
      mSt.K == 3 and "pick an upgrade" in midTxt and "LAST BOARD" not in midTxt and "restart the tour" in midTxt)
lSt, lB = PlayTourBoards(90007, 9)
lostTxt = chr(10).join(scr.Frame(lB, 0, False, None, "", True))
Check("lost tour board offers end the tour",
      not lB.Won() and "end the tour" in lostTxt and "restart the tour" in lostTxt and "new run" not in lostTxt)
fSt, fB = PlayTourBoards(90001, 9)
lastTxt = chr(10).join(scr.Frame(fB, 0, False, None, "", True))
Check("final tour board offers finish the tour", fSt.K == 9 and fB.Won() and "finish the tour" in lastTxt)

menuTxt = chr(10).join(E.TitleLines(scr, len(E.Premise), "menu"))
Check("menu lists the tour record", "best tour 5 boards, score 12345" in menuTxt)
Check("help names the tour", any("tour" in line.lower() for line in E.Help))
best, isNew, saved = E.RecordTourBest(4, 99999)
Check("fewer boards never beats more boards", not isNew and best == (5, 12345))
best, isNew, saved = E.RecordTourBest(5, 20000)
Check("same boards, higher score beats", isNew and best == (5, 20000))
best, isNew, saved = E.RecordTourBest(9, 100)
Check("more boards beats at any score", isNew and best == (9, 100))
lines = E.TourBestLines((9, 100), True, True)
Check("tour record wording", "Local best tour: 9 boards, score 100 (new)" in lines[0] and "Saved to" in lines[1])
os.environ["CHAIN_TOUR_FILE"] = "/nonexistent-dir/tour.txt"
best, isNew, saved = E.RecordTourBest(9, 50000)
Check("unwritable tour record reports not saved", isNew and not saved and best == (9, 50000))
lines = E.TourBestLines(best, isNew, saved)
Check("unsaved wording honest", any("could not be written" in line for line in lines))
os.environ["CHAIN_TOUR_FILE"] = tourPath

# --- 4. measured difficulty of the nine actual tour boards -------------------
# Each board played bare (no satchel) under its real tour quota/limit - the
# isolated difficulty reference, kept distinct from the family-average ranking
# that guided the ordering. Soft bounds only: this is a bot proxy.
print("   per-board clear rates (bare, real tour pressure):")
bare = []
for k in range(1, 10):
    wins = 0
    for trial in range(60):
        brng = random.Random(70000 + 1000 * k + trial)
        bb = E.TourBoard(k, {})
        while not bb.Over():
            left = bb.Limit + bb.Extra - len(bb.Log)
            aim, hit = Policy(bb, brng)
            bb.Play(aim, None, BotKind(bb, hit, left))
        wins += bb.Won()
    bare.append(wins / 60.0)
    print("   board", k, families[k - 1], str(round(100 * wins / 60)) + "%")
Check("board 1 is a gentle opener (bare bot clears at least 70%)", bare[0] >= 0.70)
Check("early boards (1-3) mostly clear (bare bot at least 60%)", min(bare[0:3]) >= 0.60)
Check("late boards (7-9) carry the jeopardy (bare bot at most 60%)", max(bare[6:9]) <= 0.60)
Check("board 9 is the hardest slot (bare bot no better than board 1)", bare[8] <= bare[0])

# --- 5. full-tour simulation bounds ------------------------------------------
complete = 0
failAt = {}
trials = 200
for trial in range(trials):
    trng = random.Random(90000 + trial)
    stS = E.RunState(0, tour=True)
    bS = E.Attach(E.TourBoard(1, stS.Satchel), stS)
    while True:
        while not bS.Over():
            left = bS.Limit + bS.Extra - len(bS.Log)
            aim, hit = Policy(bS, trng)
            bS.Play(aim, None, BotKind(bS, hit, left))
        if not bS.Won():
            failAt[stS.K] = failAt.get(stS.K, 0) + 1
            break
        stS.Boards.append(bS)
        if stS.K >= E.TourLength:
            complete += 1
            break
        offer = E.RunOffer(stS.Run, stS.K)
        pick = offer[0] if offer else "0"
        stS.Picks.append(pick)
        stS.Satchel[pick] = stS.Satchel.get(pick, 0) + 1
        stS.K += 1
        bS = E.Attach(E.TourBoard(stS.K, stS.Satchel), stS)
rate = complete / trials
print("   full-tour bot completion", str(round(100 * rate, 1)) + "% over", trials, "trials; failures by board:", dict(sorted(failAt.items())))
Check("tour is completable but earned (bot completes 10-65%)", 0.10 <= rate <= 0.65)
Check("nobody falls on board 1", failAt.get(1, 0) == 0)
Check("failures cluster late (board 5+)", sum(v for k, v in failAt.items() if k >= 5) >= 0.5 * sum(failAt.values()))

# --- 6. web tour flows -------------------------------------------------------
import ChainWeb as W

SERVER = W.make_server(0)
PORT = SERVER.server_address[1]
threading.Thread(target=SERVER.serve_forever, daemon=True).start()

def api(path, body="GET", raw=False):
    url = "http://127.0.0.1:" + str(PORT) + path
    if body != "GET":
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as r:
            data = r.read()
            return (r.status, data.decode()) if raw else (r.status, json.loads(data))
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if raw:
            return (e.code, body)
        try:
            return (e.code, json.loads(body))
        except ValueError:
            return (e.code, {"raw": body})

K = W.TOKEN

status, st = api("/api/start?k=" + K, {"mode": "tour"})
engSt = E.RunState(0, tour=True)
engB = E.Attach(E.TourBoard(1, engSt.Satchel), engSt)
Check("web tour starts on curated board 1", status == 200 and st["screen"] == "play" and st["board"]["k"] == 1
      and st["board"]["style"].startswith("zigzag"))
Check("web tour runs as run 0 (fixed ladder)", st["board"]["run"] == 0)
Check("web tour board hash matches engine", st["board"]["hash"] == engB.Hash())
Check("web tour pressure from the curve", st["board"]["quota"] == 9 and st["board"]["limit"] == 8)
Check("unknown mode still rejected", api("/api/start?k=" + K, {"mode": "tournament"})[0] == 400)

# lose board 1 through the API: TOUR OVER, record written, code issued
for i in range(14):
    if st["screen"] != "play":
        break
    rS = api("/api/shot?k=" + K, {"aim": 0, "ball": "n"})[1]
    st = api("/api/done?k=" + K, {"gen": rS["gen"], "shotId": rS["shotId"]})[1]
Check("web tour loss reaches gameover", st["screen"] == "gameover" and st["result"]["kind"] == "tourover")
Check("web tour over counts cleared boards", st["result"]["cleared"] == 0 and st["result"]["code"].startswith("CH25T--"))
with open(os.environ["CHAIN_TOUR_FILE"]) as fh:
    saved = fh.read().strip()
Check("web tour best recorded", saved == str(st["result"]["bestBoards"]) + "," + str(st["result"]["bestScore"]))
status, st = api("/api/advance?k=" + K, {})
Check("web advance restarts the tour", status == 200 and st["screen"] == "play" and st["board"]["k"] == 1
      and st["board"]["style"].startswith("zigzag") and st["board"]["quota"] == 9)
Check("web board json flags the tour", st["board"].get("tour") is True and st["board"].get("marathon") is False)

# win board 1 through the API with scripted policy aims (seed 90001, board 1 shots)
crng = random.Random(90001)
script = []   # (aim, kind) across the whole completing tour
cSt = E.RunState(0, tour=True)
cB = E.Attach(E.TourBoard(1, cSt.Satchel), cSt)
cPicks = []
while True:
    while not cB.Over():
        left = cB.Limit + cB.Extra - len(cB.Log)
        aim, hit = Policy(cB, crng)
        kind = BotKind(cB, hit, left)
        cB.Play(aim, None, kind)
        script.append((aim, kind))
    if not cB.Won():
        break
    cSt.Boards.append(cB)
    if cSt.K >= E.TourLength:
        break
    offer = E.RunOffer(cSt.Run, cSt.K)
    pick = offer[0] if offer else "0"
    cPicks.append(pick)
    cSt.Picks.append(pick)
    cSt.Satchel[pick] = cSt.Satchel.get(pick, 0) + 1
    cSt.K += 1
    cB = E.Attach(E.TourBoard(cSt.K, cSt.Satchel), cSt)
completeCode = cSt.Code() if cSt.K >= E.TourLength else None
Check("scripted tour completes (fixture sanity)", completeCode is not None and len(script) == 57 and len(cPicks) == 8)

status, st = api("/api/start?k=" + K, {"mode": "tour"})
picksSent = 0
for aim, kind in script:
    if st["screen"] == "draft":
        st = api("/api/pick?k=" + K, {"pick": str(st["offer"].index(cPicks[picksSent]) + 1)})[1]
        picksSent += 1
    rS = api("/api/shot?k=" + K, {"aim": aim, "ball": kind})[1]
    st = api("/api/done?k=" + K, {"gen": rS["gen"], "shotId": rS["shotId"]})[1]
    if st["screen"] == "gameover":
        break
Check("web tour reaches TOUR COMPLETE", st["screen"] == "complete" and st["result"]["kind"] == "tourcomplete")
Check("web tour complete code matches engine", st["result"]["code"] == completeCode)
Check("web tour complete totals match engine", st["result"]["total"] == sum(b.Score for b in cSt.Boards))
with open(os.environ["CHAIN_TOUR_FILE"]) as fh:
    saved = fh.read().strip()
Check("web tour complete best recorded", saved == "9," + str(st["result"]["total"]))
status, st = api("/api/advance?k=" + K, {})
Check("web advance after completion starts the tour again", status == 200 and st["board"]["k"] == 1
      and st["board"]["style"].startswith("zigzag"))

# restart keeps the tour
api("/api/shot?k=" + K, {"aim": 0, "ball": "n"})
st = api("/api/restart?k=" + K, {})[1]
Check("web restart stays in the tour", st["screen"] == "play" and st["board"]["k"] == 1
      and st["board"]["style"].startswith("zigzag") and "Tour restarted" in st["message"])
api("/api/quit?k=" + K, {})

status, st = api("/api/state?k=" + K)
Check("web title lists the tour record", status == 200 and st["records"].get("bestTourBoards") == 9
      and st["records"]["bestTourScore"] == int(saved.split(",")[1]))

# watch a tour code: replays to over, hashes match the engine, writes no records
os.remove(os.environ["CHAIN_TOUR_FILE"])
wState = E.RunState(0, tour=True)
wBoard = E.Attach(E.TourBoard(1, wState.Satchel), wState)
status, w = api("/api/watch?k=" + K, {"code": midCode})
Check("tour watch starts", status == 200)
hashOk = True
watchEnd = None
advances = 0
while True:
    status, d = api("/api/watchnext?k=" + K, {})
    if "frames" in d:
        wBoard.Play(d["shot"]["aim"], None, d["shot"]["kind"])
        hashOk = hashOk and d["board"]["hash"] == wBoard.Hash()
        api("/api/watchdone?k=" + K, {"gen": d["gen"], "shotId": d["shotId"]})
    elif "watchAdvance" in d:
        advances += 1
        wState.Boards.append(wBoard)
        pick = d["watchAdvance"]["pick"]
        wState.Picks.append(pick)
        if pick != "0":
            wState.Satchel[pick] = wState.Satchel.get(pick, 0) + 1
        wState.K += 1
        wBoard = E.Attach(E.TourBoard(wState.K, wState.Satchel), wState)
    else:
        watchEnd = d["watchDone"]
        wState.Boards.append(wBoard)
        break
Check("tour watch replays the failure", watchEnd is not None and watchEnd["won"] is False and advances == 5 and wState.K == 6)
Check("tour watch shot hashes match the engine", hashOk)
Check("tour watch writes no records", not os.path.exists(os.environ["CHAIN_TOUR_FILE"]))
Check("bad tour watch rejected", api("/api/watch?k=" + K, {"code": "CH25T-xs-"})[0] == 400)
api("/api/quit?k=" + K, {})

# watch a partial tour code (last board won, tour continues): the run stays open
pSt = E.RunState(0, tour=True)
pB = E.Attach(E.TourBoard(1, pSt.Satchel), pSt)
prng = random.Random(90001)
while len(pSt.Boards) < 3:
    while not pB.Over():
        left = pB.Limit + pB.Extra - len(pB.Log)
        aim, hit = Policy(pB, prng)
        pB.Play(aim, None, BotKind(pB, hit, left))
    assert pB.Won()
    pSt.Boards.append(pB)
    if len(pSt.Boards) >= 3:
        break
    offer = E.RunOffer(pSt.Run, pSt.K)
    pick = offer[0] if offer else "0"
    pSt.Picks.append(pick)
    if pick != "0":
        pSt.Satchel[pick] = pSt.Satchel.get(pick, 0) + 1
    pSt.K += 1
    pB = E.Attach(E.TourBoard(pSt.K, pSt.Satchel), pSt)
partCode = pSt.Code()
if os.path.exists(os.environ["CHAIN_TOUR_FILE"]):
    os.remove(os.environ["CHAIN_TOUR_FILE"])
status, _ = api("/api/watch?k=" + K, {"code": partCode})
Check("partial tour watch starts", status == 200)
assert status == 200
partEnd = None
while True:
    status, d = api("/api/watchnext?k=" + K, {})
    if "frames" in d:
        api("/api/watchdone?k=" + K, {"gen": d["gen"], "shotId": d["shotId"]})
    elif "watchAdvance" in d:
        pass
    else:
        partEnd = d["watchDone"]
        break
Check("partial tour watch stays open", partEnd is not None and partEnd["won"] is True and partEnd["open"] is True
      and partEnd["boardsCleared"] == 3)
api("/api/quit?k=" + K, {})
Check("partial tour watch writes no records", not os.path.exists(os.environ["CHAIN_TOUR_FILE"]))

# --- 7. terminal tour loop through a real pty --------------------------------
import pty as Pty
import select as Select
import struct, fcntl, termios, re, time

def PanelBlock(txt, heading):
    # the boxed panel rows following a heading; Drive turns each trailing
    # escape into a newline, so artifact-empty lines sit between real rows
    lines = txt.split("\n")
    block = []
    grab = False
    for line in lines:
        s = line.strip()
        if heading in s:
            grab = True
        if not grab:
            continue
        if not s:
            continue
        if "|" not in line and "│" not in line and not set(s) <= set("+-"):
            break
        block.append(line.rstrip())
    return block


def PanelCode(txt, label):
    # reassemble a code that ChainDemo.CodeLines splits across boxed panel rows
    lines = txt.split("\n")
    parts = []
    grab = False
    for line in lines:
        s = line.strip()
        if label in s:
            grab = True
            continue
        if grab:
            if not s:
                continue
            body = s.strip("|│").strip()
            if not body:
                break
            parts.append(body)
    return "".join(parts)


def Drive(args, keys, cols=110, rows=50, wait=0.12, tail=1.2):
    pid, fd = Pty.fork()
    if pid == 0:
        os.chdir(Here)
        os.execvp("python3", ["python3", "ChainDemo.py", "--delay", "0", "--mono", "--ascii"] + args)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    buf = b""
    def Pump(t):
        nonlocal buf
        end = time.time() + t
        while time.time() < end:
            r, _, _ = Select.select([fd], [], [], 0.03)
            if r:
                try:
                    d = os.read(fd, 65536)
                except OSError:
                    return
                if not d:
                    return
                buf += d
    Pump(0.8)
    for k in keys:
        os.write(fd, {"SP": b" ", "R": b"\x1b[C", "L": b"\x1b[D", "w": b"\x00"}.get(k, k.encode()))
        Pump(wait)
    Pump(tail)
    try:
        os.waitpid(pid, os.WNOHANG)
    except OSError:
        pass
    return re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"\n", buf).decode("utf8", "replace")

def TourKeys(seed):
    trng = random.Random(seed)
    tSt = E.RunState(0, tour=True)
    tB = E.Attach(E.TourBoard(1, tSt.Satchel), tSt)
    keys = []
    aim = E.DefaultAim
    while True:
        while not tB.Over():
            left = tB.Limit + tB.Extra - len(tB.Log)
            a, hit = Policy(tB, trng)
            kind = BotKind(tB, hit, left)
            d = a - aim
            keys += ["R"] * d if d > 0 else ["L"] * (-d)
            aim = a
            if kind != "n":
                keys.append(str("nrxs".index(kind) + 1))
            keys += ["SP", "w", "w", "w", "w", "w"]
            tB.Play(a, None, kind)
        if not tB.Won():
            return keys, tSt, tB, False
        tSt.Boards.append(tB)
        if tSt.K >= E.TourLength:
            return keys, tSt, tB, True
        offer = E.RunOffer(tSt.Run, tSt.K)
        pick = offer[0] if offer else "0"
        tSt.Picks.append(pick)
        tSt.Satchel[pick] = tSt.Satchel.get(pick, 0) + 1
        keys += ["w", "w", "n", "w", "w"]
        keys += ["0" if pick == "0" else str(E.RunOffer(tSt.Run, tSt.K).index(pick) + 1), "w", "w"]
        tSt.K += 1
        tB = E.Attach(E.TourBoard(tSt.K, tSt.Satchel), tSt)

os.environ["CHAIN_TOUR_FILE"] = os.path.join(TMP, "tour-pty.txt")
menu = Drive(["--menu"], ["w", "w"])
Check("menu offers the tour", "[T] the tour" in menu)
menuGo = Drive(["--menu"], ["w", "w", "t", "w", "w", "w", "w"], wait=0.15)
Check("t starts the tour", "30005" in menuGo and "(zigzag)" in menuGo)
Check("tour hud shows tour progress", "Tour board 1/9" in menuGo)
menuPick = Drive(["--menu"], ["w", "w", "\x1b[B", "\x1b[B", "\r", "w", "w", "w", "w"], wait=0.15)
Check("menu cursor starts the tour", "30005" in menuPick and "(zigzag)" in menuPick)

keys, tSt, tB, won = TourKeys(90007)
failCode = tSt.Code(tB)
txt = Drive(["--tour"], ["w", "w"] + keys + ["w", "w", "n", "w", "w", "q", "w", "w"])
Check("terminal TOUR OVER panel", "TOUR OVER" in txt)
Check("terminal tour cleared count", "5 boards cleared of 9" in txt.replace("\n", " "))
Check("terminal tour over panel fits the box", max(len(l) for l in PanelBlock(txt, "TOUR OVER")) <= 104)
Check("terminal tour code matches engine", PanelCode(txt, "Tour code") == failCode)
Check("terminal tour best line shown", "Local best tour:" in txt)
saved = open(os.environ["CHAIN_TOUR_FILE"]).read().strip()
total = sum(b.Score for b in tSt.Boards) + tB.Score
Check("terminal tour record holds 5,total", saved == "5," + str(total))
Check("terminal lost board offers end the tour", "end the tour" in txt)

rs = Drive(["--resume", failCode], ["w", "w", "w"], wait=0.15)
Check("resume wiring loads the tour", "30008" in rs and "Tour board 6/9" in rs)
txt = Drive(["--tour"], ["w", "w"] + keys + ["w", "w", "r", "w", "w", "w"])
Check("terminal restart keeps the tour", "Tour restarted" in txt and "30005" in txt)

keys, tSt, tB, won = TourKeys(90001)
doneCode = tSt.Code()
txt = Drive(["--tour"], ["w", "w"] + keys + ["w", "w", "n", "w", "w", "q", "w", "w"])
Check("terminal TOUR COMPLETE panel", won and "TOUR COMPLETE" in txt)
Check("terminal completion counts all nine", "all 9 boards cleared" in txt.replace("\n", " "))
Check("terminal tour complete panel fits the box", max(len(l) for l in PanelBlock(txt, "TOUR COMPLETE")) <= 104)
Check("terminal completion code matches engine", PanelCode(txt, "Tour code") == doneCode)
saved = open(os.environ["CHAIN_TOUR_FILE"]).read().strip()
Check("terminal completion record holds 9,total", saved == "9," + str(sum(b.Score for b in tSt.Boards)))
Check("terminal tour completion does not touch the long record", not os.path.exists(os.environ["CHAIN_LONG_TOUR_FILE"]))

if Fails:
    print("FAILS", len(Fails))
    sys.exit(1)
print("PASS")
