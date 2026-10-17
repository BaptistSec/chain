"""Marathon mode (CH23M). Asserts and exits non-zero on failure.
Covers: the pinned escalation curve, marathon codes and resume round-trips,
per-board shot limits, restart keeping marathon mode, cross-parser rejection,
the marathon best file, and that marathon boards use the unchanged generator."""
import sys, random, importlib.util, os, collections, tempfile
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec)
Spec.loader.exec_module(E)

bad = collections.Counter()

def Policy(b, rng):
    best = []
    for a in range(len(E.Directions)):
        c = b.Clone(); c.Fire(a, None, E.PreviewSteps, False, True, "n")
        if c.Struck:
            best.append((a, b.Grid.get(c.Struck[0])))
    targets = [a for a, s in best if s == "#"]
    pool = targets or [a for a, s in best] or list(range(len(E.Directions)))
    return rng.choice(pool), bool(targets)

def Kind(b, hit, left):
    n = sum(b.Stock.values())
    if n == 0 or left > n + 4:
        return "n"
    for k in (["x", "r", "s"] if hit else ["s", "r", "x"]):
        if b.Stock.get(k, 0) > 0:
            return k
    return "n"

def PlayMarathon(run, rng):
    state = E.RunState(run, marathon=True)
    board = E.Attach(E.RunBoard(run, 1, state.Satchel, marathon=True), state)
    while True:
        while not board.Over():
            left = board.Limit + board.Extra - len(board.Log)
            aim, hit = Policy(board, rng)
            board.Play(aim, None, Kind(board, hit, left))
        if not board.Won():
            return state, board
        state.Boards.append(board)
        choice = rng.randrange(4)
        pick = E.RunOffer(run, state.K)[choice] if choice < 3 else "0"
        state.Picks.append(pick)
        if pick != "0":
            state.Satchel[pick] = state.Satchel.get(pick, 0) + 1
        state.K += 1
        board = E.Attach(E.RunBoard(run, state.K, state.Satchel, marathon=True), state)

# 1. The pinned curve
expectQ = {1: 8, 2: 8, 3: 9, 4: 9, 5: 10, 6: 10, 7: 11, 8: 11, 9: 12, 12: 12, 13: 12, 20: 12}
expectS = {1: 8, 6: 8, 7: 7, 12: 7, 13: 6, 20: 6}
for k, q in expectQ.items():
    if E.MarathonQuota(k) != q:
        bad["quota curve"] += 1
for k, s in expectS.items():
    if E.MarathonShotLimit(k) != s:
        bad["shot curve"] += 1

# 2. Per-board limits and unchanged generator
for k in (1, 7, 9, 13):
    b = E.RunBoard(777, k, dict(E.RunStart), marathon=True)
    if b.Limit != E.MarathonShotLimit(k):
        bad["board limit"] += 1
    if b.Quota != E.MarathonQuota(k):
        bad["board quota"] += 1
    fresh = E.Board(E.RunBoardSeed(777, k))
    if E.LayoutHash(b.Grid) != E.LayoutHash(fresh.Grid) or b.Bumps != fresh.Bumps or b.Style != fresh.Style:
        bad["generator changed"] += 1
    while not b.Won() and len(b.Log) < b.Limit + b.Extra + 5:
        b.Play(0, None, "n")
    if not b.Over():
        bad["limit not enforced"] += 1

