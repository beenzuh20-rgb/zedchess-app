// local-db.js - Complete localStorage-based backend (replaces Firebase)

/* =========================
   USERS / AUTH
========================= */
export function getUsers() {
  return JSON.parse(localStorage.getItem("users") || "{}");
}

function saveUsers(users) {
  localStorage.setItem("users", JSON.stringify(users));
}

export function signupUser(username, email, password) {
  const users = getUsers();
  
  // Check if email already exists
  for (const id in users) {
    if (users[id].email === email) {
      return { success: false, error: "Email already registered" };
    }
  }

  const uid = "user_" + Date.now() + "_" + Math.random().toString(36).substring(2, 6);
  
  users[uid] = {
    username,
    email,
    password, // In a real app, never store plaintext passwords
    coins: 1000,
    createdAt: Date.now()
  };
  
  saveUsers(users);
  return { success: true, uid };
}

export function loginUser(email, password) {
  const users = getUsers();
  
  for (const uid in users) {
    if (users[uid].email === email && users[uid].password === password) {
      setCurrentUser(uid);
      return { success: true, uid, username: users[uid].username };
    }
  }
  
  return { success: false, error: "Invalid email or password" };
}

export function setCurrentUser(uid) {
  if (uid) {
    localStorage.setItem("currentUser", uid);
  } else {
    localStorage.removeItem("currentUser");
  }
}

export function getCurrentUser() {
  return localStorage.getItem("currentUser");
}

export function getCurrentUserData() {
  const uid = getCurrentUser();
  if (!uid) return null;
  const users = getUsers();
  return users[uid] || null;
}

export function isLoggedIn() {
  return getCurrentUser() !== null;
}

export function logoutUser() {
  setCurrentUser(null);
}

export function onAuthChange(callback) {
  // Simple polling-based auth state listener
  let lastUid = getCurrentUser();
  
  callback(lastUid ? { uid: lastUid } : null);
  
  setInterval(() => {
    const currentUid = getCurrentUser();
    if (currentUid !== lastUid) {
      lastUid = currentUid;
      callback(currentUid ? { uid: currentUid } : null);
    }
  }, 500);
}

/* =========================
   WALLET
========================= */
export function getWallet(uid) {
  const users = getUsers();
  const user = users[uid];
  return user ? user.coins : 0;
}

export function updateWallet(uid, amount) {
  const users = getUsers();
  if (users[uid]) {
    users[uid].coins = (users[uid].coins || 0) + amount;
    saveUsers(users);
    return users[uid].coins;
  }
  return 0;
}

export function listenWallet(uid, callback) {
  callback(getWallet(uid));
  
  const interval = setInterval(() => {
    callback(getWallet(uid));
  }, 1000);
  
  return () => clearInterval(interval);
}

/* =========================
   ROOMS
========================= */
export function getRooms() {
  return JSON.parse(localStorage.getItem("rooms") || "{}");
}

function saveRooms(rooms) {
  localStorage.setItem("rooms", JSON.stringify(rooms));
}

export function createRoom(roomId, player1Uid) {
  const rooms = getRooms();
  
  rooms[roomId] = {
    player1: player1Uid,
    player2: null,
    moves: [],
    turn: "white",
    whiteTime: 300,
    blackTime: 300,
    status: "waiting",
    createdAt: Date.now()
  };
  
  saveRooms(rooms);
}

export function getRoom(roomId) {
  const rooms = getRooms();
  return rooms[roomId] || null;
}

export function updateRoom(roomId, updates) {
  const rooms = getRooms();
  if (rooms[roomId]) {
    Object.assign(rooms[roomId], updates);
    saveRooms(rooms);
  }
}

export function listenRoom(roomId, callback) {
  callback(getRoom(roomId));
  
  const interval = setInterval(() => {
    callback(getRoom(roomId));
  }, 500);
  
  return () => clearInterval(interval);
}

/* =========================
   QUEUE (Matchmaking)
========================= */
export function getQueue() {
  return JSON.parse(localStorage.getItem("queue") || "[]");
}

function saveQueue(queue) {
  localStorage.setItem("queue", JSON.stringify(queue));
}

export function joinQueue(uid) {
  const queue = getQueue();
  
  // Don't add if already in queue
  if (queue.find(e => e.uid === uid)) return false;
  
  queue.push({
    uid,
    createdAt: Date.now()
  });
  
  saveQueue(queue);
  return true;
}

export function leaveQueue(uid) {
  let queue = getQueue();
  queue = queue.filter(e => e.uid !== uid);
  saveQueue(queue);
}

export function findOpponent(uid) {
  const queue = getQueue();
  return queue.find(e => e.uid !== uid) || null;
}

export function removeFromQueue(uid) {
  leaveQueue(uid);
}

export function listenQueue(callback) {
  callback(getQueue());
  
  const interval = setInterval(() => {
    callback(getQueue());
  }, 1000);
  
  return () => clearInterval(interval);
}