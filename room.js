import { getCurrentUser, getCurrentUserData, createRoom } from "./local-db.js";

window.createRoom = async function () {
  const userData = getCurrentUserData();

  if (!userData) {
    alert("Login first");
    return;
  }

  const uid = getCurrentUser();
  const roomId = "room_" + Math.random().toString(36).substring(2, 8);

  createRoom(roomId, uid);

  window.location.href = "chess.html?room=" + roomId;
};