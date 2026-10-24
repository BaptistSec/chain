#!/usr/bin/env python3
"""CHAIN web UI - a localhost graphical surface over the ChainDemo engine.

    python3 ChainWeb.py                 serve and open the browser
    python3 ChainWeb.py --no-browser    serve only, print the link
    python3 ChainWeb.py --port 8765     pin a port (default: a free one)

The server listens on 127.0.0.1 only and every request needs the per-launch
token in the URL it prints, so no other process or machine can drive the game.
All rules, physics, run codes and records come from ChainDemo unchanged: the
browser is a renderer and input device, the Python engine stays the referee.
"""
import json
import os
import secrets
import stat
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ChainDemo as E

TOKEN = secrets.token_urlsafe(12)

def SessionPath():
    return os.environ.get("CHAIN_SESSION_FILE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "ChainSession.json")

def ReadSessionCodes(path):
    """The menu's recovery codes, if a previous session saved them. Anything
    unreadable or malformed simply means no saved codes; startup never fails."""
    try:
        with open(path) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return "", []
    if not isinstance(data, dict):
        return "", []
    last = data.get("lastCode", "")
    old = data.get("oldCodes", [])
    if not isinstance(last, str):
        last = ""
    if not isinstance(old, list):
        old = []
    return last, [c for c in old if isinstance(c, str)][-5:]

def WriteSessionCodes(path, last, old):
    folder = os.path.dirname(path) or "."
    temp = os.path.join(folder, ".chainsess-" + os.urandom(8).hex() + ".tmp")
    created = False
    try:
        if os.path.lexists(path) and not stat.S_ISREG(os.lstat(path).st_mode):
            return False
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        created = True
        with os.fdopen(descriptor, "w") as handle:
            handle.write(json.dumps({"lastCode": last, "oldCodes": list(old)[-5:]}) + "\n")
        os.replace(temp, path)
        return True
    except OSError:
        if created:
            try:
                os.unlink(temp)
            except OSError:
                pass
        return False


def BoardJson(board, state=None):
    grid = [[x, y, s] for (x, y), s in sorted(board.Grid.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
    return {
        "seed": board.Seed if isinstance(board.Seed, int) else 0,
        "hash": board.Hash(),
        "grid": grid,
        "bumps": {str(c[0]) + "," + str(c[1]): h for c, h in board.Bumps.items()},
        "jackpot": list(board.Jackpot) if board.Jackpot else None,
        "stock": dict(board.Stock),
        "score": board.Score,
        "credit": board.Credit,
        "quota": getattr(board, "Quota", None),
        "total": board.Total,
        "targetsLeft": board.TargetsLeft(),
        "dockPaid": board.DockPaid,
        "shots": len(board.Log),
        "extra": board.Extra,
        "limit": board.Limit,
        "streak": board.Streak,
        "meter": board.Meter,
        "overdrive": bool(board.OverGiven),
        "over": board.Over(),
        "won": board.Won(),
        "dock": E.DockX(E.DockPhase * len(board.Log)),
        "run": state.Run if state else None,
        "k": state.K if state else None,
        "marathon": bool(state and state.Marathon),
        "code": state.Code(board) if state else None,
        "style": board.Style,
    }



def ShotData(board, state, aim, kind, gen, shot_id):
    """One shot with the animation hook: the exact payload the client replays.
    Shared by live play (Shoot) and spectating (WatchNext)."""
    logBefore = len(board.Log)
    frames = []
    events = []
    timeline = []
    prev = dict(board.Grid)

    def hook(x, y, cells=None, kind=None):
        if x is None:
            ev = {"e": kind, "cells": [[c[0], c[1], s] for c, s in sorted(cells.items())]}
            events.append({"kind": kind, "cells": ev["cells"]})
            timeline.append(ev)
        else:
            gone = [[c[0], c[1], s] for c, s in prev.items() if c not in board.Grid]
            if gone:
                timeline.append({"e": "hit", "cells": sorted(gone)})
            prev.clear()
            prev.update(board.Grid)
            frames.append([x, y])
            timeline.append({"b": [x, y], "d": E.DockX(board.Live.Steps + E.DockPhase * logBefore)})

    shot = board.Play(aim, hook, kind)
    return {
        "frames": frames,
        "events": events,
        "timeline": timeline,
        "gen": gen,
        "shotId": shot_id,
        "dockStart": E.DockX(E.DockPhase * logBefore),
        "dockEnd": E.DockX(shot.Steps + E.DockPhase * logBefore),
        "shot": {"aim": shot.Aim, "kind": shot.Kind, "points": shot.Points,
                 "targets": shot.Targets, "rally": shot.Rally, "chain": shot.Chain,
                 "mult": shot.Mult, "caught": shot.Caught, "paid": shot.Paid,
                 "refund": shot.Refund, "overdrive": shot.Overdrive,
                 "jackpot": shot.Jackpot, "steps": shot.Steps, "floorX": shot.FloorX},
        "message": E.ShotMessage(board, shot),
        "board": BoardJson(board, state),
    }


class Session:
    """One player's game. All rules go through the ChainDemo engine."""

    def __init__(self):
        self.lock = threading.Lock()
        self.selftest = None
        self.gen = 0
        self.shot_seq = 0
        self.pending_shot = 0
        self.screen = "title"
        self.state = None
        self.board = None
        self.busy = False
        self.offer = None
        self.result = None
        self.message = ""
        self.last_code, self.old_codes = ReadSessionCodes(SessionPath())
        self._codes_saved = (self.last_code, tuple(self.old_codes))
        self.watch = None

    def _save_codes(self):
        snap = (self.last_code, tuple(self.old_codes))
        if snap != self._codes_saved:
            WriteSessionCodes(SessionPath(), self.last_code, self.old_codes)
            self._codes_saved = snap

    def Records(self):
        best, _ = E.ReadBest(E.BestPath())
        mBoards, mTotal, _ = E.ReadMarathonBest(E.MarathonBestPath())
        return {"bestRun": best, "bestMarathonBoards": mBoards, "bestMarathonScore": mTotal}

    def StateJson(self):
        data = {"screen": self.screen, "message": self.message, "gen": self.gen}
        if self.screen == "title":
            data["records"] = self.Records()
            data["daily"] = E.DailyLabel()
            data["oldCodes"] = list(self.old_codes)
            data["lastCode"] = self.last_code
        if self.board is not None and self.screen != "title":
            data["board"] = BoardJson(self.board, self.state)
        if self.screen == "draft":
            data["offer"] = self.offer
            data["notes"] = {"r": "Rebound: bounces off the floor once",
                             "x": "Blast: big blast, flies on",
                             "s": "Second Chance: refunds the shot if it clears 0 or 1 target"}
            data["satchel"] = dict(self.state.Satchel)
            data["code"] = self.state.Code(self.board)
        if self.screen in ("gameover", "complete") and self.result:
            data["result"] = self.result
        return data

    def Start(self, mode):
        with self.lock:
            if mode not in ("run", "marathon", "daily"):
                return None, "unknown mode"
            marathon = mode == "marathon"
            run = E.DailyRun() if mode == "daily" else E.random.SystemRandom().randint(1, E.MaxRunNumber)
            self.state = E.RunState(run, marathon=marathon)
            self.board = E.Attach(E.RunBoard(run, 1, self.state.Satchel, False, marathon, False), self.state)
            self.screen = "play"
            self.result = None
            self.busy = False
            self.old_codes = []
            self.last_code = ""
            self.watch = None
            self._save_codes()
            self.gen += 1
            self.message = ("Marathon board 1   quota " + str(self.board.Quota) + " of " + str(self.board.Total) + ", " + str(self.board.Limit) + " shots" if marathon
                            else "Board 1 of " + str(len(E.RunQuotas)))
            return self.StateJson(), None

    def Resume(self, code):
        with self.lock:
            try:
                self.state, self.board = E.ResumeRun(code.strip())
            except (ValueError, KeyError, IndexError) as exc:
                return None, "That run code did not load: " + str(exc)
            self.screen = "play"
            self.result = None
            self.busy = False
            self.old_codes = []
            self.last_code = ""
            self.watch = None
            self._save_codes()
            self.gen += 1
            self.message = "Resumed run " + str(self.state.Run)
            if self.board.Over():
                # A quit-at-draft code resumes with the board already won and the
                # pick still pending; a finished code resumes already over. Route
                # exactly like a resolved shot instead of trapping the board in play.
                self.Resolve()
            return self.StateJson(), None

    def Preview(self, aim, ball):
        with self.lock:
            if self.screen != "play" or self.board is None or self.board.Over():
                return {"path": []}
            if not 0 <= aim < len(E.Directions):
                return {"path": []}
            path = self.board.Trace(aim, ball)
            return {"path": [list(p) for p in path]}

    def Shoot(self, aim, ball):
        with self.lock:
            if self.screen != "play" or self.board is None:
                return None, "no board in play"
            if self.busy:
                return None, "busy"
            if self.board.Over():
                return None, "board is over"
            if ball not in ("n", "r", "x", "s"):
                return None, "unknown ball"
            if ball != "n" and self.board.Stock.get(ball, 0) <= 0:
                return None, "No " + E.KindNames[ball] + " balls left"
            if not isinstance(aim, int) or not 0 <= aim < len(E.Directions):
                return None, "bad aim"
            self.busy = True
            self.shot_seq += 1
            self.pending_shot = self.shot_seq
            return ShotData(self.board, self.state, aim, ball, self.gen, self.pending_shot), None

    def Watch(self, code):
        """Spectate a run code shot by shot. The whole code is validated up front
        with the engine's own ResumeRun; play then advances lazily, one shot per
        WatchNext, through the same ShotData payload live play uses. Watching
        never touches records, the satchel offer, or any run in progress:
        it only enters from the menu (or re-enters while already watching),
        so a live run is never displaced and its recovery code stays good."""
        with self.lock:
            if self.screen not in ("title", "watch"):
                return None, "finish or quit your current run before watching"
            text = code.strip()
            try:
                E.ResumeRun(text)
                run, picks, chunks, legacy, marathon, mid = E.ParseRunCodeFull(text)
            except (ValueError, KeyError, IndexError) as exc:
                return None, "That run code did not load: " + str(exc)
            state = E.RunState(run, legacy, marathon, mid)
            board = E.Attach(E.RunBoard(run, 1, state.Satchel, legacy, marathon, mid), state)
            self.watch = {"state": state, "board": board, "picks": picks, "chunks": chunks,
                          "legacy": legacy, "marathon": marathon, "mid": mid,
                          "ci": 0, "si": 0, "done": False}
            self.state = None
            self.board = None
            self.screen = "watch"
            self.result = None
            self.busy = False
            self.gen += 1
            self.message = "Watching " + ("marathon " if marathon else "run ") + str(run)
            data = self.StateJson()
            data["board"] = BoardJson(board, state)
            return data, None

    def WatchNext(self):
        """Advance the spectated run: the next shot, a board-cleared hop, or the end."""
        with self.lock:
            if self.screen != "watch" or self.watch is None:
                return None, "nothing to watch"
            if self.busy:
                return None, "busy"
            w = self.watch
            if w["done"]:
                return None, "watch is over"
            board = w["board"]
            state = w["state"]
            if board.Over():
                if board.Won() and w["ci"] < len(w["chunks"]) - 1:
                    state.Boards.append(board)
                    pick = w["picks"][w["ci"]]
                    state.Picks.append(pick)
                    if pick != "0":
                        state.Satchel[pick] = state.Satchel.get(pick, 0) + 1
                    cleared, score = state.K, board.Score
                    state.K += 1
                    w["board"] = E.Attach(E.RunBoard(state.Run, state.K, state.Satchel, w["legacy"], w["marathon"], w["mid"]), state)
                    w["ci"] += 1
                    w["si"] = 0
                    data = self.StateJson()
                    data["board"] = BoardJson(w["board"], state)
                    data["watchAdvance"] = {"cleared": cleared, "score": score, "pick": pick}
                    return data, None
                if board.Won():
                    state.Boards.append(board)
                w["done"] = True
                open_ = board.Won() and (w["marathon"] or state.K < len(E.RunQuotas))
                self.message = ("Watch finished - the run continues from the code" if open_
                                else "Watch finished - run complete, all " + str(len(state.Boards)) + " boards cleared" if board.Won()
                                else "Watch finished - marathon over, " + str(len(state.Boards)) + " boards cleared" if w["marathon"]
                                else "Watch finished - the run ends here")
                data = self.StateJson()
                data["board"] = BoardJson(board, state)
                data["watchDone"] = {"won": board.Won(), "boardsCleared": len(state.Boards),
                                     "total": sum(b.Score for b in state.Boards) + (0 if board.Won() else board.Score),
                                     "marathon": w["marathon"], "open": open_}
                data["message"] = self.message
                return data, None
            if w["si"] >= len(w["chunks"][w["ci"]]):
                w["done"] = True
                self.message = "Watch finished - the run continues from the code"
                data = self.StateJson()
                data["board"] = BoardJson(board, state)
                data["watchDone"] = {"won": False, "boardsCleared": len(state.Boards),
                                     "total": sum(b.Score for b in state.Boards) + board.Score,
                                     "marathon": w["marathon"], "open": True}
                data["message"] = self.message
                return data, None
            aim, kind = w["chunks"][w["ci"]][w["si"]]
            w["si"] += 1
            self.busy = True
            self.shot_seq += 1
            self.pending_shot = self.shot_seq
            return ShotData(board, state, aim, kind, self.gen, self.pending_shot), None

    def WatchDone(self, gen=None, shot_id=None):
        """Client finished watching a spectated shot; releases the busy gate."""
        with self.lock:
            if gen != self.gen or shot_id != self.pending_shot or not self.busy:
                return self.StateJson()
            self.busy = False
            self.pending_shot = 0
            return self.StateJson()

    def Done(self, gen=None, shot_id=None):
        """Client finished watching the shot; only now may the next one fire.
        Completion binds the exact shot, not just the run generation: a done
        from before a restart/quit/advance is stale, and a duplicate or
        retried done for an older shot must not clear a newer shot's busy."""
        with self.lock:
            if gen != self.gen or shot_id != self.pending_shot or not self.busy:
                return self.StateJson()
            self.busy = False
            self.pending_shot = 0
            if self.screen == "play" and self.board is not None and self.board.Over():
                self.Resolve()
            return self.StateJson()

    def Resolve(self):
        board, state = self.board, self.state
        if state is None:
            return
        if board.Won():
            if state.Marathon or state.K < len(E.RunQuotas):
                self.offer = E.RunOffer(state.Run, state.K)
                self.screen = "draft"
            else:
                state.Boards.append(board)
                total = sum(b.Score for b in state.Boards)
                best, isNew, saved = E.RecordBest(total)
                self.result = {"kind": "complete", "boards": len(state.Boards), "total": total,
                               "best": best, "isNew": isNew, "saved": saved,
                               "code": state.Code(), "next": E.NextRunNumber(state.Run)}
                self.screen = "complete"
        elif state.Marathon:
            state.Boards.append(board)
            cleared = len(state.Boards) - 1
            total = sum(b.Score for b in state.Boards)
            best, isNew, saved = E.RecordMarathonBest(cleared, total)
            self.result = {"kind": "marathonover", "cleared": cleared, "total": total,
                           "bestBoards": best[0], "bestScore": best[1], "isNew": isNew, "saved": saved,
                           "code": state.Code(), "next": E.NextRunNumber(state.Run)}
            self.screen = "gameover"
        else:
            self.result = {"kind": "runover", "score": board.Score, "k": state.K,
                           "code": state.Code(board), "next": E.NextRunNumber(state.Run)}
            self.screen = "gameover"

    def Pick(self, choice):
        with self.lock:
            if self.screen != "draft" or self.offer is None:
                return None, "no upgrade on offer"
            if choice in ("1", "2", "3"):
                pick = self.offer[int(choice) - 1]
            elif choice == "0":
                pick = "0"
            else:
                return None, "bad pick"
            state, board = self.state, self.board
            state.Boards.append(board)
            state.Picks.append(pick)
            if pick != "0":
                state.Satchel[pick] = state.Satchel.get(pick, 0) + 1
            state.K += 1
            self.board = E.Attach(E.RunBoard(state.Run, state.K, state.Satchel, state.Legacy, state.Marathon, state.Mid), state)
            self.offer = None
            self.screen = "play"
            self.gen += 1
            self.message = ("Marathon board " + str(state.K) + "   quota " + str(self.board.Quota) + " of " + str(self.board.Total) + ", " + str(self.board.Limit) + " shots" if state.Marathon
                            else "Board " + str(state.K) + " of " + str(len(E.RunQuotas)))
            return self.StateJson(), None

    def Advance(self):
        """The [any key] button on the game-over and run-complete screens."""
        with self.lock:
            if self.screen not in ("gameover", "complete") or self.result is None:
                return None, "nothing to advance to"
            state = self.state
            if self.result["kind"] == "marathonover":
                self.state = E.RunState(E.NextRunNumber(state.Run), marathon=True)
                self.board = E.Attach(E.RunBoard(self.state.Run, 1, self.state.Satchel, False, True), self.state)
                self.message = "New marathon " + str(self.state.Run)
            else:
                self.state = E.RunState(E.NextRunNumber(state.Run))
                self.board = E.Attach(E.RunBoard(self.state.Run, 1, self.state.Satchel, False, False, False), self.state)
                self.message = "New run " + str(self.state.Run)
            self.screen = "play"
            self.result = None
            self.gen += 1
            return self.StateJson(), None

    def Restart(self):
        with self.lock:
            if self.state is None:
                return None, "no run to restart"
            old = self.state.Code(self.board)
            s = self.state
            self.old_codes = (self.old_codes + [old])[-5:]
            self._save_codes()
            self.state = E.RunState(s.Run, s.Legacy, s.Marathon, s.Mid)
            self.board = E.Attach(E.RunBoard(s.Run, 1, self.state.Satchel, s.Legacy, s.Marathon, s.Mid), self.state)
            self.screen = "play"
            self.result = None
            self.busy = False
            self.gen += 1
            self.message = ("Marathon restarted from board 1, score and satchel reset. The old marathon code shows on the menu." if s.Marathon
                            else "Run restarted from board 1, score and satchel reset. The old run code shows on the menu.")
            data = self.StateJson()
            data["oldCode"] = old
            return data, None

    def Quit(self):
        with self.lock:
            code = self.state.Code(self.board) if self.state is not None and self.board is not None else ""
            if code:
                self.last_code = code
            self._save_codes()
            self.watch = None
            self.screen = "title"
            self.state = None
            self.board = None
            self.result = None
            self.busy = False
            self.gen += 1
            data = self.StateJson()
            data["quitCode"] = code
            return data


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CHAIN</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg: #1b2027; --panel: #232a33; --panel2: #2a323d; --edge: #3a4450;
    --text: #d7dee6; --dim: #8b98a5; --accent: #39c2d7; --gold: #ffd24a;
    --good: #5fd787; --bad: #ff5f5f; --violet: #d75fff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: Verdana, Geneva, sans-serif; font-size: 14px; }
  #app { max-width: 1000px; margin: 0 auto; padding: 10px 12px 14px; }
  .hidden { display: none !important; }

  /* title screen */
  #title { text-align: center; padding-top: 6vh; }
  #title h1 {
    font-size: clamp(44px, 21vw, 84px); letter-spacing: clamp(6px, 3.5vw, 14px); color: var(--accent);
    text-shadow: 0 2px 0 #166070, 0 4px 12px rgba(0,0,0,.6);
    font-family: "Trebuchet MS", Verdana, sans-serif; margin-bottom: 2px;
  }
  #title .tag { color: var(--dim); margin-bottom: 34px; }
  .menu { display: inline-block; text-align: left; max-width: 100%; }
  .menu button {
    display: block; width: 320px; max-width: 100%; margin: 7px 0; padding: 10px 14px;
    background: var(--panel); color: var(--text); border: 1px solid var(--edge);
    border-radius: 4px; font-size: 15px; text-align: left; cursor: pointer;
  }
  .menu button:hover, .menu button.hot { background: var(--panel2); border-color: var(--accent); }
  .menu .k { color: var(--accent); font-weight: bold; margin-right: 10px; }
  #records { margin-top: 26px; color: var(--gold); }
  #quitcode { margin-top: 14px; color: var(--dim); font-family: Consolas, monospace; font-size: 12px; word-break: break-all; }
  #oldcodes { margin-top: 6px; color: var(--dim); font-family: Consolas, monospace; font-size: 12px; word-break: break-all; }
  #resumeRow { margin-top: 22px; }
  #resumeRow input {
    width: min(300px, 100%); padding: 7px 9px; background: var(--panel); border: 1px solid var(--edge);
    border-radius: 4px; color: var(--text); font-family: Consolas, monospace; font-size: 12px;
  }
  #resumeRow button { padding: 7px 12px; background: var(--panel); color: var(--accent); border: 1px solid var(--edge); border-radius: 4px; cursor: pointer; }
  #title .foot { margin-top: 26px; color: var(--dim); font-size: 12px; }
  #startErr { color: var(--bad); margin-top: 10px; min-height: 18px; }

  /* game screen */
  #hud { display: flex; justify-content: space-between; align-items: baseline; padding: 4px 2px 8px; }
  #hud .who { color: var(--dim); }
  #hud .who b { color: var(--text); font-weight: normal; }
  #hud .score { font-size: 20px; color: var(--gold); font-family: Consolas, monospace; text-align: right; }
  @keyframes lowpulse { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
  .lowshots { animation: lowpulse 1.1s infinite; }
  #stage { position: relative; }
  canvas#board { display: block; box-sizing: content-box; background: #10141a; border: 1px solid var(--edge); border-radius: 6px; }
  #msg { min-height: 18px; padding: 5px 2px 2px; color: var(--text); }
  #msg .pts { color: var(--gold); }
  #bar { display: flex; justify-content: space-between; align-items: center; padding-top: 8px; flex-wrap: wrap; gap: 8px; }
  #balls .ball {
    display: inline-block; margin-right: 6px; padding: 5px 10px; border: 1px solid var(--edge);
    border-radius: 4px; background: var(--panel); cursor: pointer; color: var(--dim);
  }
  #balls .ball .k { color: var(--accent); font-weight: bold; margin-right: 6px; }
  #balls .ball.sel { border-color: var(--gold); color: var(--text); }
  #balls .ball.empty { opacity: .38; cursor: default; }
  #keys { color: var(--dim); font-size: 12px; }
  #keys b { color: var(--accent); font-weight: bold; }
  #keys .tc { display: none; }
  #balls .wc { display: none; }
  @media (pointer: coarse) { #keys .kb { display: none; } #keys .tc { display: inline; } #balls .wc { display: inline; } }

  /* overlays */
  .overlay {
    position: absolute; inset: 0; background: rgba(16,20,26,.82);
    display: flex; align-items: flex-start; justify-content: center; border-radius: 6px;
    overflow-y: auto; overflow-x: hidden;
  }
  .overlay .sheet { margin: auto; }
  .overlay-fixed {
    position: fixed; inset: 0; background: rgba(16,20,26,.92); z-index: 30;
    display: flex; align-items: flex-start; justify-content: center; overflow-y: auto; padding: 4vh 12px;
  }
  .sheet {
    background: var(--panel); border: 1px solid var(--edge); border-radius: 8px;
    padding: 26px 30px; min-width: min(380px, calc(100vw - 24px)); max-width: min(640px, calc(100vw - 24px)); text-align: center;
    box-shadow: 0 10px 40px rgba(0,0,0,.5);
  }
  .sheet h2 { font-size: 22px; letter-spacing: 2px; margin-bottom: 14px; color: var(--accent); }
  .sheet h2.gold { color: var(--gold); }
  .sheet p { margin: 6px 0; }
  .sheet .big { font-size: 26px; color: var(--gold); font-family: Consolas, monospace; }
  .sheet .code { font-family: Consolas, monospace; font-size: 12px; color: var(--dim); word-break: break-all; margin-top: 10px; }
  .sheet .row { margin-top: 18px; }
  .sheet button {
    padding: 9px 16px; margin: 0 5px; background: var(--panel2); color: var(--text);
    border: 1px solid var(--edge); border-radius: 4px; cursor: pointer; font-size: 14px;
  }
  .sheet button:hover { border-color: var(--accent); }
  .sheet button .k { color: var(--accent); font-weight: bold; margin-right: 6px; }
  .cue {
    position: absolute; width: 26px; height: 26px; display: none; pointer-events: none;
    background: var(--panel); border: 1px solid var(--edge); border-radius: 50%;
    box-shadow: 0 2px 8px rgba(0,0,0,.55);
  }
  .cue.on { display: block; }
  .cue::after {
    content: ""; position: absolute; left: 50%; top: 44%; width: 8px; height: 8px;
    border-right: 2px solid var(--accent); border-bottom: 2px solid var(--accent);
    transform: translate(-50%, -50%) rotate(45deg);
  }
  .card {
    display: inline-block; width: 176px; vertical-align: top; margin: 8px 6px 0; padding: 14px 12px;
    background: var(--panel2); border: 1px solid var(--edge); border-radius: 6px; cursor: pointer;
  }
  .card:hover { border-color: var(--gold); }
  .card .k { color: var(--accent); font-weight: bold; font-size: 16px; }
  .card .name { font-weight: bold; margin: 6px 0 4px; }
  .card .what { color: var(--dim); font-size: 12px; min-height: 44px; }
  .card .have { color: var(--gold); font-size: 12px; margin-top: 6px; }
  #helpBody { text-align: left; }
  #helpBody h3 { color: var(--text); font-size: 14px; margin: 14px 0 4px; }
  #helpBody p { color: var(--dim); line-height: 1.5; }
  #helpBody b { color: var(--accent); font-weight: bold; }
  #helpBody .legend span { display: inline-block; margin: 3px 12px 3px 0; }
</style>
</head>
<body>
<div id="app">

  <div id="title">
    <h1>CHAIN</h1>
    <div class="tag">a game of falling charges</div>
    <div class="menu" id="menu">
      <button data-act="run"><span class="k">Enter</span>Start a run</button>
      <button data-act="marathon"><span class="k">M</span>Marathon</button>
      <button data-act="daily"><span class="k">D</span>Daily run <span id="daily"></span></button>
      <button data-act="help"><span class="k">H</span>How to play</button>
    </div>
    <div id="records"></div>
    <div id="quitcode"></div>
    <div id="oldcodes"></div>
    <div id="resumeRow">
      <input id="resumeCode" placeholder="paste a run code to continue">
      <button id="resumeBtn">Continue</button>
      <button id="watchBtn">Watch</button>
    </div>
    <div id="startErr"></div>
    <div class="foot">Same local date, same starting boards. Share your run code to compare; there is no online leaderboard.</div>
  </div>

  <div id="game" class="hidden">
    <div id="hud">
      <span class="who" id="who"></span>
      <span id="stats"></span>
      <span class="score" id="score">0</span>
    </div>
    <div id="stage">
      <canvas id="board" width="928" height="720"></canvas>
      <div id="draft" class="overlay hidden"></div>
      <div id="result" class="overlay hidden"></div>
    </div>
    <div id="msg"></div>
    <div id="bar">
      <span id="balls"></span>
      <span id="keys"><span class="kb"><b>&larr;</b><b>&rarr;</b> aim &nbsp;<b>Space</b> fire &nbsp;<b>P</b> preview &nbsp;<b>F</b> fast &nbsp;<b>R</b> restart &nbsp;<b>S</b> sound &nbsp;<b>Q</b> menu</span><span class="tc"><b>drag</b> aim &nbsp;<b>tap</b> fire</span></span>
    </div>
  </div>

  <div id="helpOv" class="overlay-fixed hidden"></div>

</div>
<script>/*__APP__*/
</script>
</body>
</html>
"""


APP_JS = r"""
var TOKEN = "__TOKEN__";
var CS = 18, OX = 14, OY = 24, W = 50, H = 38;
var FITS = {chrome: 142};
var DIRS = __DIRS__;
var S = {screen:"title", board:null, aim:19, ball:"n", preview:true, fast:false,
         playing:false, msg:"", dock:25, records:null, daily:"", gen:0};
var cv = document.getElementById("board"), ctx = cv.getContext("2d");
var gridMap = {}, ballPos = null, trail = [], popFx = [], pathDots = [], slideFx = [], catchFx = [], fxPump = false, flourishFx = [], recoilT = 0, shotCredits = 0, ambientT = 0, ambientOn = false, textFx = [];
var winFx = null;
var dimFx = null, dockRender = 25;
var arriveFx = null, wantArrive = false;
var scoreFx = null, scoreShown = 0, justArrived = false;
var lastBoardId = null;
function jackpotUp() { var b = S.board; return !!(b && b.jackpot && gridMap[b.jackpot[0]+","+b.jackpot[1]]); }
function ambientNeeded() { return S.screen === "play" && S.board && !S.board.over && (jackpotUp() || S.board.targetsLeft === 1); }
function ambientKick() {
  if (ambientOn) return;
  ambientOn = true;
  (function pump() {
    if (!ambientNeeded()) { ambientOn = false; return; }
    ambientT++;
    draw();
    setTimeout(pump, 90);
  })();
}
function ringActive() { return !!(S.board && !S.board.over && S.board.targetsLeft === 1); }
function lastTargetCells() { var out = []; for (var k in gridMap) { if (gridMap[k][2] === "#") out.push(gridMap[k]); } return out; }
function dockPipsLeft() { return S.board ? Math.max(0, 2 - (S.board.dockPaid || 0)) : 0; }
function popHeat(n) { return n <= 3 ? "255,210,74" : n <= 8 ? "255,175,0" : "255,95,208"; }
function winBurst(gen) {
  var n = 0;
  for (var k in gridMap) { var g = gridMap[k]; popFx.push({x: g[0], y: g[1], r: 5, a: 0.85, c: "255,210,74", g: gen}); n++; }
  winFx = {cells: n, a: 1, g: gen};
  startFxPump();
}
function kindRGB(kind) { return kind === "x" ? "255,95,95" : kind === "r" ? "255,175,0" : kind === "s" ? "135,255,135" : "57,194,215"; }
function shotTint() { return kindRGB((S.playing && S.shotKind) || "n"); }

function api(path, body) {
  return fetch(path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + TOKEN,
    body === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)})
    .then(function(r){ if(!r.ok) return r.json().then(function(e){throw e;}); return r.json(); });
}
function cellXY(x, y) { return [OX + x*CS, OY + y*CS]; }
function show(id, on) {
  document.getElementById(id).classList.toggle("hidden", !on);
  if (on) requestAnimationFrame(refreshCues);
}
/* scroll affordance: an accent chevron pinned at the bottom of an overlay while
   more content sits below; disappears at the end and when nothing overflows */
