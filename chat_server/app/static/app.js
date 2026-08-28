(() => {
  const B = document.body;
  const BASE = B.dataset.base || "";
  const ME = parseInt(B.dataset.me, 10);
  const IS_ADMIN = B.dataset.admin === "1";
  const VAPID = B.dataset.vapid;

  const $ = (id) => document.getElementById(id);
  const api = (p, opt) => fetch(BASE + p, Object.assign({credentials: "same-origin"}, opt));

  let state = {rooms: [], users: [], online: new Set()};
  let currentRoom = null;
  let typingTimer = null;
  let replyTo = null;
  // Zustand des gerade gerenderten Verlaufs - steuert Tagestrenner und die
  // Wiederholung des Absendernamens. Nicht aus dem DOM ablesen: der letzte
  // Knoten ist im Normalfall eine .msg, kein .day.
  let lastDay = "";
  let lastAuthor = null;
  const typingUsers = new Map();

  // ---------- Hilfen ----------
  const esc = (s) => (s || "").replace(/[&<>"]/g, (c) =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

  const timeOf = (ts) => new Date(ts * 1000)
    .toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"});

  const dayOf = (ts) => {
    const d = new Date(ts * 1000), now = new Date();
    const same = (a, b) => a.toDateString() === b.toDateString();
    if (same(d, now)) return "Heute";
    const y = new Date(now.getTime() - 86400000);
    if (same(d, y)) return "Gestern";
    return d.toLocaleDateString("de-DE", {weekday: "short", day: "2-digit", month: "2-digit", year: "numeric"});
  };

  const shortTime = (ts) => {
    if (!ts) return "";
    const d = new Date(ts * 1000);
    return d.toDateString() === new Date().toDateString()
      ? timeOf(ts) : d.toLocaleDateString("de-DE", {day: "2-digit", month: "2-digit"});
  };

  const fileSize = (b) => b < 1024 ? b + " B"
    : b < 1048576 ? (b / 1024).toFixed(0) + " KB" : (b / 1048576).toFixed(1) + " MB";

  const toast = (text) => {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = text;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3200);
  };

  // ---------- Räume ----------
  function renderRooms() {
    const list = $("rooms");
    if (!state.rooms.length) {
      list.innerHTML = '<div class="empty" style="padding:24px">Noch keine Unterhaltung. Leg mit „+ Neu“ los.</div>';
      return;
    }
    list.innerHTML = state.rooms.map((r) => {
      const online = r.is_group
        ? r.members.some((m) => m.id !== ME && state.online.has(m.id))
        : r.members.some((m) => m.id !== ME && state.online.has(m.id));
      const prev = r.last ? (r.is_group ? `${r.last.author}: ${r.last.text}` : r.last.text) : "Noch keine Nachricht";
      return `<div class="room ${currentRoom === r.id ? "active" : ""}" data-id="${r.id}">
        <div class="name"><span class="dot ${online ? "on" : ""}"></span>${esc(r.name)}${r.is_group ? " ·" + r.members.length : ""}</div>
        <div class="time">${shortTime(r.last ? r.last.at : 0)}</div>
        <div class="preview">${esc(prev)}</div>
        ${r.unread ? `<span class="badge">${r.unread}</span>` : ""}
      </div>`;
    }).join("");
    list.querySelectorAll(".room").forEach((el) =>
      el.addEventListener("click", () => openRoom(parseInt(el.dataset.id, 10))));
  }

  function roomById(id) { return state.rooms.find((r) => r.id === id); }

  async function openRoom(id) {
    if (currentRoom !== id) cancelReply();
    currentRoom = id;
    const room = roomById(id);
    $("app").classList.add("room-open");
    $("chat-header").hidden = false;
    $("composer").hidden = false;
    $("btn-invite").hidden = !room.is_group;
    $("room-title").textContent = room.name;
    const others = room.members.filter((m) => m.id !== ME);
    $("room-sub").textContent = room.is_group
      ? room.members.map((m) => m.display_name).join(", ")
      : (others.length && state.online.has(others[0].id) ? "online" : "offline");

    const res = await api(`/api/rooms/${id}/messages`);
    const msgs = await res.json();
    $("messages").innerHTML = "";
    lastDay = "";
    lastAuthor = null;
    msgs.forEach((m) => appendMsg(m));
    scrollDown();
    room.unread = 0;
    renderRooms();
    api(`/api/rooms/${id}/read`, {method: "POST"});
    $("input").focus();
  }

  function scrollDown() {
    const box = $("messages");
    box.scrollTop = box.scrollHeight;
  }

  function appendMsg(m) {
    const box = $("messages");
    const day = dayOf(m.at);
    if (day !== lastDay) {
      const d = document.createElement("div");
      d.className = "day";
      d.textContent = day;
      box.appendChild(d);
      lastDay = day;
      lastAuthor = null;
    }
    const prevAuthor = lastAuthor;
    lastAuthor = m.user_id;
    const wrap = document.createElement("div");
    wrap.className = "msg" + (m.user_id === ME ? " mine" : "") + (m.deleted ? " gone" : "");
    wrap.dataset.id = m.id;
    const room = roomById(m.room_id);
    const showAuthor = room && room.is_group && m.user_id !== ME && m.user_id !== prevAuthor;
    let inner = showAuthor ? `<div class="author">${esc(m.author)}</div>` : "";

    if (m.deleted) {
      inner += `<div class="bubble"><span class="gone-text">Nachricht gelöscht</span>
        <div class="meta">${timeOf(m.at)}</div></div>`;
      wrap.innerHTML = inner;
      box.appendChild(wrap);
      return;
    }

    let quoteHtml = "";
    if (m.reply) {
      quoteHtml = `<div class="quote" data-target="${m.reply.id}">
        <span class="q-author">${esc(m.reply.author)}</span>
        <span class="q-text">${esc(m.reply.text)}</span></div>`;
    }
    let fileHtml = "";
    if (m.file) {
      const url = `${BASE}/files/${m.file.id}`;
      fileHtml = (m.file.mime || "").startsWith("image/")
        ? `<a href="${url}" target="_blank" rel="noopener"><img src="${url}" alt="${esc(m.file.name)}"></a>`
        : `<a class="file-link" href="${url}?dl=1">📄 <span>${esc(m.file.name)}</span>
             <span class="fsize">${fileSize(m.file.size)}</span></a>`;
    }
    const canDelete = m.user_id === ME || IS_ADMIN;
    inner += `<div class="bubble">${quoteHtml}${fileHtml}${esc(m.body)}
      <div class="meta">${timeOf(m.at)}</div>
      <div class="actions">
        <button class="act" data-act="reply">Antworten</button>
        ${canDelete ? '<button class="act del" data-act="delete">Löschen</button>' : ""}
      </div></div>`;
    wrap.innerHTML = inner;
    box.appendChild(wrap);
  }

  $("messages").addEventListener("click", (e) => {
    const quote = e.target.closest(".quote");
    if (quote) {
      const target = $("messages").querySelector(`.msg[data-id="${quote.dataset.target}"]`);
      if (target) {
        target.scrollIntoView({block: "center", behavior: "smooth"});
        target.classList.add("flash");
        setTimeout(() => target.classList.remove("flash"), 1200);
      } else {
        toast("Die zitierte Nachricht liegt weiter oben im Verlauf.");
      }
      return;
    }
    const act = e.target.closest(".act");
    if (act) {
      const msg = act.closest(".msg");
      const id = parseInt(msg.dataset.id, 10);
      if (act.dataset.act === "reply") startReply(id, msg);
      else deleteMessage(id);
      msg.classList.remove("open");
      return;
    }
    const bubble = e.target.closest(".bubble");
    if (bubble && !e.target.closest("a")) {
      const msg = bubble.closest(".msg");
      const wasOpen = msg.classList.contains("open");
      $("messages").querySelectorAll(".msg.open").forEach((el) => el.classList.remove("open"));
      if (!wasOpen) msg.classList.add("open");
    }
  });

  function startReply(id, msgEl) {
    const author = msgEl.querySelector(".author")?.textContent
      || (msgEl.classList.contains("mine") ? B.dataset.name : roomById(currentRoom).name);
    const text = msgEl.querySelector(".bubble").childNodes[0]?.textContent?.trim()
      || msgEl.querySelector(".bubble").textContent.trim();
    replyTo = id;
    $("reply-bar").hidden = false;
    $("reply-author").textContent = author;
    $("reply-text").textContent = text.slice(0, 90);
    $("input").focus();
  }

  function cancelReply() {
    replyTo = null;
    $("reply-bar").hidden = true;
  }
  $("reply-cancel").addEventListener("click", cancelReply);

  async function deleteMessage(id) {
    const res = await api(`/api/messages/${id}`, {method: "DELETE"});
    if (!res.ok) {
      const data = await res.json();
      toast(data.error || "Löschen fehlgeschlagen.");
    }
  }

  function pushMessage(m) {
    const box = $("messages");
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
    appendMsg(m);
    if (atBottom || m.user_id === ME) scrollDown();
  }

  // ---------- Socket ----------
  // Erst Polling, dann auf WebSocket hochstufen - das ist die Standardfolge
  // von Socket.IO. Andersherum beantwortet der Werkzeug-Server die allererste
  // Anfrage mit 500 ("write() before start_response"), fuellt das Add-on-Log
  // mit Tracebacks und verzoegert jeden Verbindungsaufbau um einen Fehlversuch.
  const socket = io({path: BASE + "/socket.io", transports: ["polling", "websocket"]});

  socket.on("connect_error", () => toast("Verbindung unterbrochen – versuche es erneut."));

  socket.on("message", (m) => {
    const room = roomById(m.room_id);
    if (room) {
      room.last = {text: m.body || "Datei", author: m.author, at: m.at};
      if (m.room_id === currentRoom) {
        pushMessage(m);
        api(`/api/rooms/${m.room_id}/read`, {method: "POST"});
      } else if (m.user_id !== ME) {
        room.unread = (room.unread || 0) + 1;
      }
      state.rooms.sort((a, b) => (b.last?.at || 0) - (a.last?.at || 0));
      renderRooms();
    } else {
      loadState();
    }
  });

  socket.on("message_deleted", (d) => {
    const el = $("messages").querySelector(`.msg[data-id="${d.id}"]`);
    if (el && d.room_id === currentRoom) {
      el.classList.add("gone");
      el.querySelector(".bubble").innerHTML =
        `<span class="gone-text">Nachricht gelöscht</span>`;
    }
    const room = roomById(d.room_id);
    if (room) loadState();
  });

  socket.on("presence", (p) => {
    if (p.online) state.online.add(p.user_id); else state.online.delete(p.user_id);
    renderRooms();
    if (currentRoom) {
      const room = roomById(currentRoom);
      if (room && !room.is_group) {
        const other = room.members.find((m) => m.id !== ME);
        $("room-sub").textContent = other && state.online.has(other.id) ? "online" : "offline";
      }
    }
  });

  socket.on("room_added", () => loadState());

  // Konten geaendert oder entfernt - Namen und Auswahllisten nachziehen.
  socket.on("user_changed", () => loadState());
  socket.on("user_removed", () => loadState());

  // Wer gesperrt oder geloescht wird, fliegt serverseitig aus der Verbindung.
  socket.on("disconnect", (reason) => {
    if (reason === "io server disconnect") location.reload();
  });

  socket.on("typing", (t) => {
    if (t.room_id !== currentRoom || t.user_id === ME) return;
    typingUsers.set(t.user_id, t.name);
    renderTyping();
    setTimeout(() => { typingUsers.delete(t.user_id); renderTyping(); }, 3000);
  });

  function renderTyping() {
    const names = [...typingUsers.values()];
    $("typing").textContent = names.length
      ? `${names.join(", ")} schreibt${names.length > 1 ? "en" : ""} …` : "";
  }

  // ---------- Senden ----------
  const input = $("input");
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
    if (!typingTimer && currentRoom) {
      socket.emit("typing", {room_id: currentRoom, name: B.dataset.name});
      typingTimer = setTimeout(() => { typingTimer = null; }, 1500);
    }
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
  $("btn-send").addEventListener("click", send);

  function send(fileId) {
    const body = input.value.trim();
    if ((!body && !fileId) || !currentRoom) return;
    socket.emit("send", {room_id: currentRoom, body, file_id: fileId || null,
                         reply_to: replyTo});
    input.value = "";
    input.style.height = "auto";
    cancelReply();
  }

  $("btn-file").addEventListener("click", () => $("file-input").click());
  $("file-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file || !currentRoom) return;
    const fd = new FormData();
    fd.append("file", file);
    toast("Datei wird hochgeladen …");
    const res = await api("/api/upload", {method: "POST", body: fd});
    const data = await res.json();
    if (!res.ok) { toast(data.error || "Upload fehlgeschlagen."); return; }
    send(data.id);
    e.target.value = "";
  });

  $("btn-back").addEventListener("click", () => {
    $("app").classList.remove("room-open");
    currentRoom = null;
  });

  // ---------- Modals ----------
  function modal(html) {
    const root = $("modal-root");
    root.innerHTML = `<div class="modal-bg"><div class="modal">${html}</div></div>`;
    root.querySelector(".modal-bg").addEventListener("click", (e) => {
      if (e.target.classList.contains("modal-bg")) root.innerHTML = "";
    });
    return root;
  }
  const closeModal = () => { $("modal-root").innerHTML = ""; };

  $("btn-new").addEventListener("click", () => {
    const others = state.users.filter((u) => u.id !== ME);
    const root = modal(`<h2>Neue Unterhaltung</h2>
      <div class="field"><label>Gruppenname (leer lassen für Einzelchat)</label>
      <input id="m-name" placeholder="z. B. Familie"></div>
      <div id="m-users">${others.map((u) =>
        `<div class="pick" data-id="${u.id}"><span class="dot ${state.online.has(u.id) ? "on" : ""}"></span>${esc(u.display_name)}</div>`
      ).join("") || '<p class="hint">Es gibt noch keine anderen Konten.</p>'}</div>
      <div class="row"><button class="btn ghost" id="m-cancel">Abbrechen</button>
      <button class="btn" id="m-ok">Anlegen</button></div>`);
    const sel = new Set();
    root.querySelectorAll(".pick").forEach((el) => el.addEventListener("click", () => {
      const id = parseInt(el.dataset.id, 10);
      sel.has(id) ? sel.delete(id) : sel.add(id);
      el.classList.toggle("sel");
    }));
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    root.querySelector("#m-ok").addEventListener("click", async () => {
      const name = root.querySelector("#m-name").value.trim();
      const members = [...sel];
      if (!members.length) return toast("Wähle mindestens eine Person aus.");
      const isGroup = !!name || members.length > 1;
      if (isGroup && !name) return toast("Gruppen brauchen einen Namen.");
      const res = await api("/api/rooms", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name, members, is_group: isGroup}),
      });
      const data = await res.json();
      if (!res.ok) return toast(data.error);
      closeModal();
      await loadState();
      openRoom(data.id);
    });
  });

  $("btn-invite").addEventListener("click", () => {
    const room = roomById(currentRoom);
    const inRoom = new Set(room.members.map((m) => m.id));
    const cands = state.users.filter((u) => !inRoom.has(u.id));
    const root = modal(`<h2>Person zu „${esc(room.name)}“ hinzufügen</h2>
      ${cands.map((u) => `<div class="pick" data-id="${u.id}">${esc(u.display_name)}</div>`).join("")
        || '<p class="hint">Alle Konten sind schon in dieser Gruppe.</p>'}
      <div class="row"><button class="btn ghost" id="m-cancel">Schließen</button></div>`);
    root.querySelectorAll(".pick").forEach((el) => el.addEventListener("click", async () => {
      await api(`/api/rooms/${currentRoom}/members`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({user_id: parseInt(el.dataset.id, 10)}),
      });
      closeModal();
      await loadState();
      toast("Person hinzugefügt.");
    }));
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
  });

  $("btn-settings").addEventListener("click", () => {
    const root = modal(`<h2>Einstellungen</h2>
      <div class="field"><label>Aktuelles Passwort</label><input id="p-old" type="password"></div>
      <div class="field"><label>Neues Passwort</label><input id="p-new" type="password"></div>
      <button class="btn" id="p-ok">Passwort ändern</button>
      ${IS_ADMIN ? `<hr class="sep">
        <h2>Benutzer verwalten</h2>
        <div id="u-list" class="user-list"><p class="hint">Wird geladen …</p></div>
        <button class="btn ghost" id="u-new">+ Neues Konto</button>` : ""}
      <div class="row"><button class="btn ghost" id="m-cancel">Schließen</button>
      <a class="btn ghost" style="text-align:center;text-decoration:none;line-height:2.2" href="${BASE}/logout">Abmelden</a></div>`);
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    root.querySelector("#p-ok").addEventListener("click", async () => {
      const res = await api("/api/me/password", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({old: root.querySelector("#p-old").value,
                              new: root.querySelector("#p-new").value}),
      });
      const data = await res.json();
      toast(res.ok ? "Passwort geändert." : data.error);
      if (res.ok) closeModal();
    });
    if (IS_ADMIN) {
      renderUserAdmin(root);
      root.querySelector("#u-new").addEventListener("click", () => newUserDialog());
    }
  });

  // ---------- Benutzerverwaltung (nur Administratoren) ----------
  async function adminCall(path, opt, okText) {
    const res = await api(path, opt);
    let data = {};
    try { data = await res.json(); } catch (err) { /* 204 o. ae. */ }
    toast(res.ok ? okText : (data.error || "Das hat nicht geklappt."));
    return res.ok;
  }

  async function renderUserAdmin(root) {
    const box = root.querySelector("#u-list");
    if (!box) return;
    const res = await api("/api/users");
    if (!res.ok) { box.innerHTML = '<p class="hint">Liste nicht verfügbar.</p>'; return; }
    const users = await res.json();
    // Der letzte verbliebene Administrator darf sich nicht selbst entmachten -
    // dann gaebe es niemanden mehr, der Konten verwaltet.
    const letzterAdmin = users.filter((u) => u.is_admin && u.active).length <= 1;
    box.innerHTML = users.map((u) => {
      const selbst = u.id === ME;
      const schuetzen = selbst || (u.is_admin && letzterAdmin);
      return `
      <div class="urow ${u.active ? "" : "off"}" data-id="${u.id}">
        <div class="uinfo">
          <span class="uname">${esc(u.display_name)}</span>
          <span class="utag">@${esc(u.username)}</span>
          ${u.is_admin ? '<span class="chip admin">Admin</span>' : ""}
          ${u.active ? "" : '<span class="chip off">gesperrt</span>'}
          ${selbst ? '<span class="chip me">du</span>' : ""}
        </div>
        <div class="uacts">
          <button class="act" data-act="pw" title="Passwort zurücksetzen">Passwort</button>
          ${schuetzen ? "" : `
          <button class="act" data-act="admin" title="${u.is_admin ? "Administratorrecht entziehen" : "Zum Administrator machen"}">${u.is_admin ? "Kein Admin" : "Admin"}</button>
          <button class="act" data-act="active" title="${u.active ? "Konto sperren" : "Konto entsperren"}">${u.active ? "Sperren" : "Entsperren"}</button>
          <button class="act del" data-act="del" title="Konto endgültig löschen">Löschen</button>`}
          ${!selbst && u.is_admin && letzterAdmin
            ? '<span class="hint inline">letzter Administrator</span>' : ""}
        </div>
      </div>`;
    }).join("") || '<p class="hint">Es gibt noch keine weiteren Konten.</p>';

    box.querySelectorAll(".act").forEach((btn) => btn.addEventListener("click", async () => {
      const row = btn.closest(".urow");
      const id = parseInt(row.dataset.id, 10);
      const user = users.find((u) => u.id === id);
      const json = (body) => ({method: "PATCH",
                               headers: {"Content-Type": "application/json"},
                               body: JSON.stringify(body)});
      let ok = false;
      if (btn.dataset.act === "pw") {
        return passwordDialog(user, root);
      } else if (btn.dataset.act === "admin") {
        ok = await adminCall(`/api/users/${id}`, json({is_admin: !user.is_admin}),
                             user.is_admin ? "Administratorrecht entzogen."
                                           : "Konto ist jetzt Administrator.");
      } else if (btn.dataset.act === "active") {
        ok = await adminCall(`/api/users/${id}`, json({active: !user.active}),
                             user.active ? "Konto gesperrt." : "Konto entsperrt.");
      } else if (btn.dataset.act === "del") {
        if (!confirm(`Konto „${user.display_name}“ endgültig löschen?\n\n`
                     + "Die Nachrichten bleiben im Verlauf stehen, erscheinen aber "
                     + "unter „Gelöschtes Konto“. Das lässt sich nicht rückgängig machen."))
          return;
        ok = await adminCall(`/api/users/${id}`, {method: "DELETE"}, "Konto gelöscht.");
      }
      if (ok) { renderUserAdmin(root); loadState(); }
    }));
  }

  function passwordDialog(user, settingsRoot) {
    const root = modal(`<h2>Passwort zurücksetzen</h2>
      <p class="hint">für <strong>${esc(user.display_name)}</strong> (@${esc(user.username)})</p>
      <div class="field"><label>Neues Passwort (min. 6 Zeichen)</label>
        <input id="r-pw" type="text" autocomplete="off"></div>
      <p class="hint">Das Konto wird auf allen Geräten abgemeldet. Gib das Passwort
        persönlich weiter und lass es danach selbst ändern.</p>
      <div class="row"><button class="btn ghost" id="r-cancel">Abbrechen</button>
      <button class="btn" id="r-ok">Zurücksetzen</button></div>`);
    root.querySelector("#r-cancel").addEventListener("click", closeModal);
    root.querySelector("#r-ok").addEventListener("click", async () => {
      const ok = await adminCall(`/api/users/${user.id}/password`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({password: root.querySelector("#r-pw").value}),
      }, "Passwort zurückgesetzt.");
      if (ok) { closeModal(); $("btn-settings").click(); }
    });
    void settingsRoot;
  }

  function newUserDialog() {
    const root = modal(`<h2>Neues Konto anlegen</h2>
      <div class="field"><label>Benutzername (zum Anmelden, klein geschrieben)</label>
        <input id="u-name" autocomplete="off"></div>
      <div class="field"><label>Anzeigename</label><input id="u-disp" autocomplete="off"></div>
      <div class="field"><label>Passwort (min. 6 Zeichen)</label>
        <input id="u-pw" type="text" autocomplete="off"></div>
      <label class="check"><input type="checkbox" id="u-admin"> Administrator</label>
      <div class="row"><button class="btn ghost" id="n-cancel">Abbrechen</button>
      <button class="btn" id="n-ok">Anlegen</button></div>`);
    root.querySelector("#n-cancel").addEventListener("click", closeModal);
    root.querySelector("#n-ok").addEventListener("click", async () => {
      const ok = await adminCall("/api/users", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          username: root.querySelector("#u-name").value,
          display_name: root.querySelector("#u-disp").value,
          password: root.querySelector("#u-pw").value,
          is_admin: root.querySelector("#u-admin").checked,
        }),
      }, "Konto angelegt.");
      if (ok) { closeModal(); loadState(); $("btn-settings").click(); }
    });
  }

  // ---------- Medien ----------
  let medienRaum = 0;  // 0 = alle Unterhaltungen

  $("btn-media").addEventListener("click", () => {
    medienRaum = currentRoom || 0;
    medienDialog();
  });

  function medienDialog() {
    const optionen = state.rooms
      .map((r) => `<option value="${r.id}" ${r.id === medienRaum ? "selected" : ""}>${esc(r.name)}</option>`)
      .join("");
    const root = modal(`<div class="media-head">
        <h2>Bilder und Dateien</h2>
        <select id="md-room" class="media-filter">
          <option value="0" ${medienRaum ? "" : "selected"}>Alle Unterhaltungen</option>
          ${optionen}
        </select>
      </div>
      <div id="md-body" class="media-body"><p class="hint">Wird geladen …</p></div>
      <div class="row"><button class="btn ghost" id="m-cancel">Schließen</button></div>`);
    root.querySelector(".modal").classList.add("wide");
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    root.querySelector("#md-room").addEventListener("change", (e) => {
      medienRaum = parseInt(e.target.value, 10);
      ladeMedien(root);
    });
    ladeMedien(root);
  }

  async function ladeMedien(root) {
    const box = root.querySelector("#md-body");
    const res = await api("/api/media" + (medienRaum ? `?room=${medienRaum}` : ""));
    if (!res.ok) { box.innerHTML = '<p class="hint">Konnte nicht geladen werden.</p>'; return; }
    const alle = await res.json();
    if (!alle.length) {
      box.innerHTML = '<p class="hint">Hier wurde noch nichts geteilt.</p>';
      return;
    }
    const bilder = alle.filter((m) => (m.mime || "").startsWith("image/"));
    const dateien = alle.filter((m) => !(m.mime || "").startsWith("image/"));
    const raumName = (id) => roomById(id)?.name || "Unterhaltung";
    const herkunft = (m) => `${esc(m.author)} · ${medienRaum ? "" : esc(raumName(m.room_id)) + " · "}${shortTime(m.at)}`;

    box.innerHTML = `
      ${bilder.length ? `<div class="media-grid">${bilder.map((m) => `
        <figure class="media-cell" data-id="${m.id}">
          <a href="${BASE}/files/${m.id}" target="_blank" rel="noopener">
            <img src="${BASE}/files/${m.id}" alt="${esc(m.name)}" loading="lazy">
          </a>
          <figcaption>${herkunft(m)}</figcaption>
          ${m.can_delete ? '<button class="media-del" data-act="del" title="Löschen">✕</button>' : ""}
        </figure>`).join("")}</div>` : ""}
      ${dateien.length ? `<div class="media-files">${dateien.map((m) => `
        <div class="media-row" data-id="${m.id}">
          <a class="file-link" href="${BASE}/files/${m.id}?dl=1">📄 <span>${esc(m.name)}</span>
            <span class="fsize">${fileSize(m.size)}</span></a>
          <span class="media-meta">${herkunft(m)}</span>
          ${m.can_delete ? '<button class="act del" data-act="del">Löschen</button>' : ""}
        </div>`).join("")}</div>` : ""}`;

    box.querySelectorAll('[data-act="del"]').forEach((btn) =>
      btn.addEventListener("click", async () => {
        const el = btn.closest("[data-id]");
        const eintrag = alle.find((m) => m.id === parseInt(el.dataset.id, 10));
        if (!confirm(`„${eintrag.name}“ endgültig löschen?\n\n`
                     + "Die Datei verschwindet aus der Unterhaltung und wird vom "
                     + "Server entfernt. Das lässt sich nicht rückgängig machen."))
          return;
        const res = await api(`/api/media/${eintrag.id}`, {method: "DELETE"});
        if (!res.ok) {
          const daten = await res.json().catch(() => ({}));
          toast(daten.error || "Löschen fehlgeschlagen.");
          return;
        }
        toast("Datei gelöscht.");
        ladeMedien(root);
        if (eintrag.room_id === currentRoom) openRoom(currentRoom);
      }));
  }

  // ---------- Push ----------
  const b64 = (s) => {
    const pad = "=".repeat((4 - (s.length % 4)) % 4);
    const raw = atob((s + pad).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
  };

  $("btn-push").addEventListener("click", async () => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      return toast("Dieser Browser unterstützt keine Push-Benachrichtigungen.");
    }
    if (location.protocol !== "https:" && location.hostname !== "localhost") {
      return toast("Push braucht HTTPS – öffne den Chat über deine externe Adresse.");
    }
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return toast("Benachrichtigungen wurden abgelehnt.");
    try {
      const reg = await navigator.serviceWorker.register(BASE + "/sw.js", {scope: BASE + "/"});
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: b64(VAPID),
      });
      const res = await api("/api/push/subscribe", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(sub),
      });
      toast(res.ok ? "Benachrichtigungen sind aktiv." : "Anmeldung für Push fehlgeschlagen.");
    } catch (err) {
      toast("Push konnte nicht eingerichtet werden: " + err.message);
    }
  });

  // ---------- Start ----------
  async function loadState() {
    const res = await api("/api/state");
    if (res.status === 401) return location.reload();
    const data = await res.json();
    state.rooms = data.rooms;
    state.users = data.users;
    state.online = new Set(data.online);
    renderRooms();
  }

  loadState().then(() => {
    const wanted = parseInt(new URLSearchParams(location.search).get("room"), 10);
    if (wanted && roomById(wanted)) openRoom(wanted);
  });
})();
