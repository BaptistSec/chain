#!/usr/bin/env python3
"""WebTest25 - the localhost web surface (ChainWeb.py).

Covers: token gate, loopback binding, page, state flow, physics parity (the same
shots through the HTTP API must produce byte-identical engine state to driving
ChainDemo directly), the busy/generation shot gate, and terminal-equivalent run
selection. Asserts and exits non-zero on failure.
"""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TMP = tempfile.mkdtemp(prefix="chainweb-")
os.environ["CHAIN_BEST_FILE"] = os.path.join(TMP, "best.txt")
os.environ["CHAIN_MARATHON_FILE"] = os.path.join(TMP, "marathon.txt")

import ChainDemo as E
import ChainWeb as W

Fails = []

def Check(name, ok):
    print(("ok  " if ok else "FAIL") + " " + name)
    if not ok:
        Fails.append(name)

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

Check("server bound to loopback only", SERVER.server_address[0] == "127.0.0.1")
Check("page refused without token", api("/")[0] == 403)
Check("api refused without token", api("/api/state")[0] == 403)
Check("api refused with wrong token", api("/api/state?k=wrong")[0] == 403)
status, html = api("/?k=" + K, raw=True)
Check("page serves with token", status == 200 and "CHAIN" in html and K in html)

status, st = api("/api/state?k=" + K)
Check("title state", status == 200 and st["screen"] == "title" and "records" in st and st["daily"])

# run selection: fresh runs vary like the terminal; daily stays the date
runs = set()
for _ in range(2):
    st = api("/api/start?k=" + K, {"mode": "run"})[1]
    runs.add(st["board"]["run"])
    api("/api/quit?k=" + K, {})
Check("fresh runs pick varied run numbers (terminal behaviour)", len(runs) == 2)
st = api("/api/start?k=" + K, {"mode": "daily"})[1]
Check("daily stays deterministic", st["board"]["run"] == E.DailyRun())
api("/api/quit?k=" + K, {})

status, st = api("/api/start?k=" + K, {"mode": "run"})
RUN = st["board"]["run"]
engState = E.RunState(RUN)
eng = E.Attach(E.RunBoard(RUN, 1, engState.Satchel, False, False, False), engState)
Check("run starts on board 1", status == 200 and st["screen"] == "play" and st["board"]["k"] == 1 and not st["board"]["marathon"])
Check("board hash matches engine", st["board"]["hash"] == eng.Hash())
Check("quota and limit from engine", st["board"]["quota"] == eng.Quota and st["board"]["limit"] == eng.Limit)

status, pv = api("/api/preview?aim=19&ball=n&k=" + K)
Check("preview matches engine trace", [list(p) for p in eng.Trace(19)] == pv["path"] and len(pv["path"]) > 3)

# full-board parity: same bot shots via API and directly on the engine
parityOk = True
clientGrid = {}   # mirrors the browser client's gridMap update rules
fallEvents = 0
sameColFalls = 0
tlOk = True
for i in range(eng.Limit):
    if eng.Over():
        break
    aim, kind = E.BotAim(eng)
    if not clientGrid:
        for pos, sym in eng.Grid.items():
            clientGrid[pos] = sym
    frames, events, docks = [], [], []
    logB = len(eng.Log)
    def hook(x, y, cells=None, kind_=None):
        if x is None:
            events.append(kind_)
        else:
            frames.append([x, y])
            docks.append(E.DockX(eng.Live.Steps + E.DockPhase * logB))
    eng.Play(aim, hook, kind)
    status, r = api("/api/shot?k=" + K, {"aim": aim, "ball": kind})
    if status != 200:
        parityOk = False
        print("   shot %d refused: %s" % (i, r))
        break
    if r["board"]["hash"] != eng.Hash() or r["board"]["score"] != eng.Score:
        parityOk = False
        print("   DIVERGED at shot %d: api %s vs engine %s" % (i, r["board"]["hash"], eng.Hash()))
        break
    if r["frames"] != frames or len(r["events"]) != len(events):
        parityOk = False
        break
    tl = r.get("timeline", [])
    for e in tl:
        if "b" in e:
            continue
        if e["e"] == "fall":
            fallEvents += 1
            xs = {}
            for c in e["cells"]:
                xs.setdefault(c[0], 0)
                xs[c[0]] += 1
            if any(n > 1 for n in xs.values()):
                sameColFalls += 1
            for c in e["cells"]:
                clientGrid.pop((c[0], c[1] - 1), None)
            for c in e["cells"]:
                clientGrid[(c[0], c[1])] = c[2]
        else:
            for c in e["cells"]:
                clientGrid.pop((c[0], c[1]), None)
    if dict(eng.Grid) != clientGrid:
        parityOk = False
        print("   CLIENT-GRID DIVERGED at shot %d: mirror %d cells vs engine %d" % (i, len(clientGrid), len(eng.Grid)))
        break
    if [e["b"] for e in tl if "b" in e] != frames or [e["d"] for e in tl if "b" in e] != docks:
        tlOk = False
        print("   TIMELINE DIVERGED at shot %d: web dock %s vs engine %s" % (
            i, [e["d"] for e in tl if "b" in e][-8:], docks[-8:]))
        break
    st = api("/api/done?k=" + K, {"gen": r["gen"], "shotId": r["shotId"]})[1]
