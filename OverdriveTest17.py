import sys, os, re, random, importlib.util
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec); Spec.loader.exec_module(E)
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
Check(E.OverdriveRally == 3 and E.OverdriveNeed == 3, "constants: rally 3, 3 segments")
def Fresh(seed):
    st = E.RunState(seed)
    return E.Attach(E.RunBoard(seed, 1, dict(st.Satchel)), st)
# find a seed and aim sequence with at least three shots of rally >= 3 on one board
found = None
for seed in range(1, 400):
    b = Fresh(seed); rng = random.Random(seed); log = []
    while not b.Over() and len(log) < 12:
        aim = rng.randrange(len(E.Directions))
        before = (b.Meter, b.Stock["r"], b.OverGiven)
        s = b.Play(aim, None, "n")
        log.append((aim, s.Rally, before, (b.Meter, b.Stock["r"], b.OverGiven), s.Overdrive))
    if b.OverGiven:
        found = (seed, log, b); break
Check(found is not None, "a board exists where Overdrive is earned")
if found:
    seed, log, b = found
    ok = True
    meter = 0; earned = 0
    for aim, rally, before, after, od in log:
        if rally >= E.OverdriveRally and meter < E.OverdriveNeed:
            meter += 1
        if after[0] != meter:
            ok = False
        if od:
            earned += 1
            ok = ok and after[1] == before[1] + 1 and meter == E.OverdriveNeed
        else:
            ok = ok and after[1] == before[1]
    Check(ok, "meter counts rally>=3 shots; stock grows by exactly 1 at the third")
    Check(earned == 1, "Overdrive pays once per board")
    Check(b.Meter == E.OverdriveNeed and b.OverGiven == 1, "meter caps at 3 and stays")
    # replay reproduces meter and stock
    state = E.RunState(seed)
    twin = Fresh(seed)
    for aim, *_ in log:
        twin.Play(aim, None, "n")
    Check(twin.Hash() == b.Hash() and twin.Meter == b.Meter and twin.Stock == b.Stock, "same shots replay to the same meter, stock and hash")
    code = E.RunState.Code(b.RunInfo, b)
    st2, b2 = E.ResumeRun(code)
    Check(b2.Hash() == b.Hash() and b2.Stock == b.Stock and b2.Meter == b.Meter, "run code resume reproduces Overdrive state")
    # new board starts with meter 0 and refilled satchel (no carried bonus)
    nxt = E.RunBoard(seed, 2, dict(b.RunInfo.Satchel))
    Check(nxt.Meter == 0 and nxt.OverGiven == 0, "next board starts with an empty meter")
    Check(nxt.Stock["r"] == b.RunInfo.Satchel.get("r", 0), "next board stock comes from the satchel only (earned rebound does not carry)")
    # HUD and message
    lines = E.Screen(True, 0, True).Frame(b, 20, False, None, "", False)
    text = "\n".join(lines)
    Check("Overdrive [###] +1" in text, "HUD shows full meter and the +1 earned mark")
    Check(max(len(re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", l)) for l in lines) <= 102, "HUD line fits 102 columns")
    last = [x for x in b.Log if x.Overdrive]
    Check(bool(last) and "OVERDRIVE: +1 rebound ball" in E.ShotMessage(b, last[0]), "shot message announces Overdrive")
e = Fresh(3)
Check("Overdrive [---]" in "\n".join(E.Screen(True, 0, True).Frame(e, 20, False, None, "", False)), "fresh board HUD shows empty meter")
print("FAILS " + str(len(Fails)))
sys.exit(1 if Fails else 0)
