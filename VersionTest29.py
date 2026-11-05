"""CH26 versioning: CH21, CH23, CH24 and CH25 codes keep resolving to their exact pinned boards through four frozen arms. CH26 codes use the same fifteen-shape tuned generator with the twin ball in the draft pool; only CH26 codes may carry twin shots or twin picks."""
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
Frozen25Digest = "96367202d727891640f7b8cb4abaa6e3fa54e83f2dae3409c5266beaca091ad3"   # CH25 fifteen-shape generator pin from VersionTest25, now a frozen arm
def Digest(make):
    d = hashlib.sha256()
    for s in range(30001, 30601):
        b = make(s); d.update((b.Hash() + "|" + str(b.Jackpot) + "|" + b.Style).encode())
    return d.hexdigest()
Check(Digest(lambda s: E.Board(s, True)) == OldDigest, "CH21-prefix boards on seeds 30001..30600 identical to the published CH22 engine (digest %s)" % Digest(lambda s: E.Board(s, True))[:8])
Check(Digest(lambda s: E.Board(s, mid2=True)) == Mid2Digest, "CH23 boards on seeds 30001..30600 match their pin via the mid2 arm (%s)" % Digest(lambda s: E.Board(s, mid2=True))[:8])
Check(Digest(lambda s: E.Board(s, mid=True)) == MidDigest, "CH24 boards on seeds 30001..30600 match their pin via the mid arm (%s)" % Digest(lambda s: E.Board(s, mid=True))[:8])
Check(Digest(lambda s: E.Board(s)) == Frozen25Digest, "CH25/CH26 boards on seeds 30001..30600 match the frozen CH25 pin - the twin ball did not touch the generator (%s)" % Digest(lambda s: E.Board(s))[:8])
Check(E.Version == "CH26" and E.MidVersion == "CH24" and E.Mid2Version == "CH23" and E.LegacyVersion == "CH21" and E.MidLayoutCount == 13 and E.Mid2LayoutCount == 13 and len(E.LayoutNames) == 15, "version CH26, mid CH24 (frozen tuned set of thirteen), mid2 CH23 (frozen set of thirteen), legacy CH21")
Check(E.RunPool == ["r", "x", "s"] and E.TwinPool == ["r", "x", "s", "t"], "pools: frozen three for old codes, four with twin for CH26")
Check(E.PoolForCode("CH26R-1-9.10.10--") == E.TwinPool and E.PoolForCode("CH26T--") == E.TwinPool and E.PoolForCode("CH26L--") == E.TwinPool and E.PoolForCode("CH26M-1--") == E.TwinPool, "PoolForCode: every CH26 arm gets the twin pool")
Check(E.PoolForCode("CH25R-1-9.10.10--") == E.RunPool and E.PoolForCode("CH25T--") == E.RunPool and E.PoolForCode("CH25L--") == E.RunPool and E.PoolForCode("CH25M-1--") == E.RunPool and E.PoolForCode("CH24R-1-9.10.10--") == E.RunPool and E.PoolForCode("CH23M-1--") == E.RunPool and E.PoolForCode("CH21R-1-9.10.10--") == E.RunPool, "PoolForCode: every frozen arm keeps pool-3")
# draft offers: pool-3 formula byte-identical for old codes, rotating 3-of-4 for CH26
oldOffers = [E.RunOffer(30001, k, E.RunPool) for k in range(1, 7)]
Check(oldOffers == [["s", "r", "x"], ["r", "x", "s"], ["x", "s", "r"], ["s", "r", "x"], ["r", "x", "s"], ["x", "s", "r"]], "pool-3 offers keep the old rotation exactly")
newOffers = [E.RunOffer(30001, k, E.TwinPool) for k in range(1, 9)]
Check(newOffers == [["x", "s", "t"], ["s", "t", "r"], ["t", "r", "x"], ["r", "x", "s"], ["x", "s", "t"], ["s", "t", "r"], ["t", "r", "x"], ["r", "x", "s"]], "CH26 offers rotate a 3-of-4 leave-one-out over the twin pool")
Check(all(len(o) == 3 for o in newOffers) and sum("t" in o for o in newOffers[:4]) == 3, "twin appears in three of every four CH26 drafts")
# single-board codes: each prefix picks its generator and keeps its prefix; CH25 and CH26 share the generator
for seed in (1, 77, 30001, 30002, 31234):
    old = E.Replay("CH21-" + str(seed) + "-0.5.9"); mid2 = E.Replay("CH23-" + str(seed) + "-0.5.9"); mid = E.Replay("CH24-" + str(seed) + "-0.5.9"); f25 = E.Replay("CH25-" + str(seed) + "-0.5.9"); new = E.Replay("CH26-" + str(seed) + "-0.5.9")
    Check(old.Legacy and not old.Mid and not old.Mid2 and mid2.Mid2 and not mid2.Mid and not mid2.Legacy and mid.Mid and not mid.Mid2 and not mid.Legacy and not f25.Legacy and not f25.Mid and not f25.Mid2 and not new.Legacy and not new.Mid and not new.Mid2, "seed %d: prefix picks the generator" % seed)
    Check(old.Code().startswith("CH21-") and mid2.Code().startswith("CH23-") and mid.Code().startswith("CH24-") and f25.Code().startswith("CH25-") and new.Code().startswith("CH26-"), "seed %d: Code() keeps the prefix" % seed)
    Check(E.BoardPrefix(old) == "CH21" and E.BoardPrefix(mid2) == "CH23" and E.BoardPrefix(mid) == "CH24" and E.BoardPrefix(f25) == "CH25" and E.BoardPrefix(new) == "CH26", "seed %d: replay label keeps the code's own version" % seed)
    Check(f25.Hash() == new.Hash() and f25.Score == new.Score, "seed %d: CH25 and CH26 boards play identically" % seed)