function refreshCues() {
  document.querySelectorAll(".overlay, .overlay-fixed").forEach(function(el) {
    if (el.classList.contains("hidden")) return;
    var cue = null;
    for (var i = 0; i < el.children.length; i++) if (el.children[i].className === "cue" || el.children[i].className === "cue on") cue = el.children[i];
    if (!cue) { cue = document.createElement("div"); cue.className = "cue"; el.appendChild(cue); }
    var more = el.scrollHeight - el.scrollTop - el.clientHeight > 4;
    cue.style.left = (el.scrollLeft + el.clientWidth - 40) + "px";
    cue.style.top = (el.scrollTop + el.clientHeight - 40) + "px";
    cue.className = more ? "cue on" : "cue";
  });
}
window.addEventListener("resize", refreshCues);
document.addEventListener("scroll", function(ev) {
  var t = ev.target;
  if (t && t.classList && (t.classList.contains("overlay") || t.classList.contains("overlay-fixed"))) refreshCues();
}, true);

/* ---------- sprites ---------- */
function drawCell(x, y, sym, bumps, jackpot) {
  var px = OX + x*CS, py = OY + y*CS, c = CS;
  ctx.save();
  if (arriveFx) {
    var ael = performance.now() - arriveFx.t - (y * 20 + (x % 4) * 14);
    if (ael < 0) { ctx.restore(); return; }
    if (ael < 130) ctx.globalAlpha = ael / 130;
  }
  if (sym === "#") {
    ctx.fillStyle = jackpot ? "#ff5fd0" : "#ffd24a";
    ctx.strokeStyle = jackpot ? "#a03090" : "#9a7d10";
    rr(px+1, py+1, c-2, c-2, 3); ctx.fill(); ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,.35)"; ctx.fillRect(px+3, py+3, c-6, 3);
    if (jackpot) { var pl = 1 + 0.18*Math.sin(ambientT*0.7);
      ctx.fillStyle = "rgba(255,95,208," + (0.10 + 0.08*Math.sin(ambientT*0.7)) + ")"; circ(px+c/2, py+c/2, c/2+2); ctx.fill();
      ctx.fillStyle = "#fff"; star(px+c/2, py+c/2, 5, 6*pl, 2.5*pl); ctx.fill(); }
  } else if (sym === "o" || sym === "+") {
    ctx.fillStyle = sym === "o" ? "#37c8e8" : "#c86ff0";
    ctx.strokeStyle = "rgba(0,0,0,.4)";
    if (sym === "o") { circ(px+c/2, py+c/2, c/2-2); ctx.fill(); ctx.stroke();
      ctx.fillStyle = "rgba(255,255,255,.45)"; circ(px+c/2-2, py+c/2-2.5, 2); ctx.fill(); }
    else { ctx.beginPath(); ctx.moveTo(px+c/2, py+1); ctx.lineTo(px+c-1, py+c/2);
      ctx.lineTo(px+c/2, py+c-1); ctx.lineTo(px+1, py+c/2); ctx.closePath(); ctx.fill(); ctx.stroke(); }
  } else if (sym === "*") {
    var left = 3 - (bumps || 0);
    ctx.strokeStyle = "#5fd787"; ctx.lineWidth = 2.5;
    circ(px+c/2, py+c/2, c/2-2.5); ctx.stroke();
    ctx.fillStyle = "#5fd787";
    for (var i = 0; i < left; i++) { circ(px + c/2 + (i-1)*5, py + c/2, 1.8); ctx.fill(); }
  } else if (sym === "B") {
    ctx.fillStyle = "#ff5f5f"; circ(px+c/2, py+c/2, c/2-3); ctx.fill();
    ctx.strokeStyle = "#a02020"; ctx.lineWidth = 1.5;
    for (var a = 0; a < 8; a++) { var t = a*Math.PI/4;
      ctx.beginPath(); ctx.moveTo(px+c/2+Math.cos(t)*(c/2-3), py+c/2+Math.sin(t)*(c/2-3));
      ctx.lineTo(px+c/2+Math.cos(t)*(c/2-1), py+c/2+Math.sin(t)*(c/2-1)); ctx.stroke(); }
    ctx.fillStyle = "#401010"; circ(px+c/2, py+c/2, 2.2); ctx.fill();
  } else if (sym === "F") {
    ctx.fillStyle = "#87ff87"; ctx.font = 'bold 14px Verdana, "DejaVu Sans", sans-serif'; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("\u2665", px+c/2, py+c/2+1);
  } else if (sym === "/" || sym === "\\") {
    ctx.strokeStyle = "#c8ccd2"; ctx.lineWidth = 3;
    ctx.beginPath();
    if (sym === "/") { ctx.moveTo(px+2, py+c-2); ctx.lineTo(px+c-2, py+2); }
    else { ctx.moveTo(px+2, py+2); ctx.lineTo(px+c-2, py+c-2); }
    ctx.stroke();
  }
  ctx.restore();
}
function rr(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x+r, y); ctx.arcTo(x+w, y, x+w, y+h, r); ctx.arcTo(x+w, y+h, x, y+h, r); ctx.arcTo(x, y+h, x, y, r); ctx.arcTo(x, y, x+w, y, r); ctx.closePath(); }
function circ(x, y, r) { ctx.beginPath(); ctx.arc(x, y, r, 0, 7); }
function star(cx, cy, n, ro, ri) { ctx.beginPath(); for (var i = 0; i < 2*n; i++) { var r = i%2 ? ri : ro, t = i*Math.PI/n - Math.PI/2; ctx[i ? "lineTo" : "moveTo"](cx+Math.cos(t)*r, cy+Math.sin(t)*r); } ctx.closePath(); }