wonBoard = eng.Won()
Check("full-board shot parity (hash, score, frames, events)", parityOk)
Check("chronological timeline mirrors engine steps (ball positions + true dock x)", tlOk)
Check("client grid-update rules reproduce engine state from the timeline", parityOk)
print("   fall coverage: %d fall events, %d with same-column chains" % (fallEvents, sameColFalls))
print("   board outcome after bot play: won=%s shots=%d" % (wonBoard, len(eng.Log)))

if wonBoard:
    Check("draft offered after cleared board", st["screen"] == "draft" and st["offer"] == E.RunOffer(RUN, 1))
    status, st = api("/api/pick?k=" + K, {"pick": "1"})
    Check("pick advances to board 2", status == 200 and st["screen"] == "play" and st["board"]["k"] == 2)
else:
    Check("lost run reaches gameover", st["screen"] == "gameover" and st["result"]["kind"] == "runover")
    status, st = api("/api/advance?k=" + K, {})
    Check("advance starts next run", status == 200 and st["screen"] == "play" and st["board"]["run"] == E.NextRunNumber(RUN))

# fall coverage drive: fixed aims across fresh runs, mirroring the browser
# client's gridMap rules from the timeline; must reproduce every server grid
clientGrid2 = {}
fallEvents2 = 0
sameColFalls2 = 0
shotsChecked = 0
boardsTried = 0
ok2 = True
while (fallEvents2 < 8 or sameColFalls2 < 1) and boardsTried < 60 and ok2:
    boardsTried += 1
    api("/api/quit?k=" + K, {})
    st = api("/api/start?k=" + K, {"mode": "run"})[1]
    clientGrid2 = {(c[0], c[1]): c[2] for c in st["board"]["grid"]}
    for aim in (0, 9, 19, 29, 38):
        if st.get("screen") != "play":
            break
        status, r = api("/api/shot?k=" + K, {"aim": aim, "ball": "n"})
        if status != 200:
            break
        for e in r["timeline"]:
            if "b" in e:
                continue
            if e["e"] == "fall":
                fallEvents2 += 1
                xs = {}
                for c in e["cells"]:
                    xs[c[0]] = xs.get(c[0], 0) + 1
                if any(n > 1 for n in xs.values()):
                    sameColFalls2 += 1
                for c in e["cells"]:
                    clientGrid2.pop((c[0], c[1] - 1), None)
                for c in e["cells"]:
                    clientGrid2[(c[0], c[1])] = c[2]
            else:
                for c in e["cells"]:
                    clientGrid2.pop((c[0], c[1]), None)
        shotsChecked += 1
        if {(c[0], c[1]): c[2] for c in r["board"]["grid"]} != clientGrid2:
            ok2 = False
            print("   CLIENT-GRID DIVERGED on coverage drive (aim %d)" % aim)
            break
        st = api("/api/done?k=" + K, {"gen": r["gen"], "shotId": r["shotId"]})[1]
api("/api/quit?k=" + K, {})
Check("client fall-update rules reproduce engine state across %d coverage shots" % shotsChecked, ok2)
print("   coverage: %d boards, %d shots, %d fall events, %d same-column" % (boardsTried, shotsChecked, fallEvents2, sameColFalls2))

# falls are dormant in generated play: verify the scan fact, then exercise the
# real engine settle/gravity on synthetic stacks to prove the client's origin rule
looseSupported = 0
looseTotal = 0
for seed in range(30001, 30021):
    stS = E.RunState(seed)
    for k in (1, 2, 3):
        bS = E.Attach(E.RunBoard(seed, k, stS.Satchel, False, False, False), stS)
        for c, s in bS.Grid.items():
            if s in E.LooseSymbols:
                looseTotal += 1
                if (c[0], c[1] + 1) in bS.Grid:
                    looseSupported += 1
