import sys
import ChainDemo as C

Fails = []


def Check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        Fails.append(name)


Check("dock stays on the floor row range", all(C.DockHalf <= C.DockX(s) <= C.Width - 1 - C.DockHalf for s in range(0, 2000)))
Check("dock sweep is periodic and integer", C.DockX(0) == C.DockX(2 * C.DockSpan) and all(isinstance(C.DockX(s), int) for s in range(300)))
Check("dock moves at most one cell per step", all(abs(C.DockX(s + 1) - C.DockX(s)) <= 1 for s in range(1000)))
Check("dock visits both ends", C.DockX(C.DockSpan) == C.Width - 1 - C.DockHalf and C.DockX(0) == C.DockHalf)
caught = missed = 0
weird = 0
for run in range(1, 13):
    b = C.RunBoard(20261000 + run, 1, {"r": 1, "x": 1})
    for aim in range(0, 39, 2):
        c = b.Clone()
        base = c.Extra
        shot = c.Play(aim, None, "n")
        if shot.FloorX >= 0:
            expect = abs(shot.FloorX - C.DockX(shot.Steps + C.DockPhase * (len(c.Log) - 1))) <= C.DockHalf
            if expect != shot.Caught:
                weird += 1
            if shot.Caught:
                caught += 1
                if shot.Paid and (c.Extra - base < 1 or shot.Points < C.CatchPoints):
                    weird += 1
            else:
                missed += 1
        else:
            if shot.Caught:
                weird += 1
print("caught", caught, "missed", missed)
Check("catch rule consistent in every observed shot", weird == 0)
for seed, aim in ((1, 17), (2, 15), (5, 3), (9, 30)):
    r = C.Board(seed)
    n = 0
    while not r.Over() and n < 200:
        r.Play(aim)
        n += 1
    Check("repeat repro seed " + str(seed) + " aim " + str(aim) + " ends, paid catches within bound", r.Over() and sum(s.Paid for s in r.Log) <= C.DockCap and len(r.Log) <= C.ShotLimit + C.DockCap + 3)
r = C.Board(1)
n = 0
while not r.Over() and n < 200:
    r.Play(17)
    n += 1
Check("Board(1) aim 17 repeated: score and shots bounded", r.Score < 5000 and len(r.Log) <= C.ShotLimit + C.DockCap + 3)
Check("dock phase differs between consecutive identical shots", len({C.DockX(100 + C.DockPhase * k) for k in range(5)}) > 1)
Check("some shots caught and some missed", caught > 0 and missed > 0)
a = C.RunBoard(20261008, 1, {"r": 1, "x": 1})
b = C.RunBoard(20261008, 1, {"r": 1, "x": 1})
ra = [(a.Play(k, None, "n").Points, a.Extra, a.Hash()) for k in (5, 20, 33)]
rb = [(b.Play(k, None, "n").Points, b.Extra, b.Hash()) for k in (5, 20, 33)]
Check("shots are deterministic with the dock", ra == rb)
code = "CH14R-20261008-9.10.10-00-11x.5r/1.2.3/4.5"
try:
    C.ParseRunCode(code)
    Check("CH14 run code parses", True)
except ValueError:
    Check("CH14 run code parses", False)
try:
    C.ParseRunCode(code.replace("CH14", "CH13"))
    Check("CH13 code rejected by CH14", False)
except ValueError:
    Check("CH13 code rejected by CH14", True)
print("FAILS", len(Fails))
sys.exit(1 if Fails else 0)
