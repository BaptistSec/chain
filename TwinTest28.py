"""CH26 twin ball: the split half is a plain ball on the mirror path from the first
peg contact - no floor rebound, no dock catch, no blast, no re-split, one Settle,
and it never perturbs the main flight. Twins come from draft picks only, the HUD
shows [5] only when the run pool carries twins, and the terminal wiring (offer,
pick, satchel, next-board stock, ball key 5) works end to end. Web twin coverage
lives in WebTest26 (real Chrome, 148 client checks)."""
import sys, os, re, random, importlib.util
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec); Spec.loader.exec_module(E)
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)

Check(E.KindNames.get("t") == "twin", "kind table names the twin ball")
Check(E.TwinPool == ["r", "x", "s", "t"] and E.RunPool == ["r", "x", "s"], "pools: runs keep three, CH26 offers four")

def TwinBoard(seed):
    b = E.Board(seed)
    b.Stock = dict(b.Stock); b.Stock["t"] = 9
    return b

def PathOf(board, aim, kind):
    path = []
    shot = board.Play(aim, lambda x, y, *rest: path.append((x, y)) if x is not None else None, kind)
    return path, shot

# a split: find a seed and aim where the twin flight adds positions past the n-ball path
found = None
for seed in range(1, 400):
    for aim in range(len(E.Directions)):
        bn = TwinBoard(seed); pn, sn = PathOf(bn, aim, "n")
        if not sn.Targets and not sn.Bonus:
            continue
        bt = TwinBoard(seed); pt, st = PathOf(bt, aim, "t")
        if len(pt) > len(pn):
            found = (seed, aim, pn, pt, sn, st)
            break
    if found: break
Check(found is not None, "a twin shot splits on some board")
seed, aim, pn, pt, sn, st = found
Check(pt[:len(pn)] == pn, "the main half flies the exact n-ball path, split does not perturb it")
Check((seed, aim, len(pn), len(pt)) == (1, 0, 86, 125), "the pinned split case stays the pinned split case")
btPin = TwinBoard(1); PathOf(btPin, 0, "t")
Check(btPin.Hash()[:8] == "efb91b87" and btPin.Score == 280, "the pinned split board lands on the pinned hash and score")
seg = pt[len(pn):]
Check(len(seg) >= 2, "the twin half really flies (more than one position)")
floors = [i for i, (x, y) in enumerate(seg) if y >= E.Height - 1]
Check(not floors or floors[-1] == len(seg) - 1, "the twin half stops at the floor, never rebounds")
Check(all(y < E.Height for (x, y) in seg), "the twin half never crosses the floor line")
Check(st.FloorX == sn.FloorX and st.Caught == sn.Caught, "dock and floor records come from the main half only")
Check(len(pt) <= E.StepCap, "one shared step budget bounds both halves, no runaway re-split")

# determinism and code roundtrip: same seed and aim replay byte-identically
h1 = TwinBoard(seed); PathOf(h1, aim, "t")
h2 = TwinBoard(seed); PathOf(h2, aim, "t")
Check(h1.Hash() == h2.Hash(), "twin shots are deterministic")

# whiff: no contact, no twin flight, identical path and removals to the n-ball
whiff = None
for seed2 in range(1, 400):
    for aim2 in range(len(E.Directions)):
        bn = TwinBoard(seed2); pn2, sn2 = PathOf(bn, aim2, "n")
        if sn2.Targets or sn2.Bonus or sn2.SettlePops:
            continue
        bt = TwinBoard(seed2); pt2, st2 = PathOf(bt, aim2, "t")
        if pt2 == pn2 and not st2.Targets and not st2.SettlePops:
            whiff = (seed2, aim2)
            break
    if whiff: break
Check(whiff is not None, "a whiffed twin shot spawns no second ball and removes nothing")
Check(whiff == (1, 10), "the pinned whiff case stays the pinned whiff case")

# stock: exactly one charge per twin shot, empty stock refuses
b = TwinBoard(seed)
before = b.Stock["t"]
b.Play(aim, None, "t")
Check(b.Stock["t"] == before - 1, "one twin charge per shot, the split half costs nothing extra")
b.Stock["t"] = 0
try:
    b.Play(aim, None, "t"); Check(False, "empty twin stock refuses the shot")
except ValueError:
    Check(True, "empty twin stock refuses the shot")

# F pegs: the twin half earns free-shot bonuses too
bonus = None
for seed3 in range(1, 400):
    for aim3 in range(len(E.Directions)):
        bn = TwinBoard(seed3); pn3, sn3 = PathOf(bn, aim3, "n")
        bt = TwinBoard(seed3); pt3, st3 = PathOf(bt, aim3, "t")
        if len(pt3) > len(pn3) and st3.Bonus > sn3.Bonus:
            bonus = (seed3, aim3, sn3.Bonus, st3.Bonus)
            break
    if bonus: break
Check(bonus is not None, "the twin half earns F-peg bonuses (main %d, both %s)" % ((bonus[2], bonus[3]) if bonus else (0, "?")))
Check(bonus == (1, 3, 0, 1), "the pinned bonus case stays the pinned bonus case")
bBP = TwinBoard(1); pBP, sBP = PathOf(bBP, 3, "t")
bBN = TwinBoard(1); pBN, sBN = PathOf(bBN, 3, "n")
Check((len(pBN), len(pBP)) == (133, 304), "the pinned bonus case twin flight keeps its length")
Check(bBP.Hash()[:8] == "3f17b0a9" and bBP.Score == 935 and sBP.Targets - sBN.Targets == 2, "the twin half removes its pinned pegs in the bonus case")

