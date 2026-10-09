import sys, os, random, re, collections, hashlib, importlib.util
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec); Spec.loader.exec_module(E)
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
Strip = lambda x: re.sub("\x1b\\[[0-9;]*[A-Za-z]", "", x)
Check(E.JackpotPoints == 500, "jackpot constant is 500")
bad = collections.Counter(); hits = shots = boards = 0
for seed in range(30001, 30301):
    rng = random.Random(seed)
    b = E.Board(seed); boards += 1
    t = sorted(c for c, v in b.Grid.items() if v == "#")
    if b.Jackpot != t[seed % len(t)]: bad["placement"] += 1
    if b.Grid.get(b.Jackpot) != "#": bad["not a target"] += 1
    if E.Board(seed).Jackpot != b.Jackpot: bad["not deterministic"] += 1
    b.Stock["s"] = 3
    got = 0
    while not b.Over():
        k = "n"
        if rng.random() < 0.4:
            o = [c for c in "rxs" if b.Stock.get(c, 0) > 0]
            if o: k = rng.choice(o)
        before = dict(b.Grid); score = b.Score; up = b.Jackpot in before
        # same shot on a clone without the jackpot bonus = reference score
        ref = b.Clone(); ref.Jackpot = None
        a = rng.randrange(len(E.Directions))
        sh = b.Play(a, None, k)
        refshot = ref.Play(a, None, k) if (k == "n" or ref.Stock.get(k, 0) > 0) else None
        shots += 1
        gone = up and b.Jackpot not in b.Grid
        if bool(sh.Jackpot) != gone: bad["flag vs grid"] += 1
        if sh.Jackpot:
            got += 1
            if refshot is not None and sh.Points != refshot.Points + E.JackpotPoints: bad["bonus not exactly +500"] += 1
        elif refshot is not None and sh.Points != refshot.Points: bad["points differ without jackpot"] += 1
        if b.Score - score != sh.Points: bad["score sum"] += 1
        msg = E.ShotMessage(b, sh)
        if sh.Jackpot and "JACKPOT +500" not in msg: bad["message"] += 1
        if len(msg) > E.Width * E.CellCols: bad["message width"] += 1
    if got > 1: bad["paid twice"] += 1
    hits += got
    r = E.Board(seed); r.Stock["s"] = 3
    for x in b.Log: r.Play(x.Aim, None, x.Kind)
    if r.Hash() != b.Hash() or r.Score != b.Score or [x.Jackpot for x in r.Log] != [x.Jackpot for x in b.Log]: bad["replay"] += 1
Check(not bad, "jackpot: placement, one-target-only, +500 exactly once and only on that shot, score sums, message, replay (%d boards, %d shots, %d jackpots, problems %s)" % (boards, shots, hits, dict(bad)))
Check(hits > 100, "enough jackpot hits to mean something (%d)" % hits)
# no rng draw: layouts are identical to CH18 (same grid for the same seeds)
Old = sys.argv and os.environ.get("CH18_DIR")
if Old and os.path.exists(os.path.join(Old, "ChainDemo.py")):
    sp = importlib.util.spec_from_file_location("old", os.path.join(Old, "ChainDemo.py")); O = importlib.util.module_from_spec(sp); sp.loader.exec_module(O)
    same = all(O.Board(s).Grid == E.Board(s).Grid for s in range(30001, 30301))
    Check(same, "every board layout is identical to CH18 (set CH18_DIR to the CH18 folder)")
else:
    print("note CH18_DIR not set: layout identity against CH18 not checked")
# rendering
b = E.Board(30001)
for plain in (False, True):
    for mono in (True, False):
        f = E.Screen(mono, 0, plain).Frame(b, 20, False, None, "x", False)
        text = "\n".join(Strip(l) for l in f)
        glyph = "$$" if plain else "\u2605\u2605"
        Check(text.count(glyph) == 1 and max(len(Strip(l)) for l in f) <= 102 and any("jackpot" in l for l in f), "frame shows exactly one jackpot glyph %r plus a legend entry, within 102 columns (plain=%s mono=%s)" % (glyph, plain, mono))
        if mono: Check("\x1b" not in "".join(f), "no colour codes in mono")
cf = E.Screen(False, 0, False).Frame(b, 20, False, None, "x", False)
Check(any("38;5;213" in l for l in cf), "jackpot has its own colour in colour mode")
# board files have no jackpot
Check(E.Board.Jackpot is None, "boards without a numeric seed (board files) have no jackpot")
print("FAILS", len(Fails))
sys.exit(1 if Fails else 0)