Check(E.ResultBlock(E.Replay("CH25-31024-10")).startswith("CHAIN CH25  board 31024"), "result block labels a CH25 replay CH25, not the current version")
Check(E.ResultBlock(E.Replay("CH26-31024-10")).startswith("CHAIN CH26  board 31024"), "result block labels a CH26 replay CH26")
Check("Code CH25-31024-10" in E.ResultBlock(E.Replay("CH25-31024-10")), "result block re-emits the old code verbatim")
Combo = lambda make: "|".join(make(s).Hash() for s in range(30001, 30021))
arms = (Combo(lambda s: E.Board(s, True)), Combo(lambda s: E.Board(s, mid2=True)), Combo(lambda s: E.Board(s, mid=True)))
Check(len(set(arms)) == 3, "the three frozen generators give three different board sequences over 20 seeds")
# twin shots: only CH26 codes parse them, every older prefix rejects them
seed, aims, legacy, mid, mid2 = E.ParseCodeFull("CH26-31024-10t")
Check(aims == [(10, "t")] and not (legacy or mid or mid2), "CH26 code parses a twin shot")
for bad in ("CH25-31024-10t", "CH24-31024-10t", "CH23-31024-10t", "CH21-31024-10t"):
    try: E.ParseCodeFull(bad); Check(False, "rejects " + bad)
    except ValueError: Check(True, "rejects " + bad)
# twins come from draft picks only: a plain board holds no twin stock, like the score ball
for bare in ("CH26-31024-10t", "CH26-31024-10s", "CH25-31024-10s"):
    try: E.Replay(bare); Check(False, "plain board stocks no " + bare.rsplit(None, 1)[-1][-1] + " in " + bare)
    except ValueError: Check(True, "plain board stocks none for " + bare)
for bad in ("CH22-5-1", "CH20-5-1", "CH27-5-1", "CH5-5-1", "CH21CH23-5-1"):
    try: E.Replay(bad); Check(False, "rejects " + bad)
    except ValueError: Check(True, "rejects " + bad)
# run codes: build a run of each generation with random play, resume it, expect the same code and board
rng = random.Random(9)
for legacy, mid, mid2, pool, prefix in ((True, False, False, E.RunPool, "CH21R"), (False, False, True, E.RunPool, "CH23R"), (False, True, False, E.RunPool, "CH24R"), (False, False, False, E.RunPool, "CH25R"), (False, False, False, E.TwinPool, "CH26R")):
    st = E.RunState(30001, legacy, False, mid, mid2, False, False, pool, prefix if prefix != E.Version + "R" else None)
    b = E.Attach(E.RunBoard(30001, 1, st.Satchel, legacy, False, mid, mid2, pool), st)
    while not b.Over():
        b.Play(rng.randrange(len(E.Directions)), None, "n")
    code = st.Code(b)
    st2, b2 = E.ResumeRun(code)
    Check(code.startswith(prefix + "-") and st2.Legacy == legacy and st2.Mid == mid and st2.Mid2 == mid2 and st2.Code(b2) == code and b2.Hash() == b.Hash(), prefix + " run code resumes to the same board and keeps its prefix")
    Check(st2.Pool == pool, prefix + " resume keeps its pool")
    Check(E.BoardPrefix(b2) == prefix[:4], prefix + " resumed run board labels " + prefix[:4])
