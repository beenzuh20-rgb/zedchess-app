/* ZedChess realtime client.
 * Connects over Socket.IO, handles toasts/notifications, theme toggle,
 * and exposes helpers used by the lobby + game pages.
 */
(function () {
  const socket = io({ transports: ["websocket", "polling"] });

  // ---- Theme ---------------------------------------------------------
  const root = document.documentElement;
  const saved = localStorage.getItem("zc-theme");
  if (saved) root.setAttribute("data-theme", saved);
  const toggle = document.getElementById("themeToggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      localStorage.setItem("zc-theme", next);
    });
  }

  // ---- Toasts --------------------------------------------------------
  function toast(type, body) {
    const stack = document.getElementById("toast-stack");
    if (!stack) return;
    const el = document.createElement("div");
    el.className = "toast " + (type || "");
    el.innerHTML = `<strong>${body}</strong>`;
    stack.appendChild(el);
    setTimeout(() => {
      el.style.transition = "opacity .4s";
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 400);
    }, 5000);
  }

  socket.on("notification", (n) => {
    toast(n.type, n.body);
    // bump nav badge if present
    const badge = document.getElementById("navNotif");
    if (badge) badge.style.display = "inline-block";
  });

  // ---- Auto-reconnect: re-join lobby room after a dropped socket ----
  socket.on("disconnect", () => {
    const t = setTimeout(() => socket.connect(), 1500);
    return () => clearTimeout(t);
  });
  socket.on("connect", () => {
    // The server adds every authenticated socket to the "lobby" room and
    // pushes the current challenge + online lists on connect. We also ask
    // explicitly to cover any connect-time race so a refresh never shows
    // an empty lobby.
    socket.emit("lobby:request_state");
  });

  // ---- Global live challenges (visible on every page) ------------
  // Tracks seen challenge ids so we only toast when something NEW appears.
  const seenChallenges = new Set();
  socket.on("lobby:challenges", (list) => {
    const panel = document.getElementById("globalChallenges");
    const count = document.getElementById("liveChallengesCount");
    if (count) {
      count.textContent = list.length;
      count.style.display = list.length ? "inline-block" : "none";
    }
    if (panel) {
      if (!list.length) {
        panel.innerHTML = `<div class="text-dim" style="padding:6px 10px;font-size:.8rem;">No open challenges</div>`;
      } else {
        panel.innerHTML = list.slice(0, 8).map((c) => {
          const priv = c.opponent ? ` <span class="badge">private</span>` : "";
          const stake = c.stake > 0 ? `<span class="text-gold">K${c.stake}</span>` : "Casual";
          return `<a class="live-ch" href="/lobby/">
            <span><i class="fa-solid fa-user"></i> ${c.challenger}${priv}</span>
            <span class="badge badge-rated">${c.time_control}</span>
            <span>${stake}</span></a>`;
        }).join("");
      }
    }
    // Toast only for genuinely new open challenges (not on first load).
    const isFirst = seenChallenges.size === 0;
    const current = new Set(list.map((c) => c.id));
    if (!isFirst) {
      list.forEach((c) => {
        if (!seenChallenges.has(c.id)) {
          toast("challenge", `New challenge from ${c.challenger} (${c.time_control}${c.stake ? ", K" + c.stake : ""})`);
        }
      });
    }
    seenChallenges.clear();
    current.forEach((id) => seenChallenges.add(id));
  });

  // Toggle the live-challenges dropdown.
  const lcBtn = document.querySelector(".live-challenges-btn");
  const lcPanel = document.getElementById("globalChallenges");
  if (lcBtn && lcPanel) {
    lcBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      lcPanel.classList.toggle("show");
    });
    document.addEventListener("click", (e) => {
      if (!lcPanel.contains(e.target) && !lcBtn.contains(e.target))
        lcPanel.classList.remove("show");
    });
  }

  // ---- CSRF helper for fetch POST --------------------------------
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  window.zcPost = async function (url, data) {
    const fd = new FormData();
    for (const k in data) fd.append(k, data[k]);
    const res = await fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": csrfMeta ? csrfMeta.content : "" },
      body: fd,
    });
    return res;
  };

  window.zcSocket = socket;
  window.zcToast = toast;
})();
