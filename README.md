# CHAIN

A terminal game in Python. Aim a cannon, fire a ball into a board of pegs and targets, and earn credits to clear three boards in a row. Python 3 standard library only.

**Status: work in progress, updated about every three hours.** This is a visible working copy, not a release. Everything below is builder-reported from my own automated tests. Not AI-proof. Not tested: a real Windows console, a person playing a full run, colour by a human eye (I render the frames to images and look at them, and a separate reviewer checks them).

## Play

Needs Python 3 and a terminal at least 104 columns by 47 rows.

- Linux or macOS: `python3 ChainDemo.py --run 1` (any run number from 1 to 1000000000)
- Windows: put `ChainDemo.py`, `Play.bat` and `PlayText.bat` in one folder and double-click `Play.bat`. Windows is untested.

`HowToRun.txt` has the keys and rules. Keys: left/right aim, space fires, 1 to 4 choose the ball, p preview, f fast, r restart run, n next, q quit.

## What a run is

Three boards. You need to earn a quota of credits on each (8, 9, 10; one credit per target cleared) using 10 base shots. After boards 1 and 2 you pick an upgrade (Rebound, Blast or Second Chance, +1 charge each) or skip. The run code printed on exit replays the whole run, and `--resume CODE` continues it.

## Screenshots

Rendered from the real frames by `AnsiPng.py` (a small converter from terminal colour codes to an image).

- `screenshots/board-start.png`: a fresh board with the aim preview.
- `screenshots/one-shot-sequence.png`: five moments of one shot, with the rally message and the credits bar filling.
- `screenshots/draft.png`: the upgrade pick screen (example state, not a real run score).

## Tests

All the `Chain*`, `Inert*`, `Pty*`, `Width*`, `Stale*` and `Mark*` scripts assert and exit non-zero on failure. They are my own tests, so treat results as builder-reported. `PtyDrive10.py` plays whole runs through a real pseudo-terminal.

## Notes

- The version string in the game is CH10. This copy is the CH10 rules plus small drawing-only changes (coloured rally and last-credit messages, a highlighted credits bar on the last credit, and bold score after a 1500+ point shot). Physics, scores and run codes are the same as CH10.
- `chain-satchel-design-draft7a.md` is the design note.
- Earlier README text (version CH2) is replaced.
