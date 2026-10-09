import pty, os, sys, time, select, struct, fcntl, termios, re, importlib.util
here = os.path.dirname(os.path.abspath(__file__))
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
def Drive(env, args, cols=110, rows=50, keys=(b" ", b"q")):
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(here)
        e = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        e.update(env); e["TERM"] = "xterm"
        os.execvpe("python3", ["python3", "ChainDemo.py", "--delay", "0", "--ascii"] + args, e)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
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
        os.write(fd, k); Pump(0.3)
    Pump(1.0)
    try: os.waitpid(pid, os.WNOHANG)
    except OSError: pass
    return buf.decode("utf8", "replace")
Sgr = re.compile("\x1b\\[[0-9;]*m")
off = Drive({"NO_COLOR": "1"}, ["--run", "3"])
Check("Window too small" not in off and len(off) > 1000, "NO_COLOR=1 game starts and draws (%d bytes)" % len(off))
Check(not Sgr.search(off), "NO_COLOR=1: no colour codes at all")
on = Drive({}, ["--run", "3"])
Check(len(Sgr.findall(on)) > 20, "NO_COLOR unset: colour codes present (%d)" % len(Sgr.findall(on)))
empty = Drive({"NO_COLOR": ""}, ["--run", "3"])
Check(len(Sgr.findall(empty)) > 20, "NO_COLOR empty: colour stays on, as the standard says")
flag = Drive({}, ["--mono", "--run", "3"])
Check(not Sgr.search(flag), "--mono still turns colour off")
both = Drive({"NO_COLOR": "1"}, ["--mono", "--run", "3"])
Check(not Sgr.search(both), "--mono plus NO_COLOR: off")
# size hint
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", os.path.join(here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec); Spec.loader.exec_module(E)
need = (E.Width * E.CellCols + 4, E.Height + 10)
st = E.RunState(3); b = E.Attach(E.RunBoard(3, 1, dict(st.Satchel)), st)
strip = lambda x: re.sub("\x1b\\[[0-9;]*[A-Za-z]", "", x)
widest = 0; rows = 0
for over in (False, True):
    for mono in (True, False):
        f = E.Screen(mono, 0, False).Frame(b, 20, True, None, "x" * 100, over)
        widest = max(widest, max(len(strip(l)) for l in f)); rows = max(rows, len(f))
print("real frame: widest %d columns, %d rows; advertised minimum %d x %d" % (widest, rows, need[0], need[1]))
Check(widest <= need[0] and rows <= need[1], "advertised minimum size holds the real frame")
Check(need[0] - widest <= 3 and need[1] - rows <= 3, "advertised minimum is not stale (slack %d cols, %d rows)" % (need[0] - widest, need[1] - rows))
small = Drive({}, ["--run", "3"], cols=need[0] - 1, rows=need[1])
Check("Window too small: needs at least %d columns and %d rows" % need in strip(small), "one column short shows the size message with the right numbers")
fit = Drive({}, ["--run", "3"], cols=need[0], rows=need[1])
Check("Window too small" not in fit, "exactly the advertised size starts the game")
print("FAILS", len(Fails))
sys.exit(1 if Fails else 0)
