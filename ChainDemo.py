import argparse
import os
import shutil
import hashlib
import math
import sys
import time

IsWindows = os.name == "nt"
if IsWindows:
    import msvcrt
else:
    import select
    import termios
    import tty

Version = "CH2"
Width = 100
Height = 38
CannonX = 50
ShotLimit = 10
StepCap = 1200
WallDrift = 12
BounceDrift = 7
TargetCount = 16
GroupSize = 3
CascadeCap = 5
PreviewSteps = 160
DefaultAim = 19
LooseSymbols = "o+"
SolidSymbols = "o+#*B"
MirrorSymbols = "/\\"
Directions = [
    (-97, 24), (-95, 31), (-93, 37), (-90, 44), (-87, 50), (-83, 56), (-79, 62),
    (-74, 67), (-69, 72), (-64, 77), (-59, 81), (-53, 85), (-47, 88), (-41, 91),
    (-34, 94), (-28, 96), (-21, 98), (-14, 99), (-7, 100), (0, 100), (7, 100),
    (14, 99), (21, 98), (28, 96), (34, 94), (41, 91), (47, 88), (53, 85),
    (59, 81), (64, 77), (69, 72), (74, 67), (79, 62), (83, 56), (87, 50),
    (90, 44), (93, 37), (95, 31), (97, 24),
]
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
        self.Chain = 0
        self.Cascade = 0
        self.SettlePops = 0
        self.Steps = 0


class Board:
    def __init__(self, seed):
        self.Seed = seed
        self.Grid = {}
        self.Bumps = {}
        self.Score = 0
        self.Log = []
        self.Generate()

    def Generate(self):
        rng = Rng(self.Seed)
        self.Place(rng, "#", TargetCount, 1)
        self.Place(rng, "B", 14, 2)
        self.Place(rng, "*", 16, 1)
        self.Place(rng, "/", 6, 1)
        self.Place(rng, "\\", 6, 1)
        self.Place(rng, "o", 130, 6)
        self.Place(rng, "+", 120, 6)

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
        return other

    def Solid(self, x, y):
        if x < 0 or x >= Width or y < 0:
            return 1
        symbol = self.Grid.get((x, y))
        if symbol is not None and symbol in SolidSymbols:
            return 2
        return 0

    def TargetsLeft(self):
        return sum(1 for s in self.Grid.values() if s == "#")

    def Won(self):
        return self.TargetsLeft() == 0

    def Over(self):
        return self.Won() or len(self.Log) >= ShotLimit

    def Remove(self, cell, points, shot, removed):
        symbol = self.Grid.pop(cell)
        removed.add(cell)
        shot.Pegs += 1
        shot.Points += points
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
        elif symbol == "*":
            shot.Points += 5
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

    def Gravity(self, vacated):
        vacated = set(vacated)
        fallen = set()
        changed = True
        while changed:
            changed = False
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
                    changed = True
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
                for near in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if near not in seen and self.Grid.get(near) == symbol:
                        seen.add(near)
                        group.append(near)
            if len(group) >= GroupSize:
                popped.update(group)
                for cx, cy in group:
                    for near in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if self.Grid.get(near) == "#":
                            popped.add(near)
        return popped

    def Settle(self, removed, shot, hook):
        vacated = set(removed)
        for cascade in range(1, CascadeCap + 1):
            fallen = self.Gravity(vacated)
            if hook and fallen:
                hook(None, None, {c: self.Grid[c] for c in fallen}, "fall")
            popped = self.FindGroups(fallen)
            if not popped:
                break
            info = {c: self.Grid[c] for c in popped}
            for cell in sorted(popped):
                symbol = self.Grid.pop(cell)
                shot.Pegs += 1
                shot.SettlePops += 1
                if symbol == "#":
                    shot.Targets += 1
                    shot.Points += 50 * cascade
                else:
                    shot.Points += 10 * cascade
            shot.Cascade = cascade
            vacated = set(popped)
            if hook:
                hook(None, None, info, "pop")

    def Fire(self, aim, hook=None, maxSteps=StepCap, settle=True, stopAtHit=False):
        vx, vy = Directions[aim]
        x, y = CannonX, 0
        ax = ay = 0
        m = max(abs(vx), abs(vy))
        shot = Shot(aim)
        removed = set()
        uses = {}
        while shot.Steps < maxSteps:
            shot.Steps += 1
            ax += abs(vx)
            ay += abs(vy)
            sx = sy = 0
            if ax >= m:
                ax -= m
                sx = 1 if vx > 0 else -1
            if ay >= m:
                ay -= m
                sy = 1 if vy > 0 else -1
            if sx == 0 and sy == 0:
                continue
            if sy > 0 and y + sy >= Height:
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
            if not flipX:
                x += sx
            if not flipY:
                y += sy
            for cell in cells:
                if self.Grid.get(cell) == "*":
                    self.Bumps[cell] = self.Bumps.get(cell, 0) + 1
                    vy += BounceDrift
                    if self.Bumps[cell] >= 3:
                        del self.Grid[cell]
                        removed.add(cell)
                        continue
                self.Hit(cell, shot, removed)
            if stopAtHit and cells:
                break
            symbol = self.Grid.get((x, y))
            if symbol is not None and symbol in MirrorSymbols and uses.get((x, y), 0) < 2:
                uses[(x, y)] = uses.get((x, y), 0) + 1
                vx, vy = (-vy, -vx) if symbol == "/" else (vy, vx)
                vy += BounceDrift
                ax = ay = 0
                m = max(abs(vx), abs(vy))
            if hook:
                hook(x, y)
        if settle:
            self.Settle(removed, shot, hook)
        return shot

    def Play(self, aim, hook=None):
        shot = self.Fire(aim, hook)
        self.Score += shot.Points
        self.Log.append(shot)
        return shot

    def Trace(self, aim):
        path = []
        clone = self.Clone()
        clone.Fire(aim, lambda x, y, *rest: path.append((x, y)) if x is not None else None, PreviewSteps, False, True)
        return path

    def Hash(self):
        data = repr(sorted(self.Grid.items())) + repr(sorted(self.Bumps.items())) + str(self.Score)
        return hashlib.sha256(data.encode()).hexdigest()[:8]

    def Code(self):
        return Version + "-" + str(self.Seed) + "-" + ".".join(str(s.Aim) for s in self.Log)

    def BiggestChain(self):
        return max([s.Chain for s in self.Log] + [0])

    def SettlePopTotal(self):
        return sum(s.SettlePops for s in self.Log)


