import {
  getCurrentUser,
  getCurrentUserData,
  getWallet,
  joinQueue,
  leaveQueue,
  findOpponent,
  updateRoom,
  getRoom,
  createRoom,
  removeFromQueue
} from "./local-db.js";

const STAKE = 100; // Fixed stake per match

window.findMatch = async function () {
  const userData = getCurrentUserData();
  if (!userData) {
    alert("Login first");
    return;
  }

  const uid = getCurrentUser();
  const status = document.getElementById("matchStatus");
  if (status) status.innerText = "Searching for opponent...";

  const coins = getWallet(uid);
  if (coins < STAKE) {
    alert("Not enough coins to play");
    return;
  }

  let opponent = findOpponent(uid);

  if (opponent) {
    // Match found!
    const roomId = "room_" + Math.random().toString(36).substring(2, 8);

    // Deduct stake from both players
    let userCoins = getWallet(uid);
    let oppCoins = getWallet(opponent.uid);

    // Create room
    const roomsData = JSON.parse(localStorage.getItem("rooms") || "{}");
    roomsData[roomId] = {
      player1: opponent.uid,
      player2: uid,
      stake: STAKE,
      pot: STAKE * 2,
      winner: null,
      status: "active",
      turn: "white",
      moves: [],
      createdAt: Date.now()
    };
    localStorage.setItem("rooms", JSON.stringify(roomsData));

    // Remove opponent from queue
    removeFromQueue(opponent.uid);

    if (status) status.innerText = "Match found!";
    window.location.href = "chess.html?room=" + roomId;
    return;
  }

  // No opponent found - join queue
  const joined = joinQueue(uid);
  if (!joined) {
    if (status) status.innerText = "Already waiting...";
    return;
  }

  if (status) status.innerText = "Waiting for opponent...";
};