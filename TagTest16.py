import sys, os, re, importlib.util
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec); Spec.loader.exec_module(E)
Strip = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
board = E.Board(5)
for cell in list(board.Grid):
    if abs(cell[0] - 25) <= 6 and abs(cell[1] - 10) <= 3:
        del board.Grid[cell]
def Body(fx, mono=True, plain=True):
    lines = E.Screen(mono, 0, plain).Frame(board, 20, False, None, "", False, fx)
    return Strip.sub("", "\n".join(lines[3:3 + E.Height]))
def Tag(x, y):
    return {"tag": [x, y, "+100", 5]}
Check("+100" in Body(Tag(25, 10)), "free space: whole tag shown")
Check("+100" in Body(Tag(25, 10), False, False), "free space, colour on: whole tag shown")
for name, extra in (("burst on left cell", {"burst": {(24, 9): 3}}), ("burst on right cell", {"burst": {(25, 9): 2}}), ("flash", {"flash": {(25, 9): ("o", "pop")}})):
    fx = Tag(25, 10); fx.update(extra)
    text = Body(fx)
    Check("+1" not in text and "100" not in text, name + ": whole tag skipped, no partial score text")
Check("+100" in Body(dict(Tag(25, 10), burst={(30, 9): 3})), "burst outside the tag span leaves the tag shown")
fx = Tag(25, 1)
text = Body(fx)
Check("+100" not in text, "tag over the cannon row is skipped whole")
Check("+" not in "".join(Body(Tag(25, 1)).split("\n")[0]) , "cannon row has no stray tag characters")
print("FAILS", len(Fails))
sys.exit(1 if Fails else 0)
