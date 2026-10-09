"""Reproducible balance numbers. Usage: python3 BalanceCH19.py [first_seed] [count]
Defaults: seeds 30001..30300. Policy = PlayRun from ChainTest15.py (unmodified).
Prints runs complete, boards played/won, Overdrive earned, and a random-aim baseline."""
import sys, os, random
Here = os.path.dirname(os.path.abspath(__file__))
First = int(sys.argv[1]) if len(sys.argv) > 1 else 30001
Count = int(sys.argv[2]) if len(sys.argv) > 2 else 300
sys.argv = ["x"]
src = open(os.path.join(Here, "ChainTest15.py")).read().split("bad = collections.Counter()")[0]
exec(compile(src, "ChainTest15.py", "exec"))
complete = played = won = earned = 0
for seed in range(First, First + Count):
    state, board, starts, done = PlayRun(seed, random.Random(seed))
    boards = state.Boards + ([board] if board not in state.Boards else [])
    for b in boards:
        played += 1; won += 1 if b.Won() else 0; earned += 1 if b.OverGiven else 0
    complete += 1 if done else 0
print("policy runs %d (seeds %d..%d): complete %d, boards played %d, won %d, Overdrive earned %d (%.1f%% of boards played)"
      % (Count, First, First + Count - 1, complete, played, won, earned, 100.0 * earned / max(1, played)))
rw = 0
for seed in range(First, First + Count):
    r = random.Random(seed)
    st = E.RunState(seed); b = E.Attach(E.RunBoard(seed, 1, dict(st.Satchel)), st)
    while not b.Over():
        b.Play(r.randrange(len(E.Directions)), None, "n")
    rw += 1 if b.Won() else 0
print("random aim, normal balls only, board 1 of each seed: won %d of %d" % (rw, Count))
