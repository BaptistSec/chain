import pty, os, sys, time, select, struct, fcntl, termios, re, random
Argv = list(__import__("sys").argv)
os.environ["N"] = "0"
here = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(here, "ChainTest12.py")).read().split("bad = collections.Counter()")[0])

def Drive(args, keys, cols=110, rows=50, wait=0.12, tail=1.0):
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(here)
        os.execvp("python3", ["python3", "ChainDemo.py", "--delay", "0", "--mono", "--ascii"] + args)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    buf = b""
    def Pump(t):
        nonlocal buf
        end = time.time() + t
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.03)
            if r:
                try:
                    d = os.read(fd, 65536)
                except OSError:
                    return
                if not d:
                    return
                buf += d
    Pump(0.8)
    for k in keys:
        os.write(fd, {"SP": b" ", "R": b"\x1b[C", "L": b"\x1b[D", "w": b"\x00"}.get(k, k.encode()))
        Pump(wait)
    Pump(tail)
    try:
        os.waitpid(pid, os.WNOHANG)
    except OSError:
        pass
    return re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"\n", buf).decode("utf8", "replace")

def Keys(run):
    rng = random.Random(run)
    state, board, starts, complete = PlayRun(run, rng)
    if not complete:
        return None, None
    keys = []; aim = E.DefaultAim
    allb = state.Boards
    for k, b in enumerate(allb):
        for s in b.Log:
            d = s.Aim - aim
            keys += ["R"] * d if d > 0 else ["L"] * (-d)
            aim = s.Aim
            if s.Kind != "n":
                keys.append(str("nrxs".index(s.Kind) + 1))
            keys += ["SP", "w", "w", "w"]
        keys += ["w", "w", "n", "w", "w"]
        if k < len(allb) - 1:
            pick = state.Picks[k]
            keys += [str(E.RunOffer(run, k + 1).index(pick) + 1), "w", "w"]
    return keys, state

if __name__ == "__main__":
    if len(Argv) > 1 and Argv[1] == "resume":
        run = 30001
        keys, state = Keys(run)
        full = state.Code().split("-")
        mid = "-".join(full[:3]) + "-" + full[3][:1] + "-" + "/".join(full[4].split("/")[:2])
        print("resume mid-run code:", mid)
        txt2 = Drive(["--resume", mid], ["w", "w"])
        print("resume shows", sorted(set(re.findall(r"Board \d/3", txt2))), "ok" if "Board 2/3" in txt2 else "NOT ok")
        done = state.Code()
        txt4 = Drive(["--resume", done], ["w", "w", "n", "w"])
        print("resume of finished run shows RUN COMPLETE:", "RUN COMPLETE" in txt4)
        if "Board 2/3" not in txt2 or "RUN COMPLETE" not in txt4:
            sys.exit(1)
        txt3 = Drive(["--resume", "CH12R-1-8.9.10-q-1/2"], ["w"])
        print("bad-resume rejected:", "bad run code" in txt3)
        sys.exit()
    Fails = []
    def Expect(ok, text):
        print(("ok   " if ok else "FAIL ") + text)
        if not ok:
            Fails.append(text)
    for run in range(30001, 30200):
        keys, state = Keys(run)
        if keys:
            break
    print("scripted run", run, "keys", len(keys), "expected code", state.Code(), "PICK", os.environ.get("PICK"))
    txt = Drive(["--run", str(run)], keys + ["w", "w", "w"], wait=0.15)
    Expect("RUN COMPLETE" in txt, "run complete screen shown")
    Expect(state.Code() in txt, "printed code matches expected")
    Expect(len(re.findall(r"BOARD \d CLEARED", txt)) >= 1, "board cleared screens shown")
    Expect(len(re.findall(r"\[\d\] (Rebound|Blast|Second Chance)", txt)) >= 3, "draft offers shown")
    Expect("[0] Skip" in txt, "skip line shown")
    if os.environ.get("PICK") == "s":
        Expect(len(re.findall(r"Second Chance: [^\n]{0,50}", txt)) >= 1, "Second Chance feedback shown in drive output")
        print("feedback samples:", sorted(set(re.findall(r"Second Chance: [^\n]{0,50}", txt)))[:3])
    full = state.Code().split("-")
    mid = "-".join(full[:3]) + "-" + full[3][:1] + "-" + "/".join(full[4].split("/")[:2])
    txt2 = Drive(["--resume", mid], ["w", "w"])
    Expect("Board 2/3" in txt2, "resume mid-run shows board 2")
    txt3 = Drive(["--resume", "CH12R-1-8.9.10-q-1/2"], ["w"])
    Expect("bad run code" in txt3 or "error" in txt3.lower(), "bad resume rejected")
    txt5 = Drive(["--text", "--resume", mid], ["w"])
    Expect("cannot be combined" in txt5, "text plus resume rejected")
    small = Drive(["--run", "1"], ["w"], cols=90, rows=30)
    Expect("Window too small" in small, "small window message")
    quitdraft = Drive(["--run", "1"] if False else ["--run", str(run)], [k for k in keys[:keys.index("n") + 1]] + ["w", "w", "q", "w"])
    Expect("Pick one upgrade" in quitdraft or "BOARD 1 CLEARED" in quitdraft, "reached draft or clear screen before quit test")
    Expect("Run code (continue later" in quitdraft or "CH12R-" in quitdraft, "q on draft quits and prints code")
    restart = Drive(["--run", "1"], ["w", "r", "w", "w"])
    Expect("restarted" in restart, "restart message shown")
    if Fails:
        sys.exit(1)
