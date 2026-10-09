"""Per layout family measurements. Usage: python3 LayoutMeasure18.py [first_seed] [count]"""
import sys, os, random, collections
Here = os.path.dirname(os.path.abspath(__file__))
First = int(sys.argv[1]) if len(sys.argv) > 1 else 30001
Count = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
sys.argv = ["x"]
src = open(os.path.join(Here, "ChainTest15.py")).read().split("bad = collections.Counter()")[0]
exec(compile(src, "ChainTest15.py", "exec"))
Rows = collections.defaultdict(lambda: collections.Counter())
for seed in range(First, First + Count):
    b = E.Board(seed)
    fam = b.Style.split(" ")[0]
    R = Rows[fam]
    R["boards"] += 1
    loose = sum(1 for v in b.Grid.values() if v in "o+")
    targets = [c for c, v in b.Grid.items() if v == "#"]
    R["pegs"] += len(b.Grid); R["targets"] += len(targets)
    if len(targets) != E.TargetCount: R["wrong target count"] += 1
    # target spacing (min manhattan between targets)
    mind = min([abs(a[0]-c[0])+abs(a[1]-c[1]) for i, a in enumerate(targets) for c in targets[i+1:]] or [99])
    R["min spacing sum"] += mind
    if mind < E.TargetFloor: R["spacing below floor"] += 1
    # reachability from opening shot: every target struck by some aim
    hit = set()
    for a in range(len(E.Directions)):
        c = b.Clone(); c.Fire(a, None, E.PreviewSteps, False, True, "n")
        hit.update(c.Struck)
    R["opening-reachable targets"] += sum(1 for t in targets if t in hit)
    # bot and random on this board
    rng = random.Random(seed)
    bb = E.Board(seed)
    while not bb.Over():
        left = E.ShotLimit + bb.Extra - len(bb.Log)
        aim, h = Policy(bb, rng)
        bb.Play(aim, None, Kind(bb, h, left))
    R["bot won"] += bb.Won()
    r = random.Random(seed * 3 + 1); rb = E.Board(seed)
    while not rb.Over(): rb.Play(r.randrange(len(E.Directions)), None, "n")
    R["random won"] += rb.Won()
print("seeds %d..%d, %d boards" % (First, First + Count - 1, Count))
print("%-9s %6s %6s %7s %7s %9s %8s %9s %8s %8s" % ("family", "boards", "share", "pegs", "target", "reach/12", "mind", "bot win", "rand win", "flags"))
for fam, R in sorted(Rows.items()):
    n = R["boards"]
    print("%-9s %6d %5.1f%% %7.1f %7.1f %9.2f %8.1f %8.1f%% %7.1f%%   wrongT %d floor %d" % (fam, n, 100.0*n/Count, R["pegs"]/n, R["targets"]/n, R["opening-reachable targets"]/n, R["min spacing sum"]/n, 100.0*R["bot won"]/n, 100.0*R["random won"]/n, R["wrong target count"], R["spacing below floor"]))
