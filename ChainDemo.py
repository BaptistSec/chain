import argparse
import os
import shutil
import stat
import hashlib
import math
import random
import sys
import time

IsWindows = os.name == "nt"
if IsWindows:
    import msvcrt
else:
    import select
    import termios
    import tty

Version = "CH16"
PegCap = 40
PegGap = 2
Width = 50
CellCols = 2
Height = 38
CannonX = 25
ShotLimit = 8
DockHalf = 3
DockSpan = Width - 1 - 2 * DockHalf
CatchPoints = 400
DockCap = 2
DockPhase = 37
StepCap = 3600
LowerPegs = 10
LowerTop = 25
LowerRows = 8
WallDrift = 12
BlastRadius = 3
KindNames = {"n": "normal", "r": "rebound", "x": "blast", "s": "second chance"}
GravityEvery = 4
Damping = 9
Stall = 12
BounceDrift = 7
TargetCount = 12
TargetFloor = 6
GroupSize = 3
CascadeCap = 5
PreviewSteps = 70
DefaultAim = 19
LooseSymbols = "o+"
SolidSymbols = "o+#*BF"
MirrorSymbols = "/\\"
Directions = [
    (-97, 24), (-95, 31), (-93, 37), (-90, 44), (-87, 50), (-83, 56), (-79, 62),
    (-74, 67), (-69, 72), (-64, 77), (-59, 81), (-53, 85), (-47, 88), (-41, 91),
    (-34, 94), (-28, 96), (-21, 98), (-14, 99), (-7, 100), (0, 100), (7, 100),
    (14, 99), (21, 98), (28, 96), (34, 94), (41, 91), (47, 88), (53, 85),
    (59, 81), (64, 77), (69, 72), (74, 67), (79, 62), (83, 56), (87, 50),
    (90, 44), (93, 37), (95, 31), (97, 24),
]
Layouts = {}
Aimer = [None]
Stats = {"Frames": 0, "Milliseconds": 0.0}


class Rng:
    def __init__(self, seed):
        self.State = (seed * 2654435761 + 12345) % 4294967296
        for _ in range(5):
            self.Next()

    def Next(self):
        self.State = (self.State * 1664525 + 1013904223) % 4294967296
        return self.State >> 8

    def Below(self, limit):
        return self.Next() % limit


class Shot:
    def __init__(self, aim):
        self.Aim = aim
        self.Pegs = 0
        self.Targets = 0
        self.Points = 0
        self.Rally = 1
        self.Chain = 0
        self.Cascade = 0
        self.Bonus = 0
        self.Kind = "n"
        self.Mult = 1
        self.SettlePops = 0
        self.Steps = 0
        self.Caught = False
        self.Paid = False
        self.FloorX = -1


LayoutNames = ["diamonds", "waves", "chevrons", "arches", "rings"]


def DockX(step):
    p = step % (2 * DockSpan)
    return DockHalf + (p if p <= DockSpan else 2 * DockSpan - p)


def Damp(v):
    if v >= 0:
        return v * Damping // 10
    return -((-v) * Damping // 10)


def Line4(a, b):
    x, y = a
    dx = abs(b[0] - x)
    dy = abs(b[1] - y)
    sx = 1 if b[0] >= x else -1
    sy = 1 if b[1] >= y else -1
    err = dx - dy
    cells = [(x, y)]
    guard = 0
    while (x, y) != b and guard < 500:
        guard += 1
        e2 = 2 * err
        moveX = e2 > -dy
        moveY = e2 < dx
        if moveX:
            err -= dy
            x += sx
            cells.append((x, y))
        if moveY:
            err += dx
            y += sy
            cells.append((x, y))
    return cells


def Around8(x, y):
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1), (x + 1, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1))


def Path(points):
    cells = []
    for a, b in zip(points, points[1:]):
        for cell in Line4(a, b):
            if not cells or cells[-1] != cell:
                cells.append(cell)
    return cells