print("   generated boards: %d loose cells, %d with support below (falls unreachable in normal play)" % (looseTotal, looseSupported))
Check("generated boards place no loose cell above support (falls dormant by design)", looseSupported == 0)

def SettleDrive(stack, removedCells):
    stD = E.RunState(30001)
    bD = E.Attach(E.RunBoard(30001, 1, stD.Satchel, False, False, False), stD)
    for x, y in [c for c in bD.Grid if c[0] == 10 and 1 < c[1] < 13]:
        del bD.Grid[(x, y)]
    for pos, s in stack.items():
        bD.Grid[pos] = s
    mirror = dict(bD.Grid)
    for pos in removedCells:
        del bD.Grid[pos]
    events = []
    bD.Settle(set(removedCells), E.Shot(19),
              lambda x, y, cells=None, kind=None: events.append((kind, dict(cells))) if x is None else None)
    originOk = True
    for kind, cells in events:
        if kind == "fall":
            for (x, y), s in cells.items():
                if mirror.get((x, y - 1)) != s:
                    originOk = False
            for x, y in cells:
                mirror.pop((x, y - 1), None)
            for (x, y), s in cells.items():
                mirror[(x, y)] = s
        else:
            for x, y in cells:
                mirror.pop((x, y), None)
    return events, mirror == dict(bD.Grid) and originOk

# same-column chain in a single pass: two stacked loose cells, support removed
ev1, ok1 = SettleDrive({(10, 7): "#", (10, 6): "o", (10, 5): "o"}, {(10, 7)})
Check("single-pass same-column chain fall: client rules match engine", ok1 and len(ev1) == 1 and ev1[0][0] == "fall" and len(ev1[0][1]) == 2)
# multi-pass chain: one loose cell with two removed cells below falls two rows
ev2, ok2b = SettleDrive({(10, 7): "#", (10, 6): "#", (10, 5): "+"}, {(10, 6), (10, 7)})
Check("multi-pass chain fall: client rules match engine across events", ok2b and len([e for e in ev2 if e[0] == "fall"]) == 2)
# origin rule checked inside SettleDrive: each fall cell's (x, y-1) held the
# same symbol in the pre-event mirror, for every event of both scenarios

# busy gate + generation binding
api("/api/quit?k=" + K, {})
api("/api/start?k=" + K, {"mode": "run"})
status, r0 = api("/api/shot?k=" + K, {"aim": 10, "ball": "n"})
status, r = api("/api/shot?k=" + K, {"aim": 11, "ball": "n"})
Check("second shot refused while first unwatched (409)", status == 409)
api("/api/done?k=" + K, {})
status, r = api("/api/shot?k=" + K, {"aim": 11, "ball": "n"})
Check("done without a generation is a no-op (still 409)", status == 409)
api("/api/done?k=" + K, {"gen": r0["gen"], "shotId": r0["shotId"]})
status, r = api("/api/shot?k=" + K, {"aim": 11, "ball": "n"})
Check("shot allowed after done with matching generation + shot id", status == 200)
api("/api/done?k=" + K, {"gen": r["gen"], "shotId": r["shotId"]})

# QA's stale-done repro: shot, restart, new shot, stale done must not clear the new busy
status, rOld = api("/api/shot?k=" + K, {"aim": 12, "ball": "n"})
api("/api/restart?k=" + K, {})
status, rNew = api("/api/shot?k=" + K, {"aim": 13, "ball": "n"})
Check("shoot after restart works", status == 200)
api("/api/done?k=" + K, {"gen": rOld["gen"], "shotId": rOld["shotId"]})
status, r = api("/api/shot?k=" + K, {"aim": 14, "ball": "n"})
Check("stale done must not release the new shot (409)", status == 409)
api("/api/done?k=" + K, {"gen": rNew["gen"], "shotId": rNew["shotId"]})
status, r = api("/api/shot?k=" + K, {"aim": 14, "ball": "n"})
Check("matching done releases the new shot", status == 200)
api("/api/done?k=" + K, {"gen": r["gen"], "shotId": r["shotId"]})

# QA's same-generation duplicate-done repro: A completes, B starts, a replayed
# DoneA carries the same run generation and must not clear B's busy
status, rA = api("/api/shot?k=" + K, {"aim": 15, "ball": "n"})
Check("shot A starts", status == 200)
api("/api/done?k=" + K, {"gen": rA["gen"], "shotId": rA["shotId"]})
status, rB = api("/api/shot?k=" + K, {"aim": 16, "ball": "n"})
Check("shot B starts after A completes", status == 200)
api("/api/done?k=" + K, {"gen": rA["gen"], "shotId": rA["shotId"]})
status, r = api("/api/shot?k=" + K, {"aim": 17, "ball": "n"})
Check("duplicate done for A must not release shot B (409)", status == 409)
api("/api/done?k=" + K, {"gen": rB["gen"], "shotId": rB["shotId"]})
status, r = api("/api/shot?k=" + K, {"aim": 17, "ball": "n"})
Check("B's own done releases it", status == 200)
api("/api/done?k=" + K, {"gen": r["gen"], "shotId": r["shotId"]})

