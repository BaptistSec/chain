# CHAIN

A terminal game in Python. Aim a cannon, fire a ball into a board of pegs and targets, and earn credits to clear three boards in a row. Python 3 standard library only.

**Status: work in progress, updated about every three hours.** This is a visible working copy, not a release. Everything below is builder-reported from my own automated tests. Not AI-proof. Not tested: a real Windows console, a person playing a full run, colour by a human eye (I render the frames to images and look at them, and a separate reviewer checks them).

## Play

Needs Python 3 and a terminal at least 104 columns by 47 rows.

- Linux or macOS: `python3 ChainDemo.py --menu` (any run number from 1 to 1000000000)
- Windows: put `ChainDemo.py`, `Play.bat` and `PlayText.bat` in one folder and double-click `Play.bat`. Windows is untested.

`HowToRun.txt` has the keys and rules. Keys: left/right aim, space fires, 1 to 4 choose the ball, p preview, f fast, r restart run, n next, q quit.

## What a run is

Three boards. You need to earn a quota of credits on each (8, 9, 10; one credit per target cleared) using 10 base shots. After boards 1 and 2 you pick an upgrade (Rebound, Blast or Second Chance, +1 charge each) or skip. The run code printed on exit replays the whole run, and `--resume CODE` continues it.

## Screenshots

Rendered from the real frames by `AnsiPng.py` (a small converter from terminal colour codes to an image).

- `screenshots/2-board-start.png`: a fresh board with the aim preview.
- `screenshots/4-one-shot-sequence.png`: five moments of one shot, with the rally message and the credits bar filling.
- `screenshots/3-draft.png`: the upgrade pick screen (example state, not a real run score).

## Tests

All the `Chain*`, `Inert*`, `Pty*`, `Width*`, `Stale*` and `Mark*` scripts assert and exit non-zero on failure. They are my own tests, so treat results as builder-reported. `PtyDrive10.py` plays whole runs through a real pseudo-terminal.

## Notes

- The version string in the game is CH10. This copy is the CH10 rules plus small drawing-only changes (coloured rally and last-credit messages, a highlighted credits bar on the last credit, and bold score after a 1500+ point shot). Physics, scores and run codes are the same as CH10.
- `chain-satchel-design-draft7a.md` is the design note.
- Earlier README text (version CH2) is replaced.

## Update 8 Oct, 13:55

- Version CH13 (QA passed on its own checks: not exhaustive, no human play, no Windows console).
- Ball physics: gravity pulls the ball down and every wall, peg, bumper, mirror and floor bounce costs it 10% of its speed, so a shot loses energy and ends instead of pinging forever.
- Title screen with a short premise, a how to play page and a menu. Start it with `--menu` (Play.bat does).
- Daily run: press D on the menu. The run number is today's local date, so the same date gives the same starting boards. Share your run code to compare; there is no online leaderboard. TitleTest13.py checks the menu.
- CH14: a dock sweeps the floor (gold line). Land the ball in it for a free shot and +400, first 2 catches per board. Quotas are 9/10/10 with 8 shots, key presses are shown as colour chips like [Space]. Saved CH13 run codes no longer work in CH14. Tests: DockTest15, KeyTest15 and the other *15 files (builder-reported, not human play, not real Windows console).
- Local best: the run-complete screen shows your best total across completed runs and saves it to ChainBest.txt next to the game (local file only, written safely, never follows links). BestTest13.py checks it.
- Layout: every board gets 16 extra pegs in the lower rows so the bottom of the field is no longer empty.
- Tests for this version are the *13 scripts (ChainTest13 and the others). The *10 and *12 test files are older versions kept from earlier pushes and will fail against CH13 on purpose, because codes carry the version.
- Not AI-proof. Not tested by me: a real Windows console, a person playing a full run, colour by eye.
