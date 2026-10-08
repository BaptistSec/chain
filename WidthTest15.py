import sys, os, re, itertools, importlib.util
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec)
Spec.loader.exec_module(E)
Strip = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
worst = 0
count = 0
bad = []
for plain, mono in ((True, True), (False, False), (False, True)):
    for run in (1, 7, E.MaxRunNumber - 1, E.MaxRunNumber):
        for r, x, s in itertools.product(range(0, 5), repeat=3):
            if r + x + s > 6:
                continue
            sat = {"r": r, "x": x, "s": s}
            for k in (1, 2, 3):
                state = E.RunState(run)
                state.K = k
                board = E.Attach(E.RunBoard(run, k, sat), state)
                state.Satchel = dict(sat)
                board.RunInfo.Satchel = dict(sat)
                scr = E.Screen(mono, 0, plain)
                for result in (False, True):
                    if result:
                        board.Log = board.Log
                    lines = scr.Frame(board, 20, False, None, "x" * 200, result)
                    for line in lines:
                        w = len(Strip.sub("", line))
                        worst = max(worst, w)
                        if w > 104:
                            bad.append((run, sat, k, result, w))
                    count += 1
for won in (False, True):
    for run in (E.MaxRunNumber,):
        for k in (1, 3):
            state = E.RunState(run); state.K = k
            board = E.Attach(E.RunBoard(run, k, {"r": 1, "x": 1, "s": 2}), state)
            board.Won = (lambda w=won: w)
            board.Over = lambda: True
            for line in E.Screen(True, 0, True).Frame(board, 20, False, None, "", True):
                w = len(Strip.sub("", line))
                worst = max(worst, w)
                if w > 104:
                    bad.append(("result", won, k, w))
state = E.RunState(E.MaxRunNumber); state.K = 1
lb = E.Attach(E.RunBoard(E.MaxRunNumber, 1, {"r": 1, "x": 1}), state)
lb.Won = lambda: False
lb.Over = lambda: True
lossLines = E.Screen(True, 0, True).Frame(lb, 20, False, None, "", True)
assert any("[N] new run 1   [R] restart run 1000000000" in l for l in lossLines), "max run loss controls"
assert E.NextRunNumber(E.MaxRunNumber) == 1 and E.NextRunNumber(5) == 6
print("frames", count, "worst visible width", worst, "over 104:", len(bad))
if bad:
    print(bad[:5]); sys.exit(1)