/* ---------- board drawing ---------- */
function drawStyleEmblem(style) {
  if (!style) return;
  var base = style.replace(" mirrored", ""), cx = OX + W*CS/2, cy = OY + H*CS/2, R = H*CS*0.30;
  ctx.save();
  ctx.globalAlpha = 0.05; ctx.strokeStyle = "#39c2d7"; ctx.lineWidth = 10; ctx.lineJoin = "round";
  ctx.beginPath();
  if (base === "diamonds") {
    ctx.moveTo(cx, cy-R); ctx.lineTo(cx+R, cy); ctx.lineTo(cx, cy+R); ctx.lineTo(cx-R, cy); ctx.closePath();
  } else if (base === "waves") {
    for (var i = 0; i <= 40; i++) { var x = cx-R + 2*R*i/40, y = cy + Math.sin(i/40*Math.PI*3)*R*0.45; ctx[i ? "lineTo" : "moveTo"](x, y); }
  } else if (base === "chevrons") {
    ctx.moveTo(cx-R, cy-R*0.5); ctx.lineTo(cx, cy+R*0.5); ctx.lineTo(cx+R, cy-R*0.5);
    ctx.moveTo(cx-R, cy-R); ctx.lineTo(cx, cy); ctx.lineTo(cx+R, cy-R);
  } else if (base === "arches") {
    ctx.arc(cx, cy+R*0.6, R, Math.PI, 2*Math.PI);
  } else if (base === "rings" || base === "spiral") {
    ctx.arc(cx, cy, R, 0, 7); ctx.moveTo(cx+R*0.6, cy); ctx.arc(cx, cy, R*0.6, 0, 7);
    ctx.moveTo(cx+R*0.25, cy); ctx.arc(cx, cy, R*0.25, 0, 7);
  } else if (base === "funnel") {
    ctx.moveTo(cx-R, cy-R); ctx.lineTo(cx+R, cy-R); ctx.lineTo(cx+R*0.2, cy+R); ctx.lineTo(cx-R*0.2, cy+R); ctx.closePath();
  } else if (base === "stairs") {
    ctx.moveTo(cx-R, cy+R); ctx.lineTo(cx-R, cy+R*0.33); ctx.lineTo(cx-R*0.33, cy+R*0.33); ctx.lineTo(cx-R*0.33, cy-R*0.33);
    ctx.lineTo(cx+R*0.33, cy-R*0.33); ctx.lineTo(cx+R*0.33, cy-R); ctx.lineTo(cx+R, cy-R);
  } else if (base === "cross") {
    ctx.moveTo(cx, cy-R); ctx.lineTo(cx, cy+R); ctx.moveTo(cx-R, cy); ctx.lineTo(cx+R, cy);
  } else if (base === "zigzag") {
    ctx.moveTo(cx-R, cy-R*0.6); ctx.lineTo(cx-R*0.33, cy+R*0.6); ctx.lineTo(cx+R*0.33, cy-R*0.6); ctx.lineTo(cx+R, cy+R*0.6);
  } else if (base === "bowl") {
    ctx.arc(cx, cy-R*0.6, R, 0, Math.PI);
  } else if (base === "pinwheel") {
    for (var a = 0; a < 4; a++) { var t = a*Math.PI/2;
      ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(t)*R, cy + Math.sin(t)*R);
      ctx.lineTo(cx + Math.cos(t+0.6)*R*0.55, cy + Math.sin(t+0.6)*R*0.55); ctx.closePath(); }
  } else if (base === "columns") {
    for (var c2 = -2; c2 <= 2; c2++) { ctx.moveTo(cx + c2*R*0.45, cy-R); ctx.lineTo(cx + c2*R*0.45, cy+R); }
  }
  ctx.stroke();
  ctx.restore();
}
function draw() {
  ambientKick();
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (S.shake > 0.3) {
    ctx.save();
    ctx.translate((Math.random()-0.5)*S.shake, (Math.random()-0.5)*S.shake);
    S.shake *= 0.85;
  } else S.shake = 0;
  var b = S.board;
  if (b) drawStyleEmblem(b.style);
  var sliding = {};
  for (var sf = 0; sf < slideFx.length; sf++) sliding[slideFx[sf].x+","+slideFx[sf].y1] = true;
  for (var key in gridMap) { if (sliding[key]) continue; var g = gridMap[key]; drawCell(g[0], g[1], g[2], (b && b.bumps[key]) || 0, b && b.jackpot && b.jackpot[0] === g[0] && b.jackpot[1] === g[1]); }
  if (ringActive()) {
    var ra = 0.35 + 0.3*Math.sin(ambientT*0.7);
    ctx.strokeStyle = "rgba(255,210,74," + ra + ")"; ctx.lineWidth = 2;
    lastTargetCells().forEach(function(g) { circ(OX + g[0]*CS + CS/2, OY + g[1]*CS + CS/2, CS/2 + 2); ctx.stroke(); });
  }
  // floor + dock
  var fy = OY + H*CS;
  ctx.fillStyle = "#2a323d"; ctx.fillRect(OX, fy, W*CS, 6);
  if (b) {
    dockRender += (S.dock - dockRender) * 0.22; if (Math.abs(S.dock - dockRender) < 0.05) dockRender = S.dock;
    ctx.fillStyle = catchFx.length ? "#ffd24a" : "#ffaf00"; ctx.fillRect(OX + (dockRender-3)*CS, fy-1, 7*CS, 8);
      for (var dp = 0; dp < 2; dp++) { ctx.fillStyle = dp < dockPipsLeft() ? "#0d1117" : "rgba(13,17,23,.18)"; circ(OX + (dockRender - 1 + dp*2)*CS, fy+3, 2.5); ctx.fill(); } }
  // cannon + aim
  var cp = cellXY(25, 0), kick = recoilT > 0 ? -Math.min(recoilT, 4) : 0;
  if (recoilT > 0) recoilT--;
  ctx.fillStyle = "#d7dee6";
  ctx.beginPath(); ctx.moveTo(cp[0]+CS/2-7, OY-8+kick); ctx.lineTo(cp[0]+CS/2+7, OY-8+kick); ctx.lineTo(cp[0]+CS/2, OY+6+kick); ctx.closePath(); ctx.fill();
  if (S.screen === "play" && b && !b.over && !S.playing) {
    var v = DIRS[Math.max(0, Math.min(DIRS.length - 1, S.aim | 0))], len = Math.hypot(v[0], v[1]);
    ctx.strokeStyle = "rgba(215,222,230,.55)"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(cp[0]+CS/2, OY+4);
    ctx.lineTo(cp[0]+CS/2 + v[0]/len*34, OY+4 + v[1]/len*34); ctx.stroke();
    if (S.preview && pathDots.length) {
      for (var i = 0; i < pathDots.length; i += 2) {
        ctx.fillStyle = "rgba(57,194,215," + (0.75 - 0.6*i/pathDots.length) + ")";
        circ(OX + pathDots[i][0]*CS + CS/2, OY + pathDots[i][1]*CS + CS/2, 2); ctx.fill();
      }
    }
  }
  // ball + trail
  var tint = shotTint();
  for (var t = 0; t < trail.length; t++) {
    ctx.fillStyle = "rgba(" + tint + "," + (0.05 + 0.05*t) + ")";
    circ(OX + trail[t][0]*CS + CS/2, OY + trail[t][1]*CS + CS/2, 4); ctx.fill();
  }
  if (ballPos) {
    ctx.fillStyle = "rgba(" + tint + ",.22)"; circ(OX + ballPos[0]*CS + CS/2, OY + ballPos[1]*CS + CS/2, 10); ctx.fill();
    ctx.fillStyle = "#fff"; circ(OX + ballPos[0]*CS + CS/2, OY + ballPos[1]*CS + CS/2, 6.5); ctx.fill();
    ctx.strokeStyle = "rgba(" + tint + ",.8)"; ctx.lineWidth = 1.5; circ(OX + ballPos[0]*CS + CS/2, OY + ballPos[1]*CS + CS/2, 8.5); ctx.stroke();
  }
  // pop flashes
  for (var p = popFx.length-1; p >= 0; p--) {
    var f = popFx[p];
    if (f.g !== S.gen) { popFx.splice(p, 1); continue; }
    f.r += 0.9; f.a -= 0.06;
    if (f.a <= 0) { popFx.splice(p, 1); continue; }
    ctx.strokeStyle = "rgba(" + (f.c || "255,210,74") + "," + f.a + ")"; ctx.lineWidth = 2;
    circ(OX + f.x*CS + CS/2, OY + f.y*CS + CS/2, f.r); ctx.stroke();
  }
  // falling cells slide one row
  for (var s2 = slideFx.length-1; s2 >= 0; s2--) {
    var sl = slideFx[s2];
    if (sl.g !== S.gen) { slideFx.splice(s2, 1); continue; }
    sl.t += 0.34;
    if (sl.t >= 1) { slideFx.splice(s2, 1); drawCell(sl.x, sl.y1, sl.sym, 0, false); continue; }
    drawCell(sl.x, sl.y0 + (sl.y1 - sl.y0)*sl.t, sl.sym, 0, false);
  }
  // positional reward floaters
  for (var tf = textFx.length-1; tf >= 0; tf--) {
    var fx2 = textFx[tf];
    if (fx2.g !== S.gen) { textFx.splice(tf, 1); continue; }
    fx2.a -= 0.02; fx2.y -= 0.055;
    if (fx2.a <= 0) { textFx.splice(tf, 1); continue; }
    ctx.save();
    ctx.globalAlpha = Math.max(fx2.a, 0);
    ctx.font = 'bold 15px Verdana, "DejaVu Sans", sans-serif'; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    var tx = OX + fx2.x*CS + CS/2, ty = OY + fx2.y*CS;
    ctx.fillStyle = "#0d1117"; ctx.fillText(fx2.text, tx+1, ty+1);
    ctx.fillStyle = "rgba(" + fx2.rgb + ",1)"; ctx.fillText(fx2.text, tx, ty);
    ctx.restore();
  }
  if (dimFx && dimFx.g === S.gen && dimFx.a > 0.02) {
    ctx.fillStyle = "rgba(255,95,95," + (0.22 * dimFx.a) + ")";
    ctx.fillRect(OX, OY, W*CS, H*CS);
    dimFx.a *= 0.94;
  }
  if (winFx && winFx.g === S.gen && winFx.a > 0.02) {
    ctx.fillStyle = "rgba(255,210,74," + (0.30 * winFx.a) + ")";
    ctx.fillRect(OX, OY, W*CS, H*CS);
    winFx.a *= 0.93;
  }
  // end-of-shot flourish: engine's own shot facts, one line + points
  for (var fl = flourishFx.length-1; fl >= 0; fl--) {
    var fe = flourishFx[fl];
    if (fe.g !== S.gen) { flourishFx.splice(fl, 1); continue; }
    fe.a -= 0.02;
    if (fe.a <= 0) { flourishFx.splice(fl, 1); continue; }
    ctx.save();
    if (fe.a < 1) ctx.translate(0, (1-fe.a)*-18);
    ctx.globalAlpha = Math.max(fe.a, 0);
    ctx.font = 'bold 30px Verdana, "DejaVu Sans", sans-serif'; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = "#0d1117"; var cx2 = OX + W*CS/2, cy2 = OY + H*CS*0.42;
    ctx.fillText(fe.text, cx2+2, cy2+2);
    ctx.fillStyle = "#ffd24a"; ctx.fillText(fe.text, cx2, cy2);
    ctx.font = 'bold 15px Verdana, "DejaVu Sans", sans-serif'; ctx.fillStyle = "#d7dee6";
    ctx.fillText(fe.sub, cx2, cy2 + 26);
    ctx.restore();
  }
  // dock catch pulse
  for (var cf = catchFx.length-1; cf >= 0; cf--) {
    var f2 = catchFx[cf];
    if (f2.g !== S.gen) { catchFx.splice(cf, 1); continue; }
    f2.r += 1.4; f2.a -= 0.05;
    if (f2.a <= 0) { catchFx.splice(cf, 1); continue; }
    ctx.strokeStyle = "rgba(255,175,0," + f2.a + ")"; ctx.lineWidth = 3;
    circ(OX + f2.x*CS + CS/2, OY + H*CS - CS/2, f2.r); ctx.stroke();
  }
  if (S.shake) ctx.restore();
}
function syncGrid(grid) {
  gridMap = {};
  (grid || []).forEach(function(c) { gridMap[c[0]+","+c[1]] = c; });
}

