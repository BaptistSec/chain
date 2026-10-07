# CHAIN

A terminal game in Python. Aim a cannon, fire a ball into a board of pegs, and set off chain reactions. No third-party packages; Python 3 required.

This is a test board (version CH2), not the full game.

## Play

You need Python 3 ([python.org](https://www.python.org/downloads/); on Windows tick "Add python.exe to PATH").

- **Windows:** keep `ChainDemo.py`, `Play.bat` and `PlayText.bat` in one folder and double-click `Play.bat`. If the window says the console does not support colour, double-click `PlayText.bat` instead (plain text mode, you type an aim number).
- **Linux or macOS:** open a terminal in the folder and run `python3 ChainDemo.py`. Linux tested; macOS untested.

The board is big. The window needs at least 104 columns and 47 rows. `Play.bat` tries to resize it. On Linux or macOS, enlarge the terminal or shrink the font.

## Goal

Clear all 16 targets (`#`) in 10 shots.

| Symbol | What it does |
| --- | --- |
| `o` `+` | Plain pegs. They pop when hit. |
| `#` | Target. Clear them all to win. |
| `B` | Bomb. Pops its neighbours and chains into bombs next to it. |
| `*` | Bumper. Breaks on the 3rd hit, counted across shots. |
| `/` `\` | Mirrors. |

After a shot, loose pegs (`o` and `+`) fall into the gaps. If 3 or more of the same kind touch after falling, they pop, and pop targets next to them, and that can repeat.

## Keys

| Key | Action |
| --- | --- |
| left / right, or `a` / `d` | Change the aim (39 angles) |
| space or enter | Fire |
| `p` | Preview line on or off |
| `f` | Ball animation off, for fast play |
| `r` | Restart the same board |
| `n` | Next board |
| `q` | Quit and print your result and board code |

## Options

```
python3 ChainDemo.py --seed 7
python3 ChainDemo.py --code CODE
python3 ChainDemo.py --check CODE --show
python3 ChainDemo.py --text
python3 ChainDemo.py --mono --delay 0
python3 ChainDemo.py --selftest
```

- `--seed N` starts board N. A date such as `--seed 20261007` gives a shared daily board.
- `--code CODE` loads a shared board code.
- `--check CODE` prints a headless replay result. Add `--show` to print the board too.
- `--text` plain text mode. `--mono` turns colour off. `--delay 0` makes the ball instant.
- `--log` (interactive or `--text` play only, off unless you ask) adds your result to `ChainLog.txt` in the folder you run from when you quit after firing at least one shot. It does not log `--check` replays.
- `--selftest` runs a built-in repeatability check.

## Known limits

- git ZIP downloads give LF line endings for the .bat launchers. Use the release ZIP for the exact tested files.
- On Windows, `python` may be a shortcut to the Microsoft Store without a working interpreter. If the launcher opens the Store or fails, install Python from python.org.
- Not tested on a real Windows console: the animated mode, the arrow keys and how smooth the screen feels. It has been tested on Linux, and an earlier build was checked in Windows CI.
- Some rebounds (side walls, bumpers, mirrors) add downward drift, and a 1,200-step limit stops any very long shot. About 0.7% of random shots still reach that limit.

## Licence

MIT. See [LICENSE](LICENSE).
