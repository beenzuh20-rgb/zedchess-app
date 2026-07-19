/* Lobby realtime client: challenges, online users, chat, matchmaking. */
(function () {
  const socket = window.zcSocket;
  const myId = window.ZC_USER_ID;

  // ---- Elements ----
  const challengeList = document.getElementById("challengeList");
  const onlineList = document.getElementById("onlineList");
  const chatLog = document.getElementById("chatLog");
  const chatInput = document.getElementById("chatInput");
  const searchInput = document.getElementById("playerSearch");

  // ---- Challenges ----
  socket.on("lobby:challenges", (list) => {
    if (!challengeList) return;
    challengeList.innerHTML = "";
    list.forEach((c) => {
      const li = document.createElement("div");
      li.className = "card challenge";
      const privateBadge = c.opponent ? `<span class="badge">private</span>` : "";
      const stake = c.stake > 0 ? `<span class="text-gold">K${c.stake}</span>` : "Casual";
      li.innerHTML = `
        <div class="ch-row">
          <span class="ch-player"><i class="fa-solid fa-user"></i> ${c.challenger}</span>
          ${privateBadge}
          <span class="badge badge-rated">${c.time_control}</span>
          <span class="ch-stake">${stake}</span>
        </div>
        <button class="btn btn-primary btn-sm accept" data-id="${c.id}">Accept</button>`;
      li.querySelector(".accept").addEventListener("click", () => {
        socket.emit("lobby:challenge_accept", { challenge_id: c.id });
      });
      challengeList.appendChild(li);
    });
  });

  socket.on("lobby:error", (d) => window.zcToast("defeat", d.msg));
  socket.on("game:start", (d) => {
    window.zcToast("match_start", "Match starting!");
    setTimeout(() => (window.location.href = "/game/" + d.room_id), 800);
  });

  // ---- Online users ----
  socket.on("lobby:online", (users) => {
    if (!onlineList) return;
    onlineList.innerHTML = "";
    users.forEach((u) => {
      const li = document.createElement("div");
      li.className = "online-user";
      li.innerHTML = `<span class="badge badge-online"><i class="fa-solid fa-circle"></i></span>
        <img class="avatar-sm" src="${u.avatar || "/static/img/default-avatar.svg"}">
        <span>${u.username}</span> <span class="text-dim">(${u.rating})</span>`;
      onlineList.appendChild(li);
    });
  });

  // ---- Chat ----
  if (chatInput) {
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && chatInput.value.trim()) {
        socket.emit("lobby:chat", { body: chatInput.value.trim() });
        chatInput.value = "";
      }
    });
  }
  socket.on("lobby:chat", (m) => {
    if (!chatLog) return;
    const div = document.createElement("div");
    div.className = "chat-msg";
    div.innerHTML = `<strong>${m.username}</strong>: ${m.body}`;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  });

  // ---- Create challenge buttons ----
  document.querySelectorAll("[data-create-challenge]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tc = document.getElementById("tcSelect").value;
      const stake = parseFloat(document.getElementById("stakeInput").value || "0");
      const rated = document.getElementById("ratedCheck").checked;
      const opponent = document.getElementById("opponentInput").value.trim();
      socket.emit("lobby:challenge_create", {
        time_control: tc, stake, rated, opponent,
      });
    });
  });

  // ---- Search ----
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.trim();
      if (q.length >= 2) window.location.href = "/lobby/search?q=" + encodeURIComponent(q);
    });
  }
})();