# marathon loss + record + advance
api("/api/quit?k=" + K, {})
# A random marathon board is nondeterministic here: caught balls refund
# shots, so blind play can outlast the iteration cap (or even clear the
# board). Resume a FIXED marathon instead: run 40003 loses to blind aim-0
# play in exactly the shot limit, every time (engine-verified).
status, st = api("/api/resume?k=" + K, {"code": "CH24M-40003--"})
MNO = 40003
Check("marathon starts", st["screen"] == "play" and st["board"]["marathon"] and st["board"]["limit"] == E.MarathonShotLimit(1))
for i in range(12):
    if st["screen"] != "play":
        break
    rS = api("/api/shot?k=" + K, {"aim": 0, "ball": "n"})[1]
    st = api("/api/done?k=" + K, {"gen": rS["gen"], "shotId": rS["shotId"]})[1]
Check("marathon loss reaches gameover", st["screen"] == "gameover" and st["result"]["kind"] == "marathonover")
with open(os.environ["CHAIN_MARATHON_FILE"]) as fh:
    saved = fh.read().strip()
Check("marathon best recorded", saved == str(st["result"]["bestBoards"]) + "," + str(st["result"]["bestScore"]))
status, st = api("/api/advance?k=" + K, {})
Check("advance starts next marathon", status == 200 and st["board"]["marathon"] and st["board"]["run"] == E.NextRunNumber(MNO) and st["board"]["k"] == 1)

# resume parity
api("/api/quit?k=" + K, {})
st = api("/api/start?k=" + K, {"mode": "run"})[1]
rS = api("/api/shot?k=" + K, {"aim": 19, "ball": "n"})[1]
st = api("/api/done?k=" + K, {"gen": rS["gen"], "shotId": rS["shotId"]})[1]
code = st["board"]["code"]
status, st2 = api("/api/resume?k=" + K, {"code": code})
rState, rBoard = E.ResumeRun(code)
Check("resume loads the run", status == 200 and st2["screen"] == "play")
Check("resume board hash matches engine ResumeRun", st2["board"]["hash"] == rBoard.Hash())
status, r = api("/api/resume?k=" + K, {"code": "CH24R-9-9.9.9-zzz"})
Check("bad run code rejected", status == 400)

# resume branch routing: a quit-at-draft or finished code resumes with the board
# already over; the session must route to draft / gameover / complete, never trap
# the board in play. Codes are fixed and engine-verified; every branch is checked
# against an independent engine ResumeRun replay.
BRANCHES = [
    ("midboard run resumes to play", "CH24R-40001-9.10.10--7.29", "play", None),
    ("won board resumes to draft", "CH24R-40001-9.10.10--7.29.25.9", "draft", None),
    ("lost run resumes to gameover", "CH24R-40002-9.10.10--0.7.14.21.28.35.3.10.17", "gameover", "runover"),
    ("marathon midboard resumes to play", "CH24M-40003--", "play", None),
    ("marathon won board resumes to draft", "CH24M-40003--38r.2", "draft", None),
    ("marathon loss resumes to gameover", "CH24M-40003--0.0.0.0.0.0.0.0", "gameover", "marathonover"),
    ("completed run resumes to complete", "CH24R-40001-9.10.10-00-4r.10/3r.33x/30x.11r", "complete", "complete"),
]
for name, code, wantScreen, wantKind in BRANCHES:
    eState, eBoard = E.ResumeRun(code)
    status, st = api("/api/resume?k=" + K, {"code": code})
    ok = status == 200 and st["screen"] == wantScreen
    Check(name, ok)
    Check(name + " (engine agrees over=" + str(eBoard.Over()) + " won=" + str(eBoard.Won()) + ")",
          eBoard.Over() == (wantScreen != "play") and (wantScreen not in ("draft", "complete") or eBoard.Won()))
    if wantScreen == "draft":
        Check(name + " offers the pending upgrade", st.get("offer") == list(E.RunOffer(eState.Run, eState.K)))
        status, st2 = api("/api/pick?k=" + K, {"pick": "1"})
        Check(name + " pick advances to the next board",
              status == 200 and st2["screen"] == "play" and st2["board"]["k"] == eState.K + 1)
    if wantKind is not None:
        Check(name + " result kind", st.get("result", {}).get("kind") == wantKind)
    if wantKind == "runover":
        Check(name + " runover records no best", "isNew" not in st["result"] and "saved" not in st["result"])
    if wantKind == "complete":
        eState.Boards.append(eBoard)
        Check(name + " total matches engine", st["result"]["total"] == sum(b.Score for b in eState.Boards))
        Check(name + " best covers total", st["result"]["best"] >= st["result"]["total"])

