import {
  getCurrentUser,
  getCurrentUserData,
  getWallet,
  updateWallet,
  listenWallet
} from "./local-db.js";

/* =========================
   INIT WALLET (creates user with 1000 coins on first login)
========================= */
export function initWallet() {
  const userData = getCurrentUserData();
  if (!userData) return;
  // Wallet is already initialized on signup with 1000 coins
}

/* =========================
   GET BALANCE LIVE
========================= */
export function listenWalletBalance(callback) {
  const uid = getCurrentUser();
  if (!uid) return;

  return listenWallet(uid, callback);
}