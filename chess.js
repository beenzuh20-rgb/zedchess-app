import {
  getCurrentUser,
  onAuthChange,
  getRoom,
  updateRoom,
  createRoom,
  listenRoom,
  getUsers,
  updateWallet
} from "./local-db.js";

/* =========================
   ROOM
========================= */
const urlParams = new URLSearchParams(window.location.search);
const roomId = urlParams.get("room");

if (!roomId) {
  document.body.innerHTML = "<h2>❌ No room ID found</h2>";
  throw new Error("Missing roomId");
}

/* =========================
   AUTH
========================= */
let currentUser = null;

onAuthChange((user) => {
  if (!user) {
    document.body.innerHTML = "<h2>❌ Not logged in</h2>";
    return;
  }

  currentUser = user;
  initGame();
});

/* =========================
   GAME STATE
========================= */
let game;
let myColor = null;
let selectedSquare = null;

let whiteTime = 300;
let blackTime = 300;
let timerInterval = null;

let lastMoveCount = 0;
let roomUnsubscribe = null;

/* =========================
   INIT
========================= */
function initGame() {
  game = new Chess();

  createBoard();
  joinRoom();
  listenToRoom();
}

/* =========================
   JOIN ROOM
========================= */
async function joinRoom() {
  const roomData = getRoom(roomId);

  if (!roomData) {
    createRoom(roomId, currentUser.uid);

    myColor = "white";
    startTimer(300, 300);
    return;
  }

  if (!roomData.player2 && roomData.player1 !== currentUser.uid) {
    updateRoom(roomId, {
      player2: currentUser.uid
    });

    myColor = "black";
  } else {
    myColor = roomData.player1 === currentUser.uid ? "white" : "black";
  }

  whiteTime = roomData.whiteTime ?? 300;
  blackTime = roomData.blackTime ?? 300;

  replayMoves(roomData.moves || []);
  startTimer(roomData.whiteTime, roomData.blackTime);
}

/* =========================
   BOARD
========================= */
function createBoard() {
  const board = document.getElementById("board");
  board.innerHTML = "";

  for (let i = 0; i < 64; i++) {
    const sq = document.createElement("div");

    const row = Math.floor(i / 8);
    const col = i % 8;

    sq.className = (row + col) % 2 === 0 ? "square white" : "square black";

    sq.onclick = () => handleClick(i);

    board.appendChild(sq);
  }
}

/* =========================
   CLICK SYSTEM
========================= */
function handleClick(i) {
  const col = i % 8;
  const row = 8 - Math.floor(i / 8);
  const square = String.fromCharCode(97 + col) + row;

  if (!selectedSquare) {
    selectedSquare = square;
    return;
  }

  makeMove(selectedSquare, square);
  selectedSquare = null;
}

/* =========================
   MOVE
========================= */
async function makeMove(from, to) {
  const roomData = getRoom(roomId);
  if (!roomData) return;

  const moves = roomData.moves || [];

  moves.push({ from, to });

  updateRoom(roomId, {
    moves,
    turn: roomData.turn === "white" ? "black" : "white"
  });
  
  // Check for checkmate/stalemate
  applyMovesAndCheckGameOver(moves);
}

/* =========================
   CHECK GAME OVER
========================= */
function applyMovesAndCheckGameOver(moves) {
  const tempGame = new Chess();
  let lastMoveSuccess = true;
  
  for (const m of moves) {
    const result = tempGame.move({ from: m.from, to: m.to, promotion: 'q' });
    if (!result) {
      lastMoveSuccess = false;
      break;
    }
  }
  
  if (tempGame.isGameOver()) {
    clearInterval(timerInterval);
    
    let winner = null;
    if (tempGame.isCheckmate()) {
      // The side that delivered checkmate wins
      winner = myColor ? getCurrentUser() : null;
    }
    
    updateRoom(roomId, {
      status: "finished",
      winner: winner
    });
    
    // Payout to winner if there's a stake
    const roomData = getRoom(roomId);
    if (roomData.stake && winner) {
      updateWallet(winner, roomData.pot || 0);
    }
    
    setTimeout(() => {
      alert("Game Over! " + (tempGame.isCheckmate() ? "Checkmate!" : tempGame.isDraw() ? "Draw!" : "Stalemate!"));
    }, 100);
  }
}

