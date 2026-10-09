import sys, os, random, collections, importlib.util
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
src = open(os.path.join(Here, "ChainTest15.py")).read().split("bad = collections.Counter()")[0]
exec(compile(src, "ChainTest15.py", "exec"))
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
New = ["spiral", "funnel", "stairs"]
Old = ["diamonds", "waves", "chevrons", "arches", "rings"]
Check(E.LayoutNames == Old + New, "layout names: five old families then spiral, funnel, stairs")
First, Count = 30001, 1200
Fam = collections.defaultdict(collections.Counter)
Hashes = {}
Scatter = collections.Counter()
for seed in range(First, First + Count):
    b = E.Board(seed)
    origin = E.LayoutNames[E.Rng(seed).Below(len(E.LayoutNames))]
    fam = b.Style.split(" ")[0]
    R = Fam[origin]
    R["boards"] += 1
    if fam == "scatter": Scatter[origin] += 1
    targets = [c for c, v in b.Grid.items() if v == "#"]
    R["targets ok"] += len(targets) == E.TargetCount
    R["in bounds"] += all(1 <= x <= E.Width - 2 and 4 <= y <= E.Height - 5 for x, y in b.Grid)
    R["floor ok"] += min([abs(a[0]-c[0])+abs(a[1]-c[1]) for i, a in enumerate(targets) for c in targets[i+1:]] or [99]) >= E.TargetFloor
    hit = set()
    for a in range(len(E.Directions)):
        c = b.Clone(); c.Fire(a, None, E.PreviewSteps, False, True, "n"); hit.update(c.Struck)
    R["reach"] += sum(1 for t in targets if t in hit)
    R["pegs"] += len(b.Grid)
    if seed - First < 150: Hashes[seed] = b.Hash()
    rng = random.Random(seed); bb = E.Board(seed)
    while not bb.Over():
        left = E.ShotLimit + bb.Extra - len(bb.Log)
        aim, h = Policy(bb, rng)
        bb.Play(aim, None, Kind(bb, h, left))
    R["bot"] += bb.Won()
rate = lambda o: 100.0 * Fam[o]["bot"] / Fam[o]["boards"]
oldAvg = sum(Fam[o]["bot"] for o in Old) / sum(Fam[o]["boards"] for o in Old) * 100
print("old-family bot win average %.1f%%" % oldAvg)
for o in Old + New:
    R = Fam[o]; n = R["boards"]
    print("  %-9s boards %3d  scatter %2d  pegs %.1f  reach %.1f/12  bot win %.1f%%" % (o, n, Scatter[o], R["pegs"]/n, R["reach"]/n, rate(o)))
for o in New:
    R = Fam[o]; n = R["boards"]
    Check(n >= 100, "%s appears often enough (%d of %d boards)" % (o, n, Count))
    Check(Scatter[o] == 0, "%s never collapses to scatter" % o)
    Check(R["targets ok"] == n and R["in bounds"] == n, "%s: exactly %d targets and every cell inside the board" % (o, E.TargetCount))
    Check(R["floor ok"] >= 0.9 * n, "%s keeps the %d-cell target spacing on at least 90%% of boards (%.0f%%)" % (o, E.TargetFloor, 100.0 * R["floor ok"] / n))
    Check(R["reach"] / n >= 7.0, "%s: an opening shot can strike at least 7 of 12 targets on average (%.1f)" % (o, R["reach"] / n))
    Check(abs(rate(o) - oldAvg) <= 15.0 and 50.0 <= rate(o) <= 85.0, "%s bot clear rate %.1f%% within 15 points of the old families (%.1f%%) and 50-85%%" % (o, rate(o), oldAvg))
Check(all(E.Board(s).Hash() == h for s, h in Hashes.items()), "boards are deterministic per seed (150 rebuilt)")
Check(len(set(Hashes.values())) == len(Hashes), "150 consecutive seeds give 150 different boards")
# every family renders inside the screen and looks different
shapes = {}
for seed in range(First, First + 400):
    b = E.Board(seed); fam = b.Style.split(" ")[0]
    if fam in New and fam not in shapes:
        lines = E.Screen(True, 0, False).Frame(b, 20, False, None, "", False)
        shapes[fam] = lines
        Check(max(len(l) for l in lines) <= 104, "%s frame fits 104 columns" % fam)
Check(len(shapes) == 3, "rendered one board of each new family")
print("FAILS", len(Fails))
sys.exit(1 if Fails else 0)
