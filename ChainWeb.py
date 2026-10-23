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
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ChainDemo as E

TOKEN = secrets.token_urlsafe(12)


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
        "shots": len(board.Log),
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
        self.old_codes = []

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
            board = self.board
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

            shot = board.Play(aim, hook, ball)
            data = {
                "frames": frames,
                "events": events,
                "timeline": timeline,
                "gen": self.gen,
                "shotId": self.pending_shot,
                "dockStart": E.DockX(E.DockPhase * logBefore),
                "dockEnd": E.DockX(shot.Steps + E.DockPhase * logBefore),
                "shot": {"aim": shot.Aim, "kind": shot.Kind, "points": shot.Points,
                         "targets": shot.Targets, "rally": shot.Rally, "chain": shot.Chain,
                         "mult": shot.Mult, "caught": shot.Caught, "paid": shot.Paid,
                         "refund": shot.Refund, "overdrive": shot.Overdrive,
                         "jackpot": shot.Jackpot, "steps": shot.Steps, "floorX": shot.FloorX},
                "message": E.ShotMessage(board, shot),
                "board": BoardJson(board, self.state),
            }
            return data, None

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
    font-size: 84px; letter-spacing: 14px; color: var(--accent);
    text-shadow: 0 2px 0 #166070, 0 4px 12px rgba(0,0,0,.6);
    font-family: "Trebuchet MS", Verdana, sans-serif; margin-bottom: 2px;
  }
  #title .tag { color: var(--dim); margin-bottom: 34px; }
  .menu { display: inline-block; text-align: left; }
  .menu button {
    display: block; width: 320px; margin: 7px 0; padding: 10px 14px;
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
    width: 300px; padding: 7px 9px; background: var(--panel); border: 1px solid var(--edge);
    border-radius: 4px; color: var(--text); font-family: Consolas, monospace; font-size: 12px;
  }
  #resumeRow button { padding: 7px 12px; background: var(--panel); color: var(--accent); border: 1px solid var(--edge); border-radius: 4px; cursor: pointer; }
  #title .foot { margin-top: 26px; color: var(--dim); font-size: 12px; }
  #startErr { color: var(--bad); margin-top: 10px; min-height: 18px; }

  /* game screen */
  #hud { display: flex; justify-content: space-between; align-items: baseline; padding: 4px 2px 8px; }
  #hud .who { color: var(--dim); }
  #hud .who b { color: var(--text); font-weight: normal; }
  #hud .score { font-size: 20px; color: var(--gold); font-family: Consolas, monospace; }
  #stage { position: relative; }
  canvas#board { display: block; background: #10141a; border: 1px solid var(--edge); border-radius: 6px; }
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

  /* overlays */
  .overlay {
    position: absolute; inset: 0; background: rgba(16,20,26,.82);
    display: flex; align-items: center; justify-content: center; border-radius: 6px;
  }
  .overlay-fixed {
    position: fixed; inset: 0; background: rgba(16,20,26,.92); z-index: 30;
    display: flex; align-items: flex-start; justify-content: center; overflow-y: auto; padding: 4vh 12px;
  }
  .sheet {
    background: var(--panel); border: 1px solid var(--edge); border-radius: 8px;
    padding: 26px 30px; min-width: 380px; max-width: 640px; text-align: center;
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
      <span id="keys"><b>&larr;</b><b>&rarr;</b> aim &nbsp;<b>Space</b> fire &nbsp;<b>P</b> preview &nbsp;<b>F</b> fast &nbsp;<b>R</b> restart &nbsp;<b>Q</b> menu</span>
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
var gridMap = {}, ballPos = null, trail = [], popFx = [], pathDots = [], slideFx = [], catchFx = [], fxPump = false, flourishFx = [], recoilT = 0;

function api(path, body) {
  return fetch(path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + TOKEN,
    body === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)})
    .then(function(r){ if(!r.ok) return r.json().then(function(e){throw e;}); return r.json(); });
}
function cellXY(x, y) { return [OX + x*CS, OY + y*CS]; }
function show(id, on) { document.getElementById(id).classList.toggle("hidden", !on); }