/* =========================
   SYNC (via polling - replaces Firestore onSnapshot)
========================= */
function listenToRoom() {
  if (roomUnsubscribe) roomUnsubscribe();
  
  roomUnsubscribe = listenRoom(roomId, (roomData) => {
    if (!roomData) return;

    document.getElementById("roomInfo").innerText = "Room: " + roomId;
    document.getElementById("status").innerText = "Turn: " + roomData.turn;

    document.getElementById("whitePlayer").innerText =
      roomData.player1 ? "White: Player 1" : "White: Waiting...";

    document.getElementById("blackPlayer").innerText =
      roomData.player2 ? "Black: Player 2" : "Black: Waiting...";

    whiteTime = roomData.whiteTime ?? 300;
    blackTime = roomData.blackTime ?? 300;

    // prevent constant replay loop
    if ((roomData.moves || []).length !== lastMoveCount) {
      replayMoves(roomData.moves || []);
      lastMoveCount = roomData.moves.length;
      
      // Re-check game over state after replay
      applyMovesAndCheckGameOver(roomData.moves || []);
    }
  });
}

/* =========================
   REPLAY
========================= */
function replayMoves(moves) {
  game = new Chess();
  for (const m of moves) {
    try {
      game.move({ from: m.from, to: m.to, promotion: 'q' });
    } catch(e) {
      // Ignore invalid moves in replay
    }
  }
  render();
}

/* =========================
   RENDER BOARD
========================= */
function render() {
  const board = document.getElementById("board");
  const g = game.board();

  board.innerHTML = "";

  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 8; c++) {

      const sq = document.createElement("div");
      sq.className = (r + c) % 2 === 0
        ? "square white"
        : "square black";

      const piece = g[r][c];

      if (piece) {
        const pieceEl = getPiece(piece);
        sq.appendChild(pieceEl);
      }

      board.appendChild(sq);
    }
  }
}

/* =========================
   PIECES
========================= */
function getPiece(p) {
  const map = {
    p:"♟", r:"♜", n:"♞", b:"♝", q:"♛", k:"♚",
    P:"♙", R:"♖", N:"♘", B:"♗", Q:"♕", K:"♔"
  };

  const key = p.color === "w"
    ? p.type.toUpperCase()
    : p.type.toLowerCase();

  const span = document.createElement("span");
  span.innerText = map[key];

  span.classList.add(p.color === "w"
    ? "white-piece"
    : "black-piece"
  );

  return span;
}

/* =========================
   TIMER
========================= */
function startTimer(w, b) {
  clearInterval(timerInterval);

  whiteTime = Number(w) || 300;
  blackTime = Number(b) || 300;

  timerInterval = setInterval(() => {
    const roomData = getRoom(roomId);
    if (roomData && roomData.status === "finished") {
      clearInterval(timerInterval);
      return;
    }

    if (game.game_over()) {
      clearInterval(timerInterval);
      return;
    }

    if (game.turn() === "w") {
      whiteTime = Math.max(0, whiteTime - 1);
    } else {
      blackTime = Math.max(0, blackTime - 1);
    }

    updateTimerUI();
  }, 1000);
}

function updateTimerUI() {
  const w = document.getElementById("whiteTime");
  const b = document.getElementById("blackTime");

  if (w) w.innerText = formatTime(whiteTime);
  if (b) b.innerText = formatTime(blackTime);
}

function formatTime(sec) {
  sec = Number(sec);
  if (isNaN(sec)) return "0:00";

  const m = Math.floor(sec / 60);
  const s = sec % 60;

  return m + ":" + (s < 10 ? "0" + s : s);
}

/* =========================
   PAYOUT WINNER
========================= */
async function payoutWinner(roomId, winnerUid) {
  const roomData = getRoom(roomId);
  if (!roomData) return;

  if (roomData.status === "finished") return;

  const pot = roomData.pot || 0;

  updateRoom(roomId, {
    winner: winnerUid,
    status: "finished"
  });

  // Give coins to winner
  const users = getUsers();
  if (users[winnerUid]) {
    users[winnerUid].coins = (users[winnerUid].coins || 0) + pot;
    localStorage.setItem("users", JSON.stringify(users));
  }
}