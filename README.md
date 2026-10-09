# CHAIN

A terminal game in Python. Aim a cannon, fire a ball into a board of pegs and targets, and clear every board in a run. Python 3 standard library only.

**Status: work in progress.** Version CH15.  CH15 spreads the 12 targets across the board instead of in clusters. Everything below is builder-reported from my own automated tests. Not AI-proof. Not tested: a real Windows console, a person playing a full run, colour by a human eye.

## Run it

- Linux or macOS: `python3 ChainDemo.py --menu`
- Windows: keep `ChainDemo.py`, `Play.bat` and `PlayText.bat` in one folder and double-click `Play.bat`. Windows is untested.

The terminal needs at least 104 columns by 48 rows. `HowToRun.txt` has the keys and rules.

## What a run is

Three boards. Earn the credit quota on each (9, 10, 10; one credit per target cleared) within 8 base shots (dock and heart bonus shots can add more). A dock sweeps the floor: land the ball in it for a free shot and +400 (first 2 catches per board). Press D on the menu for the daily run. The run code printed on exit replays the whole run; codes from CH14 and earlier no longer work.


## Tests

The `*15` scripts (`ChainTest15.py`, `DockTest15.py`, `KeyTest15.py` and the rest) assert and exit non-zero on failure. They are my own tests, so treat results as builder-reported. `PtyDrive15.py` plays whole runs through a real pseudo-terminal.
