import sys, os, random, hashlib, re, importlib.util
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec); Spec.loader.exec_module(E)
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
def Strip(x): return re.sub("\x1b\\[[0-9;]*[A-Za-z]", "", x)
Limit = E.Width * E.CellCols
Pinned = "e7cc97ad1f1f1753b16cc4a22ca01ff4ff217846d8449180f05569d319d97400"
digest = hashlib.sha256(); wins = losses = 0; bad = []; frameBad = []
for seed in range(30001, 30301):
    rng = random.Random(seed)
    st = E.RunState(seed); b = E.Attach(E.RunBoard(seed, 1, dict(st.Satchel)), st)
    b.Stock["s"] = 3
    while not b.Over():
        k = "n"
        if rng.random() < 0.5:
            opts = [c for c in "rxs" if b.Stock.get(c, 0) > 0]
            if opts: k = rng.choice(opts)
        b.Play(rng.randrange(len(E.Directions)), None, k)
    digest.update((b.Hash() + "|" + str(len(b.Log))).encode())
    recap = E.Recap(b)
    # independent recount: replay the aims on a fresh board and read the HUD credits line
    fresh = E.Attach(E.RunBoard(seed, 1, dict(st.Satchel)), st); fresh.Stock["s"] = 3
    for s in b.Log: fresh.Play(s.Aim, None, s.Kind)
    scr = E.Screen(True, 0, False)
    frame = scr.Frame(fresh, 20, False, None, "x", True)
    hud = [l for l in frame if "Credits" in l][0]
    m = re.search(r"Credits (\d+)/(\d+)", hud)
    left = int(m.group(2)) - int(m.group(1))
    shots = sum(1 for s in b.Log)
    rally = max([s.Rally for s in b.Log] + [1])
    chain = max([s.Chain for s in b.Log] + [0])
    won = left == 0
    if won:
        wins += 1
        want = "Cleared in %d %s, best rally x%d, best chain %d, Overdrive %s" % (shots, "shot" if shots == 1 else "shots", rally, chain, "earned" if b.OverGiven else "not earned")
    else:
        losses += 1
        want = "OUT OF SHOTS: %d %s left to clear" % (left, "target" if left == 1 else "targets")
    if recap != want or len(recap) > Limit - 1 or recap != E.Recap(fresh): bad.append((recap, want))
    rows = [l for l in frame if Strip(l).strip() == recap]
    if len(rows) != 1 or "\x1b" in "".join(frame): frameBad.append(seed)
Check(not bad, "recap numbers match an independent recount (replay plus HUD credits) and fit the screen: %d wins, %d losses" % (wins, losses))
if bad: print(bad[0])
Check(wins > 0 and losses > 0, "both outcomes covered")
Check(not frameBad, "result frame shows the recap exactly once; mono has no colour codes")
colour = E.Screen(False, 0, False).Frame(b, 20, False, None, "x", True)
Check(any(Strip(l).strip() == recap for l in colour), "recap also shows in colour mode")
Check(digest.hexdigest() == Pinned, "engine replay digest identical to the CH18 pin (" + digest.hexdigest()[:8] + ")")
# run summary
st = E.RunState(5); first = E.Attach(E.RunBoard(5, 1, dict(st.Satchel)), st)
rng = random.Random(5)
while not first.Over(): first.Play(rng.randrange(len(E.Directions)), None, "n")
st.Boards.append(first)
second = E.Attach(E.RunBoard(5, 2, dict(st.Satchel)), st)
second.Play(10, None, "n")
lines = E.RunSummary(st, second)
want1 = "Board 1: %s, %d %s, score %d" % ("cleared" if first.Won() else "out of shots, %d left" % first.TargetsLeft(), len(first.Log), "shot" if len(first.Log) == 1 else "shots", first.Score)
Check(len(lines) == 2 and lines[0] == want1 and lines[1].startswith("Board 2: unfinished, 1 shot, score "), "run summary lists each board: " + " / ".join(lines))
print("FAILS", len(Fails))
sys.exit(1 if Fails else 0)
