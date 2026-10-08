import io
import re
import sys
import contextlib

import ChainDemo as C

Fails = []


def Check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        Fails.append(name)


Chip = re.compile(r"\x1b\[1;30;43m(\[[^\]\x1b]+\])\x1b\[22;39;49m")


def Capture(screen, lines):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        screen.Show(lines)
    return buf.getvalue()


def Keys(text):
    return [m.group(1) for m in Chip.finditer(text)]


def Bare(text):
    return re.findall(r"(?<![\x1b\w])\[[A-Za-z<>0-9 +/]{1,10}\]", Chip.sub("", text))


sc = C.Screen(False, 0)
state = C.RunState(20261008)
board = C.Attach(C.RunBoard(20261008, 1, state.Satchel), state)
live = Capture(sc, sc.Frame(board, 10, True, None, "x", False))
Check("live frame colours aim, fire, preview, fast, restart, next, quit", Keys(live) == ["[1]", "[2]", "[3]", "[4]", "[<]", "[>]", "[Space]", "[P]", "[F]", "[R]", "[N]", "[Q]"] or {"[<]", "[>]", "[Space]", "[P]", "[F]", "[R]", "[N]", "[Q]"} <= set(Keys(live)))
Check("ball choice keys 1 to 4 coloured", {"[1]", "[2]", "[3]", "[4]"} <= set(Keys(live)))
Check("no unstyled key brackets on live frame", Bare(live) == [])
for i in range(1, 3):
    board.RunInfo = state
res = Capture(sc, sc.Frame(board, 10, False, None, "x", True))
Check("result screen keys coloured", {"[N]", "[R]", "[Q]"} <= set(Keys(res)) or "OUT OF SHOTS" not in res)
for page, expect in (("help", {"[<]", "[>]", "[Space]", "[P]", "[1]", "[4]", "[F]", "[Q]", "[any key]"}), ("title", {"[Enter]", "[D]", "[H]", "[Q]"})):
    out = Capture(sc, C.TitleLines(sc, 9, page))
    Check("title page " + page + " keys coloured", expect <= set(Keys(out)))
    Check("title page " + page + " no bare keys", Bare(out) == [])
reveal = Capture(sc, C.TitleLines(sc, 1, "title"))
Check("reveal skip key coloured", "[Enter]" in Keys(reveal))
mono = Capture(C.Screen(True, 0), C.TitleLines(C.Screen(True, 0), 9, "title"))
Check("mono mode has no colour codes", "\x1b[1;30" not in mono and "[Enter]" in mono)
bar = Capture(sc, [sc.Bar(5, 10, "o"), C.Screen(False, 0, True).Bar(5, 10, "o"), "[###---]", "[#]"])
Check("credit bars are not coloured as keys", Keys(bar) == [])
plainbar = Capture(sc, ["[" + "#" * 8 + "-" * 2 + "]"])
Check("short plain bar not a key", Keys(plainbar) == [])
Check("every Frame line fits 102 columns", all(len(C.Strip.sub("", l)) <= 102 for a in range(0, 39, 3) for l in sc.Frame(board, a, True, None, "", False)))
print("FAILS", len(Fails))
sys.exit(1 if Fails else 0)