# the exact trap QA reported: resumed won board must accept no shot but must
# reach its draft; after the fix the shot refusal comes from the draft screen,
# not from a stuck play screen
status, st = api("/api/resume?k=" + K, {"code": "CH24R-40001-9.10.10--7.29.25.9"})
status, r = api("/api/shot?k=" + K, {"aim": 7, "ball": "n"})
Check("resumed won board refuses shots from draft", status == 400 and st["screen"] == "draft")

status, st = api("/api/quit?k=" + K, {})
Check("quit returns to title with code", status == 200 and st["screen"] == "title" and st["quitCode"].startswith("CH24R-"))

# restart keeps the abandoned run's code reachable (terminal parity: old codes at quit)
st = api("/api/start?k=" + K, {"mode": "run"})[1]
rS = api("/api/shot?k=" + K, {"aim": 19, "ball": "n"})[1]
st = api("/api/done?k=" + K, {"gen": rS["gen"], "shotId": rS["shotId"]})[1]
first = st["board"]["code"]
status, r = api("/api/restart?k=" + K, {})
Check("restart returns the abandoned code", status == 200 and r.get("oldCode") == first)
Check("restart message points at the menu", "menu" in r.get("message", ""))
rS = api("/api/shot?k=" + K, {"aim": 20, "ball": "n"})[1]
st = api("/api/done?k=" + K, {"gen": rS["gen"], "shotId": rS["shotId"]})[1]
second = st["board"]["code"]
Check("two abandoned codes differ", first != second)
api("/api/restart?k=" + K, {})
status, st = api("/api/quit?k=" + K, {})
Check("title lists both abandoned codes in order", st.get("oldCodes") == [first, second])
Check("title still shows the current code", st.get("quitCode", "").startswith("CH24R-"))
api("/api/start?k=" + K, {"mode": "run"})
st = api("/api/quit?k=" + K, {})[1]
Check("a new run clears abandoned codes", st.get("oldCodes") == [])

# retention lifecycle pins (mutant targets: dropping the [-5:] cap or the Resume
# reset must each fail exactly one of these)
st = api("/api/start?k=" + K, {"mode": "run"})[1]
kept = []
for i in range(7):
    rS = api("/api/shot?k=" + K, {"aim": 10 + i, "ball": "n"})[1]
    st = api("/api/done?k=" + K, {"gen": rS["gen"], "shotId": rS["shotId"]})[1]
    kept.append(st["board"]["code"])
    api("/api/restart?k=" + K, {})
st = api("/api/quit?k=" + K, {})[1]
Check("retention caps at the five most recent", st.get("oldCodes") == kept[-5:])
api("/api/start?k=" + K, {"mode": "run"})
rS = api("/api/shot?k=" + K, {"aim": 19, "ball": "n"})[1]
st = api("/api/done?k=" + K, {"gen": rS["gen"], "shotId": rS["shotId"]})[1]
one = st["board"]["code"]
api("/api/restart?k=" + K, {})
status, r = api("/api/resume?k=" + K, {"code": "CH24R-9-9.9.9-zzz"})
Check("invalid resume still rejected", status == 400)
st = api("/api/quit?k=" + K, {})[1]
Check("invalid resume preserves kept codes", st.get("oldCodes") == [one])
api("/api/start?k=" + K, {"mode": "run"})
rS = api("/api/shot?k=" + K, {"aim": 19, "ball": "n"})[1]
st = api("/api/done?k=" + K, {"gen": rS["gen"], "shotId": rS["shotId"]})[1]
one = st["board"]["code"]
api("/api/restart?k=" + K, {})
status, st = api("/api/resume?k=" + K, {"code": "CH24R-40001-9.10.10--7.29"})
Check("valid resume loads for the clear test", status == 200 and st["screen"] == "play")
st = api("/api/quit?k=" + K, {})[1]
Check("valid resume clears kept codes", st.get("oldCodes") == [])

SERVER.shutdown()
SERVER.server_close()
print("FAILS", len(Fails))
sys.exit(1 if Fails else 0)
