import sys, random, os
os.environ["N"] = "0"
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ChainTest12.py")).read().split("bad = collections.Counter()")[0])
Sleeps = []
E.time.sleep = lambda t: Sleeps.append(t)

class Keys0:
    def Pressed(self):
        return False

class KeysDown:
    def Pressed(self):
        return True

def Screen(delay, reduced=False, fast=False, keys=None):
    scr = E.Screen(True, delay, True)
    scr.Show = lambda lines: None
    scr.Keys = keys
    scr.Reduced = reduced
    scr.Fast = fast
    return scr

failures = []
def Check(ok, text):
    if not ok:
        failures.append(text)

Config = {"d0": (0, False, False, False), "d15": (15, False, False, False), "d30": (30, False, False, False), "d60": (60, False, False, False), "red15": (15, True, False, False), "red30": (30, True, False, False), "red60": (60, True, False, False), "fast30": (30, False, True, False), "skip30": (30, False, False, True)}
shots = 0
withAdded = 0
maxDiff = {15: 0.0, 30: 0.0, 60: 0.0}
for run in range(31001, 31003):
    rng = random.Random(run)
    sat = {"r": 1, "x": 1, "s": 2}
    for k in (1, 2, 3):
        plain = E.RunBoard(run, k, sat)
        boards = {key: E.RunBoard(run, k, sat) for key in Config}
        while not plain.Over():
            left = E.ShotLimit + plain.Extra - len(plain.Log)
            aim, hit = Policy(plain, rng)
            kind = Kind(plain, hit, left)
            plain.Play(aim, None, kind)
            totals = {}
            for key, b in boards.items():
                delay, reduced, fast, skip = Config[key]
                scr = Screen(delay, reduced=reduced, fast=fast, keys=KeysDown() if skip else Keys0())
                del Sleeps[:]
                shot = E.Animate(scr, b, aim, kind)
                totals[key] = (sum(Sleeps), shot.Added)
                Check(b.Hash() == plain.Hash(), "hash mismatch " + key)
                Check(b.Code() == plain.Code(), "code mismatch " + key)
            shots += 1
            if totals["d30"][1] > 0:
                withAdded += 1
            Check(totals["fast30"][0] == 0 and totals["fast30"][1] == 0, "fast mode slept or added time")
            Check(totals["skip30"][0] == 0 and totals["skip30"][1] == 0, "skip slept or added time")
            Check(totals["d0"][0] == 0, "delay 0 slept")
            for d in (15, 30, 60):
                diff = totals["d%d" % d][0] - totals["red%d" % d][0]
                maxDiff[d] = max(maxDiff[d], diff)
                Check(totals["red%d" % d][1] == 0, "reduced mode added time at delay %d" % d)
                Check(diff <= E.BeatCap * d / 30 + 1e-9, "beat time over cap at delay %d" % d)
                Check(abs(diff - totals["d%d" % d][1] * d / 30) < 1e-9, "recorded added time does not match sleeps at delay %d" % d)
        if not plain.Won():
            break
print("shots", shots, "shots with added time at delay 30", withAdded, "max beat seconds by delay", {k: round(v, 3) for k, v in maxDiff.items()}, "cap at default delay", E.BeatCap)
if failures:
    print("FAILURES", len(failures), sorted(set(failures)))
    sys.exit(1)
print("all assertions passed")