/* ---------- HUD ---------- */
function renderHud() {
  var b = S.board;
  if (!b) return;
  var arrivedNow = justArrived; justArrived = false;
  var who = b.marathon ? ("marathon <b>" + b.run + "</b> · board <b>" + b.k + "</b>")
                       : ("run <b>" + b.run + "</b> · board <b>" + b.k + "</b> of <b>3</b>");
  document.getElementById("who").innerHTML = "CHAIN &nbsp;" + who + (b.style ? ' <span style="color:var(--dim)">(' + b.style + ")</span>" : "");
  var pips = "";
  for (var i = 0; i < b.limit; i++) pips += '<span style="color:' + (i < b.shots ? "var(--gold)" : "#3a4450") + '">&#9679;</span>';
  if (!b.over && b.limit + (b.extra || 0) - b.shots <= 2) pips = '<span class="lowshots">' + pips + "</span>";
  document.getElementById("stats").innerHTML =
    "targets <b>" + b.targetsLeft + "</b> / quota " + b.quota + " &nbsp; " + pips +
    (b.streak > 1 ? ' &nbsp; streak <b style="color:var(--good)">x' + Math.min(b.streak, 4) + "</b>" : "") +
    ' &nbsp; <span style="color:var(--dim)">od</span> ' + "#".repeat(b.meter) + "-".repeat(3 - b.meter);
  var scoreTgt = b.score;
  document.getElementById("score").style.minWidth = String(scoreTgt).length + "ch";
  if (!arrivedNow && !S.playing && scoreTgt > scoreShown && !(scoreFx && scoreFx.to === scoreTgt && scoreFx.g === S.gen)) {
    scoreFx = {from: scoreShown, to: scoreTgt, t: performance.now(), dur: 500, g: S.gen, bid: b.run + ":" + b.k};
    tickScore();
  } else if (arrivedNow || scoreTgt < scoreShown || !scoreFx || scoreFx.g !== S.gen) {
    scoreFx = null; showScore(scoreTgt);
  }
  if (S.screen === "watch") {
    document.getElementById("balls").innerHTML = '<span style="color:var(--gold)">WATCH</span>' +
      (S.watchAuto ? ' <span style="color:var(--dim)">auto</span>' : "") +
      '<span class="wc"><span class="ball" data-watch="next"><span class="k">next</span></span>' +
      '<span class="ball" data-watch="auto"><span class="k">auto</span></span>' +
      '<span class="ball" data-watch="menu"><span class="k">menu</span></span>' +
      '<span class="ball" data-snd="1"><span class="k sl">' + sndLabel() + "</span></span></span>";
    document.getElementById("keys").innerHTML = '<span class="kb"><b>Space</b> next &nbsp;<b>A</b> auto &nbsp;<b>F</b> fast &nbsp;<b>S</b> sound &nbsp;<b>Q</b> menu</span><span class="tc"><b>watching</b> replay</span>';
    var wchips = document.querySelectorAll("#balls .ball[data-watch]");
    for (var w = 0; w < wchips.length; w++) wchips[w].onclick = function() { watchTap(this.dataset.watch); };
    wireSnd(document.getElementById("balls"));
    document.getElementById("msg").innerHTML = S.msg || "";
    return;
  }
  document.getElementById("keys").innerHTML = '<span class="kb"><b>&larr;</b><b>&rarr;</b> aim &nbsp;<b>Space</b> fire &nbsp;<b>P</b> preview &nbsp;<b>F</b> fast &nbsp;<b>R</b> restart &nbsp;<b>S</b> sound' + (SND.on ? '' : ' off') + ' &nbsp;<b>Q</b> menu</span><span class="tc"><b>drag</b> aim &nbsp;<b>tap</b> fire</span>';
  var names = {n:"normal", r:"rebound", x:"blast", s:"second chance"};
  var html = "";
  ["n","r","x","s"].forEach(function(k, i) {
    var n = k === "n" ? "&infin;" : (b.stock[k] || 0);
    html += '<span class="ball' + (S.ball === k ? " sel" : "") + (k !== "n" && !b.stock[k] ? " empty" : "") +
            '" data-ball="' + k + '"><span class="k">' + (i+1) + "</span>" + names[k] + " " + n + "</span>";
  });
  html += '<span class="ball" data-snd="1"><span class="k sl">' + sndLabel() + "</span></span>";
  document.getElementById("balls").innerHTML = html;
  var chips = document.querySelectorAll("#balls .ball[data-ball]");
  for (var j = 0; j < chips.length; j++) chips[j].onclick = function() { pickBall(this.dataset.ball); };
  wireSnd(document.getElementById("balls"));
  document.getElementById("msg").innerHTML = S.msg || "";
}
function pickBall(k) {
  if (S.playing || !S.board || S.board.over) return;
  if (k !== "n" && !(S.board.stock[k] > 0)) { S.msg = "No " + k + " balls left"; sndDeny(); renderHud(); return; }
  if (k !== S.ball) sndSelect();
  S.ball = k; refreshPreview(); renderHud();
}

/* ---------- preview ---------- */
function refreshPreview() {
  if (!S.preview || !S.board || S.board.over || S.playing || S.screen !== "play") { pathDots = []; draw(); return; }
  api("/api/preview?aim=" + S.aim + "&ball=" + S.ball).then(function(d) { pathDots = d.path; draw(); });
}

/* ---------- shot playback ---------- */
/* sound: tiny synthesized WebAudio juice, no assets. Pops climb in pitch
   within a shot like the classic chain ramp; S toggles sound on any screen
   and the choice sticks in localStorage. Beeps are decision-logged so the
   client selftest can assert them without audible output. */
var SND = { ctx: null, gain: null, on: true, pops: 0, popFreqs: [], log: [], seq: 0 };
try { SND.on = localStorage.getItem("chainSound") !== "off"; } catch (e) {}
function ac() {
  if (!SND.ctx) {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (AC) { try { SND.ctx = new AC(); } catch (e) {} }
  }
  if (SND.ctx && !SND.gain) { SND.gain = SND.ctx.createGain(); SND.gain.gain.value = SND.on ? 1 : 0; SND.gain.connect(SND.ctx.destination); }
  if (SND.ctx && SND.ctx.state === "suspended") SND.ctx.resume();
  return SND.ctx;
}
function beep(f0, f1, dur, type, vol) {
  if (!SND.on) return;
  var c = ac(); if (!c) return;
  SND.log.push(Math.round(f0)); if (SND.log.length > 400) SND.log.shift();
  var o = c.createOscillator(), g = c.createGain(), t = c.currentTime;
  o.type = type || "sine";
  o.frequency.setValueAtTime(f0, t);
  if (f1 && f1 !== f0) o.frequency.exponentialRampToValueAtTime(f1, t + dur);
  g.gain.setValueAtTime(vol, t);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g); g.connect(SND.gain || c.destination);
  o.start(t); o.stop(t + dur);
}
function sndFire() { beep(160, 70, 0.09, "triangle", 0.18); }
function sndPop(n) {
  var st = Math.min(n, 24), f = Math.round(330 * Math.pow(2, st / 12));
  SND.popFreqs.push(f); beep(f, 0, 0.07, "sine", 0.10);
}
/* delayed notes play only if sound is still on AND the screen has not changed
   since they were scheduled: muting or leaving cuts a sting short cleanly */