# 3. Marathon playthroughs with code round-trip (n runs over seeds)
checked = 0
for run in range(30001, 30051):
    rng = random.Random(run)
    state, board = PlayMarathon(run, rng)
    code = state.Code(board)
    if not code.startswith(E.Version + "M-"):
        bad["code prefix"] += 1
    s2, b2 = E.ResumeRun(code)
    if not s2.Marathon:
        bad["resume lost marathon"] += 1
    if s2.Code(b2) != code:
        bad["code roundtrip"] += 1
    if b2.Hash() != board.Hash():
        bad["final hash"] += 1
    if s2.K != state.K:
        bad["resume board number"] += 1
    if b2.Limit != board.Limit or b2.Quota != board.Quota:
        bad["resume limits"] += 1
    allBoards = state.Boards + [board]
    for i, b in enumerate(allBoards[:-1]):
        if not b.Won():
            bad["lost board before the last"] += 1
    for b in allBoards:
        if len(b.Log) > b.Limit + b.Extra:
            bad["over limit"] += 1
        if any(v < 0 for v in b.Stock.values()):
            bad["negative stock"] += 1
        for s in b.Log:
            if s.Kind == "s" and (s.Targets <= 1) != bool(s.Refund):
                bad["refund rule"] += 1
            if s.Kind != "s" and s.Refund:
                bad["refund on other ball"] += 1
        checked += 1
    # mid-marathon resume: code after board 1 was won
    if state.K >= 2:
        first = state.Boards[0]
        midState = E.RunState(run, marathon=True)
        midState.Boards.append(first)
        midState.Picks.append(state.Picks[0])
        if state.Picks[0] != "0":
            midState.Satchel[state.Picks[0]] = midState.Satchel.get(state.Picks[0], 0) + 1
        midState.K = 2
        midBoard = E.Attach(E.RunBoard(run, 2, midState.Satchel, marathon=True), midState)
        midCode = midState.Code(midBoard)
        s3, b3 = E.ResumeRun(midCode)
        if not s3.Marathon or s3.K != 2 or b3.Quota != E.MarathonQuota(2) or b3.Limit != E.MarathonShotLimit(2):
            bad["mid resume"] += 1
        if s3.Code(b3) != midCode:
            bad["mid roundtrip"] += 1

# 4. Restart keeps marathon mode (same calls the r key makes)
st = E.RunState(42, marathon=True)
st2 = E.RunState(st.Run, st.Legacy, st.Marathon)
if not st2.Marathon or not st2.Code().startswith(E.Version + "M-"):
    bad["restart keeps marathon"] += 1

# 5. Cross-parser rejection and bad marathon codes
okCode = None
for run in range(30001, 30003):
    rng = random.Random(run)
    st, bd = PlayMarathon(run, rng)
    okCode = st.Code(bd)
    break
runCode = E.RunState(42).Code(E.Attach(E.RunBoard(42, 1, dict(E.RunStart)), E.RunState(42)))
for code, parser, want in ((okCode, E.ParseCodeFull, False),
                           (runCode, E.ParseRunCodeFull, True),
                           ("CH21M-1--", E.ParseRunCodeFull, False),
                           ("CH23M-0--", E.ParseRunCodeFull, False),
                           ("CH23M-1-x-", E.ParseRunCodeFull, False),
                           ("CH23M-1--999", E.ParseRunCodeFull, False),
                           ("CH23M-1-r-", E.ParseRunCodeFull, False)):
    try:
        parser(code)
        accepted = True
    except ValueError:
        accepted = False
    if accepted != want:
        bad["parser " + code[:12]] += 1

# 6. Marathon best file
folder = tempfile.mkdtemp()
path = os.path.join(folder, "best.txt")
os.environ["CHAIN_MARATHON_FILE"] = path
if E.ReadMarathonBest(path) != (0, 0, True):
    bad["best empty"] += 1
best, isNew, saved = E.RecordMarathonBest(5, 12000)
if not isNew or not saved or best != (5, 12000):
    bad["best first"] += 1
best, isNew, saved = E.RecordMarathonBest(5, 11000)
if isNew or best != (5, 12000):
    bad["best lower total"] += 1
best, isNew, saved = E.RecordMarathonBest(5, 13000)
if not isNew or best != (5, 13000):
    bad["best tie total"] += 1
best, isNew, saved = E.RecordMarathonBest(7, 100)
if not isNew or best != (7, 100):
    bad["best more boards"] += 1
open(path, "w").write("not a best file")
if E.ReadMarathonBest(path) != (0, 0, True):
    bad["best corrupt"] += 1
del os.environ["CHAIN_MARATHON_FILE"]

# 7. Standard run codes and board codes are untouched
state = E.RunState(42)
board = E.Attach(E.RunBoard(42, 1, state.Satchel), state)
code = state.Code(board)
if not code.startswith(E.Version + "R-"):
    bad["run code prefix"] += 1
s2, b2 = E.ResumeRun(code)
if s2.Marathon:
    bad["run resumed as marathon"] += 1

print("marathon checks: boards checked", checked, "violations", dict(bad) if bad else "none")
if bad:
    sys.exit(1)
print("PASS")
