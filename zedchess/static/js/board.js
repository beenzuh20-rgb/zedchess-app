/* ============================================================
   ZedChess board renderer (client-side view only).
   - Renders FEN provided by the server.
   - Sends moves to the server; never decides legality/time.
   - Animated moves, last-move highlight, legal-move dots,
     promotion popup, board flip, coordinates, check indicator.
   ============================================================ */
(function () {
  const GLYPHS = {
    p: "♟", r: "♜", n: "♞", b: "♝", q: "♛", k: "♚",
    P: "♙", R: "♖", N: "♘", B: "♗", Q: "♕", K: "♔",
  };

  class ZedBoard {
    constructor(el, opts = {}) {
      this.el = el;
      this.fen = opts.fen || "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
      this.orientation = opts.orientation || "white";
      this.interactive = !!opts.onMove; // click-to-move enabled?
      this.onMove = opts.onMove || null;
      this.lastFrom = null;
      this.lastTo = null;
      this.selected = null;
      this.legal = []; // uci squares for selected piece
      this.flipped = this.orientation === "black";
      this._build();
      this.render();
    }

    _build() {
      this.el.innerHTML = "";
      this.squares = [];
      for (let i = 0; i < 64; i++) {
        const sq = document.createElement("div");
        sq.dataset.idx = i;
        sq.addEventListener("click", () => this._click(i));
        this.el.appendChild(sq);
        this.squares.push(sq);
      }
    }

    parseFen(fen) {
      const [placement, turn, castling, ep] = fen.split(" ");
      const rows = placement.split("/");
      const board = {}; // "e4" -> piece char
      for (let r = 0; r < 8; r++) {
        let file = 0;
        for (const ch of rows[r]) {
          if (/\d/.test(ch)) {
            file += parseInt(ch, 10);
          } else {
            const f = String.fromCharCode(97 + file);
            const rank = 8 - r;
            board[`${f}${rank}`] = ch;
            file++;
          }
        }
      }
      return { board, turn, castling, ep };
    }

    _squareName(idx) {
      const r = Math.floor(idx / 8);
      const c = idx % 8;
      let file = c, rank = 7 - r;
      if (this.flipped) { file = 7 - c; rank = r; }
      return String.fromCharCode(97 + file) + (rank + 1);
    }

    _idxFromName(name) {
      const file = name.charCodeAt(0) - 97;
      const rank = parseInt(name[1], 10) - 1;
      let c = file, r = 7 - rank;
      if (this.flipped) { c = 7 - file; r = rank; }
      return r * 8 + c;
    }

    setFen(fen, lastFrom, lastTo) {
      this.fen = fen;
      this.lastFrom = lastFrom || null;
      this.lastTo = lastTo || null;
      this.selected = null;
      this.legal = [];
      this.render();
    }

    setLegal(uciMoves, from) {
      this.selected = from;
      this.legal = uciMoves.map((u) => u.slice(2, 4));
      this.render();
    }

    render() {
      const { board } = this.parseFen(this.fen);
      for (let i = 0; i < 64; i++) {
        const sq = this.squares[i];
        const name = this._squareName(i);
        const r = Math.floor(i / 8), c = i % 8;
        const isLight = (r + c) % 2 === 0;
        sq.className = "sq " + (isLight ? "light" : "dark");
        sq.innerHTML = "";

        // coordinates
        if (c === 0) {
          const rank = document.createElement("span");
          rank.className = "coord-rank";
          rank.style.left = "3px"; rank.style.top = "2px";
          rank.textContent = name[1];
          sq.appendChild(rank);
        }
        if (r === 7) {
          const file = document.createElement("span");
          file.className = "coord-file";
          file.style.right = "3px"; file.style.bottom = "1px";
          file.textContent = name[0];
          sq.appendChild(file);
        }

        if (name === this.lastFrom || name === this.lastTo)
          sq.classList.add("lastmove");
        if (this.selected === name) sq.classList.add("selectable");
        if (this.legal.includes(name)) {
          const dot = document.createElement("span");
          dot.style.cssText =
            "position:absolute;width:26%;height:26%;border-radius:50%;background:rgba(0,0,0,.28);";
          sq.appendChild(dot);
          sq.classList.add("selectable");
        }

        const piece = board[name];
        if (piece) {
          const span = document.createElement("span");
          span.className = "piece";
          span.textContent = GLYPHS[piece];
          span.style.color = piece === piece.toUpperCase() ? "#fff" : "#111";
          span.style.textShadow = piece === piece.toUpperCase()
            ? "0 1px 2px rgba(0,0,0,.5)" : "0 0 1px rgba(255,255,255,.4)";
          if (name === this.lastTo)
            span.style.transform = "translateY(-4px)";
          sq.appendChild(span);
        }
      }
    }

    _click(idx) {
      if (!this.interactive) return;
      const name = this._squareName(idx);
      const { board } = this.parseFen(this.fen);

      // If a piece is already selected and we click a legal destination, move.
      if (this.selected) {
        if (this.legal.includes(name)) {
          const from = this.selected;
          this.selected = null;
          this.legal = [];
          this.render();
          this.onMove(from, name);
          return;
        }
        if (name === this.selected) {
          // Re-click selected piece: deselect.
          this.selected = null;
          this.legal = [];
          this.render();
          return;
        }
        // Clicked elsewhere: switch selection if it's one of our pieces.
        const piece = board[name];
        const myTurn = (window.ZC_MY_COLOR === "white" && piece && piece === piece.toUpperCase()) ||
                       (window.ZC_MY_COLOR === "black" && piece && piece === piece.toLowerCase());
        if (myTurn) {
          this.selected = null;
          this.legal = [];
          this.render();
          this.onMove(name, null); // request legal moves
        } else {
          this.selected = null;
          this.legal = [];
          this.render();
        }
        return;
      }

      // Nothing selected: select our own piece and request its legal moves.
      const piece = board[name];
      const myTurn = (window.ZC_MY_COLOR === "white" && piece && piece === piece.toUpperCase()) ||
                     (window.ZC_MY_COLOR === "black" && piece && piece === piece.toLowerCase());
      if (piece && myTurn) {
        this.onMove(name, null);
      }
    }

    flip() {
      this.flipped = !this.flipped;
      this.render();
    }
  }

  window.ZedBoard = ZedBoard;
})();