/* ---------- sprites ---------- */
function drawCell(x, y, sym, bumps, jackpot) {
  var px = OX + x*CS, py = OY + y*CS, c = CS;
  ctx.save();
  if (sym === "#") {
    ctx.fillStyle = jackpot ? "#ff5fd0" : "#ffd24a";
    ctx.strokeStyle = jackpot ? "#a03090" : "#9a7d10";
    rr(px+1, py+1, c-2, c-2, 3); ctx.fill(); ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,.35)"; ctx.fillRect(px+3, py+3, c-6, 3);
    if (jackpot) { ctx.fillStyle = "#fff"; star(px+c/2, py+c/2, 5, 6, 2.5); ctx.fill(); }
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
  // floor + dock
  var fy = OY + H*CS;
  ctx.fillStyle = "#2a323d"; ctx.fillRect(OX, fy, W*CS, 6);
  if (b) { ctx.fillStyle = catchFx.length ? "#ffd24a" : "#ffaf00"; ctx.fillRect(OX + (S.dock-3)*CS, fy-1, 7*CS, 8); }
  // cannon + aim
  var cp = cellXY(25, 0), kick = recoilT > 0 ? -Math.min(recoilT, 4) : 0;
  if (recoilT > 0) recoilT--;
  ctx.fillStyle = "#d7dee6";
  ctx.beginPath(); ctx.moveTo(cp[0]+CS/2-7, OY-8+kick); ctx.lineTo(cp[0]+CS/2+7, OY-8+kick); ctx.lineTo(cp[0]+CS/2, OY+6+kick); ctx.closePath(); ctx.fill();
  if (S.screen === "play" && b && !b.over && !S.playing) {
    var v = DIRS[S.aim], len = Math.hypot(v[0], v[1]);
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
  for (var t = 0; t < trail.length; t++) {
    ctx.fillStyle = "rgba(215,222,230," + (0.10 + 0.08*t) + ")";
    circ(OX + trail[t][0]*CS + CS/2, OY + trail[t][1]*CS + CS/2, 4); ctx.fill();
  }
  if (ballPos) {
    ctx.fillStyle = "#fff"; circ(OX + ballPos[0]*CS + CS/2, OY + ballPos[1]*CS + CS/2, 5.5); ctx.fill();
    ctx.strokeStyle = "rgba(57,194,215,.8)"; ctx.lineWidth = 1.5; circ(OX + ballPos[0]*CS + CS/2, OY + ballPos[1]*CS + CS/2, 7.5); ctx.stroke();
  }
  // pop flashes
  for (var p = popFx.length-1; p >= 0; p--) {
    var f = popFx[p];
    if (f.g !== S.gen) { popFx.splice(p, 1); continue; }
    f.r += 0.9; f.a -= 0.06;
    if (f.a <= 0) { popFx.splice(p, 1); continue; }
    ctx.strokeStyle = "rgba(255,210,74," + f.a + ")"; ctx.lineWidth = 2;
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
  var who = b.marathon ? ("marathon <b>" + b.run + "</b> · board <b>" + b.k + "</b>")
                       : ("run <b>" + b.run + "</b> · board <b>" + b.k + "</b> of <b>3</b>");
  document.getElementById("who").innerHTML = "CHAIN &nbsp;" + who + (b.style ? ' <span style="color:var(--dim)">(' + b.style + ")</span>" : "");
  var pips = "";
  for (var i = 0; i < b.limit; i++) pips += '<span style="color:' + (i < b.shots ? "var(--gold)" : "#3a4450") + '">&#9679;</span>';
  document.getElementById("stats").innerHTML =
    "targets <b>" + b.targetsLeft + "</b> / quota " + b.quota + " &nbsp; " + pips +
    (b.streak > 1 ? ' &nbsp; streak <b style="color:var(--good)">x' + Math.min(b.streak, 4) + "</b>" : "") +
    ' &nbsp; <span style="color:var(--dim)">od</span> ' + "#".repeat(b.meter) + "-".repeat(3 - b.meter);
  document.getElementById("score").textContent = b.score;
  var names = {n:"normal", r:"rebound", x:"blast", s:"second chance"};
  var html = "";
  ["n","r","x","s"].forEach(function(k, i) {
    var n = k === "n" ? "&infin;" : (b.stock[k] || 0);
    html += '<span class="ball' + (S.ball === k ? " sel" : "") + (k !== "n" && !b.stock[k] ? " empty" : "") +
            '" data-ball="' + k + '"><span class="k">' + (i+1) + "</span>" + names[k] + " " + n + "</span>";
  });
  document.getElementById("balls").innerHTML = html;
  var chips = document.querySelectorAll("#balls .ball");
  for (var j = 0; j < chips.length; j++) chips[j].onclick = function() { pickBall(this.dataset.ball); };
  document.getElementById("msg").innerHTML = S.msg || "";
}
function pickBall(k) {
  if (S.playing || !S.board || S.board.over) return;
  if (k !== "n" && !(S.board.stock[k] > 0)) { S.msg = "No " + k + " balls left"; renderHud(); return; }
  S.ball = k; refreshPreview(); renderHud();
}

/* ---------- preview ---------- */
function refreshPreview() {
  if (!S.preview || !S.board || S.board.over || S.playing) { pathDots = []; draw(); return; }
  api("/api/preview?aim=" + S.aim + "&ball=" + S.ball).then(function(d) { pathDots = d.path; draw(); });
}

/* ---------- shot playback ---------- */
function fire() {
  if (S.playing || !S.board || S.board.over || S.screen !== "play") return;
  S.playing = true; pathDots = []; recoilT = 6;
  api("/api/shot", {aim: S.aim, ball: S.ball}).then(function(resp) {
    S.ball = "n"; S.lastShot = resp.shot;
    playShot(resp, function() {
      S.board = resp.board; syncGrid(resp.board.grid); S.dock = resp.board.dock;
      S.msg = resp.message; ballPos = null; trail = [];
      if (resp.shot && resp.shot.caught) { catchFx.push({x: resp.shot.floorX, r: 6, a: 0.95, g: resp.gen}); startFxPump(); }
      var sh = resp.shot || {}, big = null, sub = "+" + sh.points;
      if (sh.jackpot) big = "JACKPOT";
      else if (sh.overdrive) big = "OVERDRIVE";
      else if (sh.paid) big = "CAUGHT IN THE DOCK";
      else if (sh.rally >= 3) big = "RALLY x" + sh.rally;
      else if (sh.mult >= 3) big = "STREAK x" + sh.mult;
      if (sh.rally >= 3 && big !== "RALLY x" + sh.rally) sub += "  rally x" + sh.rally;
      if (big) { flourishFx.push({text: big, sub: sub, a: 1, g: resp.gen}); startFxPump(); }
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
    if (ev.e === "pop") { popFx.push({x:c[0], y:c[1], r:6, a:0.9, g:gen}); delete gridMap[key];
      S.shake = Math.max(S.shake || 0, (blast || c[2] === "B") ? 6 : 3); }
    else { popFx.push({x:c[0], y:c[1], r:3, a:0.5, g:gen}); delete gridMap[key]; }
  });
  startFxPump();
}
function startFxPump() {
  if (fxPump) return;
  fxPump = true;
  (function pump() {
    draw();
    if (popFx.length || slideFx.length || catchFx.length || flourishFx.length || S.shake > 0.3) setTimeout(pump, 50);
    else fxPump = false;
  })();
}
function playShot(resp, done) {
  // Chronological engine record: ball steps, peg removals and settle events
  // replay in the exact order the simulation produced them.
  var tl = resp.timeline && resp.timeline.length ? resp.timeline
       : resp.frames.map(function(f) { return {b: f}; }).concat(resp.events);
  var i = 0;
  var perTick = S.fast ? 6 : 2;
  function step() {
    var moved = 0, slow = false;
    while (i < tl.length && moved < perTick && !slow) {
      var ev = tl[i++];
      if (ev.b) {
        ballPos = ev.b; trail.push(ev.b); if (trail.length > 6) trail.shift();
        if (typeof ev.d === "number") S.dock = ev.d;
        moved++;
      } else {
        applyShotEvent(ev, resp.gen, resp.shot && resp.shot.kind === "x");
        if (ev.e !== "hit") slow = true;
      }
    }
    draw();
    if (i < tl.length) { setTimeout(step, slow ? (S.fast ? 60 : 160) : (S.fast ? 8 : 16)); return; }
    done();
  }
  step();
}

/* ---------- screens ---------- */
function applyState(st) {
  var prevGen = S.gen;
  S.screen = st.screen; S.msg = st.message || "";
  if (typeof st.gen === "number") S.gen = st.gen;
  if (S.gen !== prevGen) {
    popFx = popFx.filter(function(f) { return f.g === S.gen; });
    slideFx = slideFx.filter(function(f) { return f.g === S.gen; });
    catchFx = catchFx.filter(function(f) { return f.g === S.gen; });
    flourishFx = flourishFx.filter(function(f) { return f.g === S.gen; });
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
    document.getElementById("quitcode").textContent = st.quitCode ? "Run code (replays this run): " + st.quitCode : "";
    document.getElementById("oldcodes").innerHTML = (st.oldCodes || []).map(function(c) { return "Before the restart: " + c; }).join("<br>");
    S.board = null; draw(); return;
  }
  if (st.board) { S.board = st.board; if (!S.playing) { syncGrid(st.board.grid); S.dock = st.board.dock; } }
  show("draft", st.screen === "draft"); show("result", st.screen === "gameover" || st.screen === "complete");
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
  html += '</div><div class="row"><button data-pick="0"><span class="k">[0]</span>Skip</button><button data-go="menu"><span class="k">[Q]</span>menu</button></div>' +
          '<p class="code">run code so far: ' + st.code + "</p></div>";
  var el = document.getElementById("draft"); el.innerHTML = html;
  el.querySelectorAll("[data-pick]").forEach(function(n) { n.onclick = function() { pick(n.dataset.pick); }; });
  el.querySelectorAll("[data-go]").forEach(function(n) { n.onclick = function() { go(n.dataset.go); }; });
}
function renderResult(st) {
  var r = st.result, html = "";
  if (r.kind === "complete") {
    html = '<div class="sheet"><h2 class="gold">RUN COMPLETE</h2><p>all 3 boards cleared</p><p class="big">' + r.total + "</p>" +
           (r.isNew ? '<p style="color:var(--good)">new best score</p>' : "<p style='color:var(--dim)'>best " + r.best + "</p>") +
           '<p class="code">run code: ' + r.code + '</p><div class="row"><button data-go="advance"><span class="k">Enter</span>run ' + r.next +
           '</button><button data-go="menu"><span class="k">Q</span>menu</button></div></div>';
  } else if (r.kind === "marathonover") {
    html = '<div class="sheet"><h2>MARATHON OVER</h2><p>' + r.cleared + (r.cleared === 1 ? " board" : " boards") + ' cleared</p><p class="big">' + r.total + "</p>" +
           (r.isNew ? '<p style="color:var(--good)">new marathon best</p>' : "<p style='color:var(--dim)'>best " + r.bestBoards + " boards, " + r.bestScore + "</p>") +
           '<p class="code">marathon code: ' + r.code + '</p><div class="row"><button data-go="advance"><span class="k">Enter</span>marathon ' + r.next +
           '</button><button data-go="menu"><span class="k">Q</span>menu</button></div></div>';
  } else {
    html = '<div class="sheet"><h2>RUN OVER</h2><p>board ' + r.k + " fell</p><p class='big'>" + r.score + "</p>" +
           '<p class="code">run code: ' + r.code + '</p><div class="row"><button data-go="advance"><span class="k">Enter</span>run ' + r.next +
           '</button><button data-go="restart"><span class="k">R</span>retry run</button><button data-go="menu"><span class="k">Q</span>menu</button></div></div>';
  }
  var el = document.getElementById("result"); el.innerHTML = html;
  el.querySelectorAll("[data-go]").forEach(function(n) { n.onclick = function() { go(n.dataset.go); }; });
}
function go(what) {
  if (what === "advance") api("/api/advance", {}).then(applyState);
  else if (what === "restart") api("/api/restart", {}).then(applyState);
  else api("/api/quit", {}).then(applyState);
}
function pick(choice) { api("/api/pick", {pick: choice}).then(applyState); }
function start(mode) {
  document.getElementById("startErr").textContent = "";
  api("/api/start", {mode: mode}).then(function(st) { S.aim = 19; S.ball = "n"; applyState(st); })
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
    "<h3>Controls</h3><p><b>&larr; &rarr;</b> or mouse aim &nbsp; <b>Space</b> or click fire &nbsp; <b>1-4</b> ball &nbsp; <b>P</b> preview &nbsp; <b>F</b> fast &nbsp; <b>R</b> restart &nbsp; <b>Q</b> menu</p>" +
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
  if (k === "ArrowLeft" || k === "a") { S.aim = Math.max(0, S.aim - 1); refreshPreview(); draw(); ev.preventDefault(); }
  else if (k === "ArrowRight" || k === "d") { S.aim = Math.min(DIRS.length - 1, S.aim + 1); refreshPreview(); draw(); ev.preventDefault(); }
  else if (k === " " || k === "Enter") { fire(); ev.preventDefault(); }
  else if (k === "p" || k === "P") { S.preview = !S.preview; refreshPreview(); draw(); }
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
  draw();
}
window.addEventListener("resize", layout);
cv.addEventListener("mousemove", function(ev) {
  if (S.playing || !S.board || S.board.over || S.screen !== "play") return;
  var r = cv.getBoundingClientRect();
  var mx = (ev.clientX - r.left) * (cv.width / r.width), my = (ev.clientY - r.top) * (cv.height / r.height);
  var cx = OX + 25*CS + CS/2, cy = OY;
  var best = 0, bd = 1e9;
  for (var i = 0; i < DIRS.length; i++) {
    var v = DIRS[i], ang = Math.atan2(v[1], v[0]), ma = Math.atan2(my - cy, mx - cx);
    var d = Math.abs(ang - ma);
    if (d < bd) { bd = d; best = i; }
  }
  if (best !== S.aim) { S.aim = best; refreshPreview(); draw(); }
});
cv.addEventListener("click", function() { if (S.screen === "play") fire(); });
document.getElementById("menu").addEventListener("click", function(ev) {
  var b = ev.target.closest("button"); if (!b) return;
  var act = b.dataset.act;
  if (act === "help") showHelp();
  else start(act);
});
document.getElementById("resumeBtn").onclick = function() {
  var code = document.getElementById("resumeCode").value.trim();
  if (!code) return;
  api("/api/resume", {code: code}).then(function(st) { S.aim = 19; S.ball = "n"; applyState(st); })
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
    t("title screen on load", S.screen === "title");
    key("Enter");
    var ok = await until(function() { return S.screen === "play" && S.board; }, 5000);
    t("Enter starts a run", !!ok);
    var shots0 = S.board ? S.board.shots : -1;
    key("ArrowRight"); t("ArrowRight aims right", S.aim === 20);
    key("ArrowLeft"); t("ArrowLeft aims back", S.aim === 19);
    key("3"); t("key 3 picks blast", S.ball === "x");
    key("4"); t("key 4 refused with empty second-chance stock", S.ball === "x");
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
    slideFx.length = 0;
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
            sess.selftest = [str(x)[:200] for x in body.get("lines", [])][:100]
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