Check(b2.Stock.keys() == {"r", "x", "s", "t"}, "CH26R board stocks all four kinds")
# a CH25R and a CH26R run of the same seed share the layout but not the stock keys
stA = E.RunState(30001, False, False, False, False, False, False, E.RunPool, "CH25R")
bA = E.Attach(E.RunBoard(30001, 1, stA.Satchel, pool=E.RunPool), stA)
stB = E.RunState(30001)
bB = E.Attach(E.RunBoard(30001, 1, stB.Satchel, pool=stB.Pool), stB)
Check(E.LayoutHash(bA.Grid) == E.LayoutHash(bB.Grid) and bA.Style == bB.Style, "CH25R and CH26R run boards share the layout")
Check(bA.Stock.keys() == {"r", "x", "s"} and bB.Stock.keys() == {"r", "x", "s", "t"}, "CH25R stocks three kinds, CH26R four")
# twin picks: accepted on CH26 arms, rejected on every frozen arm
for good in ("CH26R-30001-9.10.10-t-10/8", "CH26M-30001-t-10/8", "CH26T-t-10/8", "CH26L-t-10/8"):
    try: E.ParseRunCodeFull(good); Check(True, "accepts twin pick in " + good.split("-")[0])
    except ValueError: Check(False, "accepts twin pick in " + good.split("-")[0])
for bad in ("CH25R-30001-9.10.10-t-10/8", "CH24R-30001-9.10.10-t-10/8", "CH25M-30001-t-10/8", "CH23M-30001-t-10/8", "CH25T-t-10/8", "CH25L-t-10/8"):
    try: E.ParseRunCodeFull(bad); Check(False, "rejects twin pick in " + bad.split("-")[0])
    except ValueError: Check(True, "rejects twin pick in " + bad.split("-")[0])
# twin shot letters: accepted on CH26 arms, rejected on frozen arms
for good, bad in (("CH26T--10t", "CH25T--10t"), ("CH26L--10t", "CH25L--10t"), ("CH26M-30001--10t", "CH25M-30001--10t"), ("CH26R-30001-9.10.10--10t", "CH25R-30001-9.10.10--10t")):
    try: E.ParseRunCodeFull(good); Check(True, "accepts twin shot in " + good.split("-")[0])
    except ValueError: Check(False, "accepts twin shot in " + good.split("-")[0])
    try: E.ParseRunCodeFull(bad); Check(False, "rejects twin shot in " + bad.split("-")[0])
    except ValueError: Check(True, "rejects twin shot in " + bad.split("-")[0])
# marathon codes: CH23M, CH24M, CH25M and CH26M all resume to their own generator and keep their prefix
for mid, mid2, pool, prefix in ((False, True, E.RunPool, "CH23M"), (True, False, E.RunPool, "CH24M"), (False, False, E.RunPool, "CH25M"), (False, False, E.TwinPool, "CH26M")):
    st = E.RunState(30001, marathon=True, mid=mid, mid2=mid2, pool=pool, prefix=prefix if prefix != E.Version + "M" else None)
    b = E.Attach(E.RunBoard(30001, 1, st.Satchel, marathon=True, mid=mid, mid2=mid2, pool=pool), st)
    b.Play(0, None, "n")
    code = st.Code(b)
    st2, b2 = E.ResumeRun(code)
    Check(code.startswith(prefix + "-") and st2.Marathon and st2.Mid == mid and st2.Mid2 == mid2 and st2.Code(b2) == code and b2.Hash() == b.Hash(), prefix + " marathon code resumes and keeps its prefix")
for bad in ("CH21M-1--", "CH22M-1--", "CH27M-1--"):
    try: E.ParseRunCode(bad); Check(False, "rejects " + bad)
    except ValueError: Check(True, "rejects " + bad)
# tour and long tour arms: frozen CH25 and current CH26 both parse, resume and keep their prefix and pool
for code, long in (("CH25T--", False), ("CH26T--", False), ("CH25L--", True), ("CH26L--", True)):
    st, b = E.ResumeRun(code)
    Check(st.Code(b) == code and st.Long == long and st.Tour == (not long), code + " resumes and re-emits its prefix")
    Check(st.Pool == (E.TwinPool if code.startswith(E.Version) else E.RunPool), code + " keeps its pool")
# CH25 boards: no scatter, per-shape target counts, new-family quality pins (generator untouched by CH26)
Fam = collections.defaultdict(list)
for seed in range(30001, 31201):
    b = E.Board(seed); Fam[b.Style.split(" ")[0]].append(b)
Check("scatter" not in Fam, "scatter fallback is gone on CH25/CH26 (0 of 1200)")
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