def ParseCode(code):
    parts = code.strip().split("-")
    if len(parts) not in (2, 3) or parts[0] != Version:
        raise ValueError("Unknown code version or wrong number of parts")
    seed = int(parts[1])
    if seed < 0:
        raise ValueError("Seed cannot be negative")
    aims = []
    if len(parts) > 2 and parts[2]:
        aims = [int(p) for p in parts[2].split(".")]
    for a in aims:
        if a < 0 or a >= len(Directions):
            raise ValueError("Bad aim in code")
    return seed, aims


def Replay(code):
    seed, aims = ParseCode(code)
    board = Board(seed)
    for aim in aims:
        if board.Over():
            break
        board.Play(aim)
    return board


def ResultBlock(board):
    total = TargetCount
    cleared = total - board.TargetsLeft()
    lines = ["CHAIN " + Version + "  board " + str(board.Seed)]
    if board.Won():
        lines.append("Cleared all " + str(total) + " targets in " + str(len(board.Log)) + " shots")
    else:
        lines.append("Cleared " + str(cleared) + " of " + str(total) + " targets in " + str(len(board.Log)) + " shots")
    lines.append("Score " + str(board.Score) + "   biggest chain " + str(board.BiggestChain()) + "   settle pops " + str(board.SettlePopTotal()))
    for number, shot in enumerate(board.Log, 1):
        lines.append("Shot " + str(number) + ": aim " + str(shot.Aim + 1) + "  pegs " + str(shot.Pegs) + "  chain " + str(shot.Chain) + "  settle " + str(shot.SettlePops))
    lines.append("Code " + board.Code())
    lines.append("Check " + board.Hash())
    if Stats["Frames"]:
        lines.append("Screen refresh average " + format(Stats["Milliseconds"] / Stats["Frames"], ".2f") + " ms over " + str(Stats["Frames"]) + " frames")
    return "\n".join(lines)


def AimDegrees(aim):
    vx, vy = Directions[aim]
    return round(math.degrees(math.atan2(vx, vy)))


Escape = "\x1b"
Reset = Escape + "[0m"
Styles = {
    "o": Escape + "[36m",
    "+": Escape + "[35m",
    "#": Escape + "[1;33m",
    "*": Escape + "[32m",
    "B": Escape + "[1;31m",
    "/": Escape + "[37m",
    "\\": Escape + "[37m",
    "@": Escape + "[1;97m",
    ".": Escape + "[34m",
    "V": Escape + "[1;97m",
    ":": Escape + "[2;37m",
    "fall": Escape + "[1;30;106m",
    "pop": Escape + "[1;97;41m",
    "title": Escape + "[1;97;44m",
    "dim": Escape + "[2m",
    "good": Escape + "[1;32m",
}


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

    def Wait(self):
        self.Read()