function later(ms, fn) { var q = SND.seq; setTimeout(function() { if (SND.on && q === SND.seq) fn(); }, ms); }
function sndCatch() { beep(523, 0, 0.09, "sine", 0.12); later(90, function() { beep(784, 0, 0.12, "sine", 0.12); }); }
function sndWin() { [523, 659, 784, 1047].forEach(function(f, i) { later(i * 95, function() { beep(f, 0, 0.14, "triangle", 0.12); }); }); }
function sndLose() { [392, 330, 262].forEach(function(f, i) { later(i * 120, function() { beep(f, 0, 0.16, "sine", 0.10); }); }); }
function soon(ms, fn) { setTimeout(fn, ms); }
function sndPick() { beep(660, 0, 0.06, "sine", 0.10); soon(60, function() { if (S.screen === "draft" || S.screen === "play") beep(880, 0, 0.09, "sine", 0.10); }); }
function sndSelect() { beep(660, 0, 0.05, "sine", 0.07); }
function sndDeny() { beep(140, 100, 0.09, "sawtooth", 0.05); }
function sndJackpot() { [880, 1108, 1318].forEach(function(f, i) { later(150 + i * 80, function() { beep(f, 0, 0.12, "triangle", 0.10); }); }); }
function sndOver() { [392, 523, 659].forEach(function(f, i) { later(i * 70, function() { beep(f, 0, 0.12, "triangle", 0.12); }); }); }
function sndLabel() { return "sound " + (SND.on ? "on" : "off"); }
function sndToggle() {
  SND.on = !SND.on;
  try { localStorage.setItem("chainSound", SND.on ? "on" : "off"); } catch (e) {}
  if (SND.gain) SND.gain.gain.value = SND.on ? 1 : 0;
  document.querySelectorAll("[data-snd] .sl").forEach(function(n) { n.textContent = sndLabel(); });
  if (S.board) renderHud();
}
function wireSnd(root) { root.querySelectorAll("[data-snd]").forEach(function(n) { n.onclick = function() { sndToggle(); }; }); }
function revealBoard() { if (arriveFx) { arriveFx = null; draw(); } }
function fire() {
  if (S.playing || !S.board || S.board.over || S.screen !== "play") return;
  revealBoard(); S.playing = true; pathDots = []; recoilT = 6; sndFire();
  api("/api/shot", {aim: S.aim, ball: S.ball}).then(function(resp) {
    S.ball = "n"; S.lastShot = resp.shot;
    playShot(resp, function() {
      S.board = resp.board; syncGrid(resp.board.grid); S.dock = resp.board.dock;
      S.msg = resp.message; ballPos = null; trail = [];
      if (resp.shot && resp.shot.caught) { catchFx.push({x: resp.shot.floorX, r: 6, a: 0.95, g: resp.gen}); startFxPump(); sndCatch();
        if (resp.shot.paid) { textFx.push({x: resp.shot.floorX, y: H-2, text: "+400", rgb: "255,210,74", a: 1, g: resp.gen}); startFxPump(); } }
      var sh = resp.shot || {}, big = null, sub = "+" + sh.points;
      if (sh.jackpot) big = "JACKPOT";
      else if (sh.overdrive) big = "OVERDRIVE";
      else if (sh.paid) big = "CAUGHT IN THE DOCK";
      else if (sh.rally >= 3) big = "RALLY x" + sh.rally;
      else if (sh.mult >= 3) big = "STREAK x" + sh.mult;
      if (sh.rally >= 3 && big !== "RALLY x" + sh.rally) sub += "  rally x" + sh.rally;
      if (big) { flourishFx.push({text: big, sub: sub, a: 1, g: resp.gen}); startFxPump(); }
      if (big === "JACKPOT") sndJackpot();
      else if (big === "OVERDRIVE") sndOver();
      api("/api/done", {gen: resp.gen, shotId: resp.shotId}).then(function(st) { S.playing = false; applyState(st); });
    });
  }).catch(function(e) { S.playing = false; S.msg = e.error || "shot refused"; renderHud(); });
}
function applyShotEvent(ev, gen, blast) {
  if (ev.e === "fall") {
    // Engine gravity moves cells exactly one row per fall event, so the
    // previous rendered position is always (x, y-1); clear it or it ghosts.
    // Batch: in a same-column chain fall one cell's destination can be
    // another's origin, so delete every origin before setting any cell.
    ev.cells.forEach(function(c) { delete gridMap[c[0]+","+(c[1]-1)]; });
    ev.cells.forEach(function(c) {
      gridMap[c[0]+","+c[1]] = [c[0], c[1], c[2]];
      slideFx.push({x: c[0], y0: c[1]-1, y1: c[1], sym: c[2], t: 0, g: gen});
    });
    startFxPump();
    return;
  }
  ev.cells.forEach(function(c) {
    var key = c[0]+","+c[1];
    if (c[2] === "#") shotCredits++;
    sndPop(SND.pops++);
    if (c[2] === "F") textFx.push({x: c[0], y: c[1], text: "+1 shot", rgb: "135,255,135", a: 1, g: gen});
    else if (S.board && S.board.jackpot && c[0] === S.board.jackpot[0] && c[1] === S.board.jackpot[1]) textFx.push({x: c[0], y: c[1], text: "+500", rgb: "255,95,208", a: 1, g: gen});
    if (ev.e === "pop") { popFx.push({x:c[0], y:c[1], r:6, a:0.9, c: popHeat(SND.pops), g:gen}); delete gridMap[key];
      S.shake = Math.max(S.shake || 0, (blast || c[2] === "B") ? 6 : 3); }
    else { popFx.push({x:c[0], y:c[1], r:3, a:0.5, c: popHeat(SND.pops), g:gen}); delete gridMap[key]; }
    if (c[2] === "#" && !winFx && S.board && S.board.targetsLeft - shotCredits <= 0) winBurst(gen);
  });
  startFxPump();
}
function showScore(v) { scoreShown = v; document.getElementById("score").textContent = v; }
function tickScore() {
  if (!scoreFx) return;
  if (scoreFx.g !== S.gen) { scoreFx = null; return; }
  var p = (performance.now() - scoreFx.t) / scoreFx.dur;
  if (p >= 1) { showScore(scoreFx.to); scoreFx = null; return; }
  var e = 1 - (1 - p) * (1 - p);
  showScore(Math.round(scoreFx.from + (scoreFx.to - scoreFx.from) * e));
  setTimeout(tickScore, 50);
}
function startFxPump() {
  if (fxPump) return;
  fxPump = true;
  (function pump() {
    draw();
    if (popFx.length || slideFx.length || catchFx.length || flourishFx.length || textFx.length || (winFx && winFx.a > 0.02) || (dimFx && dimFx.g === S.gen && dimFx.a > 0.02) || (arriveFx && performance.now() - arriveFx.t < 1100) || (!S.playing && Math.abs(S.dock - dockRender) > 0.05) || S.shake > 0.3) setTimeout(pump, 50);
    else fxPump = false;
  })();
}
function playShot(resp, done) {
  // Chronological engine record: ball steps, peg removals and settle events
  // replay in the exact order the simulation produced them.
  S.shotKind = (resp.shot && resp.shot.kind) || "n";
  var tl = resp.timeline && resp.timeline.length ? resp.timeline
       : resp.frames.map(function(f) { return {b: f}; }).concat(resp.events);
  var i = 0;
  SND.pops = 0; SND.popFreqs = [];
  shotCredits = 0; S.sawTension = false;
  var pb = S.board || {};
  var tension = !S.fast && !pb.over && pb.targetsLeft === 1;
  var perTick = S.fast ? 6 : 2;
  function step() {
    var moved = 0, slow = false;
    while (i < tl.length && moved < perTick && !slow) {
      var ev = tl[i++];
      if (ev.b) {
        ballPos = ev.b; trail.push(ev.b); if (trail.length > 10) trail.shift();
        if (typeof ev.d === "number") { S.dock = ev.d; dockRender = ev.d; }
        moved++;
      } else {
        applyShotEvent(ev, resp.gen, resp.shot && resp.shot.kind === "x");
        if (ev.e !== "hit") slow = true;
      }
    }
    draw();
    if (i < tl.length) {
      var calm = tension && shotCredits === 0 && !slow;
      if (calm) S.sawTension = true;
      setTimeout(step, (slow ? (S.fast ? 60 : 160) : (S.fast ? 8 : 16)) * (calm ? 3 : 1));
      return;
    }
    S.shotKind = "n";
    done();
  }
  step();
}

/* ---------- screens ---------- */
function applyState(st) {
  var prevGen = S.gen, prevScreen = S.screen;
  S.screen = st.screen; S.msg = st.message || "";
  if (prevScreen && prevScreen !== st.screen) SND.seq++;
  if (typeof st.gen === "number") S.gen = st.gen;
  if (S.gen !== prevGen) {
    popFx = popFx.filter(function(f) { return f.g === S.gen; });
    slideFx = slideFx.filter(function(f) { return f.g === S.gen; });
    catchFx = catchFx.filter(function(f) { return f.g === S.gen; });
    flourishFx = flourishFx.filter(function(f) { return f.g === S.gen; });
    textFx = textFx.filter(function(f) { return f.g === S.gen; });
    if (winFx && winFx.g !== S.gen) winFx = null;
    if (arriveFx && arriveFx.g !== S.gen) arriveFx = null;
    if (scoreFx && scoreFx.g !== S.gen) scoreFx = null;
  }
  show("title", st.screen === "title"); show("game", st.screen !== "title");
  if (st.screen === "title") {
    var r = st.records || {};
    document.getElementById("records").textContent =
      (r.bestRun || r.bestMarathonBoards)
        ? "Records: " + (r.bestRun ? "best run " + r.bestRun : "") + (r.bestRun && r.bestMarathonBoards ? "  ·  " : "") +
          (r.bestMarathonBoards ? "best marathon " + r.bestMarathonBoards + " boards, " + r.bestMarathonScore : "")
        : "No records yet - finish a run or a marathon and they show here.";
    document.getElementById("daily").textContent = "(" + st.daily + ")";
    var qc = st.quitCode || st.lastCode || "";
    document.getElementById("quitcode").textContent = qc ? "Run code (replays this run): " + qc : "";
    document.getElementById("oldcodes").innerHTML = (st.oldCodes || []).map(function(c) { return "Before the restart: " + c; }).join("<br>");
    S.board = null; draw(); return;
  }
  if (st.board) {
    if (!S.board) dockRender = st.board.dock;
    var bid = st.board.run + ":" + st.board.k;
    if (wantArrive || bid !== lastBoardId) { lastBoardId = bid; arriveFx = {t: performance.now(), g: S.gen}; justArrived = true; } wantArrive = false;
    S.board = st.board; if (!S.playing) { syncGrid(st.board.grid); S.dock = st.board.dock; }
    if (!S.playing) startFxPump();
  }
  if (st.screen === "gameover" && prevScreen !== "gameover" && st.result && (st.result.kind === "runover" || st.result.kind === "marathonover")) { dimFx = {a: 1, g: S.gen}; startFxPump(); }
  show("draft", st.screen === "draft"); show("result", st.screen === "gameover" || st.screen === "complete");
  if (prevScreen && prevScreen !== st.screen) {
    if (st.screen === "draft" || st.screen === "complete") sndWin();
    else if (st.screen === "gameover") sndLose();
  }
  if (st.screen === "draft") renderDraft(st);
  if (st.screen === "gameover" || st.screen === "complete") renderResult(st);
  draw(); renderHud(); refreshPreview();
}
function renderDraft(st) {
  var notes = st.notes, names = {r:"Rebound", x:"Blast", s:"Second Chance"};
  var html = '<div class="sheet"><h2 class="gold">BOARD ' + st.board.k + " CLEARED</h2>" +
             '<p class="big">' + st.board.score + '</p><p style="color:var(--dim)">pick one upgrade: +1 charge from the next board on</p><div>';
  st.offer.forEach(function(c, i) {
    html += '<div class="card" data-pick="' + (i+1) + '"><div class="k">[' + (i+1) + "]</div><div class='name'>" + names[c] +
            "</div><div class='what'>" + notes[c] + "</div><div class='have'>have " + (st.satchel[c] || 0) + " &rarr; " + ((st.satchel[c] || 0)+1) + "</div></div>";
  });
  html += '</div><div class="row"><button data-pick="0"><span class="k">[0]</span>Skip</button><button data-go="menu"><span class="k">[Q]</span>menu</button><button data-snd="1"><span class="k">[S]</span> <span class="sl">' + sndLabel() + "</span></button></div>" +
          '<p class="code">run code so far: ' + st.code + "</p></div>";
  var el = document.getElementById("draft"); el.innerHTML = html;
  el.querySelectorAll("[data-pick]").forEach(function(n) { n.onclick = function() { pick(n.dataset.pick); }; });
  el.querySelectorAll("[data-go]").forEach(function(n) { n.onclick = function() { go(n.dataset.go); }; });
  wireSnd(el);
}
function renderResult(st) {
  var r = st.result, html = "";
  if (r.kind === "complete") {
    html = '<div class="sheet"><h2 class="gold">RUN COMPLETE</h2><p>all 3 boards cleared</p><p class="big">' + r.total + "</p>" +
           (r.isNew ? '<p style="color:var(--good)">new best score</p>' : "<p style='color:var(--dim)'>best " + r.best + "</p>") +
           '<p class="code">run code: ' + r.code + '</p><div class="row"><button data-go="advance"><span class="k">Enter</span>run ' + r.next +
           '</button><button data-go="menu"><span class="k">Q</span>menu</button><button data-snd="1"><span class="k">[S]</span> <span class="sl">' + sndLabel() + "</span></button></div></div>";
  } else if (r.kind === "marathonover") {
    html = '<div class="sheet"><h2>MARATHON OVER</h2><p>' + r.cleared + (r.cleared === 1 ? " board" : " boards") + ' cleared</p><p class="big">' + r.total + "</p>" +
           (r.isNew ? '<p style="color:var(--good)">new marathon best</p>' : "<p style='color:var(--dim)'>best " + r.bestBoards + " boards, " + r.bestScore + "</p>") +
           '<p class="code">marathon code: ' + r.code + '</p><div class="row"><button data-go="advance"><span class="k">Enter</span>marathon ' + r.next +
           '</button><button data-go="menu"><span class="k">Q</span>menu</button><button data-snd="1"><span class="k">[S]</span> <span class="sl">' + sndLabel() + "</span></button></div></div>";
  } else {
    html = '<div class="sheet"><h2>RUN OVER</h2><p>board ' + r.k + " fell</p><p class='big'>" + r.score + "</p>" +
           '<p class="code">run code: ' + r.code + '</p><div class="row"><button data-go="advance"><span class="k">Enter</span>run ' + r.next +
           '</button><button data-go="restart"><span class="k">R</span>retry run</button><button data-go="menu"><span class="k">Q</span>menu</button><button data-snd="1"><span class="k">[S]</span> <span class="sl">' + sndLabel() + "</span></button></div></div>";
  }
  var el = document.getElementById("result"); el.innerHTML = html;
  el.querySelectorAll("[data-go]").forEach(function(n) { n.onclick = function() { go(n.dataset.go); }; });
  wireSnd(el);
}
function startWatch(st) {
  S.preview = false; S.watchAuto = false; S.aim = 19; S.ball = "n"; ballPos = null; trail = [];
  applyState(st);
}
/* touch watch controls: same actions and guards as the Space/A/Q keys */
function watchTap(act) {
  if (S.screen !== "watch") return;
  if (act === "next") watchStep();
  else if (act === "auto") { S.watchAuto = !S.watchAuto; renderHud(); if (S.watchAuto) watchStep(); }
  else if (act === "menu") { S.watchAuto = false; api("/api/quit", {}).then(applyState); }
}
function watchStep() {
  if (S.playing || S.screen !== "watch") return;
  S.playing = true;
  api("/api/watchnext", {}).then(function(resp) {
    if (resp.watchAdvance) {
      S.playing = false;
      S.board = resp.board; syncGrid(resp.board.grid); S.dock = resp.board.dock;
      S.msg = "Board " + resp.watchAdvance.cleared + " cleared, score " + resp.watchAdvance.score +
              (resp.watchAdvance.pick === "0" ? "" : " - +1 " + resp.watchAdvance.pick);
      draw(); renderHud();
      if (S.watchAuto) setTimeout(watchStep, S.fast ? 300 : 800);
      return;
    }
    if (resp.watchDone) {
      S.playing = false; S.watchAuto = false;
      S.board = resp.board; syncGrid(resp.board.grid); S.dock = resp.board.dock;
      S.msg = resp.message || "Watch finished";
      draw(); renderHud();
      return;
    }
    S.lastShot = resp.shot;
    playShot(resp, function() {
      S.board = resp.board; syncGrid(resp.board.grid); S.dock = resp.board.dock;
      S.msg = resp.message; ballPos = null; trail = [];
      S.playing = false;
      draw(); renderHud();
      api("/api/watchdone", {gen: resp.gen, shotId: resp.shotId});
      if (S.watchAuto) setTimeout(watchStep, S.fast ? 250 : 600);
    });
  }).catch(function(e) { S.playing = false; S.watchAuto = false; S.msg = e.error || "watch step refused"; renderHud(); });
}
function go(what) {
  if (what === "advance") api("/api/advance", {}).then(function(st) { wantArrive = true; applyState(st); });
  else if (what === "restart") api("/api/restart", {}).then(applyState);
  else api("/api/quit", {}).then(applyState);
}
function pick(choice) { api("/api/pick", {pick: choice}).then(function(st) { sndPick(); applyState(st); }); }
function start(mode) {
  document.getElementById("startErr").textContent = "";
  api("/api/start", {mode: mode}).then(function(st) { S.aim = 19; S.ball = "n"; wantArrive = true; applyState(st); })
    .catch(function(e) { document.getElementById("startErr").textContent = e.error || "could not start"; });
}
function helpHtml() {
  return '<div class="sheet" id="helpBody"><h2>HOW TO PLAY</h2>' +
    "<p>Gravity pulls the charge down. Pegs, walls, mirrors and the floor cost it speed, so a shot has a short life. Spend it where it counts.<br>" +
    "Clear nodes in one shot to build a rally. Credits open the next sector.<br>" +
    "The gold line on the floor is the dock. It sweeps side to side. Land the charge in it for a free shot and +400 - only the first 2 catches on each board pay.<br>" +
    "Marathon: boards keep coming with rising quotas and, deeper in, fewer shots. The first board you fail ends the marathon.</p>" +
    "<h3>Board pieces</h3><p class='legend'>" +
    '<span style="color:#37c8e8">&#9679;</span> loose &nbsp;<span style="color:#c86ff0">&#9670;</span> loose &nbsp;' +
    '<span style="color:#ffd24a">&#9632;</span> target &nbsp;<span style="color:#ff5fd0">&#9733;</span> jackpot &nbsp;' +
    '<span style="color:#5fd787">&#9673;</span> bumper (3 hits) &nbsp;<span style="color:#ff5f5f">&#10041;</span> bomb &nbsp;' +
    '<span style="color:#ffaf00">&#9644;</span> dock &nbsp;<span style="color:#87ff87">&#9829;</span> free shot &nbsp;' +
    '<span style="color:#c8ccd2">&#9585;&#9586;</span> mirror</p>' +
    "<h3>Controls</h3><p><b>&larr; &rarr;</b>, mouse or drag to aim &nbsp; <b>Space</b>, click or tap to fire &nbsp; <b>1-4</b> ball &nbsp; <b>P</b> preview &nbsp; <b>F</b> fast &nbsp; <b>R</b> restart &nbsp; <b>S</b> sound &nbsp; <b>Q</b> menu</p>" +
    '<div class="row"><button onclick="hideHelp()"><span class="k">Esc</span>back</button></div></div>';
}
function showHelp() { var el = document.getElementById("helpOv"); el.innerHTML = helpHtml(); show("helpOv", true); }
function hideHelp() { show("helpOv", false); }

