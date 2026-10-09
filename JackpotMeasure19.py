"""CH19 vs CH18 measurement. Usage: python3 JackpotMeasure19.py CH18_DIR [first_seed] [count]"""
import sys, os, random, importlib.util, collections
Old = sys.argv[1]
First = int(sys.argv[2]) if len(sys.argv) > 2 else 30001
Count = int(sys.argv[3]) if len(sys.argv) > 3 else 300
Here = os.path.dirname(os.path.abspath(__file__))
def Load(d, name):
    sys.argv = ["x"]
    sp = importlib.util.spec_from_file_location(name, os.path.join(d, "ChainDemo.py"))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
def Policy(E, b, rng):
    best = []
    for a in range(len(E.Directions)):
        c = b.Clone(); c.Fire(a, None, E.PreviewSteps, False, True, "n")
        if c.Struck: best.append((a, b.Grid.get(c.Struck[0])))
    targets = [a for a, s in best if s == "#"]
    pool = targets or [a for a, s in best] or list(range(len(E.Directions)))
    return rng.choice(pool), bool(targets)
def Kind(E, b, hit, left):
    n = sum(b.Stock.values())
    if n == 0 or left > n + 4: return "n"
    for k in (["x", "r", "s"] if hit else ["s", "r", "x"]):
        if b.Stock.get(k, 0) > 0: return k
    return "n"
def Run(E, seed, mode):
    rng = random.Random(seed); st = E.RunState(seed)
    board = E.Attach(E.RunBoard(seed, 1, dict(st.Satchel)), st)
    out = []
    while True:
        while not board.Over():
            left = E.ShotLimit + board.Extra - len(board.Log)
            if mode == "bot":
                aim, hit = Policy(E, board, rng); kind = Kind(E, board, hit, left)
            else:
                aim, kind = rng.randrange(len(E.Directions)), "n"
            board.Play(aim, None, kind)
        out.append(board)
        if not board.Won() or st.K >= len(E.RunQuotas): break
        st.Boards.append(board); choice = rng.randrange(4)
        pick = E.RunOffer(seed, st.K)[choice] if choice < 3 else "0"
        if pick != "0": st.Satchel[pick] = st.Satchel.get(pick, 0) + 1
        st.K += 1; board = E.Attach(E.RunBoard(seed, st.K, dict(st.Satchel)), st)
    return out
N, W = Load(Old, "old"), Load(Here, "new")
for mode in ("bot", "random"):
    R = collections.Counter()
    for seed in range(First, First + Count):
        a = Run(N, seed, mode); b = Run(W, seed, mode)
        R["runs"] += 1
        R["boards old"] += len(a); R["boards new"] += len(b)
        R["won old"] += sum(x.Won() for x in a); R["won new"] += sum(x.Won() for x in b)
        R["same clear pattern"] += [x.Won() for x in a] == [x.Won() for x in b]
        R["same shots"] += [len(x.Log) for x in a] == [len(x.Log) for x in b]
        R["score old"] += sum(x.Score for x in a); R["score new"] += sum(x.Score for x in b)
        for x in b:
            R["jackpot boards"] += 1
            hit = sum(s.Jackpot for s in x.Log); R["jackpot hit"] += hit
            R["jackpot hit on won boards"] += hit if x.Won() else 0; R["won boards"] += x.Won()
            # reachable by an opening shot from the fresh board
            f = W.RunBoard(x.Seed if False else 0, 1, {"r": 1, "x": 1}) if False else None
    print("%s: runs %d, boards old/new %d/%d, won %d/%d, identical clear pattern %d/%d, identical shot counts %d/%d" % (mode, R["runs"], R["boards old"], R["boards new"], R["won old"], R["won new"], R["same clear pattern"], R["runs"], R["same shots"], R["runs"]))
    print("   jackpot hit on %d of %d boards (%.1f%%); of won boards %.1f%%; mean score per run old %.0f new %.0f (%+.1f%%)" % (R["jackpot hit"], R["jackpot boards"], 100.0 * R["jackpot hit"] / R["jackpot boards"], 100.0 * R["jackpot hit on won boards"] / max(1, R["won boards"]), R["score old"] / R["runs"], R["score new"] / R["runs"], 100.0 * (R["score new"] - R["score old"]) / R["score old"]))
# opening reachability of the jackpot, every board seed
reach = 0; total = 0; fam = collections.defaultdict(lambda: [0, 0])
for seed in range(First, First + 1200):
    b = W.Board(seed); hit = set()
    for a in range(len(W.Directions)):
        c = b.Clone(); c.Fire(a, None, W.PreviewSteps, False, True, "n"); hit.update(c.Struck)
    f = b.Style.split(" ")[0]
    fam[f][1] += 1; total += 1
    if b.Jackpot in hit: reach += 1; fam[f][0] += 1
print("jackpot struck by some opening aim: %d of %d boards (%.1f%%)" % (reach, total, 100.0 * reach / total))
print("   by family: " + ", ".join("%s %.0f%%" % (k, 100.0 * v[0] / v[1]) for k, v in sorted(fam.items())))