def LayoutLines(style, rng):
    lines = []
    if style == 0:
        for k in range(2):
            cx = 11 + 28 * k + rng.Below(5) - 2
            cy = 12 + rng.Below(12)
            h = 3 + rng.Below(4)
            w = h + 2
            lines.append(Path([(cx - w, cy), (cx, cy - h), (cx + w, cy), (cx, cy + h), (cx - w, cy)]))
    elif style == 1:
        for row in range(2):
            y = 11 + row * 11 + rng.Below(2)
            amp = 2 + rng.Below(3)
            period = 6 + rng.Below(4)
            points = []
            x = 2 + rng.Below(3)
            up = row % 2 == 0
            while x < Width - 2:
                points.append((x, y - amp if up else y + amp))
                up = not up
                x += period
            lines.append(Path(points))
    elif style == 2:
        for k in range(4):
            top = 6 + 6 * k
            inset = 3 + 4 * k
            lines.append(Path([(inset, top), (Width // 2 - 1, top + 6), (Width - 1 - inset, top)]))
    elif style == 3:
        for k in range(3):
            cx = 10 + 15 * k
            y = 24 - 2 * rng.Below(3)
            h = 9 + rng.Below(3)
            lines.append(Path([(cx - 6, y), (cx - 5, y - h + 3), (cx - 3, y - h), (cx + 3, y - h), (cx + 5, y - h + 3), (cx + 6, y)]))
    else:
        for cx, cy in ((12, 15), (Width - 13, 15)):
            w = 5 + rng.Below(2)
            h = 4 + rng.Below(2)
            lines.append(Path([(cx - w, cy - h + 2), (cx - w + 2, cy - h), (cx + w - 2, cy - h), (cx + w, cy - h + 2), (cx + w, cy + h - 2), (cx + w - 2, cy + h), (cx - w + 2, cy + h), (cx - w, cy + h - 2), (cx - w, cy - h + 2)]))
    return lines


def Credit(shot, points, counts=True):
    if counts:
        shot.Pegs += 1
    rally = 1 + min(max(shot.Pegs - 1, 0) // 2, 4)
    shot.Rally = max(shot.Rally, rally)
    shot.Points += points * rally


class Board:
    def __init__(self, seed):
        self.Seed = seed
        self.DockPaid = 0
        self.Grid = {}
        self.Bumps = {}
        self.Extra = 0
        self.Credit = 0
        self.Stock = {"r": 2, "x": 2}
        self.Streak = 0
        self.CascadeNow = 0
        self.Struck = []
        self.Live = None
        self.Style = ""
        self.Score = 0
        self.Log = []
        if isinstance(seed, str):
            if seed not in Layouts:
                raise ValueError("This code is for a board file. Add --board FILE with the same file")
            self.Grid = dict(Layouts[seed])
        else:
            self.Generate()
        self.Total = sum(1 for v in self.Grid.values() if v == "#")

    def GenerateScatter(self):
        rng = Rng(self.Seed)
        self.Place(rng, "#", TargetCount, 1)
        self.Place(rng, "B", 4, 2)
        self.Place(rng, "F", 3, 1)
        self.Place(rng, "*", 5, 1)
        self.Place(rng, "/", 2, 1)
        self.Place(rng, "\\", 2, 1)
        self.Place(rng, "o", 8, 1)

    def Generate(self):
        rng = Rng(self.Seed)
        style = rng.Below(len(LayoutNames))
        mirror = rng.Below(2) == 0 and style in (0, 4)
        lines = LayoutLines(style, rng)
        if mirror:
            both = []
            for line in lines:
                both.append(line)
                both.append([(Width - 1 - x, y) for x, y in line])
            lines = both
        loose = []
        span = sum(1 for line in lines for c in line if 1 <= c[0] <= Width - 2 and 4 <= c[1] <= Height - 5)
        gap = 2 if span <= 80 else 3
        rows = []
        for line in lines:
            cells = [c for c in line if 1 <= c[0] <= Width - 2 and 4 <= c[1] <= Height - 5]
            index = rng.Below(gap)
            taken = 0
            row = []
            rows.append(row)
            while index < len(cells):
                if len(loose) >= PegCap:
                    break
                cell = cells[index]
                if cell not in self.Grid and all(near not in self.Grid for near in Around8(cell[0], cell[1])):
                    self.Grid[cell] = "o"
                    loose.append(cell)
                    row.append(cell)
                index += gap
        if len(loose) < 20:
            self.Grid = {}
            self.GenerateScatter()
            self.Style = "scatter"
            self.FillLower(rng)
            return
        self.Style = LayoutNames[style] + (" mirrored" if mirror else "")
        loose.sort()
        need = TargetCount
        placed = []
        pool = [c for row in rows for c in row if c in loose]
        floor = TargetFloor
        while need > 0 and pool and floor >= 0:
            far = [c for c in pool if all(abs(c[0] - p[0]) + abs(c[1] - p[1]) >= floor for p in placed)]
            if not far:
                floor -= 1
                continue
            cell = far[rng.Below(len(far))]
            pool.remove(cell)
            loose.remove(cell)
            self.Grid[cell] = "#"
            placed.append(cell)
            need -= 1
        for symbol, count in (("#", need), ("B", 4), ("*", 3), ("F", 2), ("/", 2), ("\\", 2)):
            for _ in range(count):
                if not loose:
                    break
                cell = loose.pop(rng.Below(len(loose)))
                self.Grid[cell] = symbol
                if symbol == "B" and rng.Below(2):
                    for near in Around8(cell[0], cell[1]):
                        if near not in self.Grid and 1 <= near[0] <= Width - 2 and 4 <= near[1] <= Height - 5:
                            self.Grid[near] = "B"
                            break
        self.FillLower(rng)

    def FillLower(self, rng):
        placed = 0
        tries = 0
        while placed < LowerPegs and tries < 400:
            tries += 1
            x = 3 + rng.Below(Width - 6)
            y = LowerTop + rng.Below(LowerRows)
            cell = (x, y)
            if cell in self.Grid or any(near in self.Grid for near in Around8(x, y)):
                continue
            self.Grid[cell] = "o"
            placed += 1

    def Place(self, rng, symbol, count, clusterMax):
        placed = 0
        tries = 0
        while placed < count and tries < 3000:
            tries += 1
            x = 1 + rng.Below(Width - 2)
            y = 4 + rng.Below(Height - 8)
            if (x, y) in self.Grid:
                continue
            size = 1 + rng.Below(clusterMax)
            for _ in range(size):
                if placed >= count:
                    break
                if (x, y) not in self.Grid and 1 <= x <= Width - 2 and 4 <= y <= Height - 5:
                    self.Grid[(x, y)] = symbol
                    placed += 1
                d = rng.Below(4)
                x += (1, -1, 0, 0)[d]
                y += (0, 0, 1, -1)[d]

    def Clone(self):
        other = Board.__new__(Board)
        other.__dict__.update(self.__dict__)
        other.Grid = dict(self.Grid)
        other.Log = list(self.Log)
        other.Bumps = dict(self.Bumps)
        other.Stock = dict(self.Stock)
        return other

    def Solid(self, x, y):
        if x < 0 or x >= Width or y < 0:
            return 1
        symbol = self.Grid.get((x, y))
        if symbol is not None and symbol in SolidSymbols:
            return 2
        return 0

    def TargetsLeft(self):
        return max(sum(1 for s in self.Grid.values() if s == "#") - self.Credit, 0)

    def Won(self):
        return self.TargetsLeft() == 0

    def Over(self):
        return self.Won() or len(self.Log) >= ShotLimit + self.Extra

    def Remove(self, cell, points, shot, removed):
        symbol = self.Grid.pop(cell)
        removed.add(cell)
        Credit(shot, points)
        if symbol == "#":
            shot.Targets += 1

    def Hit(self, cell, shot, removed):
        symbol = self.Grid.get(cell)
        if symbol is None:
            return
        if symbol in LooseSymbols:
            self.Remove(cell, 10, shot, removed)
        elif symbol == "#":
            self.Remove(cell, 50, shot, removed)
        elif symbol == "F":
            self.Remove(cell, 25, shot, removed)
            shot.Bonus += 1
        elif symbol == "*":
            Credit(shot, 5, False)
        elif symbol == "B":
            self.Explode(cell, shot, removed)

    def Explode(self, cell, shot, removed):
        queue = [(cell, 1)]
        while queue:
            current, depth = queue.pop(0)
            if self.Grid.get(current) != "B":
                continue
            self.Remove(current, 20 * depth, shot, removed)
            shot.Chain = max(shot.Chain, depth)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    near = (current[0] + dx, current[1] + dy)
                    symbol = self.Grid.get(near)
                    if symbol is None or near == current:
                        continue
                    if symbol == "B":
                        queue.append((near, depth + 1))
                    elif symbol in LooseSymbols:
                        self.Remove(near, 10 * depth, shot, removed)
                    elif symbol == "#":
                        self.Remove(near, 50 * depth, shot, removed)

    def Gravity(self, vacated, hook=None):
        vacated = set(vacated)
        fallen = set()
        changed = True
        while changed:
            changed = False
            moved = set()
            for x in sorted({c[0] for c in vacated}):
                for y in range(Height - 2, -1, -1):
                    symbol = self.Grid.get((x, y))
                    if symbol is None or symbol not in LooseSymbols:
                        continue
                    below = (x, y + 1)
                    if below in self.Grid or below not in vacated:
                        continue
                    del self.Grid[(x, y)]
                    self.Grid[below] = symbol
                    vacated.discard(below)
                    vacated.add((x, y))
                    fallen.discard((x, y))
                    fallen.add(below)
                    moved.add(below)
                    changed = True
            if hook and moved:
                hook(None, None, {c: self.Grid[c] for c in moved}, "fall")
        return fallen

    def FindGroups(self, fallen):
        popped = set()
        seen = set()
        for start in sorted(fallen):
            symbol = self.Grid.get(start)
            if start in seen or symbol is None or symbol not in LooseSymbols:
                continue
            group = [start]
            seen.add(start)
            index = 0
            while index < len(group):
                cx, cy = group[index]
                index += 1
                for near in Around8(cx, cy):
                    if near not in seen and self.Grid.get(near) == symbol:
                        seen.add(near)
                        group.append(near)
            if len(group) >= GroupSize:
                popped.update(group)
                for cx, cy in group:
                    for near in Around8(cx, cy):
                        if self.Grid.get(near) == "#":
                            popped.add(near)
        return popped

    def Settle(self, removed, shot, hook):
        vacated = set(removed)
        for cascade in range(1, CascadeCap + 1):
            self.CascadeNow = cascade
            fallen = self.Gravity(vacated, hook)
            popped = self.FindGroups(fallen)
            if not popped:
                break
            info = {c: self.Grid[c] for c in popped}
            for cell in sorted(popped):
                symbol = self.Grid.pop(cell)
                shot.SettlePops += 1
                if symbol == "#":
                    shot.Targets += 1
                    Credit(shot, 50 * cascade)
                else:
                    Credit(shot, 10 * cascade)
            shot.Cascade = cascade
            vacated = set(popped)
            if hook:
                hook(None, None, info, "pop")

    def Fire(self, aim, hook=None, maxSteps=StepCap, settle=True, stopAtHit=False, ballKind="n"):
        vx, vy = Directions[aim]
        x, y = CannonX, 0
        ax = ay = 0
        m = max(abs(vx), abs(vy))
        shot = Shot(aim)
        self.Live = shot
        shot.Kind = ballKind
        removed = set()
        uses = {}
        rebound = ballKind == "r"
        while shot.Steps < maxSteps:
            shot.Steps += 1
            if shot.Steps % GravityEvery == 0:
                vy += 1
                m = max(abs(vx), abs(vy))
            pace = max(100, m)
            ax += abs(vx)
            ay += abs(vy)
            sx = sy = 0
            if ax >= pace:
                ax -= pace
                sx = 1 if vx > 0 else -1
            if ay >= pace:
                ay -= pace
                sy = 1 if vy > 0 else -1
            if sx == 0 and sy == 0:
                continue
            if sy > 0 and y + sy >= Height:
                if rebound:
                    rebound = False
                    vy = Damp(-vy)
                    vx = Damp(vx)
                    m = max(abs(vx), abs(vy))
                    ay = 0
                    continue
                shot.FloorX = x
                shot.Caught = abs(x - DockX(shot.Steps + DockPhase * len(self.Log))) <= DockHalf
                break
            flipX = flipY = False
            cells = []
            if sx:
                kind = self.Solid(x + sx, y)
                if kind:
                    flipX = True
                    if kind == 1:
                        vy += WallDrift
                        m = max(abs(vx), abs(vy))
                    if kind == 2:
                        cells.append((x + sx, y))
            if sy:
                kind = self.Solid(x, y + sy)
                if kind:
                    flipY = True
                    if kind == 2:
                        cells.append((x, y + sy))
            if sx and sy and not flipX and not flipY:
                kind = self.Solid(x + sx, y + sy)
                if kind:
                    if abs(vy) >= abs(vx):
                        flipY = True
                    else:
                        flipX = True
                    if kind == 2:
                        cells.append((x + sx, y + sy))
            if flipX:
                vx = -vx
            if flipY:
                vy = -vy
            if flipX or flipY:
                vx = Damp(vx)
                vy = Damp(vy)
                m = max(abs(vx), abs(vy))
            if not flipX:
                x += sx
            if not flipY:
                y += sy
            contact = bool(cells)
            self.Struck = list(cells)
            if ballKind == "x" and cells:
                first = cells[0]
                for dx in range(-BlastRadius, BlastRadius + 1):
                    for dy in range(-BlastRadius, BlastRadius + 1):
                        near = (first[0] + dx, first[1] + dy)
                        symbol = self.Grid.get(near)
                        if symbol is None or symbol in "*/\\":
                            continue
                        if symbol == "B":
                            self.Explode(near, shot, removed)
                        else:
                            self.Hit(near, shot, removed)
                ballKind = "n"
            for cell in cells:
                if self.Grid.get(cell) == "*":
                    self.Bumps[cell] = self.Bumps.get(cell, 0) + 1
                    vy += BounceDrift
                    if self.Bumps[cell] >= 3:
                        del self.Grid[cell]
                        removed.add(cell)
                        continue
                self.Hit(cell, shot, removed)
            if stopAtHit and contact:
                break
            symbol = self.Grid.get((x, y))
            if symbol is not None and symbol in MirrorSymbols and uses.get((x, y), 0) < 2:
                uses[(x, y)] = uses.get((x, y), 0) + 1
                vx, vy = (-vy, -vx) if symbol == "/" else (vy, vx)
                vx = Damp(vx)
                vy = Damp(vy)
                vy += BounceDrift
                ax = ay = 0
                m = max(abs(vx), abs(vy))
            shot.Speed = m
            if hook:
                hook(x, y)
        if settle:
            self.Settle(removed, shot, hook)
        return shot

    def Play(self, aim, hook=None, ballKind="n"):
        if ballKind != "n":
            if self.Stock.get(ballKind, 0) <= 0:
                raise ValueError("No " + KindNames[ballKind] + " balls left")
            self.Stock[ballKind] -= 1
        shot = self.Fire(aim, hook, ballKind=ballKind)
        shot.Refund = 0
        if shot.Kind == "s" and shot.Targets <= 1:
            shot.Bonus += 1
            shot.Refund = 1
        if shot.Caught and self.DockPaid < DockCap:
            self.DockPaid += 1
            shot.Paid = True
            shot.Bonus += 1
            shot.Points += CatchPoints
        self.Extra += shot.Bonus
        if shot.Targets:
            self.Streak += 1
        else:
            self.Streak = 0
        shot.Mult = max(1, min(self.Streak, 4))
        shot.Points *= shot.Mult
        self.Score += shot.Points
        self.Log.append(shot)
        return shot

    def Trace(self, aim, ballKind="n"):
        path = []
        clone = self.Clone()
        clone.Fire(aim, lambda x, y, *rest: path.append((x, y)) if x is not None else None, PreviewSteps, False, True, ballKind)
        return path

    def Hash(self):
        data = repr(sorted(self.Grid.items())) + repr(sorted(self.Bumps.items())) + repr(sorted(self.Stock.items())) + str(self.Extra) + "," + str(self.Credit) + "," + str(self.Streak) + "," + str(self.Score)
        return hashlib.sha256(data.encode()).hexdigest()[:8]

    def Code(self):
        return Version + "-" + str(self.Seed) + "-" + ".".join(str(s.Aim) + ("" if s.Kind == "n" else s.Kind) for s in self.Log)

    def BiggestChain(self):
        return max([s.Chain for s in self.Log] + [0])

    def SettlePopTotal(self):
        return sum(s.SettlePops for s in self.Log)


def BotAim(board):
    best = None
    for kind in "nrx":
        if kind != "n" and board.Stock.get(kind, 0) <= 0:
            continue
        for k in range(len(Directions)):
            shot = board.Clone().Fire(k, ballKind=kind)
            key = (shot.Targets * 1000 + shot.Points - (150 if kind != "n" else 0), -k, kind)
            if best is None or key > best[0]:
                best = (key, k, kind)
    return best[1], best[2]


def LoadAimer(path):
    import runpy
    names = runpy.run_path(path)
    if "ChooseAim" not in names:
        raise ValueError("The script needs a function  def ChooseAim(board):  that returns an aim number")
    return names["ChooseAim"]


def ScriptAim(aimer, board):
    aim = aimer(board)
    if not isinstance(aim, int) or isinstance(aim, bool) or not 0 <= aim < len(Directions):
        raise ValueError("ChooseAim must return a whole number from 0 to " + str(len(Directions) - 1) + ", it returned " + repr(aim))
    return aim


def BotPar(seed):
    board = Board(seed)
    while not board.Over():
        aim, kind = BotAim(board)
        board.Play(aim, None, kind)
    return len(board.Log), board.Won(), board.Total - board.TargetsLeft()


def LayoutHash(grid):
    return "f" + hashlib.sha256(repr(sorted(grid.items())).encode()).hexdigest()[:8]


def LoadBoardFile(path):
    grid = {}
    with open(path) as handle:
        rows = handle.read().splitlines()
    if len(rows) > Height:
        raise ValueError("Board file has more than " + str(Height) + " lines")
    for y, row in enumerate(rows):
        row = row.rstrip("\r")
        if len(row) > Width:
            raise ValueError("Line " + str(y + 1) + " is longer than " + str(Width) + " characters")
        for x, char in enumerate(row):
            if char in SolidSymbols or char in MirrorSymbols:
                if y < 3:
                    raise ValueError("Lines 1 to 3 are the cannon zone and must hold no pegs")
                grid[(x, y)] = char
    if not any(v == "#" for v in grid.values()):
        raise ValueError("Board file needs at least one # target")
    key = LayoutHash(grid)
    Layouts[key] = grid
    return key


def ExportBoard(seed, path):
    board = Board(seed)
    rows = []
    for y in range(Height):
        rows.append("".join(board.Grid.get((x, y), " ") for x in range(Width)).rstrip())
    with open(path, "x") as handle:
        handle.write("\n".join(rows) + "\n")


def ParseCode(code):
    parts = code.strip().split("-")
    if len(parts) not in (2, 3) or parts[0] != Version:
        raise ValueError("Unknown code version or wrong number of parts")
    if parts[1].startswith("f") and len(parts[1]) == 9:
        seed = parts[1]
    else:
        seed = int(parts[1])
        if seed < 0:
            raise ValueError("Seed cannot be negative")
    aims = []
    if len(parts) > 2 and parts[2]:
        for p in parts[2].split("."):
            kind = "n"
            if p and p[-1] in "rxs":
                kind = p[-1]
                p = p[:-1]
            aim = int(p)
            if aim < 0 or aim >= len(Directions):
                raise ValueError("Bad aim in code")
            aims.append((aim, kind))
    return seed, aims


def Replay(code):
    seed, aims = ParseCode(code)
    board = Board(seed)
    for aim, kind in aims:
        if board.Over():
            break
        board.Play(aim, None, kind)
    return board


def ResultBlock(board):
    total = board.Total
    cleared = total - board.TargetsLeft()
    lines = ["CHAIN " + Version + "  board " + str(board.Seed)]
    if board.Won():
        lines.append("Cleared all " + str(total) + " targets in " + str(len(board.Log)) + " shots")
    else:
        lines.append("Cleared " + str(cleared) + " of " + str(total) + " targets in " + str(len(board.Log)) + " shots")
    lines.append("Score " + str(board.Score) + "   biggest chain " + str(board.BiggestChain()) + "   settle pops " + str(board.SettlePopTotal()))
    for number, shot in enumerate(board.Log, 1):
        lines.append("Shot " + str(number) + ": aim " + str(shot.Aim + 1) + ("" if shot.Kind == "n" else " " + KindNames[shot.Kind]) + "  pegs " + str(shot.Pegs) + "  chain " + str(shot.Chain) + "  settle " + str(shot.SettlePops))
    shots, cleared, count = BotPar(board.Seed)
    if cleared:
        lines.append("Bot par " + str(shots) + " shots (a bot that tries all " + str(len(Directions)) + " aims each shot cleared this board in " + str(shots) + ")")
    else:
        lines.append("Bot par: the bot cleared " + str(count) + " of " + str(board.Total) + " targets in " + str(shots) + " shots")
    lines.append("Code " + board.Code())
    lines.append("Check " + board.Hash())
    if Stats["Frames"]:
        lines.append("Screen refresh average " + format(Stats["Milliseconds"] / Stats["Frames"], ".2f") + " ms over " + str(Stats["Frames"]) + " frames")
    return "\n".join(lines)


def AimDegrees(aim):
    vx, vy = Directions[aim]
    return round(math.degrees(math.atan2(vx, vy)))


Escape = "\x1b"
KeyPattern = __import__("re").compile(r"\[(?![#o+*\-\u2591\u2593\u25cf\u25c9 ]*\])[A-Za-z0-9<>/ +]{1,10}\]")
Strip = __import__("re").compile(r"\x1b\[[0-9;?]*[A-Za-z]")
Reset = Escape + "[0m"
Colours = {
    "o": "38;5;45",
    "+": "38;5;171",
    "#": "1;38;5;220",
    "*": "38;5;78",
    "B": "1;38;5;203",
    "F": "1;38;5;120",
    "/": "38;5;250",
    "\\": "38;5;250",
    "@": "1;38;5;231",
    ".": "38;5;39",
    "V": "1;38;5;231",
    "fall": "1;30;106",
    "pop": "1;97;41",
    "title": "1;97;44",
    "key": "1;30;43",
    "dock": "1;38;5;214",
    "dockhit": "1;30;102",
    "dim": "2",
    "good": "1;32",
}
TrailColours = ["38;5;252", "38;5;248", "38;5;245", "38;5;242", "38;5;240", "38;5;238"]
BurstGlyphs = {3: ("*", "1;38;5;226"), 2: ("+", "38;5;208"), 1: (".", "38;5;124")}
UnicodeGlyphs = {"o": "\u25cf", "+": "\u25c6", "#": "\u2593", "*": "\u25c9", "B": "\u00a4", "F": "\u2665", "/": "\u2571", "\\": "\u2572", "@": "\u25cf", ".": "\u00b7", ":": "\u2022"}
BumperGlyphs = ["\u25c9", "\u25ce", "\u25cb"]
UnicodeWide = {"\u25cf": "\u25cf\u25cf", "\u25c6": "\u25e2\u25e3", "\u2593": "\u2593\u2593", "\u25c9": "\u25c9\u25c9", "\u25ce": "\u25ce\u25ce", "\u25cb": "\u25cb\u25cb", "\u00a4": "\u00a4\u00a4", "\u2665": "\u2665\u2665", "\u2571": "\u2571\u2571", "\u2572": "\u2572\u2572", "\u00b7": "\u00b7\u00b7", "\u2022": "\u2022\u2022"}
PlainWide = {"o": "()", "+": "<>", "#": "[]", "@": "()"}


def EnableAnsi():
    if IsWindows:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel.SetConsoleMode(handle, mode.value | 0x0004))
    return True


class Keyboard:
    def __enter__(self):
        if not IsWindows:
            self.Saved = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, kind, value, trace):
        if not IsWindows:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.Saved)

    def Read(self):
        if IsWindows:
            char = msvcrt.getwch()
            if char in ("\x00", "\xe0"):
                code = msvcrt.getwch()
                return {"K": "left", "M": "right", "H": "up", "P": "down"}.get(code, "")
            if char == "\r":
                return "enter"
            if char == "\x1b":
                return "esc"
            return char.lower()
        descriptor = sys.stdin.fileno()
        char = os.read(descriptor, 1).decode("utf-8", "ignore")
        if char == "\x1b":
            ready, _, _ = select.select([descriptor], [], [], 0.05)
            if not ready:
                return "esc"
            rest = os.read(descriptor, 2).decode("utf-8", "ignore")
            return {"[D": "left", "[C": "right", "[A": "up", "[B": "down"}.get(rest, "")
        if char == "\n":
            return "enter"
        return char.lower()

    def Pressed(self):
        if IsWindows:
            hit = False
            while msvcrt.kbhit():
                msvcrt.getwch()
                hit = True
            return hit
        ready, _, _ = select.select([sys.stdin.fileno()], [], [], 0)
        if ready:
            os.read(sys.stdin.fileno(), 1024)
            return True
        return False

    def Wait(self):
        self.Read()


TitleArt = [
    "  ____ _   _    _    ___ _   _ ",
    " / ___| | | |  / \\  |_ _| \\ | |",
    "| |   | |_| | / _ \\  | ||  \\| |",
    "| |___|  _  |/ ___ \\ | || |\\  |",
    " \\____|_| |_/_/   \\_\\___|_| \\_|",
]
Premise = [
    "The old relay grid is dark. Each board is a dead sector.",
    "You are the last keeper. Fire a charge into the pegs,",
    "light the nodes, and pass the signal along the chain.",
    "Fill the credit bar on all three sectors to bring the grid back.",
]
Help = [
    "[<] [>]  aim          [Space]  fire         [P]  preview",
    "[1] to [4]  choose the ball    [F]  fast        [Q]  quit",
    "Gravity pulls the charge down. Pegs, walls, mirrors and the floor cost it speed,",
    "so a shot has a short life. Spend it where it counts.",
    "Clear nodes in one shot to build a rally. Credits open the next sector.",
    "The gold line on the floor is the dock. It sweeps side to side. Land the charge in it",
    "for a free shot and +400, but only the first 2 catches on each board pay.",
]


def BestPath():
    return os.environ.get("CHAIN_BEST_FILE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "ChainBest.txt")


BestLimit = 32


def ReadBest(path):
    try:
        info = os.lstat(path)
    except OSError:
        return 0, True
    if not stat.S_ISREG(info.st_mode):
        return 0, False
    try:
        with open(path, "rb") as handle:
            raw = handle.read(BestLimit + 1)
    except OSError:
        return 0, True
    if len(raw) > BestLimit:
        return 0, True
    try:
        text = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        return 0, True
    if not text.isdigit() or len(text) > 12:
        return 0, True
    return int(text), True


def WriteBest(path, total):
    folder = os.path.dirname(path) or "."
    temp = os.path.join(folder, ".chainbest-" + os.urandom(8).hex() + ".tmp")
    created = False
    try:
        if os.path.lexists(path) and not stat.S_ISREG(os.lstat(path).st_mode):
            return False
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        created = True
        with os.fdopen(descriptor, "w") as handle:
            handle.write(str(total) + "\n")
        os.replace(temp, path)
        return True
    except OSError:
        if created:
            try:
                os.unlink(temp)
            except OSError:
                pass
        return False


def RecordBest(total):
    path = BestPath()
    previous, writable = ReadBest(path)
    best = max(previous, total)
    isNew = total > previous
    saved = False
    if isNew and writable:
        saved = WriteBest(path, total)
    return best, isNew, saved


def BestLines(best, isNew, saved):
    where = "ChainBest.txt next to the game" if not os.environ.get("CHAIN_BEST_FILE") else "the file named by CHAIN_BEST_FILE"
    lines = [" Local best across completed runs: " + str(best) + (" (new)" if isNew else "")]
    if isNew and saved:
        lines.append(" Saved to " + where)
    elif isNew:
        lines.append(" Not saved: the best file could not be written (shown on this screen only)")
    return lines


def DailyRun():
    today = time.localtime()
    return today.tm_year * 10000 + today.tm_mon * 100 + today.tm_mday


def DailyLabel():
    return str(DailyRun())


def TitleLines(screen, step, page):
    lines = [""] * 3
    for row in TitleArt:
        lines.append(" " * 24 + row)
    lines += ["", " " * 24 + "a terminal game of falling charges", ""]
    if page == "help":
        body = Help
    else:
        body = Premise[:step]
    for row in body:
        lines.append(" " * 14 + row)
    lines.append("")
    if page == "help":
        lines.append(" " * 14 + "[any key] back")
    elif step >= len(Premise):
        lines.append(" " * 14 + "[Enter] new run    [D] daily run (" + DailyLabel() + ")    [H] how to play    [Q] quit")
        lines.append(" " * 14 + "Same local date, same starting boards. Share your run code to compare;")
        lines.append(" " * 14 + "there is no online leaderboard.")
        lines.append(" " * 14 + "Continue a saved run:  --resume CODE")
    else:
        lines.append(" " * 14 + "[Enter] skip")
    return lines


def TitleScreen(screen, keys):
    page = "title"
    step = len(Premise) if (screen.Reduced or screen.Mono or screen.Delay == 0) else 0
    while True:
        screen.Show(TitleLines(screen, step, page))
        if page == "title" and step < len(Premise):
            time.sleep(0.45)
            if keys.Pressed():
                step = len(Premise)
            else:
                step += 1
            continue
        key = keys.Read()
        if page == "help":
            page = "title"
        elif key in ("enter", "return", " ", "space"):
            return random.SystemRandom().randint(1, MaxRunNumber)
        elif key == "d":
            return DailyRun()
        elif key == "h":
            page = "help"
        elif key in ("q", "esc"):
            return None


def NextRunNumber(run):
    return run + 1 if run < MaxRunNumber else 1


def ScoreMarkWanted(screen, points):
    return points >= LargeShotPoints and not screen.LastSkipped and not screen.Reduced and not screen.Fast and screen.Delay > 0 and not screen.Mono and not screen.Watching


class Screen:
    def __init__(self, mono, delay, plain=False):
        self.Mono = mono
        self.Reduced = False
        self.Delay = delay
        self.Fast = False
        self.Watching = False
        self.Plain = plain
        self.Keys = None
        self.ScoreMark = False
        self.LastSkipped = False
        self.Kind = "n"

    def Glyph(self, symbol, hits=0):
        if self.Plain:
            return symbol
        if symbol == "*":
            return BumperGlyphs[min(hits, 2)]
        return UnicodeGlyphs.get(symbol, symbol)

    def Wide(self, glyph, ball=False):
        if ball and not self.Plain:
            return "\u25d6\u25d7"
        table = PlainWide if self.Plain else UnicodeWide
        return table.get(glyph, glyph * CellCols)

    def Paint(self, key, text, tail=""):
        if self.Mono:
            return text
        code = Colours.get(key)
        if code is None:
            return text
        if key == "key":
            return Escape + "[" + code + "m" + text + Escape + "[22;39;49m" + tail
        if key in ("title", "fall", "pop", "dockhit"):
            return Escape + "[" + code + "m" + text + Reset + tail
        return Escape + "[" + code + "m" + text + Escape + "[22;39m" + tail

    def Background(self, y):
        if self.Mono:
            return ""
        return Escape + "[48;5;" + str(235 - min(3, y * 4 // Height)) + "m"

    def Bar(self, done, total, symbol):
        width = min(total, 20)
        filled = 0 if total == 0 else (done * width + total - 1) // total
        full = "#" if self.Plain else {"o": "\u25cf", "#": "\u2593"}.get(symbol, symbol)
        empty = "-" if self.Plain else "\u2591"
        return "[" + self.Paint(symbol, full * filled) + self.Paint("dim", empty * (width - filled)) + "]"

    def Cannon(self, aim):
        degrees = AimDegrees(aim)
        if abs(degrees) < 10:
            return "v"
        if abs(degrees) < 45:
            return "/" if degrees < 0 else "\\"
        return "<" if degrees < 0 else ">"

    def Frame(self, board, aim, preview, ball=None, message="", showResult=False, fx=None):
        fx = fx or {}
        flash = fx.get("flash") or {}
        burst = fx.get("burst") or {}
        trail = fx.get("trail") or []
        shake = " " if fx.get("shake", 0) % 2 else ""
        dots = set()
        if preview and ball is None and not board.Over():
            dots = set(board.Trace(aim, self.Kind))
        total = ShotLimit + board.Extra
        left = total - len(board.Log)
        quota = getattr(board, "Quota", board.Total)
        done = min(max(quota - board.TargetsLeft(), 0), quota)
        title = " CHAIN  board " + str(board.Seed) + ("  (" + board.Style + ")" if board.Style else "") + "  " + Version + " "
        lines = [self.Paint("title", title.ljust(Width * CellCols + 2))]
        def Status(extra):
            text = " Shots " + self.Bar(left, total, "o")
            bar = self.Bar(done, quota, "#")
            if message == "1 credit to clear" and not self.Mono and not self.Watching:
                bar = Escape + "[1;38;5;141m" + Strip.sub("", bar) + Reset
            text += "  Credits " + str(done) + "/" + str(quota) + " " + bar
            scoreText = "Score " + str(board.Score)
            if self.ScoreMark and not self.Mono and not self.Watching:
                scoreText = Escape + "[1;97m" + scoreText + Escape + "[22;39m"
            text += "  " + scoreText + "  Streak x" + str(max(1, min(board.Streak, 4)))
            if extra:
                text += "  Best chain " + str(board.BiggestChain()) + "  Settle pops " + str(board.SettlePopTotal())
            return text
        saved = self.Mono
        self.Mono = True
        longest = len(Status(True))
        self.Mono = saved
        status = Status(longest <= Width * CellCols)
        lines.append(status)
        corners = ("+", "+", "+", "+", "-", "|") if self.Plain else ("\u250c", "\u2510", "\u2514", "\u2518", "\u2500", "\u2502")
        lines.append(shake + corners[0] + corners[4] * (Width * CellCols) + corners[1])
        cannon = self.Cannon(aim)
        trailIndex = {c: n for n, c in enumerate(reversed(trail))}
        for y in range(Height):
            background = self.Background(y)
            tokens = []
            for x in range(Width):
                cell = (x, y)
                symbol = board.Grid.get(cell)
                if ball is not None and ball == cell:
                    tokens.append((Colours["@"], self.Wide(self.Glyph("@"), True)))
                elif cell in flash:
                    key = "pop" if flash[cell][1] == "pop" else "fall"
                    tokens.append((Colours[key], self.Wide(self.Glyph(flash[cell][0]))))
                elif cell in burst:
                    glyph, code = BurstGlyphs[burst[cell]]
                    tokens.append((code, glyph * CellCols))
                elif symbol is not None:
                    tokens.append((Colours[symbol], self.Wide(self.Glyph(symbol, board.Bumps.get(cell, 0)))))
                elif y == 0 and abs(x - CannonX) <= 1:
                    tokens.append((Colours["V"], ("[ ", cannon + " ", " ]")[x - CannonX + 1]))
                elif cell in trailIndex:
                    tokens.append((TrailColours[min(trailIndex[cell], len(TrailColours) - 1)], self.Wide(self.Glyph(":"))))
                elif cell in dots:
                    tokens.append((Colours["."], self.Wide(self.Glyph("."))))
                else:
                    tokens.append((None, " " * CellCols))
            if self.Mono:
                row = "".join(char for _, char in tokens)
            else:
                row = ""
                current = None
                for code, char in tokens:
                    if code != current:
                        if current is not None:
                            row += (Reset + background) if current in (Colours["pop"], Colours["fall"]) else Escape + "[22;39m"
                        if code is not None:
                            row += Escape + "[" + code + "m"
                        current = code
                    row += char
                if current is not None:
                    row += (Reset + background) if current in (Colours["pop"], Colours["fall"]) else Escape + "[22;39m"
            row = shake + corners[5] + background + row + ("" if self.Mono else Escape + "[49m") + corners[5]
            lines.append(row)
        dockAt = fx.get("dock", DockX(DockPhase * len(board.Log)))
        left = max(0, dockAt - DockHalf)
        right = min(Width - 1, dockAt + DockHalf)
        glyph = "=" if self.Plain else "\u2550"
        segment = glyph * ((right - left + 1) * CellCols)
        segment = self.Paint("dockhit" if fx.get("dockhit") else "dock", segment)
        lines.append(shake + corners[2] + corners[4] * (left * CellCols) + segment + corners[4] * ((Width - 1 - right) * CellCols) + corners[3])
        legend = " " + self.Paint("o", self.Glyph("o")) + " " + self.Paint("+", self.Glyph("+")) + " loose   " + self.Paint("#", self.Glyph("#")) + " target   "
        legend += self.Paint("*", self.Glyph("*")) + (" bumper (3 hits)   " if self.Plain else " bumper (3 hits)   ") + self.Paint("B", self.Glyph("B")) + " bomb   "
        legend += self.Paint("dock", glyph if False else ("=" if self.Plain else "\u2550")) + " dock (catch)   " + self.Paint("F", self.Glyph("F")) + " free shot   " + self.Paint("/", self.Glyph("/")) + " " + self.Paint("\\", self.Glyph("\\")) + " mirror"
        lines.append(legend)
        if self.Watching or showResult:
            lines.append(" After each shot, loose pegs fall. 3+ touching pegs of one kind pop, with any target beside them.")
        else:
            options = [("n", "[1] normal"), ("r", "[2] rebound x" + str(board.Stock["r"])), ("x", "[3] blast x" + str(board.Stock["x"])), ("s", "[4] second chance x" + str(board.Stock.get("s", 0)))]
            parts = [self.Paint("good", text) if kind == self.Kind else text for kind, text in options]
            lines.append(" Ball  " + "  ".join(parts))
        info = getattr(board, "RunInfo", None)
        if info is not None and not self.Watching:
            nxt = "  ".join(KindNames[c] + " x" + str(info.Satchel.get(c, 0)) for c in RunPool if info.Satchel.get(c, 0))
            lines.append(" Board " + str(info.K) + "/" + str(len(RunQuotas)) + "  Refunds " + str(sum(x.Refund for x in board.Log)) + "  Dock " + ("used up" if board.DockPaid >= DockCap else str(DockCap - board.DockPaid) + " left") + "  Bonus shots " + str(board.Extra - sum(x.Refund for x in board.Log)) + "  Next: " + nxt)
        if self.Watching:
            controls = " WATCH MODE   " + ("board cleared" if board.Won() else "out of shots" if board.Over() else "[any key] at the end closes it") + "   [Ctrl+C] stops"
        elif showResult:
            info = getattr(board, "RunInfo", None)
            if info is None:
                controls = " " + ("YOU WIN" if board.Won() else "OUT OF SHOTS") + "   [R] same board   [N] next board   [Q] quit and show code"
            elif not board.Won():
                controls = " OUT OF SHOTS   [N] new run " + str(NextRunNumber(info.Run)) + "   [R] restart run " + str(info.Run) + "   [Q] quit and show code"
            elif info.K >= len(RunQuotas):
                controls = " BOARD CLEARED, LAST BOARD   [N] finish the run   [R] restart run " + str(info.Run) + "   [Q] quit and show code"
            else:
                controls = " BOARD CLEARED   [N] pick an upgrade   [R] restart run " + str(info.Run) + "   [Q] quit and show code"
        else:
            controls = " [<][>] aim " + str(aim + 1) + "/" + str(len(Directions)) + " " + str(AimDegrees(aim)) + "deg  [Space] fire  [P] preview " + ("on" if preview else "off") + "  [F] fast " + ("on" if self.Fast else "off") + ("  [R] restart  [N] next  [Q] quit" if getattr(board, "RunInfo", None) is not None else "  [R] redo  [N] next  [Q] quit")
        lines.append(controls)
        text = message[:Width * CellCols]
        if not self.Mono and not self.Watching:
            if text.startswith("RALLY x"):
                bold = "1;" if text[7:8] in ("4", "5") else ""
                text = Escape + "[" + bold + "38;5;208m" + text + Reset
            elif text == "1 credit to clear":
                text = Escape + "[1;38;5;141m" + text + Reset
        lines.append(" " + text)
        return lines

    def Keys_(self, line):
        if self.Mono or "[" not in line:
            return line
        return KeyPattern.sub(lambda m: self.Paint("key", m.group(0)), line)

    def Show(self, lines):
        start = time.perf_counter()
        lines = [self.Keys_(line) for line in lines]
        sys.stdout.write(Escape + "[H" + "".join(line + Escape + "[K\n" for line in lines) + Escape + "[J")
        sys.stdout.flush()
        Stats["Milliseconds"] += (time.perf_counter() - start) * 1000
        Stats["Frames"] += 1


def ShotMessage(board, shot):
    text = "Shot " + str(len(board.Log)) + ": +" + str(shot.Points)
    if shot.Rally > 1:
        text += " (rally x" + str(shot.Rally) + ")"
    if shot.Mult > 1:
        text += " (streak x" + str(shot.Mult) + ")"
    if shot.Paid:
        text += ", caught in the dock +" + str(CatchPoints)
    elif shot.Caught:
        text += ", dock used up, no bonus"
    if shot.Bonus:
        text += ", +" + str(shot.Bonus) + " free shot"
    if shot.Kind != "n":
        text += ", " + KindNames[shot.Kind] + " ball"
    if shot.Kind == "s":
        if shot.Refund:
            text += " | Second Chance: " + str(shot.Targets) + (" target" if shot.Targets == 1 else " targets") + " cleared, shot refunded"
        else:
            text += " | Second Chance: 2+ targets, no refund"
    text += " - " + str(shot.Pegs) + " pegs, " + str(shot.Targets) + " targets, chain " + str(shot.Chain) + ", settle " + str(shot.Cascade) + " cascades (" + str(shot.SettlePops) + " pegs)"
    return text


def Animate(screen, board, aim, kind="n"):
    fx = {"flash": {}, "burst": {}, "trail": [], "shake": 0}
    previous = dict(board.Grid)
    pace = screen.Delay * 0.57 / 1000
    feel = {"step": 0, "slow": 0, "y": 0, "last": board.TargetsLeft()}

    def Fade():
        fx["burst"] = {c: t - 1 for c, t in fx["burst"].items() if t > 1}
        if fx["shake"]:
            fx["shake"] -= 1

    def Hook(x, y, cells=None, kind=""):
        if screen.Fast or fx.get("skip"):
            return
        if screen.Keys is not None and screen.Keys.Pressed():
            fx["skip"] = True
            return
        if x is not None:
            stop = 0.0
            for cell, symbol in previous.items():
                if cell not in board.Grid:
                    fx["burst"][cell] = 3
                    if symbol == "B":
                        fx["shake"] = 5
                        stop = max(stop, 0.08)
                    else:
                        stop = max(stop, 0.02)
            previous.clear()
            previous.update(board.Grid)
            live = board.Live
            fx["dock"] = DockX(live.Steps + DockPhase * len(board.Log)) if live else DockX(DockPhase * len(board.Log))
            rally = live.Rally if live else 1
            note = "Rally x" + str(rally) + " - " + str(live.Pegs) + " pegs" if rally > 1 else ""
            if stop > 0:
                stop += 0.01 * (rally - 1)
                if not screen.Reduced:
                    extra = 0.0
                    if rally > feel.get("rally", 1):
                        feel["rally"] = rally
                        extra = {2: 0.0, 3: 0.03, 4: 0.05, 5: 0.09}.get(rally, 0.0)
                        if rally >= 3:
                            note = "RALLY x" + str(rally) + " - " + str(live.Pegs) + " pegs"
                    left = board.TargetsLeft()
                    if left == 1 and feel.get("last", 2) > 1:
                        extra = max(extra, 0.06)
                        feel["cross"] = 1
                        note = "1 credit to clear"
                    feel["last"] = left
                    room = max(0.0, BeatCap - feel.get("added", 0.0))
                    extra = min(extra, room)
                    feel["added"] = feel.get("added", 0.0) + extra
                    stop += extra
            weight = 100.0 / max(50, min(100, live.Speed)) if live and getattr(live, 'Speed', 0) else 1.0
            feel["step"] += 1
            if feel["step"] < 9:
                weight *= 1.9 - 0.1 * feel["step"]
            if y > feel["y"]:
                weight *= 0.85
            elif y < feel["y"]:
                weight *= 1.15
            feel["y"] = y
            if not any((x + dx, y + dy) in board.Grid for dx in range(-3, 4) for dy in range(-2, 3)):
                weight *= 0.6
            if feel["slow"] > 0:
                weight *= 1.5
                feel["slow"] -= 1
            if board.Struck:
                feel["slow"] = 3
                strike = {c: ("@", "pop") for c in board.Struck}
                screen.Show(screen.Frame(board, aim, False, None, note, False, dict(fx, flash=strike, trail=fx["trail"])))
                time.sleep(pace * 1.5 + 0.02 * screen.Delay / 30)
                for c in board.Struck:
                    fx["trail"].append(c)
            fx["trail"].append((x, y))
            del fx["trail"][:-7]
            screen.Show(screen.Frame(board, aim, False, (x, y), note, False, dict(fx, trail=fx["trail"][:-1])))
            Fade()
            time.sleep(pace * weight + stop * screen.Delay / 30)
        elif cells:
            fx["trail"] = []
            if kind == "fall":
                fx["flash"] = {c: (sym, "fall") for c, sym in cells.items()}
                screen.Show(screen.Frame(board, aim, False, None, "Settle: loose pegs fall", False, fx))
                time.sleep(max(screen.Delay, 1) * 0.8 / 1000)
            else:
                fx["flash"] = {c: (sym, "pop") for c, sym in cells.items()}
                label = "Cascade " + str(board.CascadeNow) + ": matching pegs pop (x" + str(board.CascadeNow) + ")"
                screen.Show(screen.Frame(board, aim, False, None, label, False, fx))
                time.sleep(max(screen.Delay, 1) * 4.5 / 1000)
                fx["flash"] = {}
                for cell in cells:
                    fx["burst"][cell] = 3
                for _ in range(3):
                    screen.Show(screen.Frame(board, aim, False, None, label, False, fx))
                    Fade()
                    time.sleep(max(screen.Delay, 1) * 1.5 / 1000)
                previous.clear()
                previous.update(board.Grid)
            fx["flash"] = {}
    shot = board.Play(aim, Hook, kind)
    if shot.Paid and not (screen.Fast or screen.Reduced or screen.Mono or screen.Delay <= 0 or fx.get("skip") or screen.Watching):
        fx["dock"] = DockX(shot.Steps + DockPhase * (len(board.Log) - 1))
        fx["trail"] = []
        for beat in range(4):
            fx["dockhit"] = beat % 2 == 0
            screen.Show(screen.Frame(board, aim, False, None, "CAUGHT in the dock  +" + str(CatchPoints) + "  free shot", False, fx))
            time.sleep(min(0.03, BeatCap / 4))
        fx["dockhit"] = False
    screen.LastSkipped = bool(fx.get("skip"))
    shot.Added = feel.get("added", 0.0)
    shot.Beats = feel.get("rally", 1)
    shot.Cross = feel.get("cross", 0)
    previous.clear()
    return shot


def Watch(args, screen, keys):
    if args.replay:
        seed, aims = ParseCode(args.replay)
    else:
        seed, aims = args.seed, None
    board = Board(seed)
    screen.Watching = True
    step = 0
    label = "Replay of " + args.replay if args.replay else "Bot playing"
    while not board.Over():
        if aims is not None:
            if step >= len(aims):
                break
            aim, kind = aims[step]
        elif args.script:
            aim, kind = ScriptAim(Aimer[0], board), "n"
        else:
            aim, kind = BotAim(board)
        step += 1
        screen.Kind = kind
        screen.Show(screen.Frame(board, aim, False, None, label + ": aiming (" + KindNames[kind] + " ball)", False))
        time.sleep(0.6)
        shot = Animate(screen, board, aim, kind)
        screen.Show(screen.Frame(board, aim, False, None, ShotMessage(board, shot), board.Over()))
        time.sleep(0.9)
    screen.Show(screen.Frame(board, board.Log[-1].Aim if board.Log else DefaultAim, False, None, label + " finished. [any key]", True))
    keys.Read()
    return board


BeatCap = 0.12
LargeShotPoints = 1500
RunQuotas = (9, 10, 10)
RunPool = ["r", "x", "s"]
RunStart = {"r": 1, "x": 1}


def RunBoardSeed(run, k):
    return Rng(run * 1000 + k).Below(1000000) + 1


def RunOffer(run, k):
    a = (run * 31 + k) % 3
    return [RunPool[(a + i) % 3] for i in range(3)]


def RunBoard(run, k, satchel):
    board = Board(RunBoardSeed(run, k))
    quota = RunQuotas[k - 1]
    board.Stock = {c: satchel.get(c, 0) for c in RunPool}
    board.Credit = max(board.Total - quota, 0)
    board.Quota = quota
    return board


def Attach(board, state):
    board.RunInfo = state
    return board


class RunState:
    def __init__(self, run):
        self.Run = run
        self.K = 1
        self.Satchel = dict(RunStart)
        self.Picks = []
        self.Boards = []

    def Code(self, board=None):
        done = self.Boards + ([board] if board is not None and board not in self.Boards else [])
        shots = "/".join(".".join(str(x.Aim) + ("" if x.Kind == "n" else x.Kind) for x in b.Log) for b in done)
        return Version + "R-" + str(self.Run) + "-" + ".".join(str(q) for q in RunQuotas) + "-" + "".join(self.Picks) + "-" + shots


def ParseRunCode(code):
    if len(code) > MaxCodeLength:
        raise ValueError("Run code is too long")
    parts = code.strip().split("-")
    if parts and parts[0] in ("CH12R", "CH13R", "CH14R", "CH15R"):
        raise ValueError("Saved " + parts[0][:-1] + " run codes are no longer valid in " + Version + ". Start a new run.")
    if len(parts) != 5 or parts[0] != Version + "R":
        raise ValueError("Unknown run code version or wrong number of parts")
    if not parts[1].isdigit() or len(parts[1]) > 10:
        raise ValueError("Bad run number")
    run = int(parts[1])
    if run < 1 or run > MaxRunNumber:
        raise ValueError("Run number must be from 1 to " + str(MaxRunNumber))
    if [int(q) for q in parts[2].split(".")] != list(RunQuotas):
        raise ValueError("Run code quotas do not match this version")
    picks = list(parts[3])
    if any(p not in RunPool and p != "0" for p in picks):
        raise ValueError("Bad pick in run code")
    chunks = []
    for text in parts[4].split("/"):
        shots = []
        pieces = text.split(".") if text else []
        if len(pieces) > MaxShotsPerBoard:
            raise ValueError("Too many shots for one board")
        for p in pieces:
            kind = "n"
            if p and p[-1] in "rxs":
                kind = p[-1]
                p = p[:-1]
            if not p.isdigit() or len(p) > 3:
                raise ValueError("Bad aim in run code")
            aim = int(p)
            if aim < 0 or aim >= len(Directions):
                raise ValueError("Bad aim in run code")
            shots.append((aim, kind))
        chunks.append(shots)
    if not 1 <= len(chunks) <= len(RunQuotas) or len(picks) != len(chunks) - 1:
        raise ValueError("Run code does not fit its run")
    return run, picks, chunks


def ResumeRun(code):
    run, picks, chunks = ParseRunCode(code)
    state = RunState(run)
    board = Attach(RunBoard(run, 1, state.Satchel), state)
    for index, shots in enumerate(chunks):
        for aim, kind in shots:
            if board.Over():
                raise ValueError("Run code has shots after a board ended")
            board.Play(aim, None, kind)
        if index < len(chunks) - 1:
            if not board.Won():
                raise ValueError("Run code moves on from a board that was not won")
            state.Boards.append(board)
            state.Picks.append(picks[index])
            if picks[index] != "0":
                state.Satchel[picks[index]] = state.Satchel.get(picks[index], 0) + 1
            state.K += 1
            board = Attach(RunBoard(run, state.K, state.Satchel), state)
    return state, board


LastRunCode = [""]
OldRunCodes = []
MaxCodeLength = 1200
MaxRunNumber = 1000000000
MaxShotsPerBoard = 40


def DraftScreen(screen, keys, state, board):
    offer = RunOffer(state.Run, state.K)
    lines = ["", " BOARD " + str(state.K) + " CLEARED   score " + str(board.Score), "", " Pick one upgrade: +1 charge of that ball from the next board on.", ""]
    notes = {"r": "Rebound: bounces off the floor once", "x": "Blast: big blast, flies on", "s": "Second Chance: refunds the shot if it clears 0 or 1 target"}
    for i, c in enumerate(offer, 1):
        lines.append("  [" + str(i) + "] " + notes[c] + "  (have " + str(state.Satchel.get(c, 0)) + ", after pick " + str(state.Satchel.get(c, 0) + 1) + ")")
    lines.append("  [0] Skip: take no upgrade")
    lines += ["", " Run code so far: " + state.Code(board), ""]
    screen.Show(lines)
    while True:
        key = keys.Read()
        if key in ("1", "2", "3"):
            return offer[int(key) - 1]
        if key == "0":
            return "0"
        if key in ("q", "esc"):
            return None


def Run(args):
    size = shutil.get_terminal_size((80, 24))
    needCols = Width * CellCols + 4
    needRows = Height + 10
    if size.columns < needCols or size.lines < needRows:
        print("Window too small: needs at least " + str(needCols) + " columns and " + str(needRows) + " rows, has " + str(size.columns) + " by " + str(size.lines) + ". Enlarge the window and start again.")
        return None
    if not EnableAnsi():
        print("This console does not support colour and cursor control. Close this and double-click PlayText.bat instead (or run with --text).")
        return None
    plain = args.ascii
    try:
        "\u25cf\u2593\u2502".encode(sys.stdout.encoding or "ascii")
    except (UnicodeEncodeError, LookupError):
        plain = True
    screen = Screen(args.mono, args.delay, plain)
    screen.Reduced = args.reduced
    seed = args.seed
    state = None
    if args.resume:
        state, board = ResumeRun(args.resume)
        seed = board.Seed
    elif args.menu:
        state = None
    elif args.run:
        state = RunState(args.run)
        board = Attach(RunBoard(state.Run, state.K, state.Satchel), state)
        seed = board.Seed
    elif args.code:
        board = Replay(args.code)
        seed = board.Seed
    else:
        board = Board(seed)
    aim = DefaultAim
    preview = True
    message = ""
    sys.stdout.write(Escape + "[?1049h" + Escape + "[?25l" + Escape + "[2J")
    try:
        with Keyboard() as keys:
            screen.Keys = keys
            if args.replay or args.bot or args.script:
                return Watch(args, screen, keys)
            if args.menu:
                picked = TitleScreen(screen, keys)
                if picked is None:
                    return None
                state = RunState(picked)
                board = Attach(RunBoard(state.Run, state.K, state.Satchel), state)
                seed = board.Seed
            while True:
                screen.Show(screen.Frame(board, aim, preview, None, message, board.Over()))
                screen.ScoreMark = False
                message = ""
                key = keys.Read()
                if key in ("left", "a", "h"):
                    aim = max(0, aim - 1)
                elif key in ("right", "d", "l"):
                    aim = min(len(Directions) - 1, aim + 1)
                elif key == "p":
                    preview = not preview
                elif key == "f":
                    screen.Fast = not screen.Fast
                elif key in ("1", "2", "3", "4"):
                    wanted = "nrxs"[int(key) - 1]
                    if wanted != "n" and board.Stock.get(wanted, 0) <= 0:
                        message = "No " + KindNames[wanted] + " balls left"
                    else:
                        screen.Kind = wanted
                elif key in ("q", "esc"):
                    break
                elif state is not None and key == "r":
                    OldRunCodes.append(state.Code(board))
                    state = RunState(state.Run)
                    board = Attach(RunBoard(state.Run, 1, state.Satchel), state)
                    seed = board.Seed
                    screen.Kind = "n"
                    message = "Run restarted from board 1, score and satchel reset. The old run code prints when you quit."
                elif state is not None and key == "n":
                    if not board.Over():
                        message = "Finish this board first"
                    elif not board.Won():
                        state = RunState(NextRunNumber(state.Run))
                        board = Attach(RunBoard(state.Run, 1, state.Satchel), state)
                        seed = board.Seed
                        screen.Kind = "n"
                        message = "New run " + str(state.Run)
                    elif state.K >= len(RunQuotas):
                        state.Boards.append(board)
                        total = sum(b.Score for b in state.Boards)
                        bestLines = BestLines(*RecordBest(total))
                        screen.Show(["", " RUN COMPLETE   all " + str(len(RunQuotas)) + " boards cleared", " Total score " + str(total)] + bestLines + ["", " Run code (replays this run):", " " + state.Code(), "", " [any key] run " + str(NextRunNumber(state.Run)) + "    [Q] quit"])
                        if keys.Read() in ("q", "esc"):
                            break
                        state = RunState(NextRunNumber(state.Run))
                        board = Attach(RunBoard(state.Run, 1, state.Satchel), state)
                        seed = board.Seed
                        screen.Kind = "n"
                        message = "New run " + str(state.Run)
                    else:
                        pick = DraftScreen(screen, keys, state, board)
                        if pick is None:
                            break
                        if pick is not None:
                            state.Boards.append(board)
                            state.Picks.append(pick)
                            if pick != "0":
                                state.Satchel[pick] = state.Satchel.get(pick, 0) + 1
                            state.K += 1
                            board = Attach(RunBoard(state.Run, state.K, state.Satchel), state)
                            seed = board.Seed
                            screen.Kind = "n"
                            message = "Board " + str(state.K) + " of " + str(len(RunQuotas))
                elif key == "r":
                    board = Board(seed)
                    screen.Kind = "n"
                    message = "Same board again"
                elif key == "n":
                    if isinstance(seed, str):
                        message = "A board file has no next board"
                    else:
                        seed += 1
                        board = Board(seed)
                        screen.Kind = "n"
                        message = "Next board"
                elif key in (" ", "enter") and not board.Over():
                    shot = Animate(screen, board, aim, screen.Kind)
                    screen.ScoreMark = ScoreMarkWanted(screen, shot.Points)
                    message = ShotMessage(board, shot)
                    screen.Kind = "n"
    finally:
        if state is not None:
            LastRunCode[0] = state.Code(board)
        sys.stdout.write(Escape + "[?25h" + Escape + "[?1049l")
        sys.stdout.flush()
    return board


def TextBoard(board):
    rows = []
    rows.append("+" + "-" * Width + "+")
    for y in range(Height):
        line = ""
        for x in range(Width):
            symbol = board.Grid.get((x, y))
            if symbol is not None:
                line += symbol
            elif y == 0 and x == CannonX:
                line += "V"
            else:
                line += " "
        rows.append("|" + line + "|")
    rows.append("+" + "-" * Width + "+")
    return "\n".join(rows)


def SaveLog(args, board):
    if args.log and board.Log:
        with open("ChainLog.txt", "a") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M") + "\n" + ResultBlock(board) + "\n\n")
        print("Result added to ChainLog.txt")


def TextMode(args):
    if args.code:
        board = Replay(args.code)
    else:
        board = Board(args.seed)
    print("CHAIN text mode. Pick an aim from 1 (shallow left) to " + str(len(Directions)) + " (shallow right). 20 is straight down. Add r or x for a rebound or blast ball, like 12 r. q quits.")
    while not board.Over():
        print(TextBoard(board))
        print("Shots left " + str(ShotLimit + board.Extra - len(board.Log)) + "  rebound " + str(board.Stock["r"]) + "  blast " + str(board.Stock["x"]) + "  targets left " + str(board.TargetsLeft()) + "  score " + str(board.Score))
        try:
            answer = input("Aim: ").strip().lower()
        except EOFError:
            break
        if answer == "q":
            break
        words = answer.split()
        kind = "n"
        if len(words) == 2 and words[1] in ("r", "x"):
            kind = words[1]
            words = words[:1]
        if len(words) != 1 or not words[0].isdigit() or not 1 <= int(words[0]) <= len(Directions):
            print("Enter a number from 1 to " + str(len(Directions)) + ", optionally followed by r (rebound) or x (blast), for example  12 r")
            continue
        if kind != "n" and board.Stock.get(kind, 0) <= 0:
            print("No " + KindNames[kind] + " balls left")
            continue
        shot = board.Play(int(words[0]) - 1, None, kind)
        print("Pegs popped " + str(shot.Pegs) + ", biggest chain " + str(shot.Chain) + ", popped by settle " + str(shot.SettlePops) + ", ball steps " + str(shot.Steps))
    print(TextBoard(board))
    print(ResultBlock(board))
    SaveLog(args, board)


def BlastCheck():
    problems = 0
    for first in "#F":
        board = Board.__new__(Board)
        board.Seed = 1
        board.DockPaid = DockCap
        board.Grid = {(25, 10): first, (26, 10): "o", (28, 10): "*", (27, 11): "/", (25, 13): "#", (35, 10): "o"}
        board.Bumps = {}
        board.Extra = 0
        board.Stock = {"r": 2, "x": 2}
        board.Streak = 0
        board.CascadeNow = 0
        board.Score = 0
        board.Log = []
        board.Total = sum(1 for v in board.Grid.values() if v == "#")
        shot = board.Play(DefaultAim, None, "x")
        wantTargets = 2 if first == "#" else 1
        wantBonus = 1 if first == "F" else 0
        if shot.Targets != wantTargets or shot.Bonus != wantBonus:
            problems += 1
        if board.Grid.get((28, 10)) != "*" or board.Grid.get((27, 11)) != "/" or (35, 10) not in board.Grid:
            problems += 1
        if (26, 10) in board.Grid:
            problems += 1
    return problems


def SelfTest():
    seeds = range(1, 31)
    mismatches = 0
    stepMax = 0
    shots = 0
    settleShots = 0
    chainShots = 0
    wins = 0
    capShots = 0
    botWins = 0
    botTargets = 0
    randomTargets = 0
    pegTotal = 0
    spreadSum = 0.0
    boardsWithSettle = 0
    lengths = []
    for seed in seeds:
        rng = Rng(seed * 7 + 3)
        aims = [rng.Below(len(Directions)) for _ in range(ShotLimit)]
        a = Board(seed)
        b = Board(seed)
        for aim in aims:
            kind = "nnrx"[rng.Below(4)]
            if kind != "n" and a.Stock[kind] <= 0:
                kind = "n"
            if not a.Over():
                a.Play(aim, None, kind)
            if not b.Over():
                b.Play(aim, None, kind)
        if seed <= 3:
            import tempfile
            folder = tempfile.mkdtemp()
            path = os.path.join(folder, "b.txt")
            ExportBoard(seed, path)
            key = LoadBoardFile(path)
            twin = Board(key)
            original = Board(seed)
            for aim in aims[:3]:
                twin.Play(aim)
                original.Play(aim)
            if twin.Hash() != original.Hash() or Replay(twin.Code()).Hash() != twin.Hash():
                mismatches += 1
            os.remove(path)
            os.rmdir(folder)
        probe = Board(seed)
        probe.Play(aims[0])
        before = (dict(probe.Grid), dict(probe.Bumps), probe.Score, list(probe.Log), probe.Extra, probe.Streak, dict(probe.Stock))
        for aim in range(len(Directions)):
            for kind in "nrx":
                probe.Trace(aim, kind)
        if before != (probe.Grid, probe.Bumps, probe.Score, probe.Log, probe.Extra, probe.Streak, probe.Stock):
            mismatches += 1
        c = Replay(a.Code())
        if not (a.Hash() == b.Hash() == c.Hash()):
            mismatches += 1
        for s in a.Log:
            shots += 1
            stepMax = max(stepMax, s.Steps)
            if s.Steps >= StepCap:
                capShots += 1
            pegTotal += s.Pegs
            if s.SettlePops:
                settleShots += 1
            if s.Chain >= 2:
                chainShots += 1
        if a.SettlePopTotal():
            boardsWithSettle += 1
        if a.Won():
            wins += 1
        lengths.append(len(a.Log))
        randomTargets += a.Total - a.TargetsLeft()
        bot = Board(seed)
        while not bot.Over():
            aim, kind = BotAim(bot)
            bot.Play(aim, None, kind)
        botTargets += bot.Total - bot.TargetsLeft()
        if bot.Won():
            botWins += 1
        base = Board(seed)
        values = []
        for aim in range(len(Directions)):
            values.append(base.Clone().Fire(aim).Points)
        mean = sum(values) / len(values)
        spreadSum += math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    count = len(list(seeds))
    mismatches += BlastCheck()
    print("Boards tested " + str(count) + ", random aims, " + str(ShotLimit) + " shots each")
    print("Replay or rerun mismatches " + str(mismatches))
    print("Longest shot " + str(stepMax) + " steps (cap " + str(StepCap) + ")")
    print("Shots with a settle pop " + format(100 * settleShots / shots, ".0f") + "%")
    print("Boards where settle popped at least once " + format(100 * boardsWithSettle / count, ".0f") + "%")
    print("Shots with a bomb chain of 2 or more " + format(100 * chainShots / shots, ".0f") + "%")
    print("Average pegs popped per shot " + format(pegTotal / shots, ".1f"))
    print("Shots that ran into the step cap " + format(100 * capShots / shots, ".1f") + "%")
    print("Boards cleared by random aim " + str(wins) + " of " + str(count) + ", average targets cleared " + format(randomTargets / count, ".1f") + " of " + str(TargetCount))
    print("Boards cleared by a one-shot-lookahead bot " + str(botWins) + " of " + str(count) + ", average targets cleared " + format(botTargets / count, ".1f") + " of " + str(TargetCount))
    print("Average first-shot score spread across the " + str(len(Directions)) + " aims (standard deviation) " + format(spreadSum / count, ".1f"))


def Main():
    parser = argparse.ArgumentParser(description="CHAIN test board")
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--code", type=str, default="")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--mono", action="store_true")
    parser.add_argument("--delay", type=int, default=30)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--check", type=str, default="")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--replay", type=str, default="")
    parser.add_argument("--bot", action="store_true")
    parser.add_argument("--ascii", action="store_true")
    parser.add_argument("--script", type=str, default="")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--board", type=str, default="")
    parser.add_argument("--export", type=str, default="")
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--run", type=int, default=None)
    parser.add_argument("--menu", action="store_true")
    parser.add_argument("--resume", type=str, default="")
    parser.add_argument("--reduced", action="store_true")
    args = parser.parse_args()
    if args.seed < 0:
        parser.error("--seed cannot be negative")
    if args.delay < 0:
        parser.error("--delay cannot be negative")
    if args.run is not None and (args.run < 1 or args.run > MaxRunNumber):
        parser.error("--run must be from 1 to " + str(MaxRunNumber))
    if (args.run is not None or args.resume) and (args.text or args.code or args.check or args.replay or args.bot or args.script or args.board or args.headless):
        parser.error("--run and --resume cannot be combined with text, code, check, replay, bot, script or board options")
    if args.run is not None and args.resume:
        parser.error("use either --run or --resume, not both")
    if args.resume:
        try:
            ResumeRun(args.resume)
        except (ValueError, IndexError) as error:
            parser.error("bad run code: " + str(error))
    if args.export:
        try:
            ExportBoard(args.seed, args.export)
        except FileExistsError:
            parser.error(args.export + " already exists. Pick a new name or delete it first")
        except OSError as error:
            parser.error("could not write " + args.export + ": " + str(error))
        print("Board " + str(args.seed) + " written to " + args.export + ". Edit it in any text editor, then play it with --board " + args.export)
        return
    if args.board:
        try:
            args.seed = LoadBoardFile(args.board)
        except (OSError, ValueError) as error:
            parser.error("board file: " + str(error))
    for text in (args.code, args.check, args.replay):
        if text:
            try:
                parsed = ParseCode(text)
                if isinstance(parsed[0], str) and parsed[0] not in Layouts:
                    raise ValueError("This code is for a board file. Add --board FILE with the same file")
                Replay(text)
            except ValueError as error:
                parser.error("bad board code: " + str(error))
    if args.script:
        try:
            Aimer[0] = LoadAimer(args.script)
        except (OSError, ValueError, SyntaxError) as error:
            parser.error("script: " + str(error))
    if args.selftest:
        SelfTest()
        return
    if args.script and args.headless:
        board = Board(args.seed)
        try:
            while not board.Over():
                board.Play(ScriptAim(Aimer[0], board))
        except ValueError as error:
            parser.error("script: " + str(error))
        print(ResultBlock(board))
        return
    if args.check:
        board = Replay(args.check)
        if args.show:
            print(TextBoard(board))
        print(ResultBlock(board))
        return
    if args.text:
        TextMode(args)
        return
    if args.resume:
        try:
            ResumeRun(args.resume)
        except ValueError as error:
            parser.error("bad run code: " + str(error))
    board = Run(args)
    if board is not None:
        print(ResultBlock(board))
        if OldRunCodes:
            print("Run codes from runs you restarted:")
            for old in OldRunCodes:
                print(old)
        if LastRunCode[0]:
            print("Run code (continue later with --resume CODE):")
            print(LastRunCode[0])
        SaveLog(args, board)
    if IsWindows and not os.environ.get("CHAIN_LAUNCHER"):
        print("")
        print("Press any key to close")
        try:
            with Keyboard() as keys:
                keys.Wait()
        except Exception:
            input()


if __name__ == "__main__":
    Main()
