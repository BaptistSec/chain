import sys, os, pty, time, select, struct, fcntl, termios, importlib.util, re
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec); Spec.loader.exec_module(E)
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
def Drive(plan):
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(Here); os.execvp("python3", ["python3", "ChainDemo.py", "--menu", "--delay", "10"])
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 110, 0, 0))
    buf = b""; snaps = []
    def Pump(t):
        nonlocal buf
        end = time.time() + t
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                try: buf += os.read(fd, 65536)
                except OSError: return
    for key, wait in plan:
        if key is None:
            snaps.append(buf.decode("utf8", "replace")); Pump(wait)
        else:
            os.write(fd, key); Pump(wait)
    snaps.append(buf.decode("utf8", "replace"))
    try: os.kill(pid, 9)
    except OSError: pass
    return snaps
daily = E.DailyRun()
Check(daily == int(time.strftime("%Y%m%d")), "daily run number equals today's local date")
Check(1 <= daily <= E.MaxRunNumber, "daily run number is a valid run number")
snaps = Drive([(None, 1.0), (b"\n", 0.8), (None, 0.1), (b"d", 1.5)])
Check("[D] daily run (" + str(daily) + ")" in snaps[1], "one Enter during the reveal skips to the menu, which lists the daily run")
board = E.RunBoardSeed(daily, 1)
Check("board " + str(board) in snaps[-1] or str(board) in snaps[-1], "pressing d starts the daily run's first board (seed " + str(board) + ")")
Check("Same local date, same starting boards" in snaps[1] and "everyone" not in snaps[1], "menu wording is local-date, no overclaim")
Check("Traceback" not in snaps[-1], "no traceback")
snaps = Drive([(None, 3.0), (b"h", 0.5), (None, 0.1), (b"x", 0.5), (b"q", 0.5)])
Check("Gravity pulls the charge down" in snaps[-1], "help page opens")
sys.exit(1 if Fails else 0)
