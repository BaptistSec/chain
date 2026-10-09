import sys, os, random, hashlib, importlib.util
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec); Spec.loader.exec_module(E)
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
# Replay digest pinned from the CH18 engine over the same plays (CH17 value was e9f3620c...; layouts changed in CH18, so it moved).
CH17Digest = "e7cc97ad1f1f1753b16cc4a22ca01ff4ff217846d8449180f05569d319d97400"
Limit = E.Width * E.CellCols
digest = hashlib.sha256()
worst = 0; shots = 0; reward = 0; kinds = {}; bad = []; levels = {l: 0 for l in range(6)}
for seed in range(30001, 30301):
    rng = random.Random(seed)
    st = E.RunState(seed); b = E.Attach(E.RunBoard(seed, 1, dict(st.Satchel)), st)
    b.Stock["s"] = 3  # give Second Chance balls so every ball kind is exercised
    while not b.Over():
        k = "n"
        if rng.random() < 0.5:
            opts = [c for c in "rxs" if b.Stock.get(c, 0) > 0]
            if opts: k = rng.choice(opts)
        shot = b.Play(rng.randrange(len(E.Directions)), None, k)
        shots += 1
        kinds[k] = kinds.get(k, 0) + 1
        msg = E.ShotMessage(b, shot)
        worst = max(worst, len(msg))
        lvl = next((l for l in range(6) if hasattr(E, 'ShotText') and E.ShotText(b, shot, l) == msg), 0)
        levels[lvl] += 1
        head = "Shot " + str(len(b.Log)) + ": +" + str(shot.Points)
        ok = len(msg) <= Limit and msg.startswith(head)
        if shot.Rally > 1: ok = ok and ("(rally x" + str(shot.Rally) + ")") in msg
        if shot.Overdrive:
            reward += 1; ok = ok and "OVERDRIVE: +1 rebound ball" in msg
        if shot.Bonus: ok = ok and ("+" + str(shot.Bonus) + " free shot" in msg or "+" + str(shot.Bonus) + " shot" in msg)
        if shot.Kind == "s": ok = ok and "Second Chance" in msg
        if not ok: bad.append(msg)
    digest.update((b.Hash() + "|" + str(len(b.Log))).encode())
Check(not bad, "every message fits %d columns and keeps score, rally and reward text (%d shots, %d with Overdrive, worst %d, kinds %s, levels used %s)" % (Limit, shots, reward, worst, kinds, levels))
if bad: print("first bad:", bad[0])
got = digest.hexdigest()
print("replay digest", got)
Check(CH17Digest == "PINNED" or got == CH17Digest, "engine replay hashes identical to the CH18 pin on seeds 30001..30300")
# meter flash: draw only, same visible text with and without the flash, no colour in Mono
import re
def Strip(x): return re.sub("\x1b\\[[0-9;]*[A-Za-z]", "", x)
Seed = None
for seed in range(1, 400):
    st = E.RunState(seed); b = E.Attach(E.RunBoard(seed, 1, dict(st.Satchel)), st); rng = random.Random(seed)
    while not b.Over() and not b.OverGiven:
        b.Play(rng.randrange(len(E.Directions)), None, "n")
    if b.OverGiven: Seed = seed; break
Check(Seed is not None, "found a board with Overdrive earned for the flash check")
if Seed:
    for mono in (False, True):
        scr = E.Screen(mono, 0, False)
        a = scr.Frame(b, 20, False, None, "x", False, {})
        f = scr.Frame(b, 20, False, None, "x", False, {"meter": True})
        ha = [l for l in a if "Overdrive" in l][0]; hf = [l for l in f if "Overdrive" in l][0]
        Check(Strip(ha) == Strip(hf) and len(Strip(hf)) <= 102, "meter flash leaves the HUD text unchanged and within 102 columns (mono=%s)" % mono)
        if mono: Check("\x1b" not in hf, "no colour codes in mono mode")
        else: Check(ha != hf, "flash changes the colour of the meter in colour mode")
print("FAILS", len(Fails))
sys.exit(1 if Fails else 0)
