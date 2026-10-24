"""CH25 versioning: CH21, CH23 and CH24 codes keep resolving to their exact pinned boards through three frozen arms, CH25 codes use the fifteen-shape tuned generator with hourglass and towers."""
import sys, os, random, hashlib, collections
sys.argv = ["x"]
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import ChainDemo as E
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
OldDigest = "71803be34af68c7bedd3aa5d0fc95bb2943f6e2f5f89e14593f7a8c43a826011"   # CH21 legacy pin: sha256 over Hash|Jackpot|Style of boards 30001..30600 from the published CH22 engine (fd880a9f)
Mid2Digest = "980d944509c83dc995aef72073afdfe1e4aefaa71323dda1faa53680473ea555"   # CH23 generator pin from VersionTest23, now resolved through the mid2 arm
MidDigest = "52fb0fe01ec7c2c5aeda394a91b0f8ac9f9f12836c32d8691eb8b6012b33e910"   # CH24 tuned generator pin from VersionTest24, now resolved through the mid arm
NewDigest = "96367202d727891640f7b8cb4abaa6e3fa54e83f2dae3409c5266beaca091ad3"   # CH25 fifteen-shape generator pin
def Digest(make):
    d = hashlib.sha256()
    for s in range(30001, 30601):
        b = make(s); d.update((b.Hash() + "|" + str(b.Jackpot) + "|" + b.Style).encode())
    return d.hexdigest()
Check(Digest(lambda s: E.Board(s, True)) == OldDigest, "CH21-prefix boards on seeds 30001..30600 identical to the published CH22 engine (digest %s)" % Digest(lambda s: E.Board(s, True))[:8])
Check(Digest(lambda s: E.Board(s, mid2=True)) == Mid2Digest, "CH23 boards on seeds 30001..30600 match their pin via the mid2 arm (%s)" % Digest(lambda s: E.Board(s, mid2=True))[:8])
Check(Digest(lambda s: E.Board(s, mid=True)) == MidDigest, "CH24 boards on seeds 30001..30600 match their pin via the mid arm (%s)" % Digest(lambda s: E.Board(s, mid=True))[:8])
Check(Digest(lambda s: E.Board(s)) == NewDigest, "CH25 boards on seeds 30001..30600 match their pin (%s)" % Digest(lambda s: E.Board(s))[:8])
Check(E.Version == "CH25" and E.MidVersion == "CH24" and E.Mid2Version == "CH23" and E.LegacyVersion == "CH21" and E.MidLayoutCount == 13 and E.Mid2LayoutCount == 13 and len(E.LayoutNames) == 15, "version CH25, mid CH24 (frozen tuned set of thirteen), mid2 CH23 (frozen set of thirteen), legacy CH21")
# single-board codes: each prefix picks its own generator and keeps its prefix
for seed in (1, 77, 30001, 30002, 31234):
    old = E.Replay("CH21-" + str(seed) + "-0.5.9"); mid2 = E.Replay("CH23-" + str(seed) + "-0.5.9"); mid = E.Replay("CH24-" + str(seed) + "-0.5.9"); new = E.Replay("CH25-" + str(seed) + "-0.5.9")
    Check(old.Legacy and not old.Mid and not old.Mid2 and mid2.Mid2 and not mid2.Mid and not mid2.Legacy and mid.Mid and not mid.Mid2 and not mid.Legacy and not new.Legacy and not new.Mid and not new.Mid2, "seed %d: prefix picks the generator" % seed)
    Check(old.Code().startswith("CH21-") and mid2.Code().startswith("CH23-") and mid.Code().startswith("CH24-") and new.Code().startswith("CH25-"), "seed %d: Code() keeps the prefix" % seed)
Combo = lambda make: "|".join(make(s).Hash() for s in range(30001, 30021))
arms = (Combo(lambda s: E.Board(s, True)), Combo(lambda s: E.Board(s, mid2=True)), Combo(lambda s: E.Board(s, mid=True)), Combo(lambda s: E.Board(s)))
Check(len(set(arms)) == 4, "the four generators give four different board sequences over 20 seeds")
for bad in ("CH22-5-1", "CH20-5-1", "CH26-5-1", "CH5-5-1", "CH21CH23-5-1"):
    try: E.Replay(bad); Check(False, "rejects " + bad)
    except ValueError: Check(True, "rejects " + bad)
