CHAIN satchel prototype, design draft 7 (replaces drafts 5 and 6 for the CH10 prototype)

Scope: an isolated 3-board run. Not a release. Not shown to be fun for people. The numbers behind it come from automated aim policies, not human play.

Run
- 3 boards per run, 2 drafts. Each board has 10 base shots and 12 physical targets.
- Quota per board: 8, 9, 10 credits. A board is won when the earned credits reach the quota, checked after the full shot including settle. Targets may still be standing.
- Internally the engine uses an offset of 12 minus the quota. The offset is not earned credits. The HUD shows earned credits, which start at 0, as "Credits C/Q", with 0 <= C <= Q and 1 <= Q <= 12. Overshoot shows C = Q.
- Each cleared target is 1 credit. Normal scoring, bumper, bomb and heart-peg rules are unchanged.

Balls and charges
- Start satchel: Rebound x1, Blast x1, Second Chance x0.
- A special ball is fired instead of a normal ball and uses 1 charge. Charges refill at the start of each board. A draft pick adds 1 charge of that ball from the next board on.
- Rebound: bounces off the floor once. Blast: 11x11 blast and flies on.
- Second Chance: normal physics. After the full shot and settle, if it cleared 0 or 1 target, the base shot is refunded (one extra shot). If it cleared 2 or more targets, there is no refund; normal target, score and heart rewards still happen. The charge is spent either way. Tradeoff in one line: it is a safety net for a weak shot and a wasted charge on a strong one.
- Heart pegs still give a free shot once each. A Second Chance refund and heart-peg bonuses add together, each counted once.
- Finite attempt bound per board: 10 + Second Chance charges in stock at the start of the board + heart pegs on that board.

Draft
- After a won board, the offer is all three upgrades (+1 Rebound, +1 Blast, +1 Second Chance), listed in a rotated order set by (run x 31 + k) mod 3 for draft k. There is no random bag and no five-ball pool.
- Quit or lose: a loss ends the run. n starts the next run number. r restarts the same run from board 1 with score and satchel reset, and the old run code is shown first.

Feedback (exact)
- "Second Chance: 0 targets cleared, shot refunded" or "Second Chance: 1 target cleared, shot refunded"
- "Second Chance: 2+ targets, no refund"
- Beats: x3 to x5 rally and "1 credit to clear" crossing are drawing-only and capped at 120 ms per shot at the default delay (scaled by the delay setting, 0 at delay 0). --reduced turns them off.

Run code and resume
- CH10R-<run>-<quotas>-<picks>-<shots board 1>/<shots board 2>/<shots board 3>. Shots are the aim number, with r, x or s after it for a special ball. --resume CODE replays it and continues. Codes from CH9 scratch builds are rejected.

Evidence limits
- Win-rate and branch tables are builder-reported from an aim policy that sees the preview and a 2-shot rollout heuristic. They show Blast is the strongest forced upgrade, Rebound is close under strong play, and Second Chance gives a smaller gain (+16 and +17 wins of 200 over no upgrade in the rollout runs). Most next-board outcomes tie.
- Not tested: human play, a real Windows console, colour frames by eye.

## Revision 7a (after QA fix list)
- Draft screen shows "(have N, after pick N+1)" and "[0] Skip: take no upgrade". Skip is pick 0 in the run code.
- HUD line reads "Second Chance refunds N  Heart shots H" (N = refunds, H = other extra shots).
- Result controls are run-aware: loss gives n new run and r restart run; win gives n pick upgrade; last board gives n finish run. Restart prints the old code when you quit, not in a cut-off message.
- CLI: --run must be 1 to 1000000000; --run and --resume cannot be combined with each other or with --text, --code, --check, --replay, --bot, --script, --board, --headless. --resume validates the code before starting. Run codes are limited to 1200 characters, 3 boards, 40 shots per board, 3-digit aims.
- Tests assert and exit nonzero. Inert test asserts fast, skip, reduced, delay 0 and the per-delay cap (0.12 draw-seconds at delay 30, scaled by delay/30).
- Not claimed: that drafting is interesting or proven. Not tested: real Windows console, human play, colour frames by eye.
- --run 0 is rejected explicitly (default is no run, not 0). Play.bat uses --run 1 only when given no arguments.
- q or esc on the draft screen quits the run (0 is the separate skip key).
- There is no unused-shot bonus in CH10. Run score is the sum of the three board scores; the old fixed bonus from earlier designs is not part of this spec.
