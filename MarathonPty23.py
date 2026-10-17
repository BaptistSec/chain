"""Drives a real marathon through a pseudo-terminal: menu [M] key, full boards
with scripted policy aims, draft picks, the MARATHON OVER screen, the CH23M
code, and the ChainMarathon.txt best file. Asserts and exits non-zero on failure."""
import pty, os, sys, time, select, struct, fcntl, termios, re, random, tempfile
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
Spec = __import__("importlib.util").util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
import importlib.util
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec)
Spec.loader.exec_module(E)
exec(open(os.path.join(Here, "MarathonTest23.py")).read().split("# 1. The pinned curve")[0])

def Drive(args, keys, cols=110, rows=50, wait=0.15, tail=1.0):
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(Here)
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

def MarathonKeys(run):
    rng = random.Random(run)
    state = E.RunState(run, marathon=True)
    board = E.Attach(E.RunBoard(run, 1, state.Satchel, marathon=True), state)
    keys = []; aim = E.DefaultAim; wonBoards = []
    while True:
        while not board.Over():
            left = board.Limit + board.Extra - len(board.Log)
            a, hit = Policy(board, rng)
            kind = Kind(board, hit, left)
            d = a - aim
            keys += ["R"] * d if d > 0 else ["L"] * (-d)
            aim = a
            if kind != "n":
                keys.append(str("nrxs".index(kind) + 1))
            keys += ["SP", "w", "w", "w"]
            board.Play(a, None, kind)
        if not board.Won():
            return keys, state, board, wonBoards
        wonBoards.append(board)
        state.Boards.append(board)
        choice = rng.randrange(4)
        pick = E.RunOffer(run, state.K)[choice] if choice < 3 else "0"
        state.Picks.append(pick)
        if pick != "0":
            state.Satchel[pick] = state.Satchel.get(pick, 0) + 1
        keys += ["w", "w", "n", "w", "w"]
        keys += ["0" if pick == "0" else str(E.RunOffer(run, state.K).index(pick) + 1), "w", "w"]
        state.K += 1
        board = E.Attach(E.RunBoard(run, state.K, state.Satchel, marathon=True), state)

Fails = []
def Expect(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok:
        Fails.append(text)

run = None
for cand in range(30001, 30080):
    rng = random.Random(cand)
    st, bd = PlayMarathon(cand, rng)
    if 3 <= st.K - 1 <= 6:
        run = cand
        break
assert run, "no marathon of length 3..6 found in seeds 30001..30080"
keys, state, lastBoard, wonBoards = MarathonKeys(run)
code = state.Code(lastBoard)
cleared = len(state.Boards)
total = sum(b.Score for b in state.Boards) + lastBoard.Score
print("scripted marathon", run, "boards cleared", cleared, "keys", len(keys), "expected code", code)

bestPath = os.path.join(tempfile.mkdtemp(), "ChainMarathon.txt")
os.environ["CHAIN_MARATHON_FILE"] = bestPath
menu = Drive(["--menu"], ["w", "w"])
Expect("[M] marathon" in menu, "menu offers marathon")
menuGo = Drive(["--menu"], ["w", "w", "m", "w", "w", "w"])
Expect("Marathon board 1" in menuGo or " Marathon board 1" in menuGo.replace("\n", " "), "m starts a marathon")
txt = Drive(["--marathon", str(run)], ["w", "w"] + keys + ["w", "w", "n", "w", "w", "q", "w", "w"])
Expect("Marathon board 2" in txt, "marathon board 2 reached")
Expect("Pick one upgrade" in txt, "draft offers shown in marathon")
Expect("MARATHON OVER" in txt, "marathon over screen shown")
Expect((" " + str(cleared) + " ") in txt.split("MARATHON OVER")[1][:80] if "MARATHON OVER" in txt else False, "cleared count matches")
Expect(code in txt, "printed marathon code matches expected")
Expect("Local best marathon:" in txt, "best line shown")
try:
    savedBest = open(bestPath).read().strip()
except OSError:
    savedBest = ""
Expect(savedBest == str(cleared) + "," + str(total), "best file holds " + str(cleared) + "," + str(total) + " (got " + repr(savedBest) + ")")
if Fails:
    sys.exit(1)
print("PASS")
