import importlib.util, sys, random, hashlib, os, argparse

Parser = argparse.ArgumentParser()
Parser.add_argument("--engine", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "ChainDemo.py"))
Parser.add_argument("--seeds", type=int, default=300)
Parser.add_argument("--edge-seeds", type=int, default=200)
Args = Parser.parse_args()
Source = open(Args.engine, "rb").read()
print("Engine", Args.engine, "sha256", hashlib.sha256(Source).hexdigest()[:16])
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", Args.engine)
M = importlib.util.module_from_spec(Spec)
Spec.loader.exec_module(M)
print("Version", M.Version)

Bad = {}


def Fail(name, detail=None):
    Bad.setdefault(name, []).append(detail)


def Subsequence(small, big):
    it = iter(big)
    return all(any(s == b for b in it) for s in small)


def Counts(grid):
    out = {}
    for v in grid.values():
        out[v] = out.get(v, 0) + 1
    return out


def Column(grid, x):
    return [grid[(x, y)] for y in range(M.Height) if (x, y) in grid and grid[(x, y)] in M.LooseSymbols]


def Check(b, pre, shot, tag, context):
    if shot.Steps > M.StepCap:
        Fail(tag + " steps over cap", context + (shot.Steps,))
    if b.Score < 0:
        Fail(tag + " negative score", context)
    before = Counts(pre)
    after = Counts(b.Grid)
    for sym, n in after.items():
        if n > before.get(sym, 0):
            Fail(tag + " symbol count increased " + sym, context)
    broke = sum(1 for c, v in pre.items() if v == "*" and c not in b.Grid)
    lost = sum(before.values()) - sum(after.values())
    if lost != shot.Pegs + broke:
        Fail(tag + " peg accounting", context + (lost, shot.Pegs, broke))
    for c, v in pre.items():
        if v in "/\\" and b.Grid.get(c) != v:
            Fail(tag + " mirror changed or removed", context + (c,))
        if v == "*" and c in b.Grid and b.Grid[c] != "*":
            Fail(tag + " bumper changed", context + (c,))
    for c, v in b.Grid.items():
        if v in "*/\\" and pre.get(c) != v:
            Fail(tag + " fixed piece appeared or moved", context + (c,))
    for x in range(M.Width):
        if not Subsequence(Column(b.Grid, x), Column(pre, x)):
            Fail(tag + " loose symbol order in column changed", context + (x,))
    for (x, y) in b.Grid:
        if not (0 <= x < M.Width and 0 <= y < M.Height):
            Fail(tag + " piece outside board", context + (x, y))


def Fire(b, aim, kind, tag, context):
    pre = dict(b.Grid)

    def Hook(x, y=None, *rest):
        if y is None or rest:
            return
        if not (0 <= x < M.Width and 0 <= y < M.Height):
            Fail(tag + " ball out of bounds", context + (x, y))
        s = b.Grid.get((x, y))
        if s is not None and s in M.SolidSymbols:
            Fail(tag + " physics position on solid peg", context + (x, y, s))

    try:
        shot = b.Play(aim, Hook, ballKind=kind)
    except Exception as e:
        Fail(tag + " exception " + repr(e)[:50], context)
        return None
    Check(b, pre, shot, tag, context)
    return shot


def Generated(seed, tag):
    b = M.Board(seed)
    for (x, y) in b.Grid:
        if not (1 <= x <= M.Width - 2 and 4 <= y <= M.Height - 5):
            Fail(tag + " generated peg outside rows 4 to Height-5", (seed, x, y))
    b.Stock = {"r": 2, "x": 2, "s": 2}
    return b


Random = random.Random(9)
Shots = 0
Longest = 0
for seed in range(1, Args.seeds + 1):
    b = Generated(seed, "multi")
    for k in range(M.ShotLimit):
        kind = Random.choice("nnnrxs")
        if kind != "n" and b.Stock.get(kind, 0) <= 0:
            kind = "n"
        aim = Random.randrange(len(M.Directions))
        shot = Fire(b, aim, kind, "multi", (seed, k, aim, kind))
        if shot is None:
            break
        Shots += 1
        Longest = max(Longest, shot.Steps)
        if b.Won():
            break

Edge = 0
Aims = [0, 1, len(M.Directions) // 2, len(M.Directions) - 2, len(M.Directions) - 1]
for seed in range(1, Args.edge_seeds + 1):
    for kind in "rxsn":
        for aim in Aims:
            if Fire(Generated(seed, "edge"), aim, kind, "edge", (seed, aim, kind)) is not None:
                Edge += 1

Probed = 0
Random2 = random.Random(21)
for seed in range(1, Args.seeds + 1):
    b = Generated(seed, "probe")
    for k in range(10):
        kind = Random2.choice("nnnrxs")
        if kind != "n" and b.Stock.get(kind, 0) <= 0:
            kind = "n"
        if Fire(Generated(seed, "probe"), Random2.randrange(len(M.Directions)), kind, "probe", (seed, k, kind)) is not None:
            Probed += 1

print("Multi-shot games (every shot fully checked, damaged boards included):", Shots, "shots, longest", Longest, "steps (cap", M.StepCap, ")")
print("Extreme-aim launches, same checks:", Edge)
print("Fresh-board single-shot probes, same checks:", Probed)
print("Violations:", {k: (len(v), v[:2]) for k, v in Bad.items()} if Bad else "none")
print("Limits: peg accounting is aggregate (symbol counts must not rise; total loss equals popped plus broken bumpers), not per-piece identity. The column check compares symbol order only, so repeated 'o' pegs cannot prove identity or downward-only travel.")
print("Not covered: custom board files, determinism across machines, mirror/bumper/blast/floor scenario tests, real Windows.")
sys.exit(1 if Bad else 0)
