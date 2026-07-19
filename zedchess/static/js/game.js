/* Game realtime client: clocks, moves, resign/draw, promotion, game-over. */
(function () {
  const socket = window.zcSocket;
  const roomId = window.ZC_ROOM_ID;
  const myColor = window.ZC_MY_COLOR;        // "white" | "black" | null (spectator)
  const myId = window.ZC_USER_ID;

  const boardEl = document.getElementById("chessboard");
  let moveIndex = 0;
  let turn = "white";
  let gameOver = false;
  const history = []; // SAN list for move list rendering

  const board = new ZedBoard(boardEl, {
    orientation: myColor || "white",
    onMove: handleMove,
  });

  function handleMove(from, to) {
    if (gameOver) return;
    if (to === null) {
      // Request legal moves for the selected piece from the server.
      socket.emit("game:legal", { room_id: roomId, from });
      return;
    }
    if (turn !== myColor) return;
    // Promotion detection (pawn to last rank)
    const promo = needsPromotion(from, to);
    if (promo) {
      showPromo((piece) => sendMove(from, to, piece));
    } else {
      sendMove(from, to, null);
    }
  }

  function needsPromotion(from, to) {
    const piece = window.ZC_FEN_BOARD ? window.ZC_FEN_BOARD[from] : null;
    if (!piece || piece.toLowerCase() !== "p") return false;
    const rank = to[1];
    return (piece === "P" && rank === "8") || (piece === "p" && rank === "1");
  }

  function sendMove(from, to, promotion) {
    // Send UCI to the server; the server converts to SAN authoritatively.
    let uci = from + to;
    if (promotion) uci += promotion.toLowerCase();
    // Index is authoritative from the latest game:state; do not increment here.
    socket.emit("game:move", { room_id: roomId, san: uci, index: moveIndex + 1 });
  }

  // ---- Legal moves (for highlight + dot UX) ----
  socket.on("game:legal", (d) => {
    if (d.room_id !== roomId) return;
    if (d.from && Array.isArray(d.moves)) {
      board.setLegal(d.moves, d.from);
    }
  });

  // ---- Server state ----
  socket.on("game:state", (s) => {
    gameOver = s.status === "finished" || s.status === "aborted";
    turn = s.turn;
    moveIndex = s.moves.length;
    history.length = 0;
    s.moves.forEach((m) => history.push(m));
    // Rebuild board from FEN if present.
    if (s.fen) {
      board.setFen(s.fen);
      window.ZC_FEN_BOARD = fenToBoard(s.fen);
    }
    renderMoveList(s.moves);
    updatePlayerBars(s);
    // Refresh-safe: re-seed the clock interpolation base from authoritative state.
    applyClock(s);
    if (gameOver) showGameOver(s);
    socket.emit("game:ping", { room_id: roomId });
  });

  // ---- Clocks (server-authoritative, smooth client interpolation) ----
  // We store the banked values + the server timestamp, then derive the live
  // remaining time locally each animation frame. This keeps both players in
  // lock-step and looks smooth even if network ticks are delayed.
  const clockState = {
    white: 0, black: 0, turn: "white", running: false, serverTime: 0,
  };

  function applyClock(c) {
    if (!c) return;
    // game:state carries server_time + banked clocks; game:clock too.
    clockState.white = c.white_clock_ms ?? clockState.white;
    clockState.black = c.black_clock_ms ?? clockState.black;
    if (c.turn) clockState.turn = c.turn;
    if (typeof c.running === "boolean") clockState.running = c.running;
    if (c.server_time) clockState.serverTime = c.server_time;
  }

  socket.on("game:clock", (c) => {
    applyClock(c);
    if (c.turn) turn = c.turn;
  });

  // Compute the live remaining time (ms) for a colour, right now.
  function liveRemaining(color) {
    if (!clockState.running || !clockState.serverTime) {
      return color === "white" ? clockState.white : clockState.black;
    }
    const elapsed = Date.now() - clockState.serverTime;
    const base = color === "white" ? clockState.white : clockState.black;
    const isActive = (color === clockState.turn);
    return isActive ? Math.max(0, base - elapsed) : base;
  }

  function renderClock(color) {
    const el = document.getElementById(color + "Clock");
    if (!el) return;
    const ms = liveRemaining(color);
    const running = clockState.running && clockState.turn === color;
    el.textContent = formatClock(ms);
    el.classList.toggle("running", running);
    el.classList.toggle("low", ms <= 20000 && ms > 0);
    el.classList.toggle("flash", ms <= 10000 && ms > 0);
    el.classList.toggle("inactive", !running);
  }

  function clockLoop() {
    if (!gameOver) {
      renderClock("white");
      renderClock("black");
    }
    requestAnimationFrame(clockLoop);
  }
  requestAnimationFrame(clockLoop);

  // ---- Controls ----
  const resignBtn = document.getElementById("resignBtn");
  if (resignBtn) resignBtn.addEventListener("click", () =>
    socket.emit("game:resign", { room_id: roomId }));
  const drawBtn = document.getElementById("drawBtn");
  if (drawBtn) drawBtn.addEventListener("click", () =>
    socket.emit("game:draw_offer", { room_id: roomId }));
  const flipBtn = document.getElementById("flipBtn");
  if (flipBtn) flipBtn.addEventListener("click", () => board.flip());

  // ---- Chat ----
  const gchat = document.getElementById("gameChatInput");
  if (gchat) gchat.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && gchat.value.trim())
      socket.emit("game:chat", { room_id: roomId, body: gchat.value.trim() }), (gchat.value = "");
  });
  socket.on("game:chat", (m) => {
    const log = document.getElementById("gameChatLog");
    if (!log) return;
    const d = document.createElement("div");
    d.className = "chat-msg";
    d.innerHTML = `<strong>${m.username}</strong>: ${m.body}`;
    log.appendChild(d); log.scrollTop = log.scrollHeight;
  });

  socket.on("game:illegal", (d) => window.zcToast("defeat", d.msg));

  // ---- Draw offer / response ----
  socket.on("game:draw_offered", (d) => {
    if (d.room_id !== roomId) return;
    showDrawPrompt(d.from_name);
  });
  socket.on("game:draw_pending", () => {
    window.zcToast("info", "Draw offer sent — awaiting opponent.");
  });
  socket.on("game:draw_declined", (d) => {
    window.zcToast("info", `${(d && d.by_name) || "Opponent"} declined the draw.`);
  });

  function showDrawPrompt(fromName) {
    const pop = document.getElementById("drawPop");
    if (!pop) {
      // Fallback: simple confirm.
      const ok = confirm(`${fromName || "Opponent"} offered a draw. Accept?`);
      socket.emit("game:draw_respond", { room_id: roomId, accept: ok });
      return;
    }
    const nameEl = pop.querySelector(".draw-from");
    if (nameEl) nameEl.textContent = fromName || "Opponent";
    pop.classList.add("show");
    pop.querySelectorAll("[data-draw]").forEach((el) => {
      el.onclick = () => {
        pop.classList.remove("show");
        socket.emit("game:draw_respond", {
          room_id: roomId, accept: el.dataset.draw === "accept",
        });
      };
    });
  }

  // ---- Helpers ----
  function renderMoveList(moves) {
    const ml = document.getElementById("movelist");
    if (!ml) return;
    ml.innerHTML = "";
    for (let i = 0; i < moves.length; i += 2) {
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `<span class="num">${i / 2 + 1}.</span>
        <span class="mv">${moves[i] || ""}</span>
        <span class="mv">${moves[i + 1] || ""}</span>`;
      ml.appendChild(row);
    }
    ml.scrollTop = ml.scrollHeight;
  }

  function updatePlayerBars(s) {
    document.getElementById("whiteName").textContent =
      s.white_id ? "White" : "Waiting…";
    document.getElementById("blackName").textContent =
      s.black_id ? "Black" : "Waiting…";
  }

  function showGameOver(s) {
    const banner = document.getElementById("gameover");
    if (!banner) return;
    let text = "Game Over";
    if (s.result === "white" || s.result === "black") {
      const youWin = (s.result === myColor);
      text = youWin ? "🏆 Victory!" : "😞 Defeat";
    } else if (s.result === "draw") text = "½–½ Draw";
    banner.querySelector(".result").textContent = text;
    banner.classList.add("show");
  }

  function showPromo(cb) {
    const pop = document.getElementById("promoPop");
    if (!pop) { cb("q"); return; }
    pop.classList.add("show");
    pop.querySelectorAll(".pc").forEach((el) => {
      el.onclick = () => {
        pop.classList.remove("show");
        cb(el.dataset.piece);
      };
    });
  }

  function formatClock(ms) {
    ms = Math.max(0, ms);
    // Last 10 seconds: show tenths of a second (e.g. 0:09.3) — Lichess style.
    if (ms < 10000) {
      const sec = ms / 1000;
      return sec.toFixed(1);
    }
    let total = Math.floor(ms / 1000);
    const h = Math.floor(total / 3600);
    total %= 3600;
    const m = Math.floor(total / 60);
    const sec = total % 60;
    const pad = (n) => (n < 10 ? "0" + n : n);
    return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
  }

  // Parse a FEN placement into a {"e4": pieceChar} map for client-side checks.
  function fenToBoard(fen) {
    const map = {};
    const rows = fen.split(" ")[0].split("/");
    for (let r = 0; r < 8; r++) {
      let file = 0;
      for (const ch of rows[r]) {
        if (/\d/.test(ch)) {
          file += parseInt(ch, 10);
        } else {
          const f = String.fromCharCode(97 + file);
          const rank = 8 - r;
          map[`${f}${rank}`] = ch;
          file++;
        }
      }
    }
    return map;
  }

  // Join game room.
  socket.emit("game:join", { room_id: roomId });
  setInterval(() => socket.emit("game:ping", { room_id: roomId }), 4000);
})();