class Screen:
    def __init__(self, mono, delay):
        self.Mono = mono
        self.Delay = delay
        self.Fast = False

    def Paint(self, symbol, text):
        if self.Mono or symbol not in Styles:
            return text
        return Styles[symbol] + text + Reset

    def Bar(self, done, total, symbol):
        return "[" + self.Paint(symbol, symbol * done) + self.Paint("dim", "-" * (total - done)) + "]"

    def Cannon(self, aim):
        degrees = AimDegrees(aim)
        if abs(degrees) < 10:
            glyph = "v"
        elif abs(degrees) < 45:
            glyph = "/" if degrees < 0 else "\\"
        else:
            glyph = "<" if degrees < 0 else ">"
        return glyph

    def Frame(self, board, aim, preview, ball=None, message="", showResult=False, trail=(), flash=None):
        dots = set()
        if preview and ball is None and not board.Over():
            dots = set(board.Trace(aim))
        left = ShotLimit - len(board.Log)
        done = TargetCount - board.TargetsLeft()
        title = " CHAIN  board " + str(board.Seed) + "  " + Version + " "
        lines = [self.Paint("title", title.ljust(Width + 2))]
        status = " Shots " + self.Bar(left, ShotLimit, "o")
        status += "  Targets " + str(done) + "/" + str(TargetCount) + " " + self.Bar(done, TargetCount, "#")
        status += "  Score " + str(board.Score) + "  Best chain " + str(board.BiggestChain()) + "  Settle pops " + str(board.SettlePopTotal())
        lines.append(status)
        lines.append("+" + "-" * Width + "+")
        cannon = self.Cannon(aim)
        for y in range(Height):
            row = "|"
            for x in range(Width):
                symbol = board.Grid.get((x, y))
                if ball is not None and ball == (x, y):
                    row += self.Paint("@", "@")
                elif flash and (x, y) in flash:
                    row += self.Paint("pop" if flash[(x, y)][1] == "pop" else "fall", flash[(x, y)][0])
                elif symbol is not None:
                    row += self.Paint(symbol, symbol)
                elif y == 0 and abs(x - CannonX) <= 1:
                    row += self.Paint("V", ("[", cannon, "]")[x - CannonX + 1])
                elif (x, y) in trail:
                    row += self.Paint(":", ":")
                elif (x, y) in dots:
                    row += self.Paint(".", ".")
                else:
                    row += " "
            lines.append(row + "|")
        lines.append("+" + "-" * Width + "+")
        legend = " " + self.Paint("o", "o") + " " + self.Paint("+", "+") + " loose pegs   " + self.Paint("#", "#") + " target   "
        legend += self.Paint("*", "*") + " bumper (3 hits)   " + self.Paint("B", "B") + " bomb   " + self.Paint("/", "/") + " " + self.Paint("\\", "\\") + " mirror"
        lines.append(legend)
        lines.append(" After each shot, loose pegs fall. 3+ touching pegs of one kind pop, with any target beside them.")
        if showResult:
            controls = " " + ("YOU WIN" if board.Won() else "OUT OF SHOTS") + "   r same board   n next board   q quit and show code"
        else:
            controls = " left/right aim (" + str(aim + 1) + "/" + str(len(Directions)) + ", " + str(AimDegrees(aim)) + " deg)   space fire   p preview " + ("on" if preview else "off") + "   f fast " + ("on" if self.Fast else "off") + "   r restart   n next   q quit"
        lines.append(controls)
        lines.append(" " + message[:Width])
        return lines

    def Show(self, lines):
        start = time.perf_counter()
        sys.stdout.write(Escape + "[H" + "".join(line + Escape + "[K\n" for line in lines))
        sys.stdout.flush()
        Stats["Milliseconds"] += (time.perf_counter() - start) * 1000
        Stats["Frames"] += 1


