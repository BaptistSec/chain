"""CH24 UI round: title menu selection, records panel, framed result panels, help legend. Asserts and exits non-zero on failure."""
import sys, os, re, pty, select, struct, fcntl, termios, time, tempfile
sys.argv = ["x"]
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import ChainDemo as E
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
Esc = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
EscB = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")
def Clean(lines):
    return [Esc.sub("", l) for l in lines]
# title menu: entries, selector, records
for mono, plain in ((True, True), (True, False), (False, False)):
    s = E.Screen(mono, 0, plain)
    lines = Clean(E.TitleLines(s, len(E.Premise), "title", 1))
    text = "\n".join(lines)
    Check("[M] marathon" in text and "[Enter] start a run" in text and "[Q] quit" in text, "menu entries shown (mono=%s plain=%s)" % (mono, plain))
    Check(any(("> [M] marathon" in l) or ("\u25b8 [M] marathon" in l) for l in lines), "selector marks the second entry")
    Check("[D] daily run (" + E.DailyLabel() + ")" in text, "daily entry carries the date")
    Check(all(len(l) <= 102 for l in lines), "title lines fit 102 columns")
    raw = E.TitleLines(s, len(E.Premise), "title", 1)
    if mono:
        Check(not any("\x1b[7m" in l for l in raw), "mono: no reverse video on the selector")
    else:
        Check(any("\x1b[7m" in l for l in raw), "colour: selector uses reverse video")
# records from env-pointed files
folder = tempfile.mkdtemp()
bestPath = os.path.join(folder, "b.txt"); marathonPath = os.path.join(folder, "m.txt")
open(bestPath, "w").write("12345\n"); open(marathonPath, "w").write("7,67890\n")
os.environ["CHAIN_BEST_FILE"] = bestPath; os.environ["CHAIN_MARATHON_FILE"] = marathonPath
s = E.Screen(True, 0, True)
text = "\n".join(Clean(E.TitleLines(s, len(E.Premise), "title", 0)))
Check("best run score 12345" in text and "best marathon 7 boards, score 67890" in text, "records panel shows saved bests")
open(bestPath, "w").write("0\n"); open(marathonPath, "w").write("0,0\n")
text = "\n".join(Clean(E.TitleLines(s, len(E.Premise), "title", 0)))
Check("No records yet" in text, "zero records read as none")
del os.environ["CHAIN_BEST_FILE"]; del os.environ["CHAIN_MARATHON_FILE"]
# help page legend
s = E.Screen(True, 0, False)
text = "\n".join(Clean(E.TitleLines(s, len(E.Premise), "help")))
Check("Board pieces:" in text and "loose" in text and "target" in text and "mirror" in text and "dock" in text, "help page shows the board pieces legend")
Check("[any key] back" in text, "help page keeps the back hint")
# panels: framed, centered, width-safe in all modes
rows = [" MARATHON OVER   5 boards cleared", " Total score 26475", "", " [any key] marathon 6    [Q] quit"]
for mono, plain in ((True, True), (True, False), (False, False)):
    s = E.Screen(mono, 0, plain)
    out = s.Panel(rows)
    cleaned = Clean(out)
    Check(cleaned[0].lstrip()[:1] in ("+", "\u250c") and cleaned[-1].lstrip()[:1] in ("+", "\u2514"), "panel has a frame (plain=%s)" % plain)
    Check(all(len(l) <= 102 for l in cleaned), "panel fits 102 columns (plain=%s)" % plain)
    Check(all(len(cleaned[0]) == len(l) for l in cleaned), "panel rows share one width (plain=%s)" % plain)
    text = "\n".join(cleaned)
    Check("MARATHON OVER   5 boards cleared" in text and "[any key] marathon 6" in text, "panel keeps the result phrases verbatim")
    if not plain:
        Check(any("\u251c" in l for l in cleaned), "unicode panel has a rule under the heading")
# menu navigation drives a real marathon start
def Drive(args, keys):
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(here); os.execvp("python3", ["python3", "ChainDemo.py", "--delay", "0", "--mono"] + args)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 49, 104, 0, 0))
    buf = b""
    def Pump(t):
        nonlocal buf
        end = time.time() + t
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.03)
            if r:
                try: d = os.read(fd, 65536)
                except OSError: return
                if not d: return
                buf += d
    Pump(0.8)
    for k in keys:
        os.write(fd, k)
        Pump(0.35)
    Pump(0.6)
    try: os.kill(pid, 9)
    except OSError: pass
    return EscB.sub(b"\n", buf).decode("utf8", "replace")
out = Drive(["--menu"], [b"\x1b[B", b"\r"])
Check("Marathon board 1" in out.replace("\n", " "), "down arrow + enter starts a marathon")
out = Drive(["--menu"], [b"\x1b[B", b"\x1b[A", b"\r"])
Check("Marathon board 1" not in out.replace("\n", " ") and " CHAIN  board " in out, "up arrow wraps back and enter starts a run")
out = Drive(["--menu"], [b"m"])
Check("Marathon board 1" in out.replace("\n", " "), "letter shortcut m still starts a marathon")
print("FAILS", len(Fails)); sys.exit(1 if Fails else 0)
