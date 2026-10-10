"""CH21 vs CH20 per-shape jackpot measurement. Usage: python3 JackpotMeasure21.py CH20_DIR [first_seed] [count]"""
import sys, os, random, importlib.util, collections
Old = sys.argv[1]; First = int(sys.argv[2]) if len(sys.argv) > 2 else 30001; Count = int(sys.argv[3]) if len(sys.argv) > 3 else 600
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
def Opening(E, b):
    n = 0
    for a in range(len(E.Directions)):
        c = b.Clone(); c.Struck = []; c.Fire(a, None, E.PreviewSteps, False, True, "n")
        n += b.Jackpot in set(c.Struck)
    return n
def Play(E, seed, mode):
    rng = random.Random(seed); b = E.Board(seed)
    while not b.Over():
        left = E.ShotLimit + b.Extra - len(b.Log)
        if mode == "bot": aim, hit = Policy(E, b, rng); kind = Kind(E, b, hit, left)
        else: aim, kind = rng.randrange(len(E.Directions)), "n"
        b.Play(aim, None, kind)
    return b
O, N = Load(Old, "old"), Load(Here, "new")
for mode in ("bot", "random"):
    R = collections.defaultdict(collections.Counter)
    for seed in range(First, First + Count):
        a = Play(O, seed, mode); b = Play(N, seed, mode)
        fam = N.Board(seed).Style.split(" ")[0]
        for key in (fam, "ALL"):
            r = R[key]; r["boards"] += 1
            r["same layout"] += O.Board(seed).Grid == N.Board(seed).Grid
            r["same clear+shots"] += (a.Won() == b.Won() and len(a.Log) == len(b.Log))
            r["won"] += b.Won()
            r["hit old"] += sum(s.Jackpot for s in a.Log) > 0; r["hit new"] += sum(s.Jackpot for s in b.Log) > 0
            r["score old"] += a.Score; r["score new"] += b.Score
            nb = N.Board(seed); r["opening-strikable"] += Opening(N, nb) > 0; r["reach sum"] += Opening(N, nb)
    print("== %s aim, seeds %d..%d (%d boards)" % (mode, First, First + Count - 1, Count))
    for k in sorted(R):
        r = R[k]; n = r["boards"]
        print("%-9s n=%3d layouts same %3d clear+shots same %3d/%3d | jackpot hit old %5.1f%% new %5.1f%% | mean score %+.1f%% | opening-strikable %5.1f%% mean aims %.1f/39" % (k, n, r["same layout"], r["same clear+shots"], n, 100*r["hit old"]/n, 100*r["hit new"]/n, 100.0*(r["score new"]/r["score old"]-1), 100*r["opening-strikable"]/n, r["reach sum"]/n))
