# CHAIN Marathon mode - design spec (round 1 of the new standing order)

Status: approved direction (William via main, 2026-10-17 21:51). This is the spec; build follows in the same round.

## What it is
A long-form mode next to the standard 3-board run: boards keep coming until the
player fails a quota. First failed board ends the marathon. Score accumulates
across boards; the record is boards cleared plus total score.

## Measured before-numbers
Board solvability grid (policy bot, normal balls only, n=300 per cell, seeds
30001..30300; bot rates measure solvability, not human odds):

quota\shots    5       6       7       8
q7           94.3%   99.3%  100.0%  100.0%
q8           83.0%   96.0%   99.3%  100.0%
q9           71.3%   87.3%   95.0%   98.0%
q10          55.0%   76.3%   87.0%   94.7%
q11          33.7%   52.7%   69.7%   79.7%
q12          12.3%   23.7%   33.0%   45.0%

Current state being fixed: one session is exactly 3 boards (quotas 9/10/10, 8
shots), then the game ends; one saved number (local best total).

## The curve (pinned as CH23M)
quota(k): 8,8, 9,9, 10,10, 11,11, then 12 (clear all) from board 9 on.
shots(k): 8 on boards 1-6, 7 on boards 7-12, 6 from board 13 on.

Simulated with drafts and satchel carry-over (policy bot, n=200 runs, seeds
30001..30200):
- Curve A (chosen): median 9 boards, mean 10.0, p10 7, p90 14; 99% reach 5
  boards, 47% reach 10, 9% reach 15.
- Curve B (rejected, gentler): median 11, mean 11.2, 79% reach 10 - too flat,
  no real wall.
Curve A gives a reliable early game, a real wall at the clear-all tier, and a
long tail for great runs. Bot numbers are solvability, not human difficulty.

## Rules
- Entry: [M] on the title screen ("marathon run"). Same board physics and
  shapes; board k seed = RunBoardSeed(run, k), same derivation as runs.
- Satchel starts {"r":1,"x":1} and carries across boards; after each won board
  the same 3-offer draft as runs (or skip). This is the progression reward.
- Board k: quota = MarathonQuota(k), base shots = MarathonShotLimit(k); dock
  and Overdrive bonus shots add on top as usual.
- First lost board ends the marathon: "MARATHON OVER - N boards cleared,
  total score T", plus the marathon code (replays/resumes the attempt).
- Best marathon (boards cleared, then total score) saves to ChainMarathon.txt
  next to the game (CHAIN_MARATHON_FILE overrides), shown on the end screen.
- Restart (r) restarts the marathon from board 1 keeping marathon mode; the
  old marathon code prints on quit (same convention as runs).

## Codes and compatibility
- Marathon codes: CH23M-<run>-<picks>-<shots> (quotas are a pure function of
  the board number, pinned per prefix, so they are not encoded).
- No change to board generation. CH23/CH23R and CH21/CH21R codes replay
  byte-identically; VersionTest23.py and RestartTest23.py must pass unchanged.
- CH23M parses only as a marathon code; CH23R only as a run code; each parser
  rejects the other's prefix.

## Tests (MarathonTest23.py)
- Curve values at boundaries (boards 1,2,3,8,9,12,13,20).
- Logic-level marathon playthrough with code round-trip via ResumeRun
  (state digests match), n runs over seeds.
- Resume keeps marathon mode; a marathon code mid-run resumes to the right
  board, quota and shot limit.
- Restart keeps marathon mode and CH23M prefix.
- Per-board shot limit honored (Over at limit+Extra).
- Cross-parser rejection both ways.
- Best file: read/write/corrupt-file handling.

## Out of scope this round (approved, later rounds)
- CH24 generator: per-shape difficulty spread + scatter-fallback outlier
  (24/3000 boards on CH22 seeds 30001..33000, 25% bot-won vs 53-81% named).
- Meta beyond the marathon best file (per-mode bests, stats, goals,
  score-attack board type, easier onboarding setting).
