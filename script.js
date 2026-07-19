import {
  signupUser,
  loginUser,
  setCurrentUser,
  getCurrentUser
} from "./local-db.js";

/* =========================
   WAIT FOR DOM
========================= */
document.addEventListener("DOMContentLoaded", () => {

  // SIGNUP BUTTON
  const signupBtn = document.getElementById("signupBtn");
  if (signupBtn) {
    signupBtn.addEventListener("click", signupUserHandler);
  }

  // LOGIN BUTTON
  const loginBtn = document.getElementById("loginBtn");
  if (loginBtn) {
    loginBtn.addEventListener("click", loginUserHandler);
  }

  // LOGOUT BUTTON
  const logoutBtn = document.getElementById("logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", logoutHandler);
  }

});

/* =========================
   SIGNUP
========================= */
function signupUserHandler() {

  const username = document.getElementById("username")?.value;
  const email = document.getElementById("email")?.value;
  const password = document.getElementById("password")?.value;
  const confirm = document.getElementById("confirm")?.value;
  const terms = document.getElementById("terms")?.checked;
  const error = document.getElementById("error");

  if (error) error.textContent = "";

  // VALIDATION
  if (!username || !email || !password || !confirm) {
    if (error) error.textContent = "All fields are required";
    return;
  }

  if (password !== confirm) {
    if (error) error.textContent = "Passwords do not match";
    return;
  }

  if (!terms) {
    if (error) error.textContent = "You must accept Terms & Conditions";
    return;
  }

  const result = signupUser(username, email, password);

  if (result.success) {
    sessionStorage.setItem("username", username);
    window.location.href = "login.html";
  } else {
    if (error) {
      error.textContent = result.error;
    } else {
      alert(result.error);
    }
  }
}

/* =========================
   LOGIN
========================= */
function loginUserHandler() {

  const email = document.getElementById("loginEmail")?.value;
  const password = document.getElementById("loginPassword")?.value;

  if (!email || !password) {
    alert("Fill all fields");
    return;
  }

  const result = loginUser(email, password);

  if (result.success) {
    sessionStorage.setItem("userEmail", email);
    sessionStorage.setItem("userId", result.uid);
    window.location.href = "home.html";
  } else {
    alert(result.error);
  }
}

/* =========================
   LOGOUT
========================= */
function logoutHandler() {
  setCurrentUser(null);
  sessionStorage.clear();
  window.location.href = "index.html";
}

/* =========================
   AUTH GUARD
========================= */
export function requireAuth(redirect = "login.html") {
  if (!getCurrentUser()) {
    window.location.href = redirect;
  }
}