def Run(args):
    size = shutil.get_terminal_size((80, 24))
    needCols = Width + 4
    needRows = Height + 9
    if size.columns < needCols or size.lines < needRows:
        print("Window too small: needs at least " + str(needCols) + " columns and " + str(needRows) + " rows, has " + str(size.columns) + " by " + str(size.lines) + ". Enlarge the window and start again.")
        return None
    if not EnableAnsi():
        print("This console does not support colour and cursor control. Close this and double-click PlayText.bat instead (or run with --text).")
        return None
    screen = Screen(args.mono, args.delay)
    seed = args.seed
    if args.code:
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
            while True:
                screen.Show(screen.Frame(board, aim, preview, None, message, board.Over()))
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
                elif key in ("q", "esc"):
                    break
                elif key == "r":
                    board = Board(seed)
                    message = "Same board again"
                elif key == "n":
                    seed += 1
                    board = Board(seed)
                    message = "Next board"
                elif key in (" ", "enter") and not board.Over():
                    recent = []
                    counter = [0]

                    def Hook(x, y, cells=None, kind=""):
                        if screen.Fast:
                            return
                        if x is not None:
                            recent.append((x, y))
                            del recent[:-7]
                            counter[0] += 1
                            if counter[0] % 2:
                                return
                            screen.Show(screen.Frame(board, aim, False, (x, y), "", False, recent[:-1]))
                            if screen.Delay:
                                time.sleep(screen.Delay / 1000)
                        elif cells:
                            flash = {c: (sym, kind) for c, sym in cells.items()}
                            screen.Show(screen.Frame(board, aim, False, None, "Settle: " + ("pegs fall" if kind == "fall" else "matching pegs pop"), False, (), flash))
                            time.sleep(max(screen.Delay, 1) * 6 / 1000)
                    shot = board.Play(aim, Hook)
                    number = len(board.Log)
                    message = "Shot " + str(number) + ": " + str(shot.Pegs) + " pegs popped, bomb chain " + str(shot.Chain) + ", settle cascades " + str(shot.Cascade) + " (" + str(shot.SettlePops) + " pegs), " + str(shot.Targets) + " targets, +" + str(shot.Points) + " points"
    finally:
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
    print("CHAIN text mode. Pick an aim from 1 (shallow left) to " + str(len(Directions)) + " (shallow right). 20 is straight down. q quits.")
    while not board.Over():
        print(TextBoard(board))
        print("Shots left " + str(ShotLimit - len(board.Log)) + "  targets left " + str(board.TargetsLeft()) + "  score " + str(board.Score))
        try:
            answer = input("Aim: ").strip().lower()
        except EOFError:
            break
        if answer == "q":
            break
        if not answer.isdigit() or not 1 <= int(answer) <= len(Directions):
            print("Enter a number from 1 to " + str(len(Directions)))
            continue
        shot = board.Play(int(answer) - 1)
        print("Pegs popped " + str(shot.Pegs) + ", biggest chain " + str(shot.Chain) + ", popped by settle " + str(shot.SettlePops) + ", ball steps " + str(shot.Steps))
    print(TextBoard(board))
    print(ResultBlock(board))
    SaveLog(args, board)


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
            if not a.Over():
                a.Play(aim)
            if not b.Over():
                b.Play(aim)
        probe = Board(seed)
        probe.Play(aims[0])
        before = (dict(probe.Grid), dict(probe.Bumps), probe.Score, list(probe.Log))
        for aim in range(len(Directions)):
            probe.Trace(aim)
        if before != (probe.Grid, probe.Bumps, probe.Score, probe.Log):
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
        randomTargets += TargetCount - a.TargetsLeft()
        bot = Board(seed)
        while not bot.Over():
            best = max(range(len(Directions)), key=lambda k: (bot.Clone().Fire(k).Targets * 1000 + bot.Clone().Fire(k).Points, -k))
            bot.Play(best)
        botTargets += TargetCount - bot.TargetsLeft()
        if bot.Won():
            botWins += 1
        base = Board(seed)
        values = []
        for aim in range(len(Directions)):
            values.append(base.Clone().Fire(aim).Points)
        mean = sum(values) / len(values)
        spreadSum += math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    count = len(list(seeds))
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
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--code", type=str, default="")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--mono", action="store_true")
    parser.add_argument("--delay", type=int, default=30)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--check", type=str, default="")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--log", action="store_true")
    args = parser.parse_args()
    if args.seed < 0:
        parser.error("--seed cannot be negative")
    if args.delay < 0:
        parser.error("--delay cannot be negative")
    for text in (args.code, args.check):
        if text:
            try:
                ParseCode(text)
            except ValueError as error:
                parser.error("bad board code: " + str(error))
    if args.selftest:
        SelfTest()
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
    board = Run(args)
    if board is not None:
        print(ResultBlock(board))
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
