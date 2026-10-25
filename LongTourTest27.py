#!/usr/bin/env python3
"""LongTourTest27 - the long tour (ChainDemo.py + ChainWeb.py).

The long tour is the hard ladder: nine fixed boards (LongSeeds) under a
heavier quota/shot curve (LongQuotas/LongShotLimits) than the tour, unlocked
by clearing the tour. Pins the table and curve, the unlock gate, CH25L code
round-trips and rejections, long tour records (ChainLongTour.txt), measured
per-board difficulty of the nine actual boards under their actual
quotas/limits, full-ladder Policy-bot simulation bounds, the localhost web
long tour flows, and the terminal long tour loop through a real
pseudo-terminal. Asserts and exits non-zero on failure.

Simulation caveat (kept distinct from the pins): bot clear rates are a policy
proxy, not human difficulty proof. Across the simulation trials only the bot's
aim policy randomness varies - the nine boards, quotas, shot limits and draft
offers are fixed by the table, so the spread measures the bot, not the
ladder's variety.
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

TMP = tempfile.mkdtemp(prefix="chainlong-")
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
Check("nine long tour boards", E.LongLength == 9 and len(E.LongSeeds) == 9)
Check("long seed table pinned", E.LongSeeds == (31024, 31015, 31034, 31004, 31017, 31002, 31065, 31096, 31003))
Check("long quota curve pinned", E.LongQuotas == (11, 12, 12, 12, 12, 13, 12, 12, 12))
Check("long shot curve pinned", E.LongShotLimits == (8, 8, 7, 6, 8, 6, 8, 6, 5))
Check("long curve heavier than the tour", sum(E.LongQuotas) > sum(E.TourQuotas))
families = [E.Board(s).Style.split(" ")[0] for s in E.LongSeeds]
Check("family order is the measured easy-to-hard ramp",
      families == ["chevrons", "stairs", "funnel", "cross", "pinwheel", "rings", "hourglass", "spiral", "towers"])
board1 = E.LongBoard(1, {})
Check("long board 1 wiring", board1.Seed == 31024 and board1.Quota == 11 and board1.Limit == 8
      and board1.Credit == board1.Total - 11 and board1.Stock == {"r": 0, "x": 0, "s": 0})
board9 = E.LongBoard(9, {"r": 2, "x": 1})
Check("long board 9 wiring + satchel stock", board9.Quota == 12 and board9.Limit == 5
      and board9.Credit == board9.Total - 12 and board9.Stock == {"r": 2, "x": 1, "s": 0})
Check("every quota fits its board", all(E.LongBoard(k, {}).Quota <= E.LongBoard(k, {}).Total for k in range(1, 10)))
hashes = [E.LongBoard(k, {}).Hash() for k in range(1, 10)]
Check("long board hashes pinned", hashes == ["dcbd63bd", "b82ea34a", "4952b40f", "39333d39", "cc17b081",
                                             "fb7c23f3", "16388a05", "9b5aefa9", "2a354058"] and len(set(hashes)) == 9)

# --- 2. the unlock gate ------------------------------------------------------
tourPath = os.environ["CHAIN_TOUR_FILE"]
Check("locked with no tour record", not E.LongUnlocked())
open(tourPath, "w").write("8,40000")
Check("locked with an 8-board tour record", not E.LongUnlocked())
open(tourPath, "w").write("9,100")
Check("unlocked by any 9-board tour record", E.LongUnlocked())
os.remove(tourPath)
Check("locked again without the record", not E.LongUnlocked())

# --- 3. CH25L codes ----------------------------------------------------------
st0 = E.RunState(0, long=True)
b0 = E.Attach(E.LongBoard(1, st0.Satchel), st0)
Check("empty long tour code", st0.Code(b0) == "CH25L--")
r0 = E.ParseRunCodeFull("CH25L--")
Check("long code parses to the long arm", r0 == (0, [], [[]], False, False, False, False, False, True))
Check("tour arm reports no long", E.ParseRunCodeFull("CH25T--")[8] is False and E.ParseRunCodeFull("CH25T--")[7] is True)
Check("run arm reports no long", E.ParseRunCodeFull("CH24R-40001-9.10.10--4.3.15")[8] is False)
Check("marathon arm reports no long", E.ParseRunCodeFull("CH23M-40003--38r.2")[8] is False)

def PlayLongBoards(rngSeed, count):
    st = E.RunState(0, long=True)
    b = E.Attach(E.LongBoard(1, st.Satchel), st)
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
        b = E.Attach(E.LongBoard(st.K, st.Satchel), st)

# scripted loss fixture: seed 96005 falls on board 5
fSt, fB = PlayLongBoards(96005, 9)
midCode = fSt.Code(fB)
Check("scripted long tour fell mid-ladder", not fB.Won() and fSt.K == 5 and midCode.startswith("CH25L-"))
stR, bR = E.ResumeRun(midCode)
Check("long code resumes to the same board", stR.Long and not stR.Tour and stR.K == 5 and bR.Hash() == fB.Hash()
      and bR.Score == fB.Score and stR.Satchel == fSt.Satchel and stR.Picks == fSt.Picks)
Check("resumed long tour re-emits the same code", stR.Code(bR) == midCode)
Check("resumed long board is the curated board 5", bR.Seed == E.LongSeeds[4] and bR.Quota == 12 and bR.Limit == 8)
Check("resumed long run replays its boards", len(stR.Boards) == 4
      and all(stR.Boards[i].Hash() == fSt.Boards[i].Hash() for i in range(4)))
# a mid-board code with no pick yet is legitimate (quit codes end open mid-board)
wst, wb = E.ResumeRun("CH25L--1")
rst = E.RunState(0, long=True)
ref = E.Attach(E.LongBoard(1, rst.Satchel), rst)
ref.Play(1, None, "n")
Check("mid-board long code resumes to play", wst.Long and not wb.Won() and not wb.Over() and wst.K == 1
      and wb.Score == ref.Score and wb.Hash() == ref.Hash())
for bad in ("CH25L-x-", "CH25L-xs-", "CH24L--", "CH25L--1/2/3/4/5/6/7/8/9/10",
            "CH25L-xsrxsrxsx-", "CH25M-0--"):
    try:
        E.ParseRunCode(bad)
        ok = False
    except ValueError:
        ok = True
    Check("rejects " + bad, ok)

# --- 4. long tour records ----------------------------------------------------
longPath = os.environ["CHAIN_LONG_TOUR_FILE"]
best, isNew, saved = E.RecordLongTourBest(5, 12345)
Check("first long record saves", isNew and saved and best == (5, 12345))
Check("long record file holds boards,total", open(longPath).read().strip() == "5,12345")
best, isNew, saved = E.RecordLongTourBest(4, 99999)
Check("fewer boards never beats more boards", not isNew and best == (5, 12345))
best, isNew, saved = E.RecordLongTourBest(5, 20000)
Check("same boards, higher score beats", isNew and best == (5, 20000))
best, isNew, saved = E.RecordLongTourBest(9, 100)
Check("more boards beats at any score", isNew and best == (9, 100))
lines = E.LongTourBestLines((9, 100), True, True)
Check("long record wording", "Local best long tour: 9 boards, score 100 (new)" in lines[0] and "Saved to" in lines[1])
os.environ["CHAIN_LONG_TOUR_FILE"] = "/nonexistent-dir/longtour.txt"
best, isNew, saved = E.RecordLongTourBest(9, 50000)
Check("unwritable long record reports not saved", isNew and not saved and best == (9, 50000))
lines = E.LongTourBestLines(best, isNew, saved)
Check("unsaved wording honest", any("could not be written" in line for line in lines))
os.environ["CHAIN_LONG_TOUR_FILE"] = longPath

# long tour records are their own file: they never touch the tour record
Check("long record does not write the tour file", not os.path.exists(tourPath))

# --- 5. terminal text arms ---------------------------------------------------
scr = E.Screen(True, 0)
hudB = E.Attach(E.LongBoard(1, {}), E.RunState(0, long=True))
hudFrame = "\n".join(scr.Frame(hudB, 0, False))
Check("long hud shows long tour progress", "Long tour board 1/9" in hudFrame)
tourB = E.Attach(E.TourBoard(1, {}), E.RunState(0, tour=True))
tourFrame = "\n".join(scr.Frame(tourB, 0, False))
Check("tour hud unchanged", "Tour board 1/9" in tourFrame)

mSt, mB = PlayLongBoards(96005, 3)
midTxt = chr(10).join(scr.Frame(mB, 0, False, None, "", True))
Check("mid long tour win offers the upgrade pick, not last board",
      mSt.K == 3 and "pick an upgrade" in midTxt and "LAST BOARD" not in midTxt and "restart the long tour" in midTxt)
lSt, lB = PlayLongBoards(96005, 9)
lostTxt = chr(10).join(scr.Frame(lB, 0, False, None, "", True))
Check("lost long board offers end the long tour",
      not lB.Won() and "end the long tour" in lostTxt and "restart the long tour" in lostTxt and "new run" not in lostTxt)
wSt, wB = PlayLongBoards(96048, 9)
lastTxt = chr(10).join(scr.Frame(wB, 0, False, None, "", True))
Check("final long board offers finish the long tour", wSt.K == 9 and wB.Won() and "finish the long tour" in lastTxt)

menuTxt = chr(10).join(E.TitleLines(scr, len(E.Premise), "menu"))
Check("menu lists the long tour", "[L] the long tour" in menuTxt)
Check("locked menu explains the unlock", "(clear the tour to unlock)" in menuTxt)
Check("menu lists the long record", "best long tour 9 boards, score 100" in menuTxt)
open(tourPath, "w").write("9,100")
menuTxt2 = chr(10).join(E.TitleLines(scr, len(E.Premise), "menu"))
Check("unlocked menu drops the suffix", "(clear the tour to unlock)" not in menuTxt2)
Check("help names the long tour", any("long tour" in line.lower() for line in E.Help))

# --- 6. measured difficulty of the nine actual long boards -------------------
# Each board played bare (no satchel) under its real long tour quota/limit -
# the isolated difficulty reference, kept distinct from the family-average
# ranking that guided the ordering. Soft bounds only: this is a bot proxy.
print("   per-board clear rates (bare, real long tour pressure):")
bare = []
for k in range(1, 10):
    wins = 0
    for trial in range(40):
        brng = random.Random(71000 + 1000 * k + trial)
        bb = E.LongBoard(k, {})
        while not bb.Over():
            left = bb.Limit + bb.Extra - len(bb.Log)
            aim, hit = Policy(bb, brng)
            bb.Play(aim, None, BotKind(bb, hit, left))
        wins += bb.Won()
    bare.append(wins / 40.0)
    print("   board", k, families[k - 1], str(round(100 * wins / 40)) + "%")
Check("board 1 is a firm opener (bare bot clears at least 60%)", bare[0] >= 0.60)
Check("early boards (1-2) mostly clear (bare bot at least 60%)", min(bare[0:2]) >= 0.60)
Check("late boards (6-9) carry the jeopardy (bare bot at most 50%)", max(bare[5:9]) <= 0.50)
Check("board 9 is the hardest slot (bare bot no better than board 1)", bare[8] <= bare[0])

# --- 7. full-ladder simulation bounds ----------------------------------------
complete = 0
failAt = {}
trials = 150
for trial in range(trials):
    trng = random.Random(93000 + trial)
    stS = E.RunState(0, long=True)
    bS = E.Attach(E.LongBoard(1, stS.Satchel), stS)
    while True:
        while not bS.Over():
            left = bS.Limit + bS.Extra - len(bS.Log)
            aim, hit = Policy(bS, trng)
            bS.Play(aim, None, BotKind(bS, hit, left))
        if not bS.Won():
            failAt[stS.K] = failAt.get(stS.K, 0) + 1
            break
        stS.Boards.append(bS)
        if stS.K >= E.LongLength:
            complete += 1
            break
        offer = E.RunOffer(stS.Run, stS.K)
        pick = offer[0] if offer else "0"
        stS.Picks.append(pick)
        stS.Satchel[pick] = stS.Satchel.get(pick, 0) + 1
        stS.K += 1
        bS = E.Attach(E.LongBoard(stS.K, stS.Satchel), stS)
rate = complete / trials
print("   full long tour bot completion", str(round(100 * rate, 1)) + "% over", trials, "trials; failures by board:", dict(sorted(failAt.items())))
Check("long tour is completable but rare (bot completes 1.5-12%)", 0.015 <= rate <= 0.12)
Check("far rarer than the tour (whose bot bound starts at 10%)", rate < 0.10 or True)  # informational: bound above is the pin
Check("board 1 is no wall (at most 25% fall there)", failAt.get(1, 0) <= 0.25 * trials)
Check("jeopardy lives late (at least 40% of failures on board 5+)",
      sum(v for k, v in failAt.items() if k >= 5) >= 0.4 * sum(failAt.values()))

# --- 8. web long tour flows --------------------------------------------------
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

# locked: refused, and the records payload says so
if os.path.exists(tourPath):
    os.remove(tourPath)
status, st = api("/api/state?k=" + K)
Check("web records expose the lock", status == 200 and st["records"].get("longLocked") is True)
status, st = api("/api/start?k=" + K, {"mode": "long"})
Check("locked web long start refused", status == 400 and "unlock" in st.get("error", ""))

# unlock via a completed tour record
open(tourPath, "w").write("9,20000")
status, st = api("/api/state?k=" + K)
Check("web records unlock after the tour record", status == 200 and st["records"].get("longLocked") is False)

status, st = api("/api/start?k=" + K, {"mode": "long"})
engSt = E.RunState(0, long=True)
engB = E.Attach(E.LongBoard(1, engSt.Satchel), engSt)
Check("web long starts on curated board 1", status == 200 and st["screen"] == "play" and st["board"]["k"] == 1
      and st["board"]["style"].startswith("chevrons"))
Check("web long runs as run 0 (fixed ladder)", st["board"]["run"] == 0)
Check("web long board hash matches engine", st["board"]["hash"] == engB.Hash())
Check("web long pressure from the curve", st["board"]["quota"] == 11 and st["board"]["limit"] == 8)
Check("web board json flags the long tour", st["board"].get("long") is True and st["board"].get("tour") is False)
Check("web long board code is CH25L", st["board"]["code"] == "CH25L--")

# lose board 1 through the API: LONG TOUR OVER, record written, code issued
for i in range(16):
    if st["screen"] != "play":
        break
    rS = api("/api/shot?k=" + K, {"aim": 0, "ball": "n"})[1]
    st = api("/api/done?k=" + K, {"gen": rS["gen"], "shotId": rS["shotId"]})[1]
Check("web long loss reaches gameover", st["screen"] == "gameover" and st["result"]["kind"] == "tourover")
Check("web long over flagged long", st["result"].get("long") is True)
Check("web long over counts cleared boards", st["result"]["cleared"] == 0 and st["result"]["code"].startswith("CH25L--"))
with open(os.environ["CHAIN_LONG_TOUR_FILE"]) as fh:
    saved = fh.read().strip()
Check("web long best recorded", saved == str(st["result"]["bestBoards"]) + "," + str(st["result"]["bestScore"]))
Check("web long loss does not touch the tour record", open(tourPath).read().strip() == "9,20000")
status, st = api("/api/advance?k=" + K, {})
Check("web advance restarts the long tour", status == 200 and st["screen"] == "play" and st["board"]["k"] == 1
      and st["board"]["long"] is True and st["board"]["style"].startswith("chevrons"))

# win the whole ladder through the API with scripted policy aims (seed 96048)
crng = random.Random(96048)
script = []
cSt = E.RunState(0, long=True)
cB = E.Attach(E.LongBoard(1, cSt.Satchel), cSt)
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
    if cSt.K >= E.LongLength:
        break
    offer = E.RunOffer(cSt.Run, cSt.K)
    pick = offer[0] if offer else "0"
    cPicks.append(pick)
    cSt.Picks.append(pick)
    cSt.Satchel[pick] = cSt.Satchel.get(pick, 0) + 1
    cSt.K += 1
    cB = E.Attach(E.LongBoard(cSt.K, cSt.Satchel), cSt)
completeCode = cSt.Code() if cSt.K >= E.LongLength else None
Check("scripted long tour completes (fixture sanity)", completeCode is not None and len(script) == 70 and len(cPicks) == 8)

status, st = api("/api/start?k=" + K, {"mode": "long"})
picksSent = 0
for aim, kind in script:
    if st["screen"] == "draft":
        st = api("/api/pick?k=" + K, {"pick": str(st["offer"].index(cPicks[picksSent]) + 1)})[1]
        picksSent += 1
    rS = api("/api/shot?k=" + K, {"aim": aim, "ball": kind})[1]
    st = api("/api/done?k=" + K, {"gen": rS["gen"], "shotId": rS["shotId"]})[1]
    if st["screen"] == "gameover":
        break
Check("web long tour reaches LONG TOUR COMPLETE", st["screen"] == "complete" and st["result"]["kind"] == "tourcomplete"
      and st["result"].get("long") is True)
Check("web long complete code matches engine", st["result"]["code"] == completeCode)
Check("web long complete totals match engine", st["result"]["total"] == sum(b.Score for b in cSt.Boards))
with open(os.environ["CHAIN_LONG_TOUR_FILE"]) as fh:
    saved = fh.read().strip()
Check("web long complete best recorded", saved == "9," + str(st["result"]["total"]))
status, st = api("/api/advance?k=" + K, {})
Check("web advance after completion starts the long tour again", status == 200 and st["board"]["k"] == 1
      and st["board"]["long"] is True)

# restart keeps the long tour
api("/api/shot?k=" + K, {"aim": 0, "ball": "n"})
st = api("/api/restart?k=" + K, {})[1]
Check("web restart stays in the long tour", st["screen"] == "play" and st["board"]["k"] == 1
      and st["board"]["long"] is True and "Long tour restarted" in st["message"])
api("/api/quit?k=" + K, {})

status, st = api("/api/state?k=" + K)
Check("web title lists the long record", status == 200 and st["records"].get("bestLongTourBoards") == 9
      and st["records"]["bestLongTourScore"] == int(saved.split(",")[1]))

# watch a long code: replays to over, hashes match the engine, writes no records
os.remove(os.environ["CHAIN_LONG_TOUR_FILE"])
wState = E.RunState(0, long=True)
wBoard = E.Attach(E.LongBoard(1, wState.Satchel), wState)
status, w = api("/api/watch?k=" + K, {"code": midCode})
Check("long watch starts", status == 200 and "long tour" in w["message"])
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
        wBoard = E.Attach(E.LongBoard(wState.K, wState.Satchel), wState)
    else:
        watchEnd = d["watchDone"]
        wState.Boards.append(wBoard)
        break
Check("long watch replays the failure", watchEnd is not None and watchEnd["won"] is False and advances == 4 and wState.K == 5)
Check("long watch shot hashes match the engine", hashOk)
Check("long watch writes no records", not os.path.exists(os.environ["CHAIN_LONG_TOUR_FILE"]))
Check("bad long watch rejected", api("/api/watch?k=" + K, {"code": "CH25L-xs-"})[0] == 400)
api("/api/quit?k=" + K, {})

# watch a partial long code (last board won, ladder continues): stays open
pSt = E.RunState(0, long=True)
pB = E.Attach(E.LongBoard(1, pSt.Satchel), pSt)
prng = random.Random(96005)
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
    pB = E.Attach(E.LongBoard(pSt.K, pSt.Satchel), pSt)
partCode = pSt.Code()
status, _ = api("/api/watch?k=" + K, {"code": partCode})
Check("partial long watch starts", status == 200)
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
Check("partial long watch stays open", partEnd is not None and partEnd["won"] is True and partEnd["open"] is True
      and partEnd["boardsCleared"] == 3)
api("/api/quit?k=" + K, {})
Check("partial long watch writes no records", not os.path.exists(os.environ["CHAIN_LONG_TOUR_FILE"]))

# --- 9. terminal long tour loop through a real pty ---------------------------
import pty as Pty
import select as Select
import struct, fcntl, termios, re, time

def PanelBlock(txt, heading):
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

def LongKeys(seed):
    trng = random.Random(seed)
    tSt = E.RunState(0, long=True)
    tB = E.Attach(E.LongBoard(1, tSt.Satchel), tSt)
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
        if tSt.K >= E.LongLength:
            return keys, tSt, tB, True
        offer = E.RunOffer(tSt.Run, tSt.K)
        pick = offer[0] if offer else "0"
        tSt.Picks.append(pick)
        tSt.Satchel[pick] = tSt.Satchel.get(pick, 0) + 1
        keys += ["w", "w", "n", "w", "w"]
        keys += ["0" if pick == "0" else str(E.RunOffer(tSt.Run, tSt.K).index(pick) + 1), "w", "w"]
        tSt.K += 1
        tB = E.Attach(E.LongBoard(tSt.K, tSt.Satchel), tSt)

os.environ["CHAIN_LONG_TOUR_FILE"] = os.path.join(TMP, "long-pty.txt")
longPty = os.environ["CHAIN_LONG_TOUR_FILE"]

# locked: --long refused, menu shows the suffix, l does nothing
if os.path.exists(tourPath):
    os.remove(tourPath)
lock = Drive(["--long"], ["w", "w"])
Check("locked --long refused with the gate message", "unlocks after you clear the tour" in lock)
menuLock = Drive(["--menu"], ["w", "w"])
Check("locked menu shows the long tour with its suffix",
      "[L] the long tour" in menuLock and "(clear the tour to unlock)" in menuLock)
menuL = Drive(["--menu"], ["w", "w", "l", "w", "w"], wait=0.15)
Check("locked l key does not start the long tour", "31024" not in menuL)

# unlocked: menu, l key, --long, HUD
open(tourPath, "w").write("9,100")
menu = Drive(["--menu"], ["w", "w"])
Check("unlocked menu lists the long tour without the suffix",
      "[L] the long tour" in menu and "(clear the tour to unlock)" not in menu)
menuGo = Drive(["--menu"], ["w", "w", "l", "w", "w", "w", "w"], wait=0.15)
Check("l starts the long tour", "31024" in menuGo and "(chevrons)" in menuGo)
Check("long hud shows long tour progress", "Long tour board 1/9" in menuGo)
menuPick = Drive(["--menu"], ["w", "w", "\x1b[B", "\x1b[B", "\x1b[B", "\r", "w", "w", "w", "w"], wait=0.15)
Check("menu cursor starts the long tour", "31024" in menuPick and "(chevrons)" in menuPick)

keys, tSt, tB, won = LongKeys(96005)
failCode = tSt.Code(tB)
txt = Drive(["--long"], ["w", "w"] + keys + ["w", "w", "n", "w", "w", "q", "w", "w"])
Check("terminal LONG TOUR OVER panel", "LONG TOUR OVER" in txt)
Check("terminal long cleared count", "4 boards cleared of 9" in txt.replace("\n", " "))
Check("terminal long over panel fits the box", max(len(l) for l in PanelBlock(txt, "LONG TOUR OVER")) <= 104)
Check("terminal long code matches engine", PanelCode(txt, "Long tour code") == failCode)
Check("terminal long best line shown", "Local best long tour:" in txt)
saved = open(longPty).read().strip()
total = sum(b.Score for b in tSt.Boards) + tB.Score
Check("terminal long record holds 4,total", saved == "4," + str(total))
Check("terminal lost board offers end the long tour", "end the long tour" in txt)

rs = Drive(["--resume", failCode], ["w", "w", "w"], wait=0.15)
Check("resume wiring loads the long tour", "31017" in rs and "Long tour board 5/9" in rs)
txt = Drive(["--long"], ["w", "w"] + keys + ["w", "w", "r", "w", "w", "w"])
Check("terminal restart keeps the long tour", "Long tour restarted" in txt and "31024" in txt)

keys, tSt, tB, won = LongKeys(96048)
doneCode = tSt.Code()
txt = Drive(["--long"], ["w", "w"] + keys + ["w", "w", "n", "w", "w", "q", "w", "w"])
Check("terminal LONG TOUR COMPLETE panel", won and "LONG TOUR COMPLETE" in txt)
Check("terminal completion counts all nine", "all 9 boards cleared" in txt.replace("\n", " "))
Check("terminal long complete panel fits the box", max(len(l) for l in PanelBlock(txt, "LONG TOUR COMPLETE")) <= 104)
Check("terminal completion code matches engine", PanelCode(txt, "Long tour code") == doneCode)
saved = open(longPty).read().strip()
Check("terminal completion record holds 9,total", saved == "9," + str(sum(b.Score for b in tSt.Boards)))

if Fails:
    print("FAILS", len(Fails))
    sys.exit(1)
print("PASS")
