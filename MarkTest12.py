import sys, os, re, random, pty, time, select, struct, fcntl, termios, importlib.util
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec); Spec.loader.exec_module(E)
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
class S:
    def __init__(self, **kw):
        self.Mono = False; self.Reduced = False; self.Fast = False; self.Delay = 30; self.LastSkipped = False; self.Watching = False
        self.__dict__.update(kw)
Check(E.LargeShotPoints == 1500, "threshold constant is 1500")
Check(not E.ScoreMarkWanted(S(), 1499) and E.ScoreMarkWanted(S(), 1500) and E.ScoreMarkWanted(S(), 2670), "1499 no mark, 1500 and 2670 mark")
for name, kw in (("mono", {"Mono": True}), ("reduced", {"Reduced": True}), ("fast", {"Fast": True}), ("skip", {"LastSkipped": True}), ("delay 0", {"Delay": 0}), ("watch", {"Watching": True})):
    Check(not E.ScoreMarkWanted(S(**kw), 5000), "no mark in " + name)
sys.argv = ["x"]
exec(open(os.path.join(Here, "ChainTest12.py")).read().split("bad = collections.Counter()")[0])
rng = random.Random(1); b = E.RunBoard(144, 1, {"r": 1, "x": 1})
steps = []; aim = E.DefaultAim; pts = []
for _ in range(3):
    left = E.ShotLimit + b.Extra - len(b.Log); a, h = Policy(b, rng); k = Kind(b, h, left); sh = b.Play(a, None, k)
    keys = (["R"] * (a - aim) if a > aim else ["L"] * (aim - a)); aim = a
    if k != "n": keys.append(str("nrxs".index(k) + 1))
    steps.append(keys + ["SP"]); pts.append(sh.Points)
print("expected shot points", pts)
Check(pts[0] < 1500 and pts[1] >= 1500 and pts[2] < 1500, "fixture: shot 1 small, shot 2 large, shot 3 small")
Esc = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")
def Drive(args, plan):
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(Here); os.execvp("python3", ["python3", "ChainDemo.py", "--run", "144"] + args)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 110, 0, 0))
    buf = b""; marks = []
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
    def LastFrame():
        parts = buf.split(b"\x1b[H")
        return parts[-1] if len(parts) > 1 else b""
    Pump(0.8)
    for item in plan:
        if isinstance(item, tuple):
            os.write(fd, {"SP": b" ", "R": b"\x1b[C", "L": b"\x1b[D"}.get(item[0], item[0].encode())); Pump(item[1])
        elif item == "snap":
            marks.append(b"\x1b[1;97mScore" in LastFrame())
    try: os.write(fd, b"q")
    except OSError: pass
    Pump(0.3)
    return marks
def Plan(extraBefore, wait, skipLarge=False):
    plan = [(k, 0.05) for k in extraBefore]
    for i, keys in enumerate(steps):
        for k in keys[:-1]: plan.append((k, 0.03))
        if skipLarge and i == 1:
            plan.append(("SP", 0.05)); plan.append(("x", 0.3)); plan.append("snap")
        else:
            plan.append(("SP", wait)); plan.append("snap")
        if i == 1:
            plan.append(("p", 0.3)); plan.append("snap"); plan.append(("p", 0.3))
    return plan
Normal = Drive(["--delay", "2", "--ascii"] if False else ["--delay", "2"], Plan([], 4.0))
print("colour delay 2 snaps (after shot1, shot2, next key, shot3):", Normal)
Check(Normal == [False, True, False, False], "colour: no mark after small, mark after large shot, cleared on next key, none after next small shot")
Check(not any(Drive(["--delay", "2", "--mono"], Plan([], 4.0))), "mono: never marked")
Check(not any(Drive(["--delay", "2", "--reduced"], Plan([], 4.0))), "reduced: never marked")
Check(not any(Drive(["--delay", "0"], Plan([], 1.0))), "delay 0: never marked")
Check(not any(Drive(["--delay", "2"], Plan(["f"], 3.0))), "fast key: never marked")
spAim = None
sim = E.RunBoard(144, 1, {"r": 1, "x": 1}); simRng = random.Random(1)
for _ in range(2):
    left = E.ShotLimit + sim.Extra - len(sim.Log); a2, h2 = Policy(sim, simRng); k2 = Kind(sim, h2, left); sim.Play(a2, None, k2); spAim = a2
repeat = sim.Play(spAim, None, "n")
print("space route fixture: repeat shot at the same aim scores", repeat.Points)
Check(repeat.Points < 1500, "fixture: the shot fired by space after the large one is below 1500")
def Route(key):
    plan = []
    for j, keys in enumerate(steps[:2]):
        for k in keys[:-1]: plan.append((k, 0.03))
        plan.append(("SP", 4.0))
    plan.append("snap")
    plan.append((key, 4.0 if key == "SP" else 0.5)); plan.append("snap")
    return Drive(["--delay", "2"], plan)
for key in ("L", "R", "p", "f", "1", "2", "n", "r", "z", "SP"):
    snaps = Route(key)
    print("route", repr(key), snaps)
    Check(snaps[0] is True, "route " + repr(key) + ": mark present before the key")
    Check(snaps[1] is False, "route " + repr(key) + ": mark gone after the key" + (" (next shot fully completed first, below 1500)" if key == "SP" else ""))
ctl = Drive(["--delay", "10"], Plan([], 6.0))
print("control delay 10 no skip", ctl)
Check(ctl[1] is True, "control at delay 10 without a key during the shot: mark present")
sk = Drive(["--delay", "10"], Plan([], 0.4, skipLarge=True))
print("skip drive delay 10", sk)
Check(sk[1] is False, "same shot with an actual key during animation: no mark")
if Fails: sys.exit(1)
