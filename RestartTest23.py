"""Restart (r) inside a resumed run keeps the run's version: CH21R stays CH21R on the old generator, CH23R stays CH23R."""
import sys, os, re, pty, select, struct, fcntl, termios, time
sys.argv = ["x"]
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import ChainDemo as E
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
Esc = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")
def Drive(args, keys):
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(here); os.execvp("python3", ["python3", "ChainDemo.py", "--delay", "0", "--mono", "--ascii"] + args)
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
        os.write(fd, k.encode()); Pump(0.3)
    Pump(0.8)
    try: os.kill(pid, 9)
    except OSError: pass
    return Esc.sub(b"\n", buf).decode("utf8", "replace")
for prefix, legacy in (("CH21R", True), ("CH23R", False)):
    code = prefix + "-99-9.10.10--"
    st, b = E.ResumeRun(code)
    Check(st.Legacy == legacy, prefix + ": resumed state has legacy=" + str(legacy))
    want = E.RunBoard(99, 1, dict(st.Satchel), legacy).Hash()
    other = E.RunBoard(99, 1, dict(st.Satchel), not legacy).Hash()
    Check(want != other, prefix + ": run 99 board 1 differs between the two generators (test is meaningful)")
    out = Drive(["--resume", code], ["r", "q"])
    codes = re.findall(r"(CH2\d)R-99-[0-9.]+--", out)
    Check(bool(codes) and all(c == prefix[:4] for c in codes), prefix + ": after r, every printed run code still starts " + prefix + " (saw " + str(sorted(set(codes))) + ")")
    titles = re.findall(r"board \d+ .*?(CH2\d) ", out)
    Check(titles and titles[-1] == prefix[:4], prefix + ": title bar after restart shows " + prefix[:4] + " (saw " + str(titles[-2:]) + ")")
    # the board shown after the restart must be the generator's own board 1 of run 99: compare seed layout via title seed + shape name
    shape = E.RunBoard(99, 1, dict(st.Satchel), legacy).Style.split()[0]
    Check(("(" + shape) in out, prefix + ": restarted board shows the " + prefix[:4] + " shape " + shape)
print("FAILS", len(Fails)); sys.exit(1 if Fails else 0)
