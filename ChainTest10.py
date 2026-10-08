import sys, random, importlib.util, os, collections, hashlib
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec)
Spec.loader.exec_module(E)

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
    for k in (["s", "x", "r"] if os.environ.get("PICK") == "s" else ["x", "r", "s"] if hit else ["s", "r", "x"]):
        if b.Stock.get(k, 0) > 0:
            return k
    return "n"

def PlayRun(run, rng):
    state = E.RunState(run)
    board = E.Attach(E.RunBoard(run, 1, state.Satchel), state)
    starts = []
    while True:
        starts.append(dict(board.Stock))
        while not board.Over():
            left = E.ShotLimit + board.Extra - len(board.Log)
            aim, hit = Policy(board, rng)
            board.Play(aim, None, Kind(board, hit, left))
        if not board.Won() or state.K >= len(E.RunQuotas):
            break
        state.Boards.append(board)
        forced = os.environ.get("PICK")
        choice = rng.randrange(4)
        pick = forced if forced else (E.RunOffer(run, state.K)[choice] if choice < 3 else "0")
        state.Picks.append(pick)
        if pick != "0":
            state.Satchel[pick] = state.Satchel.get(pick, 0) + 1
        state.K += 1
        board = E.Attach(E.RunBoard(run, state.K, state.Satchel), state)
    if board.Won() and state.K >= len(E.RunQuotas):
        state.Boards.append(board)
        return state, board, starts, True
    return state, board, starts, False

bad = collections.Counter()
n = int(os.environ.get("N", "100"))
checked = 0
for run in range(30001, 30001 + n):
    rng = random.Random(run)
    state, board, starts, complete = PlayRun(run, rng)
    code = state.Code(board)
    s2, b2 = E.ResumeRun(code)
    code2 = s2.Code(b2)
    if code != code2:
        bad["code roundtrip"] += 1
    if b2.Hash() != board.Hash():
        bad["final hash"] += 1
    allBoards = state.Boards + ([] if complete else [board])
    for i, b in enumerate(allBoards):
        used = collections.Counter(s.Kind for s in b.Log)
        for c in "rxs":
            if starts[i].get(c, 0) - used.get(c, 0) != b.Stock.get(c, 0):
                bad["stock " + c] += 1
        hearts = sum(1 for v in b.Grid.values() if v == "F")
        refunds = sum(s.Refund for s in b.Log)
        if b.Extra != sum(s.Bonus for s in b.Log):
            bad["bonus sum"] += 1
        fresh = E.Board(b.Seed)
        heartPegs = sum(1 for v in fresh.Grid.values() if v == "F")
        if len(b.Log) > E.ShotLimit + starts[i].get("s", 0) + heartPegs:
            bad["attempt bound"] += 1
        if len(b.Log) > E.ShotLimit + b.Extra:
            bad["over limit"] += 1
        for s in b.Log:
            if s.Kind == "s" and (s.Targets <= 1) != bool(s.Refund):
                bad["refund rule"] += 1
            if s.Kind != "s" and s.Refund:
                bad["refund on other ball"] += 1
        if any(v < 0 for v in b.Stock.values()):
            bad["negative stock"] += 1
        quota = E.RunQuotas[i]
        done = min(max(quota - b.TargetsLeft(), 0), quota)
        if not 0 <= done <= quota:
            bad["credits range"] += 1
        checked += 1
    for badCode in (code + ".999", code.replace("CH10R", "CH9R"), code.replace("-" + str(run) + "-", "-0-", 1)):
        try:
            E.ParseRunCode(badCode)
            bad["accepted bad code"] += 1
        except ValueError:
            pass
print("runs", n, "boards checked", checked, "violations", dict(bad) if bad else "none")
if bad:
    sys.exit(1)