/* ---------- input ---------- */
document.addEventListener("keydown", function(ev) {
  var ae = document.activeElement;
  if (ae && (ae.tagName === "INPUT" || ae.tagName === "TEXTAREA")) return;
  var k = ev.key;
  if (!document.getElementById("helpOv").classList.contains("hidden")) {
    if (k === "Escape" || k === "q" || k === "Enter") hideHelp();
    return;
  }
  if (k === "s" || k === "S") { sndToggle(); return; }
  if (S.screen === "title") {
    if (k === "Enter") start("run");
    else if (k === "m" || k === "M") start("marathon");
    else if (k === "d" || k === "D") start("daily");
    else if (k === "h" || k === "H") showHelp();
    return;
  }
  if (S.screen === "draft") {
    if (["0","1","2","3"].indexOf(k) >= 0) pick(k);
    else if (k === "q" || k === "Q" || k === "Escape") go("menu");
    return;
  }
  if (S.screen === "gameover" || S.screen === "complete") {
    if (k === "Enter" || k === " ") go("advance");
    else if (k === "q" || k === "Q" || k === "Escape") go("menu");
    else if ((k === "r" || k === "R") && S.screen === "gameover") go("restart");
    return;
  }
  if (S.screen === "watch") {
    if (k === " " || k === "Enter") { watchStep(); ev.preventDefault(); }
    else if (k === "a" || k === "A") { S.watchAuto = !S.watchAuto; renderHud(); if (S.watchAuto) watchStep(); }
    else if (k === "f" || k === "F") { S.fast = !S.fast; }
    else if (k === "q" || k === "Q" || k === "Escape") { S.watchAuto = false; api("/api/quit", {}).then(applyState); }
    return;
  }
  if (k === "ArrowLeft" || k === "a") { S.aim = Math.max(0, S.aim - 1); refreshPreview(); draw(); ev.preventDefault(); }
  else if (k === "ArrowRight" || k === "d") { S.aim = Math.min(DIRS.length - 1, S.aim + 1); refreshPreview(); draw(); ev.preventDefault(); }
  else if (k === " " || k === "Enter") { fire(); ev.preventDefault(); }
  else if (k === "p" || k === "P") { S.preview = !S.preview; if (S.preview) revealBoard(); refreshPreview(); draw(); }
  else if (k === "f" || k === "F") { S.fast = !S.fast; }
  else if (k === "r" || k === "R") { api("/api/restart", {}).then(applyState); }
  else if (k === "q" || k === "Q" || k === "Escape") { api("/api/quit", {}).then(applyState); }
  else if (["1","2","3","4"].indexOf(k) >= 0) pickBall("nrxs"[+k - 1]);
  else if (k === "h" || k === "H") showHelp();
});
function layout() {
  var app = document.getElementById("app");
  var availW = Math.min(window.innerWidth, 1000) - 26;
  var availH = window.innerHeight - FITS.chrome;
  var cs = Math.min(18, Math.floor((availH - OY - 12) / H), Math.floor((availW - 2 * OX) / W));
  CS = Math.max(12, cs);
  cv.width = 2 * OX + W * CS;
  cv.height = OY + H * CS + 12;
  // narrow screens: scale the whole board into view instead of clipping it;
  // pointer mapping already normalizes by the element's displayed size
  var fit = Math.min(1, availW / cv.width);
  cv.style.width = (cv.width * fit) + "px";
  cv.style.height = (cv.height * fit) + "px";
  draw();
}
window.addEventListener("resize", layout);
function aimFromPoint(px, py) {
  if (S.playing || !S.board || S.board.over || S.screen !== "play") return;
  var r = cv.getBoundingClientRect();
  var mx = (px - r.left) * (cv.width / r.width), my = (py - r.top) * (cv.height / r.height);
  var cx = OX + 25*CS + CS/2, cy = OY;
  var best = 0, bd = 1e9;
  for (var i = 0; i < DIRS.length; i++) {
    var v = DIRS[i], ang = Math.atan2(v[1], v[0]), ma = Math.atan2(my - cy, mx - cx);
    var d = Math.abs(ang - ma);
    if (d < bd) { bd = d; best = i; }
  }
  if (best !== S.aim) { S.aim = best; refreshPreview(); draw(); }
}
cv.addEventListener("mousemove", function(ev) { aimFromPoint(ev.clientX, ev.clientY); });
cv.addEventListener("click", function() { if (S.screen === "play") fire(); });
/* touch: a drag aims and a tap fires THE AIM ON SCREEN - a tap never re-aims
   before firing, so the shot always goes where the preview points. The board
   never scrolls the page under a finger, and extra fingers are ignored. */
var touchTrack = null;
function trackedTouch(ev) {
  for (var i = 0; i < ev.changedTouches.length; i++)
    if (touchTrack && ev.changedTouches[i].identifier === touchTrack.id) return ev.changedTouches[i];
  return null;
}
cv.addEventListener("touchstart", function(ev) {
  if (S.screen !== "play") return;
  ev.preventDefault();
  if (ev.touches.length > 1) return;
  var t0 = ev.changedTouches[0];
  touchTrack = {id: t0.identifier, x: t0.clientX, y: t0.clientY, aiming: false};
}, {passive: false});
cv.addEventListener("touchmove", function(ev) {
  if (S.screen !== "play" || !touchTrack) return;
  ev.preventDefault();
  var t0 = trackedTouch(ev);
  if (!t0) return;
  if (!touchTrack.aiming && Math.abs(t0.clientX - touchTrack.x) < 12 && Math.abs(t0.clientY - touchTrack.y) < 12) return;
  touchTrack.aiming = true;
  aimFromPoint(t0.clientX, t0.clientY);
}, {passive: false});
cv.addEventListener("touchend", function(ev) {
  if (!touchTrack) return;
  var t0 = trackedTouch(ev);
  if (!t0) return;
  var wasAim = touchTrack.aiming;
  touchTrack = null;
  if (S.screen !== "play") return;
  ev.preventDefault();
  if (!wasAim) fire();
}, {passive: false});
cv.addEventListener("touchcancel", function() { touchTrack = null; });
document.getElementById("menu").addEventListener("click", function(ev) {
  var b = ev.target.closest("button"); if (!b) return;
  var act = b.dataset.act;
  if (act === "help") showHelp();
  else start(act);
});
document.getElementById("watchBtn").onclick = function() {
  var code = document.getElementById("resumeCode").value.trim();
  document.getElementById("startErr").textContent = "";
  api("/api/watch", {code: code}).then(function(st) { wantArrive = true; startWatch(st); })
    .catch(function(e) { document.getElementById("startErr").textContent = e.error || "could not watch"; });
};
document.getElementById("resumeBtn").onclick = function() {
  var code = document.getElementById("resumeCode").value.trim();
  if (!code) return;
  api("/api/resume", {code: code}).then(function(st) { S.aim = 19; S.ball = "n"; wantArrive = true; applyState(st); })
    .catch(function(e) { document.getElementById("startErr").textContent = e.error || "could not load"; });
};

