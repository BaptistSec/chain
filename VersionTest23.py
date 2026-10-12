"""CH23 versioning: old-prefix codes keep resolving to the exact CH21/CH22 boards, new-prefix codes use the new shapes."""
import sys, os, random, hashlib, collections
sys.argv = ["x"]
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import ChainDemo as E
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
OldDigest = "71803be34af68c7bedd3aa5d0fc95bb2943f6e2f5f89e14593f7a8c43a826011"   # sha256 over Hash|Jackpot|Style of boards 30001..30600 from the published CH22 engine (fd880a9f)
NewDigest = "980d944509c83dc995aef72073afdfe1e4aefaa71323dda1faa53680473ea555"
def Digest(legacy):
    d = hashlib.sha256()
    for s in range(30001, 30601):
        b = E.Board(s, legacy); d.update((b.Hash() + "|" + str(b.Jackpot) + "|" + b.Style).encode())
    return d.hexdigest()
Check(Digest(True) == OldDigest, "CH21-prefix boards on seeds 30001..30600 identical to the published CH22 engine (digest %s)" % Digest(True)[:8])
Check(Digest(False) == NewDigest, "CH23 boards on seeds 30001..30600 match their pin (%s)" % Digest(False)[:8])
Check(E.Version == "CH23" and E.LegacyVersion == "CH21", "version CH23, legacy CH21")
# single-board codes
for seed in (1, 77, 30001, 30002, 31234):
    old = E.Replay("CH21-" + str(seed) + "-0.5.9"); new = E.Replay("CH23-" + str(seed) + "-0.5.9")
    Check(old.Legacy and not new.Legacy and old.Code().startswith("CH21-") and new.Code().startswith("CH23-"), "seed %d: prefix picks the generator and Code() keeps it" % seed)
    Check(old.Code().split("-", 1)[1] == "%d-0.5.9" % seed or len(old.Log) < 3, "seed %d: CH21 code round-trips" % seed)
for bad in ("CH22-5-1", "CH20-5-1", "CH24-5-1", "CH5-5-1", "CH21CH23-5-1"):
    try: E.Replay(bad); Check(False, "rejects " + bad)
    except ValueError: Check(True, "rejects " + bad)
# run codes: build a CH21R run with bot-ish random play, resume it, expect the same code
rng = random.Random(9)
for legacy, prefix in ((True, "CH21R"), (False, "CH23R")):
    st = E.RunState(30001, legacy); b = E.Attach(E.RunBoard(30001, 1, st.Satchel, legacy), st)
    while not b.Over():
        b.Play(rng.randrange(len(E.Directions)), None, "n")
    code = st.Code(b)
    st2, b2 = E.ResumeRun(code)
    Check(code.startswith(prefix + "-") and st2.Legacy == legacy and st2.Code(b2) == code and b2.Hash() == b.Hash(), prefix + " run code resumes to the same board and keeps its prefix")
    Check(b2.Seed == E.RunBoardSeed(30001, 1) and b2.Legacy == legacy, prefix + " board seed and generator")
for bad in ("CH20R-1-1-0-", "CH22R-1-1-0-"):
    try: E.ParseRunCode(bad); Check(False, "rejects " + bad)
    except ValueError: Check(True, "rejects " + bad)
# new shapes
Fam = collections.defaultdict(list); Scat = 0
for seed in range(30001, 31201):
    b = E.Board(seed); fam = b.Style.split(" ")[0]; Fam[fam].append(b)
    if fam == "scatter": Scat += 1
for fam in ("pinwheel", "columns"):
    boards = Fam[fam]
    Check(len(boards) >= 70, "%s appears often enough (%d of 1200 boards, 1 in 13 expected = 92)" % (fam, len(boards)))
    Check(all(b.Total == 12 for b in boards), fam + ": exactly 12 targets on every board")
    Check(all(0 <= x < E.Width and 0 <= y < E.Height for b in boards for (x, y) in b.Grid), fam + ": every cell inside the board")
    Check(all(b.Jackpot is not None and b.Grid.get(b.Jackpot) == "#" for b in boards), fam + ": one jackpot, on a real target")
    Check(len({b.Hash() for b in boards}) == len(boards), fam + ": boards differ from each other")
    frames = [E.Screen(True, 0, False).Frame(b, 20, False, None, "", False) for b in boards[:40]]
    Check(all(len(l) <= 102 for f in frames for l in f), fam + ": frames fit 102 columns")
Check(Scat <= 24, "scatter fallback is rare on CH23 (%d of 1200)" % Scat)
print("FAILS", len(Fails)); sys.exit(1 if Fails else 0)