# draft offers: rotating leave-one-out over four kinds, twins in three of four
offers = [E.RunOffer(30001, k, E.TwinPool) for k in range(1, 9)]
expect = [["x", "s", "t"], ["s", "t", "r"], ["t", "r", "x"], ["r", "x", "s"]] * 2
Check(offers == expect, "CH26 draft rotates the leave-one-out offer over four kinds")
Check(all(len(set(o)) == 3 for o in offers) and sum("t" in o for o in offers[:4]) == 3, "twins appear in three of every four offers")
Check([E.RunOffer(30001, k, E.RunPool) for k in range(1, 4)] == [["s", "r", "x"], ["r", "x", "s"], ["x", "s", "r"]], "three-kind runs keep the old rotation")

# run wiring: clear board 1, take the twin at the draft, board 2 stocks it, firing spends it
st8 = E.RunState(30001)
b1 = None
for attempt in range(60):
    rng = random.Random(attempt)
    cand = E.Attach(E.RunBoard(30001, 1, dict(st8.Satchel), pool=st8.Pool), st8)
    while not cand.Over():
        cand.Play(rng.randrange(len(E.Directions)))
    if cand.Won():
        b1 = cand
        break
Check(b1 is not None, "board 1 of run 30001 is clearable, the draft is reachable")
st8.Boards.append(b1); st8.Picks.append("t"); st8.Satchel["t"] = st8.Satchel.get("t", 0) + 1; st8.K = 2
b8 = E.Attach(E.RunBoard(30001, 2, st8.Satchel, pool=st8.Pool), st8)
Check(b8.Stock.get("t", 0) == 1, "a twin pick stocks the next board")
n8 = b8.Stock["t"]
b8.Play(E.DefaultAim, None, "t")
Check(b8.Stock["t"] == n8 - 1, "firing a twin in a run spends the charge")
code = st8.Code(b8)
Check(code.startswith("CH26R-") and "t" in code.split("-")[3], "the run code carries the twin pick")
stBack, bBack = E.ResumeRun(code)
Check(bBack.Hash() == b8.Hash(), "a twin run code resumes to the same board")
Check(bBack.Log[-1].SettlePops == b8.Log[-1].SettlePops and bBack.Log[-1].Cascade == b8.Log[-1].Cascade, "one settle, identical cascades on resume")
Check(bBack.Log[-1].Kind == "t" and stBack.Picks == st8.Picks and stBack.Satchel == st8.Satchel, "resume keeps the twin shot, the pick and the satchel")
Check(E.PoolForCode("CH26R-30001-9.10.10-t-10/8") == E.TwinPool and E.PoolForCode("CH25R-30001-9.10.10-x-10/8") == E.RunPool, "the code prefix picks the satchel pool")

# frozen arms stay twin-free
st9 = E.RunState(30001)
b9 = E.Attach(E.RunBoard(30001, 1, dict(st9.Satchel), pool=E.RunPool), st9)
Check("t" not in b9.Stock, "three-kind boards carry no twin stock")
try:
    b9.Play(E.DefaultAim, None, "t"); Check(False, "three-kind boards refuse twin shots")
except ValueError:
    Check(True, "three-kind boards refuse twin shots")

# terminal wiring over a real pty: clear marathon board 1, take the twin at the draft,
# board 2 shows it in the satchel and as ball key [5], firing it spends the charge
if os.environ.get("CHAIN_NO_PTY"):
    print("ok   pty leg skipped (CHAIN_NO_PTY)")
    print("FAILS", len(Fails))
    sys.exit(1 if Fails else 0)
sys.path.insert(0, Here)
from PtyDrive15 import Drive
aims = None
for attempt in range(60):
    rng = random.Random(attempt)
    cand = E.Attach(E.RunBoard(30001, 1, dict(E.RunState(30001).Satchel), pool=E.TwinPool), E.RunState(30001))
    log = []
    while not cand.Over():
        a = rng.randrange(len(E.Directions))
        cand.Play(a)
        log.append(a)
    if cand.Won():
        aims = log
        break
Check(aims is not None, "marathon board 1 of run 30001 is clearable for the terminal drive")
keys = []
aim = E.DefaultAim
for a in aims:
    d = a - aim
    keys += ["R"] * d if d > 0 else ["L"] * (-d)
    aim = a
    keys += ["SP", "w", "w", "w"]
offer = E.RunOffer(30001, 1, E.TwinPool)
Check("t" in offer, "the first draft of run 30001 offers the twin")
keys += ["w", "w", "n", "w", "w", str(offer.index("t") + 1), "w", "w"]
txt = Drive(["--marathon", "30001"], keys)
Check("[5] twin" in txt, "the ball line shows [5] twin on a CH26 board")
Check("splits into two balls at the first peg it touches" in txt, "the draft screen describes the twin")
Check("twin x1" in txt, "the satchel shows the picked twin on board 2")
Check("[5] twin x1" in txt, "the picked twin is stocked as a ball-line charge on board 2, not only offered and collected")
txt2 = Drive(["--marathon", "30001"], keys + ["5", "SP", "w", "w", "w", "w", "q", "w"])
Check("No twin balls left" not in txt2, "the terminal accepts the stocked twin shot instead of refusing it")
Check("[5] twin x0" in txt2, "firing the twin spends the specific ball-line charge in the terminal")
Check("Traceback" not in txt2 and "ValueError" not in txt2, "the terminal twin shot never crashes")

print("FAILS", len(Fails))
sys.exit(1 if Fails else 0)