function selftest() {
  var out = [];
  function t(name, ok) { out.push((ok ? "ok   " : "FAIL ") + name); }
  function key(k) { document.dispatchEvent(new KeyboardEvent("keydown", {key: k})); }
  function until(fn, ms) {
    return new Promise(function(res) {
      var t0 = Date.now();
      (function poll() { if (fn() || Date.now() - t0 > ms) res(fn()); else setTimeout(poll, 60); })();
    });
  }
  (async function() {
    try { localStorage.removeItem("chainSound"); } catch (e) {}
    SND.on = true;
    t("title screen on load", S.screen === "title");
    key("Enter");
    var ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("Enter starts a run", !!ok);
    var shots0 = S.board ? S.board.shots : -1;
    key("ArrowRight"); t("ArrowRight aims right", S.aim === 20);
    key("ArrowLeft"); t("ArrowLeft aims back", S.aim === 19);
    var sSel = SND.log.length;
    key("3"); t("key 3 picks blast", S.ball === "x");
    t("ball select ticks", SND.log.length === sSel + 1 && SND.log[SND.log.length - 1] === 660);
    key("4"); t("key 4 refused with empty second-chance stock", S.ball === "x");
    t("refused pick buzzes", SND.log[SND.log.length - 1] === 140);
    key("1"); t("key 1 back to normal", S.ball === "n");
    S.fast = true;
    key(" ");
    t("fire starts playback", S.playing === true);
    key(" "); key("2"); key("Enter");
    ok = await until(function() { return !S.playing; }, 20000);
    t("playback completes", !!ok);
    t("exactly one shot consumed despite mid-playback keys", S.board && S.board.shots === shots0 + 1);
    t("ball resets to normal after the shot", S.ball === "n");
    t("score applied after playback", S.board && S.lastShot && S.board.score === S.lastShot.points);
    var wp = S.preview; key("p"); t("P toggles preview", S.preview === !wp); key("p");
    key("h"); t("H opens help overlay", !document.getElementById("helpOv").classList.contains("hidden"));
    key("Escape"); t("Escape closes help overlay", document.getElementById("helpOv").classList.contains("hidden"));
    key("q");
    ok = await until(function() { return S.screen === "title"; }, 5000);
    t("Q quits to title", !!ok);
    var code = (document.getElementById("quitcode").textContent.match(/CH\d+M?R?-[^ ]+/) || [""])[0];
    t("quit prints the run code", code.indexOf("CH24R-") === 0);
    if (code) {
      document.getElementById("resumeCode").value = code;
      document.getElementById("resumeBtn").click();
      ok = await until(function() { return S.screen === "play" && S.board && S.board.shots === shots0 + 1; }, 5000);
      t("resume code round-trips to the same board", !!ok);
    }
    var sl0 = SND.log.length;
    key("s"); t("S mutes sound", SND.on === false);
    try { t("mute choice persists", localStorage.getItem("chainSound") === "off"); } catch (e) { t("mute choice persists", false); }
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    t("muted shot completes with zero beeps", ok && SND.log.length === sl0);
    key("s"); t("S turns sound back on", SND.on === true);
    try { t("unmute choice persists", localStorage.getItem("chainSound") !== "off"); } catch (e) { t("unmute choice persists", false); }
    t("sound chip present on the play screen", !!document.querySelector("#balls [data-snd]"));
    document.querySelector("#balls [data-snd]").click();
    t("sound chip mutes without the keyboard", SND.on === false && document.querySelector("#balls [data-snd] .sl").textContent === "sound off");
    document.querySelector("#balls [data-snd]").click();
    t("sound chip restores sound", SND.on === true && document.querySelector("#balls [data-snd] .sl").textContent === "sound on");
    key("s");
    t("mute silences the master gain", !!SND.gain && SND.gain.gain.value === 0);
    key("s");
    t("unmute restores the master gain", !!SND.gain && SND.gain.gain.value === 1);
    var sl2 = SND.log.length;
    sndWin(); SND.on = false;
    await new Promise(function(r) { setTimeout(r, 450); });
    t("a muted sting schedules no late notes", SND.log.length === sl2);
    SND.on = true;
    sndWin(); SND.seq++;
    await new Promise(function(r) { setTimeout(r, 450); });
    t("sting notes stop after leaving the screen", SND.log.length === sl2);
    catchFx.push({x: 10, r: 6, a: 0.9, g: S.gen});
    slideFx.push({x: 10, y0: 4, y1: 5, sym: "o", t: 0, g: S.gen});
    draw();
    t("current-generation fx survive a draw", catchFx.length === 1 && slideFx.length === 1);
    catchFx.push({x: 12, r: 6, a: 0.9, g: S.gen + 99});
    popFx.push({x: 12, y: 8, r: 3, a: 0.5, g: S.gen + 99});
    slideFx.push({x: 12, y0: 4, y1: 5, sym: "o", t: 0, g: S.gen + 99});
    draw();
    t("stale-generation fx dropped on draw", catchFx.length === 1 && popFx.length === 0 && slideFx.length === 1);
    var g0 = S.gen;
    key("r");
    ok = await until(function() { return S.gen !== g0; }, 5000);
    t("restart bumps the generation", !!ok);
    t("restart clears the running catch pulse (QA residual-fx repro)", ok && catchFx.length === 0);
    key("q");
    ok = await until(function() { return S.screen === "title"; }, 5000);
    t("Q quits the restarted run", !!ok);
    document.getElementById("resumeCode").value = "CH24R-40001-9.10.10-00-4r.10/3r.33x/30x.11r";
    document.getElementById("watchBtn").click();
    ok = await until(function() { return S.screen === "watch"; }, 5000);
    t("fixed reference run opens in watch", !!ok);
    var sl1 = SND.log.length;
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    t("watch replay produces pop beeps", ok && SND.log.length - sl1 >= 2);
    t("pop pitch climbs within a shot", SND.popFreqs.length > 1 && SND.popFreqs.every(function(f, i) { return i === 0 || f >= SND.popFreqs[i - 1]; }));
    slideFx.length = 0;
    // moment sounds: draft pick confirm (real draft via fixed quit-at-draft code)
    key("q");
    await new Promise(function(r) { setTimeout(r, 600); });
    t("back at title for pick-sound test", S.screen === "title");
    document.getElementById("resumeCode").value = "CH24R-40001-9.10.10--7.29.25.9";
    document.getElementById("resumeBtn").click();
    await new Promise(function(r) { setTimeout(r, 1200); });
    t("fixed quit-at-draft code opens the draft", S.screen === "draft");
    var sPk = SND.log.length;
    key("1");
    await new Promise(function(r) { setTimeout(r, 600); });
    t("draft pick plays the confirm chime", SND.log.length >= sPk + 2 && SND.log[sPk] === 660 && SND.log[sPk + 1] === 880);
    key("q");
    await new Promise(function(r) { setTimeout(r, 600); });
    sndJackpot();
    await new Promise(function(r) { setTimeout(r, 700); });
    t("jackpot chime is three rising notes", [880, 1108, 1318].every(function(f) { return SND.log.includes(f); }));
    var sOv = SND.log.length;
    sndOver();
    await new Promise(function(r) { setTimeout(r, 400); });
    t("overdrive sting is three rising notes", SND.log.slice(sOv).join(",") === "392,523,659");
    // flourish guard: queued jackpot notes die on a screen exit (native title repro)
    var sJ2 = SND.log.length;
    sndJackpot(); SND.seq++;
    await new Promise(function(r) { setTimeout(r, 500); });
    t("jackpot notes stop after leaving the screen", SND.log.length === sJ2);
    // pick tick negative: real draft, real pick, immediate quit kills the late tick
    document.getElementById("resumeCode").value = "CH24R-40001-9.10.10--7.29.25.9";
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "draft"; }, 5000);
    t("draft re-opens for the quit-tick test", !!ok);
    var sQ = SND.log.length;
    key("1");
    var gotPick = await (function() { return new Promise(function(res) { var t0 = Date.now(); (function poll() { if (SND.log.length > sQ || Date.now() - t0 > 3000) res(SND.log.length > sQ); else setTimeout(poll, 5); })(); }); })();
    key("q");
    await new Promise(function(r) { setTimeout(r, 300); });
    t("pick confirm started before the quit", gotPick && SND.log[sQ] === 660);
    t("pick tick is silent after quitting the draft", S.screen === "title" && SND.log.slice(sQ).indexOf(880) < 0);
    // flourish wiring: real fired shots on the seeded board (native: call-site revert survived unit pins)
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeCode").value = "CH24R-40001-9.10.10--";
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("seeded board resumes for flourish wiring", !!ok);
    S.fast = true; S.aim = 11;
    var sJ3 = SND.log.length;
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    await new Promise(function(r) { setTimeout(r, 600); });
    t("jackpot flourish wired to a real shot", !!ok && SND.log.slice(sJ3).join(",").indexOf("880,1108,1318") >= 0);
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("seeded board resumes for overdrive wiring", !!ok);
    var aims = [0, 2, 1], sO = 0;
    for (var ai = 0; ai < aims.length; ai++) {
      if (ai === aims.length - 1) sO = SND.log.length;
      S.aim = aims[ai];
      key(" ");
      ok = await until(function() { return !S.playing; }, 20000);
    }
    await new Promise(function(r) { setTimeout(r, 700); });
    t("overdrive flourish wired to the third rally", !!ok && SND.log.slice(sO).join(",").indexOf("392,523,659") >= 0);
    // tension cadence: real one-short shot must actually run the calm step delay (native: multiplier revert survived)
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeCode").value = "CH24R-40001-9.10.10--4.3.15";
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("one-short board resumes for the cadence test", !!ok);
    S.fast = false; S.aim = 12;
    var delays = [], origST = window.setTimeout;
    window.setTimeout = function(fn, ms) { delays.push(ms); return origST.apply(window, arguments); };
    key(" ");
    ok = await until(function() { return !S.playing; }, 30000);
    window.setTimeout = origST;
    t("one-short shot resolves", !!ok);
    t("tension slows the ball step cadence", S.sawTension && delays.indexOf(48) >= 0);
    // board legibility: ambient jackpot pulse, last-target ring, kind tint
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeCode").value = "CH24R-40001-9.10.10--";
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("seeded board resumes for legibility", !!ok);
    t("last-target ring stays off with many targets", ringActive() === false);
    t("jackpot is up on the fresh seeded board", jackpotUp() === true);
    var at0 = ambientT;
    await new Promise(function(r) { setTimeout(r, 400); });
    t("jackpot pulse animates while uncollected", ambientT > at0);
    S.fast = true; S.aim = 11;
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    await new Promise(function(r) { setTimeout(r, 400); });
    var at1 = ambientT;
    await new Promise(function(r) { setTimeout(r, 320); });
    t("jackpot pulse stops once collected", !!ok && !jackpotUp() && ambientT === at1);
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeCode").value = "CH24R-40001-9.10.10--4.3.15";
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("one-short board resumes for the ring", !!ok);
    t("last-target ring marks the final target", ringActive() === true && lastTargetCells().length >= 1 && lastTargetCells().every(function(g) { return g[2] === "#"; }));
    var ringCols = [], origStroke = ctx.stroke;
    ctx.stroke = function() { var cs = "" + ctx.strokeStyle; if (/^rgba\(255, ?210, ?74,/.test(cs) && ringCols.indexOf(cs) < 0) ringCols.push(cs); return origStroke.apply(this, arguments); };
    await new Promise(function(r) { setTimeout(r, 900); });
    ctx.stroke = origStroke;
    t("last-target ring pulses", ringCols.length >= 2);
    key("3");
    t("blast ball selected for tint", S.ball === "x");
    S.fast = false; S.aim = 12;
    key(" ");
    ok = await until(function() { return S.playing && trail.length > 2; }, 5000);
    t("blast shot runs with a red tint", !!ok && shotTint() === "255,95,95");
    ok = await until(function() { return !S.playing; }, 20000);
    t("tint returns to normal after the shot", !!ok && shotTint() === "57,194,215");
    t("kind tint map", kindRGB("n") === "57,194,215" && kindRGB("r") === "255,175,0" && kindRGB("s") === "135,255,135" && kindRGB("x") === "255,95,95");
    // reward feedback: dock pips + positional floaters
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeCode").value = "CH24R-40001-9.10.10--";
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("seeded board resumes for rewards", !!ok);
    t("dock starts with two paying catches", dockPipsLeft() === 2 && S.board.dockPaid === 0);
    S.fast = true; S.aim = 1;
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    t("paid catch floats +400 at the dock", !!ok && textFx.some(function(f) { return f.text === "+400"; }));
    t("dock pip counts the paid catch", dockPipsLeft() === 1);
    S.aim = 4;
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    t("second paid catch empties the dock", !!ok && S.board.dockPaid === 2 && dockPipsLeft() === 0);
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("seeded board resumes for the heart", !!ok);
    S.fast = true; S.aim = 3;
    key(" ");
    ok = await until(function() { return textFx.some(function(f) { return f.text === "+1 shot"; }); }, 8000);
    t("heart pickup floats +1 shot", !!ok);
    ok = await until(function() { return !S.playing; }, 20000);
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("seeded board resumes for the jackpot floater", !!ok);
    S.fast = true; S.aim = 11;
    key(" ");
    ok = await until(function() { return textFx.some(function(f) { return f.text === "+500"; }); }, 8000);
    t("jackpot floats +500 at the star", !!ok);
    ok = await until(function() { return !S.playing; }, 20000);
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("seeded board resumes for pop heat", !!ok);
    var heatOrder = [], heatPoll = setInterval(function() {
      popFx.forEach(function(f) { var c = f.c || "255,210,74"; if (heatOrder.indexOf(c) < 0) heatOrder.push(c); });
    }, 30);
    S.fast = true; S.aim = 7;
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    clearInterval(heatPoll);
    t("pop rings heat up gold to amber to pink", !!ok && heatOrder.join("|") === "255,210,74|255,175,0|255,95,208");
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("seeded board resumes for the low-shots pulse", !!ok);
    S.fast = true; S.aim = 8;
    for (var miss = 0; miss < 6; miss++) { key(" "); ok = await until(function() { return !S.playing; }, 20000); if (!ok) break; }
    t("shots pips steady with three real left", !!ok && S.board.shots === 6 && S.board.extra === 1 && document.getElementById("stats").innerHTML.indexOf("lowshots") < 0);
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    t("shots pips pulse with two real left", !!ok && S.board.shots === 7 && document.getElementById("stats").innerHTML.indexOf("lowshots") >= 0);
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("seeded board resumes with earned extra shots", !!ok);
    S.fast = true;
    var seq = [1, 4, 8, 8, 8, 8, 8];
    for (var si = 0; si < seq.length; si++) { S.aim = seq[si]; key(" "); ok = await until(function() { return !S.playing; }, 20000); if (!ok) break; }
    t("earned extras hold the pulse off at four real left", !!ok && S.board.shots === 7 && S.board.extra === 3 && document.getElementById("stats").innerHTML.indexOf("lowshots") < 0);
    S.aim = 8; key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    t("earned extras hold the pulse off at three real left", !!ok && S.board.shots === 8 && document.getElementById("stats").innerHTML.indexOf("lowshots") < 0);
    S.aim = 8; key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    t("pulse fires when real remaining hits two", !!ok && S.board.shots === 9 && document.getElementById("stats").innerHTML.indexOf("lowshots") >= 0);
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("seeded board resumes for the clear burst", !!ok);
    var fillSeen = [], origFill = ctx.fillRect;
    ctx.fillRect = function() { var cs = "" + ctx.fillStyle; if ((cs.indexOf("255, 210, 74") >= 0 || cs.indexOf("255,210,74") >= 0) && fillSeen.indexOf(cs) < 0) fillSeen.push(cs); return origFill.apply(this, arguments); };
    S.fast = true; S.aim = 31;
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    t("ordinary shot does not burst", !!ok && !winFx);
    S.aim = 4; key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    S.aim = 9; key(" ");
    var burstCells = -1;
    ok = await until(function() { if (winFx) burstCells = winFx.cells; return !!winFx; }, 20000);
    ok = await until(function() { return !S.playing; }, 20000) && ok;
    var ok2 = await until(function() { return S.board && S.board.targetsLeft === 0; }, 5000);
    ctx.fillRect = origFill;
    t("last target pops a gold clear burst", !!ok && !!ok2 && burstCells >= 27);
    t("clear burst flashes the board gold", fillSeen.length >= 1);
    t("board clear does not dim the board", !dimFx);
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("seeded board resumes for the quiet runover", !!ok);
    S.fast = true; S.aim = 21;
    for (var q = 0; q < 9; q++) { key(" "); ok = await until(function() { return !S.playing; }, 20000); if (!ok) break; }
    var ok3 = await until(function() { return S.screen === "gameover"; }, 5000);
    t("run over without a clear stays quiet", !!ok && !!ok3 && !winFx);
    var redSeen = [], origFill2 = ctx.fillRect;
    ctx.fillRect = function() { var cs = "" + ctx.fillStyle; if ((cs.indexOf("255, 95, 95") >= 0 || cs.indexOf("255,95,95") >= 0) && redSeen.indexOf(cs) < 0) redSeen.push(cs); return origFill2.apply(this, arguments); };
    ok = await until(function() { return dimFx; }, 3000);
    await new Promise(function(r) { setTimeout(r, 600); });
    ctx.fillRect = origFill2;
    t("run over dims the board red", !!ok && redSeen.length >= 1);
    key("Enter");
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    redSeen = [];
    ctx.fillRect = function() { var cs = "" + ctx.fillStyle; if ((cs.indexOf("255, 95, 95") >= 0 || cs.indexOf("255,95,95") >= 0) && redSeen.indexOf(cs) < 0) redSeen.push(cs); return origFill2.apply(this, arguments); };
    var partA = 0, allF = 0, partFrames = 0, seenThisFrame = false, origFill5 = ctx.fill, origClear = ctx.clearRect;
    ctx.clearRect = function() { if (seenThisFrame) partFrames++; seenThisFrame = false; return origClear.apply(this, arguments); };
    ctx.fill = function() { allF++; if (ctx.globalAlpha > 0.01 && ctx.globalAlpha < 0.99) { partA++; seenThisFrame = true; } return origFill5.apply(this, arguments); };
    dockRender = S.dock;
    var arrOk = !!arriveFx && arriveFx.g === S.gen;
    await new Promise(function(r) { setTimeout(r, 800); });
    ctx.fillRect = origFill2;
    t("run over dim does not bleed into the next run", !!ok && redSeen.length === 0);
    if (seenThisFrame) partFrames++;
    var midPart = partA;
    await new Promise(function(r) { setTimeout(r, 1200); });
    partA = 0; allF = 0;
    draw();
    ctx.fill = origFill5;
    ctx.clearRect = origClear;
    t("boards sweep in on arrival", arrOk && midPart >= 20 && partFrames >= 4);
    t("arrival sweep completes cleanly", allF >= 10 && partA === 0);
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("seeded board resumes for the dock glide", !!ok);
    var dockXs = [], origFill3 = ctx.fillRect;
    ctx.fillRect = function(x) { var cs = "" + ctx.fillStyle; if ((cs === "#ffaf00" || cs === "#ffd24a") && !S.playing && dockXs.indexOf(x) < 0) dockXs.push(x); return origFill3.apply(this, arguments); };
    S.fast = true; S.aim = 8;
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    await new Promise(function(r) { setTimeout(r, 2500); });
    ctx.fillRect = origFill3;
    t("dock glides to its new spot after a shot", !!ok && S.board.dock !== 3 && dockXs.length >= 3);
    t("dock glide settles on the engine spot", Math.abs(dockRender - S.dock) < 0.06);
    var arrPreShot = arriveFx;
    var flightFrames = [], origFill4 = ctx.fillRect;
    ctx.fillRect = function(x) { var cs = "" + ctx.fillStyle; if ((cs === "#ffaf00" || cs === "#ffd24a") && ballPos) flightFrames.push({x: x, want: OX + (S.dock-3)*CS}); return origFill4.apply(this, arguments); };
    S.fast = true; S.aim = 8;
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    ctx.fillRect = origFill4;
    var fBad = 0, fXs = [];
    for (var ff = 0; ff < flightFrames.length; ff++) { if (flightFrames[ff].x !== flightFrames[ff].want) fBad++; if (fXs.indexOf(flightFrames[ff].x) < 0) fXs.push(flightFrames[ff].x); }
    t("dock follows the engine dock during flight", !!ok && flightFrames.length >= 3 && fXs.length >= 2 && fBad === 0);
    t("post-shot state push does not sweep", arriveFx === arrPreShot);
    if (S.screen !== "title") { go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000); }
    var arrBefore = arriveFx;
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("explicit reload of the same board sweeps again", !!ok && arriveFx !== arrBefore && arriveFx.g === S.gen);
    go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000);
    document.getElementById("resumeCode").value = "CH24R-40003-9.10.10--4";
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    dockRender = S.dock;
    var jFree = !!S.board && !jackpotUp() && S.board.targetsLeft > 1;
    partA = 0; partFrames = 0; seenThisFrame = false;
    ctx.clearRect = function() { if (seenThisFrame) partFrames++; seenThisFrame = false; return origClear.apply(this, arguments); };
    ctx.fill = function() { if (ctx.globalAlpha > 0.01 && ctx.globalAlpha < 0.99) { partA++; seenThisFrame = true; } return origFill5.apply(this, arguments); };
    var arrOk2 = !!ok && !!arriveFx && arriveFx.g === S.gen;
    await new Promise(function(r) { setTimeout(r, 700); });
    if (seenThisFrame) partFrames++;
    ctx.fill = origFill5; ctx.clearRect = origClear;
    t("arrival sweep animates without ambient help", jFree && arrOk2 && partFrames >= 3);
    go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000);
    document.getElementById("resumeCode").value = "CH24R-40004-9.10.10--";
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    await new Promise(function(r) { setTimeout(r, 120); });
    var arrMid = !!arriveFx && arriveFx.g === S.gen;
    S.fast = true;
    key(" ");
    var snapped = arriveFx === null && S.playing;
    ok = await until(function() { return !S.playing; }, 20000);
    t("fire during arrival reveals the full board", arrMid && snapped && !!ok);
    go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000);
    document.getElementById("resumeCode").value = "CH24R-40005-9.10.10--";
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    await new Promise(function(r) { setTimeout(r, 120); });
    var arrMid2 = !!arriveFx && arriveFx.g === S.gen;
    key("p");
    t("preview during arrival reveals the full board", arrMid2 && arriveFx === null && S.preview);
    key("p");
    go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000);
    var scEl = document.getElementById("score"), scSeen = [], scDesc = Object.getOwnPropertyDescriptor(Node.prototype, "textContent");
    Object.defineProperty(scEl, "textContent", { configurable: true, get: scDesc.get, set: function(v) { if (scSeen.indexOf(String(v)) < 0) scSeen.push(String(v)); return scDesc.set.call(this, v); } });
    document.getElementById("resumeCode").value = "CH24R-40003-9.10.10--4";
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    await new Promise(function(r) { setTimeout(r, 900); });
    t("resumed board shows its score in full, no tick", !!ok && scSeen.length === 1 && scSeen[0] === "900");
    dockRender = S.dock;
    scSeen = [];
    S.fast = true; S.aim = 3;
    key(" ");
    for (var z = 0; z < 200 && S.playing; z++) { dockRender = S.dock; await new Promise(function(r) { setTimeout(r, 50); }); }
    ok = !S.playing;
    var ambFree = !!S.board && !jackpotUp() && S.board.targetsLeft > 1;
    var scoreFinal = S.board.score;
    await new Promise(function(r) { setTimeout(r, 800); });
    var scMid = 0, scOver = false;
    for (var si = 0; si < scSeen.length; si++) { var sv = parseInt(scSeen[si], 10); if (sv > 900 && sv < scoreFinal) scMid++; if (sv > scoreFinal) scOver = true; }
    t("score ticks up after a scoring shot", !!ok && scoreFinal > 900 && scMid >= 2);
    t("score tick settles on the true score", scSeen.length > 0 && scSeen[scSeen.length - 1] === String(scoreFinal) && !scOver && String(document.getElementById("score").textContent) === String(scoreFinal));
    t("score tick animates without ambient help", ambFree && scMid >= 2);
    delete scEl.textContent;
    go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000);
    document.getElementById("resumeCode").value = "CH24R-40003-9.10.10--4";
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    var fzArr = !!ok && !!arriveFx && arriveFx.g === S.gen;
    var fzFrames = 0, origClearF = ctx.clearRect;
    ctx.clearRect = function() { fzFrames++; return origClearF.apply(this, arguments); };
    S.aim = DIRS.length;
    var fzHi = false; try { draw(); } catch (e) { fzHi = true; }
    S.aim = -1;
    var fzLo = false; try { draw(); } catch (e) { fzLo = true; }
    fzFrames = 0;
    await new Promise(function(r) { setTimeout(r, 400); });
    ctx.clearRect = origClearF;
    t("injected out-of-range aim never throws in draw", fzArr && !fzHi && !fzLo);
    t("fx pump keeps animating through an injected aim", fzFrames >= 5);
    S.aim = DIRS.length;
    S.msg = "";
    key(" ");
    ok = await until(function() { return !S.playing; }, 5000);
    t("rejected out-of-range shot recovers input", !!ok && !S.playing && !!S.msg);
    S.fast = true; S.aim = 3;
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    t("legit shot plays after an injected-aim rejection", !!ok && !!S.board);
    go("menu"); ok = await until(function() { return S.screen === "title"; }, 5000);
    document.getElementById("resumeCode").value = "CH24R-40003-9.10.10--4";
    document.getElementById("resumeBtn").click();
    ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    await new Promise(function(r) { setTimeout(r, 300); });
    var scEl2 = document.getElementById("score"), scDesc2 = Object.getOwnPropertyDescriptor(Node.prototype, "textContent"), slotW = [];
    Object.defineProperty(scEl2, "textContent", { configurable: true, get: scDesc2.get, set: function(v) { slotW.push([String(v), scEl2.getBoundingClientRect().width]); return scDesc2.set.call(this, v); } });
    var preScore = S.board.score;
    S.fast = true; S.aim = 9;
    key(" ");
    ok = await until(function() { return !S.playing; }, 20000);
    await new Promise(function(r) { setTimeout(r, 800); });
    delete scEl2.textContent;
    var wSame = slotW.length >= 2, fin2 = String(S.board && S.board.score);
    for (var wi = 1; wi < slotW.length; wi++) { if (Math.abs(slotW[wi][1] - slotW[0][1]) > 0.5) wSame = false; }
    t("score slot width holds through a digit-growing tally", !!ok && wSame && String(preScore).length < fin2.length);
    out.push("checks " + out.length + " complete");
    var fails = out.filter(function(l) { return l.indexOf("FAIL") === 0; }).length;
    document.title = "SELFTEST FAILS " + fails;
    var pre = document.createElement("pre"); pre.id = "selftest"; pre.textContent = out.join("\n");
    document.body.appendChild(pre);
    try { await api("/api/selftest", {lines: out}); } catch (e) {}
  })();
}
layout();
api("/api/state").then(function(st) {
  applyState(st);
  if (location.search.indexOf("help=1") >= 0) showHelp();
  if (location.search.indexOf("selftest=1") >= 0 && location.search.indexOf("fxdemo=1") < 0) selftest();
  if (location.search.indexOf("fxdemo=1") >= 0 && location.search.indexOf("selftest=1") >= 0) {
    S.screen = "play"; S.playing = true; S.dock = 25;
    var sty = (location.search.match(/fxstyle=([a-z]+)/) || [null, "rings"])[1];
    S.board = {grid: [], bumps: {}, stock: {}, meter: 0, jackpot: null, style: sty};
    gridMap = {"10,10": [10,10,"o"], "30,15": [30,15,"#"], "20,9": [20,9,"+"]};
    slideFx.push({x: 20, y0: 8, y1: 9, sym: "+", t: 0, g: S.gen});
    catchFx.push({x: 25, r: 6, a: 0.95, g: S.gen});
    flourishFx.push({text: "RALLY x3", sub: "+1,240  rally x3", a: 1, g: S.gen});
    show("title", false); show("game", true);
    startFxPump();
  }
});
"""

PAGE = PAGE.replace("/*__APP__*/", APP_JS)


def PageHtml():
    return PAGE.replace("__TOKEN__", TOKEN).replace("__DIRS__", json.dumps([list(d) for d in E.Directions]))


class Handler(BaseHTTPRequestHandler):
    server_version = "ChainWeb/1.0"

    def log_message(self, *a):
        pass

    def tokenOk(self):
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        return q.get("k", [""])[0] == TOKEN

    def sendJson(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def fail(self, msg, status=400):
        self.sendJson({"error": msg}, status)

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        if not self.tokenOk():
            return self.fail("forbidden", 403)
        path = urlparse(self.path).path
        q = parse_qs(urlparse(self.path).query)
        sess = self.server.session
        if path == "/" or path == "/index.html":
            body = PageHtml().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/state":
            with sess.lock:
                data = sess.StateJson()
            self.sendJson(data)
        elif path == "/api/preview":
            try:
                aim = int(q.get("aim", [str(E.DefaultAim)])[0])
            except ValueError:
                aim = E.DefaultAim
            ball = q.get("ball", ["n"])[0]
            self.sendJson(sess.Preview(aim, ball))
        else:
            self.fail("not found", 404)

    def do_POST(self):
        from urllib.parse import urlparse
        if not self.tokenOk():
            return self.fail("forbidden", 403)
        path = urlparse(self.path).path
        try:
            size = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            size = 0
        if size > 100000:
            return self.fail("body too large", 413)
        try:
            body = json.loads(self.rfile.read(size) or b"{}") if size else {}
        except ValueError:
            return self.fail("bad json")
        sess = self.server.session
        if path == "/api/start":
            data, err = sess.Start(body.get("mode", ""))
        elif path == "/api/resume":
            data, err = sess.Resume(str(body.get("code", "")))
        elif path == "/api/watch":
            data, err = sess.Watch(str(body.get("code", "")))
        elif path == "/api/watchnext":
            data, err = sess.WatchNext()
            if err == "busy":
                return self.fail("busy", 409)
        elif path == "/api/watchdone":
            gen = body.get("gen")
            sid = body.get("shotId")
            data, err = sess.WatchDone(gen if isinstance(gen, int) else None,
                                       sid if isinstance(sid, int) else None), None
        elif path == "/api/shot":
            data, err = sess.Shoot(body.get("aim"), body.get("ball", "n"))
            if err == "busy":
                return self.fail("busy", 409)
        elif path == "/api/done":
            gen = body.get("gen")
            sid = body.get("shotId")
            data, err = sess.Done(gen if isinstance(gen, int) else None,
                                  sid if isinstance(sid, int) else None), None
        elif path == "/api/pick":
            data, err = sess.Pick(str(body.get("pick", "")))
        elif path == "/api/advance":
            data, err = sess.Advance()
        elif path == "/api/restart":
            data, err = sess.Restart()
        elif path == "/api/quit":
            data, err = sess.Quit(), None
        elif path == "/api/selftest":
            if not os.environ.get("CHAIN_SELFTEST"):
                return self.fail("not found", 404)
            sess.selftest = [str(x)[:200] for x in body.get("lines", [])][:400]
            data, err = {"ok": True}, None
        else:
            return self.fail("not found", 404)
        if err:
            return self.fail(err)
        self.sendJson(data)


def make_server(port=0, session=None):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.session = session or Session()
    server.daemon_threads = True
    return server


def main(argv):
    port = 0
    openBrowser = "--no-browser" not in argv and not os.environ.get("CHAIN_NO_BROWSER")
    if "--port" in argv:
        i = argv.index("--port")
        try:
            port = int(argv[i + 1])
        except (IndexError, ValueError):
            print("Usage: python3 ChainWeb.py [--port N] [--no-browser]")
            return 2
    server = make_server(port)
    url = "http://127.0.0.1:" + str(server.server_address[1]) + "/?k=" + TOKEN
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    print("CHAIN web UI - open this link to play:", flush=True)
    print("   " + url, flush=True)
    print("Listens on this machine only. Ctrl+C stops the game.")
    if openBrowser:
        try:
            if not webbrowser.open(url):
                print("(No browser found - copy the link into any browser on this machine.)", flush=True)
        except Exception:
            print("(Could not open a browser - copy the link into any browser on this machine.)", flush=True)
    try:
        while worker.is_alive():
            worker.join(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