# run codes: build a run of each generation with random play, resume it, expect the same code and board
rng = random.Random(9)
for legacy, mid, mid2, prefix in ((True, False, False, "CH21R"), (False, False, True, "CH23R"), (False, True, False, "CH24R"), (False, False, False, "CH25R")):
    st = E.RunState(30001, legacy, False, mid, mid2); b = E.Attach(E.RunBoard(30001, 1, st.Satchel, legacy, False, mid, mid2), st)
    while not b.Over():
        b.Play(rng.randrange(len(E.Directions)), None, "n")
    code = st.Code(b)
    st2, b2 = E.ResumeRun(code)
    Check(code.startswith(prefix + "-") and st2.Legacy == legacy and st2.Mid == mid and st2.Mid2 == mid2 and st2.Code(b2) == code and b2.Hash() == b.Hash(), prefix + " run code resumes to the same board and keeps its prefix")
    Check(b2.Seed == E.RunBoardSeed(30001, 1), prefix + " board seed")
# marathon codes: CH23M, CH24M and CH25M all resume to their own generator
for mid, mid2, prefix in ((False, True, "CH23M"), (True, False, "CH24M"), (False, False, "CH25M")):
    st = E.RunState(30001, marathon=True, mid=mid, mid2=mid2); b = E.Attach(E.RunBoard(30001, 1, st.Satchel, marathon=True, mid=mid, mid2=mid2), st)
    b.Play(0, None, "n")
    code = st.Code(b)
    st2, b2 = E.ResumeRun(code)
    Check(code.startswith(prefix + "-") and st2.Marathon and st2.Mid == mid and st2.Mid2 == mid2 and st2.Code(b2) == code and b2.Hash() == b.Hash(), prefix + " marathon code resumes and keeps its prefix")
for bad in ("CH21M-1--", "CH22M-1--", "CH26M-1--"):
    try: E.ParseRunCode(bad); Check(False, "rejects " + bad)
    except ValueError: Check(True, "rejects " + bad)
# CH25 boards: no scatter, per-shape target counts, new-family quality pins
Fam = collections.defaultdict(list)
for seed in range(30001, 31201):
    b = E.Board(seed); Fam[b.Style.split(" ")[0]].append(b)
Check("scatter" not in Fam, "scatter fallback is gone on CH25 (0 of 1200)")
Want = {"diamonds": 15, "rings": 14, "funnel": 14, "cross": 13}
for fam in ("pinwheel", "columns", "hourglass", "towers"):
    boards = Fam[fam]
    Check(len(boards) >= 60, "%s appears often enough (%d of 1200 boards, 1 in 15 expected = 80)" % (fam, len(boards)))
    Check(all(b.Total == 12 for b in boards), fam + ": exactly 12 targets on every board")
    Check(all(0 <= x < E.Width and 0 <= y < E.Height for b in boards for (x, y) in b.Grid), fam + ": every cell inside the board")
    Check(all(b.Jackpot is not None and b.Grid.get(b.Jackpot) == "#" for b in boards), fam + ": one jackpot, on a real target")
    Check(len({b.Hash() for b in boards}) == len(boards), fam + ": boards differ from each other")
for fam, floor in (("hourglass", 5), ("towers", 7)):
    reach = []
    for b in Fam[fam]:
        hit = set()
        for a in range(len(E.Directions)):
            c = b.Clone(); c.Fire(a, None, E.PreviewSteps, False, True, "n"); hit.update(c.Struck)
        reach.append(sum(1 for t in (c for c, s in b.Grid.items() if s == "#") if t in hit))
    Check(min(reach) >= floor, "%s: an opening aim can strike at least %d of 12 targets on every board (worst %d, n=%d)" % (fam, floor, min(reach), len(reach)))
for fam, want in Want.items():
    Check(Fam[fam] and all(b.Total == want for b in Fam[fam]), "%s: exactly %d targets on every board (n=%d)" % (fam, want, len(Fam[fam])))
for fam in ("waves", "chevrons", "arches", "spiral", "stairs", "zigzag", "bowl"):
    Check(Fam[fam] and all(b.Total == 12 for b in Fam[fam]), fam + ": exactly 12 targets on every board")
for fam in ("diamonds", "rings"):
    gaps = []
    for b in Fam[fam]:
        targets = sorted(c for c, s in b.Grid.items() if s == "#")
        gaps.append(min(abs(a[0]-c[0]) + abs(a[1]-c[1]) for i, a in enumerate(targets) for c in targets[i+1:]))
    Check(min(gaps) >= 3, fam + ": closest target pair is at least 3 apart on every board (worst %d, n=%d)" % (min(gaps), len(gaps)))
print("FAILS", len(Fails)); sys.exit(1 if Fails else 0)
