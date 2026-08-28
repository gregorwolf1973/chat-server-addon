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

  // Standort und Kamera geben Browser nur in einem "sicheren Kontext" heraus.
  // Dazu zaehlt neben HTTPS auch localhost und 127.0.0.1 - deshalb die
  // Browser-Auskunft statt einer eigenen Namensliste.
  const sichererKontext = () =>
    window.isSecureContext || location.protocol === "https:";

  // ---------- Profilbilder ----------
  // Ohne Bild zeigen wir die Initialen auf farbigem Grund. Die Farbe haengt
  // an der Kennung, bleibt also fuer dieselbe Person immer gleich.
  const AVATAR_FARBEN = ["#3f6f6b", "#6b4f7a", "#7a5a3c", "#3c5a7a", "#6f6b3f",
                         "#7a3c4f", "#417a5a", "#54487a"];

  const initialen = (name) => (name || "?").trim().split(/\s+/).slice(0, 2)
    .map((w) => w[0] || "").join("").toUpperCase() || "?";

  function avatarHtml(kind, id, name, avatar, extra = "") {
    if (avatar) {
      return `<img class="avatar ${extra}" alt=""`
        + ` src="${BASE}/avatars/${kind}/${id}?v=${encodeURIComponent(avatar)}">`;
    }
    const farbe = AVATAR_FARBEN[Math.abs(id || 0) % AVATAR_FARBEN.length];
    return `<span class="avatar ${extra} initialen" style="background:${farbe}">`
      + `${esc(initialen(name))}</span>`;
  }

  // Bild eines Raumes: bei Gruppen das Gruppenbild, bei Direktchats das der
  // Gegenseite - so wie man es aus anderen Messengern kennt.
  function raumAvatar(room, extra = "") {
    if (room.is_group) return avatarHtml("r", room.id, room.name, room.avatar, extra);
    const other = room.members.find((m) => m.id !== ME) || room.members[0];
    return other ? avatarHtml("u", other.id, other.display_name, other.avatar, extra)
                 : avatarHtml("r", room.id, room.name, null, extra);
  }

  // Vor dem Hochladen im Browser verkleinern und mittig quadratisch
  // zuschneiden - sonst landen Handyfotos in voller Groesse auf dem Pi.
  function bildVerkleinern(datei, kante = 256) {
    return new Promise((fertig, fehler) => {
      const bild = new Image();
      bild.onload = () => {
        const seite = Math.min(bild.width, bild.height);
        const leinwand = document.createElement("canvas");
        leinwand.width = leinwand.height = kante;
        leinwand.getContext("2d").drawImage(
          bild, (bild.width - seite) / 2, (bild.height - seite) / 2, seite, seite,
          0, 0, kante, kante);
        URL.revokeObjectURL(bild.src);
        leinwand.toBlob((b) => b ? fertig(b) : fehler(new Error("Bild fehlerhaft")),
                        "image/jpeg", 0.85);
      };
      bild.onerror = () => fehler(new Error("Das ist kein lesbares Bild."));
      bild.src = URL.createObjectURL(datei);
    });
  }

  // Dateiauswahl oeffnen, Bild verkleinern und an die Adresse schicken
  function bildWaehlen(ziel, fertig) {
    const feld = document.createElement("input");
    feld.type = "file";
    feld.accept = "image/*";
    feld.addEventListener("change", async () => {
      const datei = feld.files[0];
      if (!datei) return;
      try {
        const klein = await bildVerkleinern(datei);
        const fd = new FormData();
        fd.append("file", klein, "avatar.jpg");
        const res = await api(ziel, {method: "POST", body: fd});
        const daten = await res.json().catch(() => ({}));
        if (!res.ok) { toast(daten.error || "Hochladen fehlgeschlagen."); return; }
        toast("Bild gespeichert.");
        await loadState();
        if (fertig) fertig();
      } catch (err) {
        toast(err.message);
      }
    });
    feld.click();
  }

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
      reiterZahlen();
      return;
    }
    list.innerHTML = state.rooms.map((r) => {
      const online = r.is_group
        ? r.members.some((m) => m.id !== ME && state.online.has(m.id))
        : r.members.some((m) => m.id !== ME && state.online.has(m.id));
      const prev = r.last ? (r.is_group ? `${r.last.author}: ${r.last.text}` : r.last.text) : "Noch keine Nachricht";
      return `<div class="room ${currentRoom === r.id ? "active" : ""}" data-id="${r.id}">
        ${raumAvatar(r)}
        <div class="name"><span class="dot ${online ? "on" : ""}"></span>${esc(r.name)}${r.is_group ? " ·" + r.members.length : ""}</div>
        <div class="time">${shortTime(r.last ? r.last.at : 0)}</div>
        <div class="preview">${esc(prev)}</div>
        ${r.unread ? `<span class="badge">${r.unread}</span>` : ""}
      </div>`;
    }).join("");
    list.querySelectorAll(".room").forEach((el) =>
      el.addEventListener("click", () => openRoom(parseInt(el.dataset.id, 10))));
    reiterZahlen();
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
    $("room-avatar").innerHTML = raumAvatar(room, "gross");
    $("room-avatar").title = "Angaben zur Unterhaltung";
    $("room-avatar").classList.add("aenderbar");
    hintergrundAnwenden(room);
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
    klingelZeigen();
    $("input").focus();
  }

  function scrollDown() {
    const box = $("messages");
    box.scrollTop = box.scrollHeight;
  }

  // Kraeftigere Toene als bei den Profilbildern - der Name steht als Text auf
  // dunklem Grund und soll sich abheben.
  const NAMENSFARBEN = ["#6fd3c7", "#f2a65a", "#8fbcff", "#e58fd0", "#9fd67a",
                        "#ffd166", "#c8a2ff", "#ff9b8a"];
  const namensFarbe = (id) => NAMENSFARBEN[Math.abs(id || 0) % NAMENSFARBEN.length];

  function anhangHtml(datei) {
    const url = `${BASE}/files/${datei.id}`;
    const art = (datei.mime || "").split("/")[0];
    if (art === "image") {
      return `<a class="bild" href="${url}" target="_blank" rel="noopener">`
        + `<img src="${url}" alt="${esc(datei.name)}" loading="lazy"></a>`;
    }
    if (art === "video") {
      // preload="metadata" laedt nur den Anfang - das genuegt fuer das
      // Vorschaubild, ohne das ganze Video zu ziehen.
      return `<video class="abspieler" controls playsinline preload="metadata"`
        + ` src="${url}"></video>`;
    }
    if (art === "audio") {
      return `<div class="ton"><div class="ton-name">🎵 ${esc(datei.name)}</div>`
        + `<audio class="abspieler" controls preload="metadata" src="${url}"></audio></div>`;
    }
    return `<a class="file-link" href="${url}?dl=1">📄 <span>${esc(datei.name)}</span>`
      + `<span class="fsize">${fileSize(datei.size)}</span></a>`;
  }

  // Gehoert die Nachricht zu einem Album, das gerade schon gerendert wurde?
  // Dann wandert das Bild in dessen Raster, statt eine neue Blase zu oeffnen.
  function inAlbumEinhaengen(m) {
    if (!m.album || !m.file || !(m.file.mime || "").startsWith("image/")) return false;
    const letzte = $("messages").querySelector(".msg:last-child");
    if (!letzte || letzte.dataset.album !== m.album) return false;
    const raster = letzte.querySelector(".album");
    if (!raster) return false;
    raster.insertAdjacentHTML("beforeend", albumBildHtml(m));
    raster.dataset.anzahl = Math.min(raster.children.length, 5);
    // Die Uhrzeit gehoert ans Ende des Albums, nicht zum ersten Bild
    const zeit = letzte.querySelector(".meta");
    if (zeit) zeit.textContent = timeOf(m.at);
    return true;
  }

  function albumBildHtml(m) {
    const url = `${BASE}/files/${m.file.id}`;
    return `<a class="album-bild" href="${url}" target="_blank" rel="noopener"`
      + ` data-nachricht="${m.id}">`
      + `<img src="${url}" alt="${esc(m.file.name)}" loading="lazy"></a>`;
  }

  function appendMsg(m) {
    if (inAlbumEinhaengen(m)) return;
    const box = $("messages");
    const day = dayOf(m.at);
    if (day !== lastDay) {
      const d = document.createElement("div");
      d.className = "day";
      d.textContent = day;
      box.appendChild(d);
      lastDay = day;
    }
    lastAuthor = m.user_id;
    const eigene = m.user_id === ME;
    const wrap = document.createElement("div");
    wrap.className = "msg" + (eigene ? " mine" : "") + (m.deleted ? " gone" : "");
    wrap.dataset.id = m.id;
    if (m.album) wrap.dataset.album = m.album;
    const room = roomById(m.room_id);
    // In Gruppen steht an jeder fremden Nachricht Bild und Name - im
    // Direktchat waere beides ueberfluessig, dort weiss man, mit wem man
    // schreibt.
    const zeigeAbsender = room && room.is_group && !eigene;
    const person = zeigeAbsender
      ? (room.members.find((x) => x.id === m.user_id) || null) : null;

    if (zeigeAbsender) {
      wrap.innerHTML = avatarHtml("u", m.user_id, m.author,
                                  person ? person.avatar : null, "klein");
    }

    const blase = document.createElement("div");
    blase.className = "bubble" + (m.body ? "" : " nur-anhang")
      + (m.deleted ? " nur-anhang" : "");
    let inner = zeigeAbsender
      ? `<div class="author" style="color:${namensFarbe(m.user_id)}">${esc(m.author)}</div>`
      : "";

    if (m.deleted) {
      inner += `<span class="gone-text">Nachricht gelöscht</span>`
        + `<div class="inhalt"><span class="meta">${timeOf(m.at)}</span></div>`;
      blase.innerHTML = inner;
      wrap.appendChild(blase);
      box.appendChild(wrap);
      return;
    }

    if (m.reply) {
      inner += `<div class="quote" data-target="${m.reply.id}">`
        + `<span class="q-author">${esc(m.reply.author)}</span>`
        + `<span class="q-text">${esc(m.reply.text)}</span></div>`;
    }
    if (m.poll) inner += abstimmungHtml(m.poll);
    if (m.event) inner += eventHtml(m.event);
    if (m.ort) inner += ortHtml(m.ort);
    if (m.file && m.sprachdauer) {
      inner += sprachHtml(m.file, m.sprachdauer);
    } else if (m.file && m.album && (m.file.mime || "").startsWith("image/")) {
      inner += `<div class="album" data-anzahl="1">${albumBildHtml(m)}</div>`;
    } else if (m.file) {
      inner += anhangHtml(m.file);
    }

    const canDelete = eigene || IS_ADMIN;
    // Text und Uhrzeit stecken in einem eigenen Block. Waere die Zeit an der
    // Sprechblase verankert, rutschte sie beim Aufklappen der Aktionen mit
    // nach unten und landete neben den Knoepfen.
    inner += `<div class="inhalt"><span class="text">${esc(m.body)}</span>`
      + `<span class="meta">${timeOf(m.at)}</span></div>`
      + `<div class="actions"><button class="act" data-act="reply">Antworten</button>`
      + (canDelete ? '<button class="act del" data-act="delete">Löschen</button>' : "")
      + `</div>`;
    blase.innerHTML = inner;
    wrap.appendChild(blase);
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
    const text = msgEl.querySelector(".bubble .text")?.textContent?.trim()
      || msgEl.querySelector(".file-link span")?.textContent?.trim()
      || "Datei";
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

  socket.on("connect", () => verbindungAnzeigen(true));
  socket.on("connect_error", () => verbindungAnzeigen(false));

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
  socket.on("avatar_changed", () => loadState());
  socket.on("poll_changed", async (d) => {
    const kasten = $("messages").querySelector(`.abstimmung[data-poll="${d.poll_id}"]`);
    if (!kasten) return;
    const res = await api(`/api/polls/${d.poll_id}`);
    if (res.ok) kasten.outerHTML = abstimmungHtml(await res.json());
  });
  socket.on("live_geaendert", () => liveLaden());
  socket.on("stimmung_geaendert", () => stimmungLaden());
  socket.on("event_geaendert", (d) => {
    if (d.event_id) eventNeuZeichnen(d.event_id); else terminLaden();
  });
  socket.on("room_removed", (d) => raumVerlassen(d.id));
  socket.on("room_changed", () => loadState());
  socket.on("user_pending", (u) => {
    if (IS_ADMIN) toast(`Neuer Zugangsantrag von ${u.display_name}.`);
  });
  socket.on("user_removed", () => loadState());

  // Wer gesperrt oder geloescht wird, fliegt serverseitig aus der Verbindung.
  socket.on("disconnect", (reason) => {
    if (reason === "io server disconnect") { location.reload(); return; }
    verbindungAnzeigen(false);
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
  // Auf dem Handy meldet die Bildschirmtastatur bei keydown haeufig gar kein
  // "Enter" - Gboard schickt waehrend der Worterkennung "Unidentified". Der
  // Umbruch selbst kommt aber zuverlaessig als beforeinput an, deshalb hoeren
  // wir auf beides. Am Rechner greift keydown zuerst und unterdrueckt das
  // beforeinput, es wird also nichts doppelt gesendet.
  let mitUmschalt = false;
  input.addEventListener("keydown", (e) => {
    mitUmschalt = e.shiftKey;
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
  input.addEventListener("beforeinput", (e) => {
    if (e.inputType === "insertLineBreak" && !mitUmschalt) {
      e.preventDefault();
      send();
    }
  });
  // Nicht send direkt uebergeben: der Knopf reicht sonst das Klick-Ereignis
  // als erstes Argument weiter - und das heisst dort fileId.
  $("btn-send").addEventListener("click", () => send());

  function send(fileId, album) {
    const body = input.value.trim();
    if ((!body && !fileId) || !currentRoom) return;
    if (!socket.connected) {
      verbindungAnzeigen(false);
      toast("Keine Verbindung – die Nachricht wurde nicht gesendet.");
      return;
    }
    const entwurf = input.value;
    const antwortId = replyTo;
    // Der Server bestaetigt den Empfang. Bleibt sie aus, kommt der Text
    // zurueck ins Feld, statt still zu verschwinden.
    socket.timeout(8000).emit("send",
      {room_id: currentRoom, body, file_id: fileId || null, reply_to: replyTo,
       album: album || null},
      (zeitfehler, antwort) => {
        if (zeitfehler) {
          toast("Der Server hat nicht geantwortet – bitte noch einmal senden.");
        } else if (antwort && antwort.ok === false) {
          toast(antwort.error || "Die Nachricht wurde nicht angenommen.");
        } else {
          return;
        }
        if (!input.value) {
          input.value = entwurf;
          replyTo = antwortId;
        }
      });
    input.value = "";
    input.style.height = "auto";
    cancelReply();
  }

  // Ein Balken ueber dem Eingabefeld zeigt, wenn die Verbindung fehlt -
  // sonst tippt man ins Leere und merkt es erst, wenn niemand antwortet.
  function verbindungAnzeigen(verbunden) {
    let balken = $("verbindung");
    if (!balken) {
      balken = document.createElement("div");
      balken.id = "verbindung";
      balken.className = "verbindung";
      balken.textContent = "Keine Verbindung zum Server – Nachrichten warten.";
      $("composer").parentNode.insertBefore(balken, $("composer"));
    }
    balken.hidden = !!verbunden;
  }

  // ---------- Abstimmung ----------
  function abstimmungHtml(poll) {
    const gesamt = poll.teilnehmer || 0;
    const balken = poll.optionen.map((o) => {
      const anteil = gesamt ? Math.round(o.stimmen / gesamt * 100) : 0;
      const wer = o.wer.map((w) => w.name).join(", ");
      return `<button class="wahl ${o.meine ? "meine" : ""}" data-option="${o.id}"
                      ${wer ? `title="${esc(wer)}"` : ""}>
        <span class="wahl-balken" style="width:${anteil}%"></span>
        <span class="wahl-text">${esc(o.text)}</span>
        <span class="wahl-zahl">${o.stimmen}</span>
      </button>`;
    }).join("");
    return `<div class="abstimmung" data-poll="${poll.id}">
      <div class="frage">📊 ${esc(poll.frage)}</div>
      <div class="wahlen">${balken}</div>
      <div class="wahl-fuss">${gesamt === 1 ? "1 Stimme" : `${gesamt} Stimmen`}${
        poll.mehrfach ? " · mehrere Antworten möglich" : ""}</div>
    </div>`;
  }

  // Stimme abgeben - der Server schickt die neue Auswertung zurueck
  $("messages").addEventListener("click", async (e) => {
    const knopf = e.target.closest(".wahl");
    if (!knopf) return;
    e.preventDefault();
    e.stopPropagation();
    const kasten = knopf.closest(".abstimmung");
    const res = await api(`/api/polls/${kasten.dataset.poll}/vote`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({option_id: parseInt(knopf.dataset.option, 10)}),
    });
    if (!res.ok) { toast("Die Stimme ging nicht durch."); return; }
    kasten.outerHTML = abstimmungHtml(await res.json());
  }, true);

  function abstimmungDialog() {
    if (!currentRoom) return;
    const root = modal(`<h2>Neue Abstimmung</h2>
      <div class="field"><label>Frage</label><input id="ab-frage" autocomplete="off"></div>
      <div class="field"><label>Antworten</label><div id="ab-optionen"></div></div>
      <button class="btn ghost" id="ab-mehr">+ Antwort</button>
      <label class="check"><input type="checkbox" id="ab-mehrfach">
        Mehrere Antworten erlaubt</label>
      <div class="row"><button class="btn ghost" id="m-cancel">Abbrechen</button>
      <button class="btn" id="ab-ok">Abstimmung starten</button></div>`);
    const liste = root.querySelector("#ab-optionen");
    const zeileAnfuegen = () => {
      if (liste.children.length >= 12) { toast("Zwölf Antworten sind genug."); return; }
      const zeile = document.createElement("div");
      zeile.className = "ab-zeile";
      zeile.innerHTML = `<input class="ab-option" autocomplete="off"
        placeholder="Antwort ${liste.children.length + 1}">
        <button class="act del" type="button" title="Entfernen">✕</button>`;
      zeile.querySelector(".act").addEventListener("click", () => {
        if (liste.children.length <= 2) { toast("Zwei Antworten braucht es."); return; }
        zeile.remove();
      });
      liste.appendChild(zeile);
    };
    zeileAnfuegen();
    zeileAnfuegen();
    root.querySelector("#ab-mehr").addEventListener("click", zeileAnfuegen);
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    root.querySelector("#ab-ok").addEventListener("click", async () => {
      const frage = root.querySelector("#ab-frage").value.trim();
      const optionen = [...root.querySelectorAll(".ab-option")]
        .map((i) => i.value.trim()).filter(Boolean);
      if (!frage) { toast("Die Frage fehlt."); return; }
      if (optionen.length < 2) { toast("Es braucht mindestens zwei Antworten."); return; }
      const res = await api(`/api/rooms/${currentRoom}/poll`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({frage, optionen,
                              mehrfach: root.querySelector("#ab-mehrfach").checked}),
      });
      const daten = await res.json().catch(() => ({}));
      if (!res.ok) { toast(daten.error || "Das hat nicht geklappt."); return; }
      closeModal();
    });
  }


  // ---------- Standort ----------
  // Die Weltkarte liegt als SVG im Add-on - fuer die Vorschau wird ein
  // Ausschnitt um den Punkt gezeigt. Es wird nichts von fremden Servern
  // nachgeladen; erst ein Tipp auf "In Karten öffnen" verlaesst das Haus.
  const KARTE_BREITE = 1000, KARTE_HOEHE = 650;
  const KARTE_OBEN = 83.0, KARTE_UNTEN = -60.0;

  const yMerc = (lat) => {
    const b = Math.max(Math.min(lat, 89.5), -89.5);
    return Math.log(Math.tan(Math.PI / 4 + (b * Math.PI / 180) / 2));
  };
  const Y_OBEN = yMerc(KARTE_OBEN), Y_UNTEN = yMerc(KARTE_UNTEN);

  function kartenPunkt(lat, lon) {
    return {
      x: (lon + 180) / 360 * KARTE_BREITE,
      y: (Y_OBEN - yMerc(lat)) / (Y_OBEN - Y_UNTEN) * KARTE_HOEHE,
    };
  }

  // Die Umrisse werden einmal geladen und als Symbol im Dokument abgelegt.
  // Jede Karte verweist dann per <use> darauf - eine Referenz im selben
  // Dokument, denn auf eine externe SVG-Datei laesst Chrome <use> nicht zu.
  let weltkarteBereit = false;

  async function weltkarteLaden() {
    if (weltkarteBereit || document.getElementById("weltkarte-vorrat")) return;
    try {
      const res = await api("/static/weltkarte.svg");
      if (!res.ok) return;
      const pfad = (await res.text()).match(/ d="([^"]+)"/);
      if (!pfad) return;
      const vorrat = document.createElement("div");
      vorrat.id = "weltkarte-vorrat";
      vorrat.hidden = true;
      // Bewusst <g> und nicht <symbol>: ein Symbol mit eigenem viewBox
      // skaliert sich in das <use> hinein, wodurch die ganze Welt in das
      // kleine Vorschaufeld gequetscht wuerde. Eine Gruppe behaelt ihre
      // Koordinaten, und der viewBox der Vorschau schneidet den Ausschnitt.
      vorrat.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg">`
        + `<g id="weltkarte"><path d="${pfad[1]}"/></g></svg>`;
      document.body.appendChild(vorrat);
      weltkarteBereit = true;
      // Karten, die vor dem Laden gezeichnet wurden, nachziehen
      document.querySelectorAll(".ortskarte svg").forEach((svg) => {
        if (!svg.querySelector("use")) {
          svg.innerHTML = '<use href="#weltkarte"></use>';
        }
      });
    } catch (err) { /* ohne Karte bleibt die Adresse trotzdem lesbar */ }
  }

  // Rund 20 Laengengrad Ausschnitt: genug Umriss, um die Gegend zu erkennen.
  // Der genaue Punkt steht als Koordinate darunter.
  function karteHtml(ort, weite = 56, klasse = "ortskarte") {
    const p = kartenPunkt(ort.lat, ort.lon);
    const hoehe = weite * 0.62;
    const x = Math.max(0, Math.min(KARTE_BREITE - weite, p.x - weite / 2));
    const y = Math.max(0, Math.min(KARTE_HOEHE - hoehe, p.y - hoehe / 2));
    return `<div class="${klasse}">
      <svg viewBox="${x} ${y} ${weite} ${hoehe}" preserveAspectRatio="xMidYMid slice"
           xmlns="http://www.w3.org/2000/svg">`
      + (weltkarteBereit ? '<use href="#weltkarte"></use>' : "")
      + `</svg>
      <span class="ortsnadel" style="left:${((p.x - x) / weite * 100).toFixed(2)}%;`
      + ` top:${((p.y - y) / hoehe * 100).toFixed(2)}%"></span>
    </div>`;
  }

  function ortHtml(ort) {
    const grad = `${ort.lat.toFixed(5)}, ${ort.lon.toFixed(5)}`;
    const ziel = `https://www.openstreetmap.org/?mlat=${ort.lat}&mlon=${ort.lon}#map=15/${ort.lat}/${ort.lon}`;
    return `<div class="ort" data-lat="${ort.lat}" data-lon="${ort.lon}">
      ${karteHtml(ort)}
      <div class="ortszeile"><span class="ortsgrad">📍 ${grad}</span>
        <a class="ortslink" href="${ziel}" target="_blank" rel="noopener noreferrer">In Karten öffnen</a></div>
    </div>`;
  }

  function ortSenden() {
    if (!currentRoom) return;
    if (!navigator.geolocation) {
      toast("Dieser Browser kennt keinen Standort.");
      return;
    }
    if (!sichererKontext()) {
      toast("Der Standort geht nur über HTTPS – öffne den Chat über deine "
            + "externe Adresse.");
      return;
    }
    toast("Standort wird bestimmt …");
    navigator.geolocation.getCurrentPosition((pos) => {
      const ort = {lat: pos.coords.latitude, lon: pos.coords.longitude};
      if (!socket.connected) { toast("Keine Verbindung."); return; }
      socket.timeout(8000).emit("send",
        {room_id: currentRoom, body: input.value.trim(), file_id: null,
         reply_to: replyTo, ort},
        (fehler, antwort) => {
          if (fehler || (antwort && antwort.ok === false)) {
            toast("Der Standort ließ sich nicht senden.");
          }
        });
      input.value = "";
      cancelReply();
    }, (err) => {
      toast(err.code === 1 ? "Du hast den Zugriff auf den Standort abgelehnt."
                           : "Der Standort ließ sich nicht bestimmen.");
    }, {enableHighAccuracy: true, timeout: 15000, maximumAge: 60000});
  }

  // ---------- Übersichtskarte ----------
  // Dieselben Umrisse wie bei der Ortsvorschau, aber der Ausschnitt umfasst
  // mehrere Punkte. Es wird nichts von fremden Servern nachgeladen.
  function ausschnittFuer(punkte, rand = 0.45, mindest = 34) {
    const koord = punkte.map((p) => kartenPunkt(p.lat, p.lon));
    let x1 = Math.min(...koord.map((k) => k.x));
    let x2 = Math.max(...koord.map((k) => k.x));
    let y1 = Math.min(...koord.map((k) => k.y));
    let y2 = Math.max(...koord.map((k) => k.y));
    // Ohne Mindestgröße wäre bei Punkten in derselben Stadt gar nichts zu
    // sehen: die grobe Weltkarte kennt keine Straßen, nur Küsten und Grenzen.
    let weite = Math.max(mindest, (x2 - x1) * (1 + rand * 2));
    let hoehe = Math.max(mindest * 0.62, (y2 - y1) * (1 + rand * 2));
    // Seitenverhältnis der Anzeige halten, sonst wird die Karte verzerrt
    if (weite / hoehe < 1.6) weite = hoehe * 1.6; else hoehe = weite / 1.6;
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
    const x = Math.max(0, Math.min(KARTE_BREITE - weite, mx - weite / 2));
    const y = Math.max(0, Math.min(KARTE_HOEHE - hoehe, my - hoehe / 2));
    return {x, y, weite, hoehe};
  }

  function uebersichtHtml(punkte) {
    if (!punkte.length) {
      return '<div class="karte-leer">Hier ist gerade nichts los – niemand '
        + 'teilt seinen Standort, und keine Einladung hat einen Ort.</div>';
    }
    const a = ausschnittFuer(punkte);
    const nadeln = punkte.map((p) => {
      const k = kartenPunkt(p.lat, p.lon);
      const l = ((k.x - a.x) / a.weite * 100).toFixed(2);
      const t = ((k.y - a.y) / a.hoehe * 100).toFixed(2);
      return `<span class="karten-punkt ${p.art === "termin" ? "termin" : ""}"
                    style="left:${l}%;top:${t}%" title="${esc(p.name || "")}">
        ${punktSymbolHtml(p)}
        <span class="karten-name">${esc(p.name || "")}</span></span>`;
    }).join("");
    return `<div class="grosskarte">
      <svg viewBox="${a.x} ${a.y} ${a.weite} ${a.hoehe}"
           preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">`
      + (weltkarteBereit ? '<use href="#weltkarte"></use>' : "")
      + `</svg>${nadeln}</div>`;
  }

  // Personen tragen ihr Profilbild, Einladungen eine Fahne - auf einen Blick
  // unterscheidbar, auch wenn beides dicht beieinanderliegt.
  function punktSymbolHtml(p) {
    if (p.art === "termin") return '<span class="karten-fahne">📅</span>';
    if (p.art === "tipp") return '<span class="karten-fahne stern">⭐</span>';
    if (p.user_id) return avatarHtml("u", p.user_id, p.name, p.avatar, "winzig");
    return '<span class="karten-fahne">📍</span>';
  }

  // ---------- Straßenkarte ----------
  // Leaflet liegt im Add-on, wird aber erst geladen, wenn wirklich eine ganze
  // Karte gezeigt wird - nicht beim Start und nicht in Sprechblasen. Die
  // Kacheln kommen von OpenStreetMap; das ist die einzige Stelle, an der
  // dieser Chat etwas von einem fremden Server holt. Wer das nicht will,
  // schaltet es in den Einstellungen ab und behält die Umrisskarte.
  const KACHEL_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  const KACHEL_DANK = '&copy; <a href="https://www.openstreetmap.org/copyright" '
    + 'target="_blank" rel="noopener noreferrer">OpenStreetMap</a>';

  const kachelnErlaubt = () => !(state.me && state.me.kacheln === false);

  let leafletLaeuft = null;

  function leafletLaden() {
    // Nur einmal laden, auch wenn zwei Karten gleichzeitig aufgehen
    if (leafletLaeuft) return leafletLaeuft;
    leafletLaeuft = new Promise((fertig, fehler) => {
      if (window.L) { fertig(); return; }
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = `${BASE}/static/leaflet/leaflet.css`;
      document.head.appendChild(css);
      const js = document.createElement("script");
      js.src = `${BASE}/static/leaflet/leaflet.js`;
      js.addEventListener("load", () => fertig());
      js.addEventListener("error", () => {
        leafletLaeuft = null;
        fehler(new Error("Die Kartenbibliothek ließ sich nicht laden."));
      });
      document.head.appendChild(js);
    });
    return leafletLaeuft;
  }

  function nadelSymbol(p) {
    return L.divIcon({
      className: "leaflet-eigen",
      html: `<span class="karten-punkt fest ${p.art === "termin" ? "termin" : ""}">`
        + punktSymbolHtml(p)
        + (p.name ? `<span class="karten-name">${esc(p.name)}</span>` : "")
        + `</span>`,
      iconSize: null,
    });
  }

  /**
   * Zeichnet eine echte Karte in den Behälter - oder, wenn die Kacheln aus
   * sind oder Leaflet nicht kommt, die Umrisskarte aus dem Add-on.
   */
  let offeneKarten = [];

  // Beim Filtern und beim Schliessen wird neu gezeichnet. Ohne Abbau bliebe
  // jede vorige Karte samt ihren Zuhoerern im Speicher haengen. Der Versuch
  // darf scheitern: haengt die Karte schon nicht mehr im Dokument, ist genau
  // das ja das Ziel.
  function kartenAbbauen() {
    offeneKarten.forEach((k) => {
      try { k.remove(); } catch (err) { /* war schon weg */ }
    });
    offeneKarten = [];
  }

  async function karteZeichnen(behaelter, punkte) {
    if (!behaelter) return;
    kartenAbbauen();
    if (!punkte.length) {
      behaelter.innerHTML = uebersichtHtml(punkte);
      return;
    }
    if (!kachelnErlaubt()) {
      behaelter.innerHTML = uebersichtHtml(punkte)
        + '<p class="hint">Die Straßenkarte ist abgeschaltet – in den '
        + 'Einstellungen lässt sie sich einschalten.</p>';
      return;
    }
    // Bis die Kacheln da sind, steht die Umrisskarte im Bild. So ist sofort
    // etwas zu sehen, und bei einem Fehler bleibt sie einfach stehen.
    behaelter.innerHTML = uebersichtHtml(punkte);
    try {
      await leafletLaden();
    } catch (err) {
      behaelter.insertAdjacentHTML("beforeend",
        `<p class="hint">${esc(err.message)} Es bleibt bei den Umrissen.</p>`);
      return;
    }
    behaelter.innerHTML = '<div class="echtkarte"></div>';
    const karte = L.map(behaelter.firstElementChild, {
      attributionControl: true,
      // Auf dem Telefon soll eine Wischgeste die Seite scrollen, nicht die
      // Karte verschieben - erst ein Tipp auf die Karte gibt sie frei.
      tap: true,
    });
    L.tileLayer(KACHEL_URL, {maxZoom: 19, attribution: KACHEL_DANK}).addTo(karte);
    const marken = punkte.map((p) => {
      const marke = L.marker([p.lat, p.lon], {icon: nadelSymbol(p)}).addTo(karte);
      if (p.event_id) {
        marke.on("click", () => terminAnsicht(p.event_id));
      } else if (p.tipp_id) {
        marke.on("click", () => tippAnsicht(p.tipp_id));
      }
      return marke;
    });
    if (punkte.length === 1) {
      karte.setView([punkte[0].lat, punkte[0].lon], 15);
    } else {
      karte.fitBounds(L.featureGroup(marken).getBounds().pad(0.25),
                      {maxZoom: 16});
    }
    // Der Behälter ist gerade erst im Fenster gelandet; Leaflet muss seine
    // Größe danach noch einmal nachmessen.
    setTimeout(() => karte.invalidateSize(), 60);
    offeneKarten.push(karte);
    return karte;
  }

  // ---------- Live-Standort ----------
  // Die Freigabe gehört immer zu einer Unterhaltung und läuft von selbst ab.
  // Damit ist ohne Zutun klar, wer mitsehen darf: die Mitglieder.
  let livePing = null;

  const restzeit = (bis) => {
    const s = bis - Math.floor(Date.now() / 1000);
    if (s <= 0) return "abgelaufen";
    if (s < 3600) return `noch ${Math.max(1, Math.round(s / 60))} Min`;
    const std = Math.floor(s / 3600), min = Math.round(s % 3600 / 60);
    return min ? `noch ${std} Std ${min} Min` : `noch ${std} Std`;
  };

  const meineFreigaben = () => (state.live || []).filter((l) => l.ich);

  function pingPlanen() {
    // Solange ich selbst teile, schicke ich alle zwei Minuten die neue
    // Position. Ohne eigene Freigabe wird der Standort nicht abgefragt.
    if (livePing) { clearInterval(livePing); livePing = null; }
    if (!meineFreigaben().length || !navigator.geolocation) return;
    livePing = setInterval(() => {
      if (!meineFreigaben().length) { pingPlanen(); return; }
      navigator.geolocation.getCurrentPosition((pos) => {
        api("/api/live/ping", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({lat: pos.coords.latitude, lon: pos.coords.longitude,
                                genauigkeit: pos.coords.accuracy}),
        });
      }, () => {}, {enableHighAccuracy: true, timeout: 20000, maximumAge: 30000});
    }, 120000);
  }

  function standortHolen() {
    return new Promise((fertig, fehler) => {
      if (!navigator.geolocation) {
        fehler(new Error("Dieser Browser kennt keinen Standort."));
        return;
      }
      if (!sichererKontext()) {
        fehler(new Error("Der Standort geht nur über HTTPS – öffne den Chat "
                         + "über deine externe Adresse."));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => fertig({lat: pos.coords.latitude, lon: pos.coords.longitude,
                         genauigkeit: pos.coords.accuracy}),
        (err) => fehler(new Error(err.code === 1
          ? "Du hast den Zugriff auf den Standort abgelehnt."
          : "Der Standort ließ sich nicht bestimmen.")),
        {enableHighAccuracy: true, timeout: 15000, maximumAge: 60000});
    });
  }

  function liveDialog() {
    const gruppen = state.rooms;
    if (!gruppen.length) { toast("Es gibt noch keine Unterhaltung."); return; }
    const laufend = meineFreigaben();
    const root = modal(`<h2>Standort teilen</h2>
      <p class="hint">Nur die Mitglieder der gewählten Unterhaltung sehen dich –
        und nur, solange die Freigabe läuft.</p>
      <div class="field"><label for="live-raum">Unterhaltung</label>
        <select id="live-raum">${gruppen.map((r) =>
          `<option value="${r.id}" ${r.id === currentRoom ? "selected" : ""}>${
            esc(r.name)}</option>`).join("")}</select></div>
      <div class="field"><label for="live-dauer">Dauer</label>
        <select id="live-dauer">
          <option value="15">15 Minuten</option>
          <option value="60" selected>1 Stunde</option>
          <option value="180">3 Stunden</option>
          <option value="480">8 Stunden</option>
        </select></div>
      ${laufend.length ? `<div class="live-laufend">Läuft gerade: ${
        laufend.map((l) => `${esc(l.raum)} (${restzeit(l.bis_at)})`).join(", ")}
        <button class="btn ghost klein" id="live-stopp">Alle beenden</button></div>` : ""}
      <div class="row"><button class="btn ghost" id="m-cancel">Abbrechen</button>
      <button class="btn" id="live-ok">Teilen</button></div>`);
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    const stopp = root.querySelector("#live-stopp");
    if (stopp) stopp.addEventListener("click", () => liveBeenden());
    root.querySelector("#live-ok").addEventListener("click", async () => {
      const knopf = root.querySelector("#live-ok");
      knopf.disabled = true;
      knopf.textContent = "Standort wird bestimmt …";
      try {
        const ort = await standortHolen();
        const res = await api("/api/live", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify(Object.assign({
            room_id: parseInt(root.querySelector("#live-raum").value, 10),
            minuten: parseInt(root.querySelector("#live-dauer").value, 10),
          }, ort)),
        });
        const daten = await res.json().catch(() => ({}));
        if (!res.ok) { toast(daten.error || "Das hat nicht geklappt."); return; }
        closeModal();
        toast("Standort wird geteilt.");
        await liveLaden();
      } catch (err) {
        toast(err.message);
      } finally {
        knopf.disabled = false;
        knopf.textContent = "Teilen";
      }
    });
  }

  async function liveBeenden(roomId) {
    const res = await api("/api/live", {
      method: "DELETE", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(roomId ? {room_id: roomId} : {}),
    });
    if (!res.ok) { toast("Das Beenden ging schief."); return; }
    closeModal();
    toast("Standort wird nicht mehr geteilt.");
    await liveLaden();
  }

  async function liveLaden() {
    const res = await api("/api/live");
    if (!res.ok) return;
    state.live = await res.json();
    renderKarten();
    pingPlanen();
  }

  /**
   * Was auf der Live-Karte steht: laufende Standortfreigaben und alle
   * anstehenden Einladungen, bei denen ein Ort hinterlegt ist.
   */
  // Der Filter überlebt das Schließen der Karte - wer nach "Samstag, Musik"
  // gesucht hat, will beim nächsten Öffnen nicht von vorn anfangen.
  let kartenFilter = {zeit: "alle", kategorien: new Set()};
  // Empfehlungen liegen still im Hintergrund - sie sind meist wenige und
  // stoeren nicht, lassen sich aber ausblenden.
  let kartenTipps = true;

  const ZEITRAEUME = [["alle", "Alles"], ["heute", "Heute"],
                      ["morgen", "Morgen"], ["woche", "7 Tage"]];

  /** Beginn und Ende des gewählten Zeitraums in Sekunden, oder null. */
  function zeitfenster(wahl) {
    if (wahl === "alle") return null;
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    const tag = 86400000;
    if (wahl === "heute") return [start.getTime() / 1000, (start.getTime() + tag) / 1000];
    if (wahl === "morgen") {
      return [(start.getTime() + tag) / 1000, (start.getTime() + 2 * tag) / 1000];
    }
    return [Date.now() / 1000, (start.getTime() + 7 * tag) / 1000];
  }

  function terminPasst(t) {
    const fenster = zeitfenster(kartenFilter.zeit);
    if (fenster) {
      // Ohne Zeitpunkt lässt sich nicht sagen, ob der Termin ins Fenster
      // fällt - solche stehen nur unter "Alles".
      if (!t.beginnt_at) return false;
      if (t.beginnt_at < fenster[0] || t.beginnt_at >= fenster[1]) return false;
    }
    if (kartenFilter.kategorien.size) {
      // Eines der gewählten Merkmale genügt: "wo läuft Musik oder Tanz"
      if (!t.kategorien.some((k) => kartenFilter.kategorien.has(k))) return false;
    }
    return true;
  }

  /**
   * Was auf der Live-Karte steht: laufende Standortfreigaben und die
   * anstehenden Einladungen mit Ort, die durch den Filter kommen.
   */
  function kartenPunkte() {
    const jetzt = Math.floor(Date.now() / 1000);
    const personen = (state.live || [])
      .filter((p) => p.bis_at > jetzt)
      .map((p) => Object.assign({art: "person"}, p));
    const mitOrt = (state.termine || [])
      .filter((ev) => ev.ort && !ev.abgesagt)
      .map((ev) => ({art: "termin", event_id: ev.id, name: ev.titel,
                     lat: ev.ort.lat, lon: ev.ort.lon,
                     ort_text: ev.ort_text, beginnt_at: ev.beginnt_at,
                     kategorien: ev.kategorien || [],
                     zusagen: (ev.wer.ja || []).length, meine: ev.meine}));
    const termine = mitOrt.filter(terminPasst);
    const tipps = kartenTipps
      ? (state.tipps || []).filter((x) => x.ort).map((x) => ({
          art: "tipp", tipp_id: x.id, name: x.titel,
          lat: x.ort.lat, lon: x.ort.lon, ort_text: x.ort_text,
          sterne: x.sterne, tipp_art: x.art, von: x.name}))
      : [];
    return {personen, termine, tipps, alleTermine: mitOrt,
            alleTipps: (state.tipps || []).filter((x) => x.ort),
            alle: personen.concat(termine, tipps)};
  }

  function filterLeiste(alleTermine, gezeigt, tippZahl) {
    // Nur Merkmale anbieten, die überhaupt vorkommen - tote Knöpfe helfen
    // niemandem.
    const vorhanden = [...new Set(alleTermine.flatMap((t) => t.kategorien))]
      .filter((k) => KATEGORIEN[k]);
    const aktiv = kartenFilter.zeit !== "alle" || kartenFilter.kategorien.size;
    return `<div class="kartenfilter">
      <div class="kf-zeile">
        <span class="kf-titel">Einladungen</span>
        ${ZEITRAEUME.map(([wert, text]) =>
          `<button class="mini-btn ${kartenFilter.zeit === wert ? "an" : ""}"
                   data-zeit="${wert}">${text}</button>`).join("")}
      </div>
      ${vorhanden.length ? `<div class="kf-zeile">
        ${vorhanden.map((k) =>
          `<button class="mini-btn ${kartenFilter.kategorien.has(k) ? "an" : ""}"
                   data-kat="${k}">${esc(KATEGORIEN[k])}</button>`).join("")}
      </div>` : ""}
      ${tippZahl ? `<div class="kf-zeile">
        <span class="kf-titel">Empfehlungen</span>
        <button class="mini-btn ${kartenTipps ? "an" : ""}" id="kf-tipps"
          >${tippZahl} auf der Karte</button>
      </div>` : ""}
      ${aktiv ? `<div class="kf-zeile">
        <span class="kf-zahl">${gezeigt} von ${alleTermine.length} ${
          alleTermine.length === 1 ? "Einladung" : "Einladungen"}</span>
        <button class="mini-btn" id="kf-weg">Filter aufheben</button>
      </div>` : ""}
    </div>`;
  }

  function kartenAnsicht() {
    const root = modal(`<div class="karten-kopf"><h2>Live-Karte</h2>
      <button class="btn ghost klein" id="karte-teilen">Standort teilen</button>
      <span style="flex:1"></span>
      <button class="icon-btn" id="m-cancel">✕</button></div>
      <div id="karte-inhalt"></div>`);
    root.querySelector(".modal").classList.add("wide", "hoch");
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    root.querySelector("#karte-teilen").addEventListener("click", liveDialog);
    kartenInhalt(root);
  }

  function kartenInhalt(root) {
    root = root || document.getElementById("modal-root");
    const behaelter = root.querySelector("#karte-inhalt");
    if (!behaelter) return;
    const {personen, termine, tipps, alleTermine, alleTipps, alle} = kartenPunkte();
    const osm = (p) => `https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${
      p.lon}#map=15/${p.lat}/${p.lon}`;
    behaelter.innerHTML = `${filterLeiste(alleTermine, termine.length,
                                          alleTipps.length)}
      <div id="karte-flaeche"></div>
      <div class="karten-fuss">
        ${personen.length ? '<div class="karten-gruppe">Wer teilt gerade</div>'
          + personen.map((p) => `<div class="karten-zeile">
            ${avatarHtml("u", p.user_id, p.name, p.avatar, "klein")}
            <div><div class="kz-name">${esc(p.name)}${p.ich ? " (du)" : ""}</div>
              <div class="kz-sub">${esc(p.raum)} · ${restzeit(p.bis_at)}</div></div>
            <span style="flex:1"></span>
            <a class="ortslink" target="_blank" rel="noopener noreferrer"
               href="${osm(p)}">Öffnen</a>
            ${p.ich ? `<button class="act del" data-stopp="${p.room_id}">Beenden</button>` : ""}
          </div>`).join("") : ""}
        ${termine.length ? '<div class="karten-gruppe">Einladungen</div>'
          + termine.map((t) => `<div class="karten-zeile termin"
                                     data-termin="${t.event_id}">
            <span class="karten-fahne klein">📅</span>
            <div><div class="kz-name">${esc(t.name)}</div>
              <div class="kz-sub">${terminZeit(t.beginnt_at)}${
                t.ort_text ? ` · ${esc(t.ort_text)}` : ""} · ${
                t.zusagen} ${t.zusagen === 1 ? "Zusage" : "Zusagen"}</div></div>
            <span style="flex:1"></span>
            <a class="ortslink" target="_blank" rel="noopener noreferrer"
               href="${osm(t)}">Öffnen</a>
          </div>`).join("") : ""}
        ${tipps.length ? '<div class="karten-gruppe">Empfehlungen</div>'
          + tipps.map((x) => `<div class="karten-zeile tipp-zeile"
                                   data-tipp="${x.tipp_id}">
            <span class="karten-fahne klein">⭐</span>
            <div><div class="kz-name">${esc(x.name)}</div>
              <div class="kz-sub">${esc(TIPP_ARTEN[x.tipp_art] || x.tipp_art)}${
                x.ort_text ? ` · ${esc(x.ort_text)}` : ""} · von ${esc(x.von)}</div></div>
            <span style="flex:1"></span>
            <a class="ortslink" target="_blank" rel="noopener noreferrer"
               href="${osm(x)}">Öffnen</a>
          </div>`).join("") : ""}
        ${alle.length ? "" : `<p class="hint">${alleTermine.length
          ? "Zu diesem Filter passt keine Einladung."
          : "Sobald jemand seinen Standort teilt oder eine Einladung einen Ort "
            + "bekommt, erscheint sie hier."}</p>`}
      </div>`;
    karteZeichnen(behaelter.querySelector("#karte-flaeche"), alle);

    behaelter.querySelectorAll("[data-zeit]").forEach((b) =>
      b.addEventListener("click", () => {
        kartenFilter.zeit = b.dataset.zeit;
        kartenInhalt(root);
      }));
    behaelter.querySelectorAll("[data-kat]").forEach((b) =>
      b.addEventListener("click", () => {
        const k = b.dataset.kat;
        if (kartenFilter.kategorien.has(k)) kartenFilter.kategorien.delete(k);
        else kartenFilter.kategorien.add(k);
        kartenInhalt(root);
      }));
    const tippKnopf = behaelter.querySelector("#kf-tipps");
    if (tippKnopf) tippKnopf.addEventListener("click", () => {
      kartenTipps = !kartenTipps;
      kartenInhalt(root);
    });
    behaelter.querySelectorAll("[data-tipp]").forEach((z) =>
      z.addEventListener("click", (e) => {
        if (e.target.closest("a")) return;
        tippAnsicht(parseInt(z.dataset.tipp, 10));
      }));
    const weg = behaelter.querySelector("#kf-weg");
    if (weg) weg.addEventListener("click", () => {
      kartenFilter = {zeit: "alle", kategorien: new Set()};
      kartenInhalt(root);
    });
    behaelter.querySelectorAll("[data-stopp]").forEach((b) =>
      b.addEventListener("click", () =>
        liveBeenden(parseInt(b.dataset.stopp, 10))));
    behaelter.querySelectorAll("[data-termin]").forEach((z) =>
      z.addEventListener("click", (e) => {
        if (e.target.closest("a")) return;
        terminAnsicht(parseInt(z.dataset.termin, 10));
      }));
  }

  // ---------- Reiter in der Seitenleiste ----------
  // Immer nur ein Abschnitt auf einmal, wie die Filterknöpfe bei WhatsApp.
  // Die Wahl bleibt am Gerät: sie sagt nichts über die eigenen Daten aus,
  // sondern nur, worauf man an diesem Bildschirm gerade schaut.
  const REITER = ["chats", "karten", "stimmung", "termine", "tipps"];
  let aktiverReiter = "chats";
  try {
    const gemerkt = localStorage.getItem("chat-reiter");
    if (REITER.includes(gemerkt)) aktiverReiter = gemerkt;
  } catch (err) { /* privates Fenster: dann eben chats */ }

  function reiterSetzen(name) {
    if (!REITER.includes(name)) return;
    aktiverReiter = name;
    try {
      localStorage.setItem("chat-reiter", name);
    } catch (err) { /* nicht schlimm, gilt dann nur für diese Sitzung */ }
    document.querySelectorAll(".reiter-knopf").forEach((b) =>
      b.classList.toggle("an", b.dataset.reiter === name));
    document.querySelectorAll("[data-inhalt]").forEach((s) => {
      s.hidden = s.dataset.inhalt !== name;
    });
    const feld = document.querySelector(".seiten-scroll");
    if (feld) feld.scrollTop = 0;
  }

  function reiterZahlen() {
    const setze = (id, zahl) => {
      const el = $(id);
      if (!el) return;
      el.textContent = zahl ? String(zahl) : "";
      el.hidden = !zahl;
    };
    const ungelesen = (state.rooms || [])
      .reduce((summe, r) => summe + (r.unread || 0), 0);
    const {personen, alleTermine} = kartenPunkte();
    const jetzt = Math.floor(Date.now() / 1000);
    setze("zahl-chats", ungelesen);
    setze("zahl-karten", personen.length);
    setze("zahl-stimmung",
          (state.stimmung || []).filter((s) => s.bis_at > jetzt).length);
    setze("zahl-termine", (state.termine || []).length);
    setze("zahl-tipps", (state.tipps || []).length);
  }


  function renderKarten() {
    const liste = $("karten-liste");
    if (!liste) return;
    // In der Seitenleiste steht immer der volle Stand - ein Filter, den man
    // in der Karte gesetzt hat, soll hier nichts verschwinden lassen.
    const {personen, alleTermine, alleTipps} = kartenPunkte();
    const punkte = personen;
    const teile = [];
    if (personen.length) {
      teile.push(`${personen.length} ${personen.length === 1 ? "Freigabe" : "Freigaben"}`);
    }
    if (alleTermine.length) {
      teile.push(`${alleTermine.length} ${
        alleTermine.length === 1 ? "Einladung" : "Einladungen"}`);
    }
    if (alleTipps.length) {
      teile.push(`${alleTipps.length} ${
        alleTipps.length === 1 ? "Empfehlung" : "Empfehlungen"}`);
    }
    liste.innerHTML = `<div class="karten-eintrag" id="karte-oeffnen">
        <span class="karten-symbol">🗺️</span>
        <div><div class="ke-name">Live-Karte</div>
          <div class="ke-sub">${teile.length ? teile.join(" · ")
            : "Gerade nichts los"}</div></div>
      </div>`
      + punkte.map((p) => `<div class="karten-eintrag person" data-user="${p.user_id}">
          ${avatarHtml("u", p.user_id, p.name, p.avatar, "klein")}
          <div><div class="ke-name">${esc(p.name)}${p.ich ? " (du)" : ""}</div>
            <div class="ke-sub">${esc(p.raum)} · ${restzeit(p.bis_at)}</div></div>
        </div>`).join("");
    liste.querySelectorAll(".karten-eintrag").forEach((el) =>
      el.addEventListener("click", kartenAnsicht));
    reiterZahlen();
  }

  // ---------- Stimmung ----------
  const STIMMUNG_EMOJI = ["😎", "🥳", "😌", "🤩", "😴", "🍕", "🍺", "🎬", "⚽",
                          "🎵", "🚴", "☕", "🌞", "🤔"];

  function stimmungDialog() {
    const meine = (state.stimmung || []).find((s) => s.meine);
    const root = modal(`<h2>Worauf hast du Lust?</h2>
      <p class="hint">Sichtbar für alle, mit denen du eine Unterhaltung teilst.</p>
      <div class="stimmung-emojis" id="st-emojis">${STIMMUNG_EMOJI.map((e) =>
        `<button type="button" class="st-emoji ${
          meine && meine.emoji === e ? "gewaehlt" : ""}" data-e="${e}">${e}</button>`
        ).join("")}</div>
      <div class="field"><label for="st-text">Kurz gesagt</label>
        <input id="st-text" autocomplete="off" maxlength="280"
               placeholder="Heute Abend Kino – wer kommt mit?"
               value="${meine ? esc(meine.text) : ""}"></div>
      <div class="field"><label for="st-dauer">Gilt für</label>
        <select id="st-dauer">
          <option value="2">2 Stunden</option>
          <option value="4" selected>4 Stunden</option>
          <option value="12">12 Stunden</option>
          <option value="24">Bis morgen</option>
        </select></div>
      <label class="check"><input type="checkbox" id="st-ort"> Meinen Standort dazu</label>
      <div class="row">${meine
        ? '<button class="btn ghost" id="st-weg">Meldung löschen</button>'
        : '<button class="btn ghost" id="m-cancel">Abbrechen</button>'}
      <button class="btn" id="st-ok">Setzen</button></div>`);
    let emoji = meine ? meine.emoji : "";
    root.querySelectorAll(".st-emoji").forEach((b) =>
      b.addEventListener("click", () => {
        const schon = b.classList.contains("gewaehlt");
        root.querySelectorAll(".st-emoji").forEach((x) =>
          x.classList.remove("gewaehlt"));
        if (!schon) { b.classList.add("gewaehlt"); emoji = b.dataset.e; }
        else emoji = "";
      }));
    const abbruch = root.querySelector("#m-cancel");
    if (abbruch) abbruch.addEventListener("click", closeModal);
    const weg = root.querySelector("#st-weg");
    if (weg) weg.addEventListener("click", async () => {
      await api(`/api/stimmung/${meine.id}`, {method: "DELETE"});
      closeModal();
      await stimmungLaden();
    });
    root.querySelector("#st-ok").addEventListener("click", async () => {
      const text = root.querySelector("#st-text").value.trim();
      if (!text) { toast("Schreib kurz, worauf du Lust hast."); return; }
      const nutzlast = {text, emoji,
        stunden: parseInt(root.querySelector("#st-dauer").value, 10)};
      if (root.querySelector("#st-ort").checked) {
        try {
          Object.assign(nutzlast, await standortHolen());
        } catch (err) {
          toast(err.message + " Die Meldung geht ohne Ort raus.");
        }
      }
      const res = await api("/api/stimmung", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(nutzlast),
      });
      const daten = await res.json().catch(() => ({}));
      if (!res.ok) { toast(daten.error || "Das hat nicht geklappt."); return; }
      closeModal();
      await stimmungLaden();
    });
  }

  async function stimmungLaden() {
    const res = await api("/api/stimmung");
    if (!res.ok) return;
    state.stimmung = await res.json();
    renderStimmung();
  }

  function renderStimmung() {
    const liste = $("stimmung-liste");
    if (!liste) return;
    const jetzt = Math.floor(Date.now() / 1000);
    const alle = (state.stimmung || []).filter((s) => s.bis_at > jetzt);
    reiterZahlen();
    if (!alle.length) {
      liste.innerHTML = '<div class="abschnitt-leer">Noch nichts geplant. '
        + 'Sag, worauf du Lust hast.</div>';
      return;
    }
    liste.innerHTML = alle.map((s) => `<div class="stimmung-zeile" data-id="${s.id}">
      <span class="st-icon">${s.emoji || "💬"}</span>
      <div class="st-body">
        <div class="st-kopf">${esc(s.name)}${s.meine ? " (du)" : ""}
          <span class="st-zeit">${restzeit(s.bis_at)}</span></div>
        <div class="st-text">${esc(s.text)}</div>
        ${s.ort ? `<div class="st-ort">📍 ${s.ort.lat.toFixed(3)}, ${
          s.ort.lon.toFixed(3)}</div>` : ""}
        <div class="st-fuss">
          <button class="mini-btn ${s.ich_mache_mit ? "an" : ""}" data-mit="${s.id}">
            ${s.ich_mache_mit ? "Ich bin dabei" : "Ich mach mit"}</button>
          ${s.mit.length ? `<span class="st-mit" title="${esc(
            s.mit.map((m) => m.name).join(", "))}">${s.mit.length} dabei</span>` : ""}
        </div>
      </div>
    </div>`).join("");
    liste.querySelectorAll("[data-mit]").forEach((b) =>
      b.addEventListener("click", async () => {
        const res = await api(`/api/stimmung/${b.dataset.mit}/mit`, {method: "POST"});
        if (!res.ok) { toast("Das ging nicht."); return; }
        await stimmungLaden();
      }));
  }

  // ---------- Termine ----------
  const KATEGORIEN = {
    musik: "🎵 Musik", tanz: "💃 Tanz", alkohol: "🍺 Alkohol",
    essen: "🍕 Essen", film: "🎬 Film", sport: "⚽ Sport",
    spiele: "🎲 Spiele", draussen: "🌳 Draußen", kultur: "🎭 Kultur",
    reden: "💬 Reden",
  };

  const terminZeit = (ts) => {
    if (!ts) return "Zeit offen";
    const d = new Date(ts * 1000);
    return d.toLocaleDateString("de-DE", {weekday: "short", day: "2-digit",
                                          month: "2-digit"})
      + ", " + d.toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"})
      + " Uhr";
  };

  // Aendern darf der Gastgeber und der Administrator. Ab- und zusagen darf
  // allein der Gastgeber - wer zu einer Feier laedt, entscheidet auch, ob sie
  // stattfindet.
  function verwaltenHtml(ev) {
    const meiner = ev.von.id === ME;
    const darfAendern = meiner || IS_ADMIN;
    const knoepfe = [];
    if (ev.abgesagt) {
      if (meiner) knoepfe.push('<button class="act ev-zurueck">Absage zurücknehmen</button>');
    } else {
      if (darfAendern) knoepfe.push('<button class="act ev-bearbeiten">Bearbeiten</button>');
      if (meiner) knoepfe.push('<button class="act del ev-absagen">Termin absagen</button>');
    }
    return knoepfe.length
      ? `<div class="ev-verwalten">${knoepfe.join("")}</div>` : "";
  }

  function eventHtml(ev) {
    const wer = (art) => (ev.wer[art] || []);
    const knopf = (art, text) => `<button class="ev-antwort ${
      ev.meine === art ? "gewaehlt" : ""}" data-antwort="${art}"
      ${wer(art).length ? `title="${esc(wer(art).map((w) => w.name).join(", "))}"` : ""}>
      ${text}${wer(art).length ? ` · ${wer(art).length}` : ""}</button>`;
    const bild = ev.file_id
      ? `<img class="ev-bild" alt="" src="${BASE}/files/${ev.file_id}">` : "";
    const marken = ev.kategorien.length
      ? `<div class="ev-marken">${ev.kategorien.map((k) =>
          `<span class="ev-marke">${esc(KATEGORIEN[k] || k)}</span>`).join("")}</div>`
      : "";
    const dabei = wer("ja");
    return `<div class="event ${ev.abgesagt ? "abgesagt" : ""}" data-event="${ev.id}">
      ${bild}
      <div class="ev-kopf">📅 ${esc(ev.titel)}</div>
      <div class="ev-zeit">${terminZeit(ev.beginnt_at)}</div>
      ${ev.ort_text ? `<div class="ev-ort">📍 ${esc(ev.ort_text)}</div>` : ""}
      ${ev.ort ? karteHtml(ev.ort, 56, "ortskarte ev-karte") : ""}
      ${ev.beschreibung ? `<div class="ev-text">${esc(ev.beschreibung)}</div>` : ""}
      ${marken}
      <div class="ev-von">Eingeladen von ${esc(ev.von.name)}</div>
      ${ev.abgesagt
        ? '<div class="ev-weg">Abgesagt</div>'
        : `<div class="ev-antworten">${knopf("ja", "Bin dabei")}${
            knopf("vielleicht", "Vielleicht")}${knopf("nein", "Kann nicht")}</div>`}
      ${dabei.length ? `<div class="ev-dabei">${dabei.map((w) =>
        avatarHtml("u", w.id, w.name, w.avatar, "winzig")).join("")}
        <span>${dabei.length === 1 ? "1 Zusage" : `${dabei.length} Zusagen`}</span></div>` : ""}
      ${verwaltenHtml(ev)}
    </div>`;
  }

  async function eventNeuZeichnen(eventId) {
    const kasten = document.querySelector(`.event[data-event="${eventId}"]`);
    const res = await api(`/api/events/${eventId}`);
    if (!res.ok) return;
    const ev = await res.json();
    if (kasten) kasten.outerHTML = eventHtml(ev);
    // Nachladen statt nur neu zeichnen: sagt jemand anders einen Termin ab,
    // stuende er sonst weiter in meiner Seitenleiste.
    terminLaden();
  }

  // Antworten und Absagen - überall dort, wo eine Terminkarte steht
  document.addEventListener("click", async (e) => {
    const antwort = e.target.closest(".ev-antwort");
    if (antwort) {
      e.preventDefault();
      e.stopPropagation();
      const kasten = antwort.closest(".event");
      const gewaehlt = antwort.classList.contains("gewaehlt");
      const res = await api(`/api/events/${kasten.dataset.event}/antwort`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        // Noch einmal auf dieselbe Antwort tippen nimmt sie zurück
        body: JSON.stringify({antwort: gewaehlt ? "" : antwort.dataset.antwort}),
      });
      if (!res.ok) { toast("Die Antwort ging nicht durch."); return; }
      kasten.outerHTML = eventHtml(await res.json());
      terminLaden();
      return;
    }
    const bearbeiten = e.target.closest(".ev-bearbeiten");
    if (bearbeiten) {
      e.preventDefault();
      e.stopPropagation();
      const id = bearbeiten.closest(".event").dataset.event;
      const res = await api(`/api/events/${id}`);
      if (!res.ok) { toast("Der Termin ist nicht mehr da."); return; }
      terminDialog(await res.json());
      return;
    }
    const zurueck = e.target.closest(".ev-zurueck");
    if (zurueck) {
      e.preventDefault();
      e.stopPropagation();
      const id = zurueck.closest(".event").dataset.event;
      const res = await api(`/api/events/${id}`, {
        method: "PATCH", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({abgesagt: false}),
      });
      if (!res.ok) { toast("Das ging nicht."); return; }
      eventNeuZeichnen(id);
      terminLaden();
      toast("Der Termin steht wieder.");
      return;
    }
    const absagen = e.target.closest(".ev-absagen");
    if (absagen) {
      e.preventDefault();
      e.stopPropagation();
      const kasten = absagen.closest(".event");
      if (!confirm("Den Termin für alle absagen?")) return;
      const res = await api(`/api/events/${kasten.dataset.event}`, {method: "DELETE"});
      if (!res.ok) { toast("Das Absagen ging nicht."); return; }
      eventNeuZeichnen(kasten.dataset.event);
      terminLaden();
    }
  }, true);

  // Den Ort auf der Karte antippen. Die Umrisskarte taugt dafür nicht - auf
  // ihr läge ein Punkt viele Kilometer daneben -, deshalb führt der Weg über
  // die Straßenkarte, und wer sie aus hat, kann sie hier einschalten.
  async function ortsWaehler(box, start, beiWahl) {
    if (!kachelnErlaubt()) {
      box.innerHTML = `<div class="ortswahl-aus">
        <p class="hint">Zum Antippen braucht es die Straßenkarte. Die
          Umrisskarte im Add-on kennt keine Straßen – ein Punkt darauf läge
          leicht mehrere Kilometer daneben.</p>
        <button class="btn ghost klein" type="button" id="ow-an">Straßenkarte einschalten</button>
      </div>`;
      box.querySelector("#ow-an").addEventListener("click", async () => {
        const res = await api("/api/me/karten", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({kacheln: true}),
        });
        if (!res.ok) { toast("Das ließ sich nicht speichern."); return; }
        if (state.me) state.me.kacheln = true;
        ortsWaehler(box, start, beiWahl);
      });
      return;
    }
    box.innerHTML = '<div class="echtkarte"></div>'
      + '<p class="hint">Tippe auf die Karte, um den Ort zu setzen.</p>';
    try {
      await leafletLaden();
    } catch (err) {
      box.innerHTML = `<p class="hint">${esc(err.message)}</p>`;
      return;
    }
    const karte = L.map(box.firstElementChild);
    offeneKarten.push(karte);
    L.tileLayer(KACHEL_URL, {maxZoom: 19, attribution: KACHEL_DANK}).addTo(karte);
    // Ohne bekannten Ort auf Deutschland - von dort ist jeder Ort in ein
    // paar Zoomstufen erreichbar.
    karte.setView(start ? [start.lat, start.lon] : [51.2, 10.4],
                  start ? 15 : 5);
    let marke = start
      ? L.marker([start.lat, start.lon], {icon: nadelSymbol({art: "termin"})})
          .addTo(karte)
      : null;
    karte.on("click", (e) => {
      if (marke) marke.remove();
      marke = L.marker(e.latlng, {icon: nadelSymbol({art: "termin"})}).addTo(karte);
      beiWahl({lat: e.latlng.lat, lon: e.latlng.lng});
    });
    setTimeout(() => karte.invalidateSize(), 60);
  }

  /** Neue Einladung, oder - mit ev - eine bestehende ändern. */
  function terminDialog(ev) {
    const aendern = !!ev;
    if (!aendern && !currentRoom) {
      toast("Öffne zuerst eine Unterhaltung.");
      return;
    }
    let bildDatei = null;
    let bildId = aendern ? ev.file_id : null;
    let ort = aendern && ev.ort ? {lat: ev.ort.lat, lon: ev.ort.lon} : null;

    const wannWert = (() => {
      if (!aendern || !ev.beginnt_at) return "";
      const d = new Date(ev.beginnt_at * 1000);
      const p = (n) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
        + `T${p(d.getHours())}:${p(d.getMinutes())}`;
    })();

    const root = modal(`<h2>${aendern ? "Einladung ändern" : "Einladung"}</h2>
      <div class="field"><label for="ev-titel">Was ist geplant?</label>
        <input id="ev-titel" autocomplete="off" placeholder="Grillen im Garten"
               value="${aendern ? esc(ev.titel) : ""}"></div>
      <div class="field"><label for="ev-wann">Wann</label>
        <input id="ev-wann" type="datetime-local" value="${wannWert}"></div>
      <div class="field"><label for="ev-ort">Wo</label>
        <input id="ev-ort" autocomplete="off" placeholder="Bei Gregor, Hofstraße 3"
               value="${aendern ? esc(ev.ort_text) : ""}">
        <div class="row schmal">
          <button class="btn ghost klein" type="button" id="ev-karte">Auf der Karte wählen</button>
          <button class="btn ghost klein" type="button" id="ev-hier">Aktueller Ort</button>
        </div>
        <div class="ortswahl" id="ev-kartenwahl" hidden></div>
        <div class="ev-ortstand">
          <span class="hint" id="ev-ort-status"></span>
          <button class="mini-btn" type="button" id="ev-ort-weg" hidden>Ort entfernen</button>
        </div>
      </div>
      <div class="field"><label for="ev-text">Beschreibung</label>
        <textarea id="ev-text" rows="3">${aendern ? esc(ev.beschreibung) : ""}</textarea></div>
      <div class="field"><label>Was ist geboten?</label>
        <div class="ev-kats">${Object.entries(KATEGORIEN).map(([k, txt]) =>
          `<button type="button" class="ev-kat ${
            aendern && ev.kategorien.includes(k) ? "gewaehlt" : ""}"
            data-k="${k}">${txt}</button>`).join("")}</div>
      </div>
      <div class="field"><label>Bild</label>
        <div class="row schmal">
          <button class="btn ghost klein" type="button" id="ev-bild">Bild wählen</button>
          <button class="btn ghost klein" type="button" id="ev-bild-weg"
                  ${bildId ? "" : "hidden"}>Bild entfernen</button>
        </div>
        <span class="hint" id="ev-bild-name">${bildId ? "Ein Bild ist hinterlegt." : ""}</span></div>
      <div class="row"><button class="btn ghost" id="m-cancel">Abbrechen</button>
      <button class="btn" id="ev-ok">${
        aendern ? "Änderungen speichern" : "Einladen"}</button></div>`);
    root.querySelector(".modal").classList.add("hoch");
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    root.querySelectorAll(".ev-kat").forEach((b) =>
      b.addEventListener("click", () => b.classList.toggle("gewaehlt")));

    const status = root.querySelector("#ev-ort-status");
    const wegKnopf = root.querySelector("#ev-ort-weg");
    const ortAnzeigen = () => {
      status.textContent = ort
        ? `Ort gesetzt: ${ort.lat.toFixed(5)}, ${ort.lon.toFixed(5)}`
        : "Noch kein Punkt auf der Karte.";
      wegKnopf.hidden = !ort;
    };
    ortAnzeigen();

    wegKnopf.addEventListener("click", () => {
      ort = null;
      ortAnzeigen();
      root.querySelector("#ev-kartenwahl").hidden = true;
    });

    root.querySelector("#ev-karte").addEventListener("click", () => {
      const box = root.querySelector("#ev-kartenwahl");
      if (!box.hidden) { box.hidden = true; return; }
      box.hidden = false;
      ortsWaehler(box, ort, (neu) => { ort = neu; ortAnzeigen(); });
    });

    root.querySelector("#ev-hier").addEventListener("click", async () => {
      status.textContent = "Standort wird bestimmt …";
      try {
        const gefunden = await standortHolen();
        ort = {lat: gefunden.lat, lon: gefunden.lon};
        ortAnzeigen();
        const box = root.querySelector("#ev-kartenwahl");
        if (!box.hidden) ortsWaehler(box, ort, (neu) => { ort = neu; ortAnzeigen(); });
      } catch (err) {
        status.textContent = err.message;
      }
    });

    root.querySelector("#ev-bild").addEventListener("click", () => {
      const feld = document.createElement("input");
      feld.type = "file";
      feld.accept = "image/*";
      feld.addEventListener("change", () => {
        bildDatei = feld.files[0] || null;
        root.querySelector("#ev-bild-name").textContent =
          bildDatei ? bildDatei.name : "";
        root.querySelector("#ev-bild-weg").hidden = !bildDatei && !bildId;
      });
      feld.click();
    });
    root.querySelector("#ev-bild-weg").addEventListener("click", () => {
      bildDatei = null;
      bildId = null;
      root.querySelector("#ev-bild-name").textContent = "Kein Bild.";
      root.querySelector("#ev-bild-weg").hidden = true;
    });

    root.querySelector("#ev-ok").addEventListener("click", async () => {
      const titel = root.querySelector("#ev-titel").value.trim();
      if (!titel) { toast("Der Titel fehlt."); return; }
      const knopf = root.querySelector("#ev-ok");
      knopf.disabled = true;
      try {
        if (bildDatei) {
          const fd = new FormData();
          fd.append("file", bildDatei);
          const hoch = await api("/api/upload", {method: "POST", body: fd});
          const daten = await hoch.json().catch(() => ({}));
          if (!hoch.ok) { toast(daten.error || "Das Bild ging nicht durch."); return; }
          bildId = daten.id;
        }
        const wann = root.querySelector("#ev-wann").value;
        const nutzlast = {
          titel,
          beschreibung: root.querySelector("#ev-text").value.trim(),
          ort_text: root.querySelector("#ev-ort").value.trim(),
          beginnt_at: wann ? Math.floor(new Date(wann).getTime() / 1000) : null,
          kategorien: [...root.querySelectorAll(".ev-kat.gewaehlt")]
            .map((b) => b.dataset.k),
          file_id: bildId,
          lat: ort ? ort.lat : null,
          lon: ort ? ort.lon : null,
        };
        const res = aendern
          ? await api(`/api/events/${ev.id}`, {
              method: "PATCH", headers: {"Content-Type": "application/json"},
              body: JSON.stringify(nutzlast)})
          : await api(`/api/rooms/${currentRoom}/event`, {
              method: "POST", headers: {"Content-Type": "application/json"},
              body: JSON.stringify(nutzlast)});
        const daten = await res.json().catch(() => ({}));
        if (!res.ok) { toast(daten.error || "Das hat nicht geklappt."); return; }
        closeModal();
        if (aendern) {
          eventNeuZeichnen(ev.id);
          toast("Einladung geändert.");
        }
        terminLaden();
      } finally {
        knopf.disabled = false;
      }
    });
  }

  async function terminLaden() {
    const res = await api("/api/events");
    if (!res.ok) return;
    state.termine = await res.json();
    renderTermine();
  }

  // Statt eines eigenen Reiters filtert die Terminliste selbst. "Offen" ist
  // der nuetzlichste Blick: was wartet noch auf meine Antwort.
  const TERMIN_FILTER = [
    ["", "Alle"],
    ["ja", "Zugesagt"],
    ["offen", "Offen"],
  ];
  let terminFilter = "";

  function terminPasstZumFilter(ev) {
    if (!terminFilter) return true;
    if (terminFilter === "offen") return !ev.meine;
    return ev.meine === terminFilter;
  }

  function renderTermine() {
    const liste = $("termin-liste");
    if (!liste) return;
    const alle = state.termine || [];
    const gezeigt = alle.filter(terminPasstZumFilter);

    const leiste = $("termin-filter");
    if (leiste) {
      leiste.innerHTML = alle.length
        ? TERMIN_FILTER.map(([wert, text]) => {
            const zahl = wert === ""
              ? alle.length
              : alle.filter((ev) => wert === "offen" ? !ev.meine
                                                     : ev.meine === wert).length;
            return `<button class="mini-btn ${terminFilter === wert ? "an" : ""}"
                     data-tf="${wert}">${text}${zahl ? ` · ${zahl}` : ""}</button>`;
          }).join("")
        : "";
      leiste.querySelectorAll("[data-tf]").forEach((b) =>
        b.addEventListener("click", () => {
          terminFilter = b.dataset.tf;
          renderTermine();
        }));
    }

    if (!gezeigt.length) {
      liste.innerHTML = `<div class="abschnitt-leer">${alle.length
        ? "Dazu steht nichts an."
        : "Nichts steht an. Mit ‚Einladung‘ im Chat legst du etwas an."
        }</div>`;
      reiterZahlen();
      renderKarten();
      return;
    }
    liste.innerHTML = gezeigt.map((ev) => `<div class="termin-zeile" data-id="${ev.id}"
        data-room="${ev.room_id}">
      <div class="tz-datum">${terminZeit(ev.beginnt_at)}</div>
      <div class="tz-titel">${esc(ev.titel)}</div>
      <div class="tz-sub">${esc(ev.von.name)}${ev.ort_text
        ? ` · ${esc(ev.ort_text)}` : ""} · ${
        (ev.wer.ja || []).length} Zusagen${
        ev.meine ? ` · du: ${{ja: "dabei", nein: "abgesagt",
                                   vielleicht: "vielleicht"}[ev.meine]}` : ""}</div>
    </div>`).join("");
    liste.querySelectorAll(".termin-zeile").forEach((el) =>
      el.addEventListener("click", () => terminAnsicht(parseInt(el.dataset.id, 10))));
    reiterZahlen();
    // Die Zahl neben der Live-Karte zaehlt Einladungen mit
    renderKarten();
  }

  async function terminAnsicht(eventId) {
    const res = await api(`/api/events/${eventId}`);
    if (!res.ok) { toast("Der Termin ist nicht mehr da."); return; }
    const ev = await res.json();
    const root = modal(`<div class="karten-kopf"><h2>Termin</h2>
      <span style="flex:1"></span>
      <button class="icon-btn" id="m-cancel">✕</button></div>
      ${eventHtml(ev)}
      <div class="row"><button class="btn ghost" id="ev-zum-chat">Zur Unterhaltung</button></div>`);
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    // In der ganzseitigen Ansicht lohnt die echte Karte - in der Sprechblase
    // bleibt es bei den Umrissen.
    const vorschau = root.querySelector(".ev-karte");
    if (vorschau && ev.ort) {
      const flaeche = document.createElement("div");
      flaeche.className = "ev-kartenflaeche";
      vorschau.replaceWith(flaeche);
      karteZeichnen(flaeche, [{lat: ev.ort.lat, lon: ev.ort.lon,
                               name: ev.ort_text || ev.titel}]);
    }
    root.querySelector("#ev-zum-chat").addEventListener("click", () => {
      closeModal();
      openRoom(ev.room_id);
    });
  }

  $("btn-live").addEventListener("click", liveDialog);
  $("btn-stimmung").addEventListener("click", stimmungDialog);

  // ---------- Emoji ----------
  // Eine feste Auswahl statt einer Fremdbibliothek: das haelt das Add-on klein
  // und funktioniert ohne Internet.
  const EMOJI = {
    "Gesichter": "😀😃😄😁😆😅😂🤣🙂🙃😉😊😇🥰😍🤩😘😗😚😙😋😛😜🤪😝🤑🤗🤭🤫🤔😐😑😶😏😒🙄😬🤥😌😔😪🤤😴😷🤒🤕🤢🤧🥵🥶🥴😵🤯🤠🥳😎🤓🧐😕😟🙁😮😯😲😳🥺😦😧😨😰😥😢😭😱😖😣😞😓😩😫😤😡😠🤬",
    "Gesten": "👍👎👌🤞🤘🤙👈👉👆👇✋🤚🖐🖖👋💪🙏👏🙌👐🤲🤝✍💅🤳",
    "Menschen": "👶👧👦👩👨👵👴👮👷💂👪👫👬👭💑👯💃🚶🏃",
    "Tiere": "🐶🐱🐭🐹🐰🦊🐻🐼🐨🐯🦁🐮🐷🐸🐵🐔🐧🐦🦆🦉🐝🐛🦋🐌🐞🐟🐬🐳🐋🐎🦄🌵🌲🌳🍀🌷🌹🌻🌼",
    "Essen": "🍏🍎🍐🍊🍋🍌🍉🍇🍓🍒🍑🍍🥝🍅🥕🌽🍄🍞🥐🥖🧀🍖🍗🥓🍔🍟🍕🌭🌮🍳🥘🍝🍜🍣🍱🍙🍨🍦🍰🎂🍫🍬☕🍵🍺🍻🍷🥂🥤",
    "Aktivitaet": "⚽🏀🏈⚾🎾🏐🏉🎱🏓🏸🥅🏒🏑⛳🎯🎿🏂🏋🚴🏊🏄🥇🏆🎵🎸🎤🎮🎲🎬🎨",
    "Reise": "🚗🚕🚌🚓🚒🚜🏍🚲🚋🚆✈🚁🚢⛵🚀🏠🏡🏢🏥🏫⛪🏰⛲🌍🗺🏖⛰🌄🌅🌇🌃",
    "Wetter": "☀🌞⛅☁🌦🌧⛈🌩🌨❄☃⛄🌬💨🌪🌈🌙⭐🌟✨⚡🔥💧🌊",
    "Dinge": "📱💻⌨🖥📷📹🔋🔌💡🔦📖📚📝✏📎📌📅⏰⌚🔑🔒🚪🛋🧹🧺🛒🎁🎈🎉🎶💰💶✂🔧🔨🔩⚙",
    "Herzen": "❤🧡💛💚💙💜🖤🤍🤎💔💕💞💓💗💖💘💝",
    "Zeichen": "✅❌❗❓⚠🚫🔝🆕⬆⬇➡⬅🔃🔄♻💯🔞🚻🚽🚾",
  };

  let emojiOffen = false;

  function emojiFeldAufbauen() {
    if ($("emoji-feld")) return $("emoji-feld");
    const feld = document.createElement("div");
    feld.id = "emoji-feld";
    feld.className = "emoji-feld";
    feld.hidden = true;
    const namen = Object.keys(EMOJI);
    feld.innerHTML = `<div class="emoji-reiter">${namen.map((n, i) =>
        `<button class="emoji-reiter-knopf ${i === 0 ? "aktiv" : ""}"
                 type="button" data-gruppe="${esc(n)}">${esc(n)}</button>`).join("")}</div>
      <div class="emoji-liste"></div>`;
    $("composer").parentNode.insertBefore(feld, $("composer"));

    const liste = feld.querySelector(".emoji-liste");
    const zeichnen = (gruppe) => {
      liste.innerHTML = [...EMOJI[gruppe]]
        .map((z) => `<button class="emoji" type="button">${z}</button>`).join("");
    };
    zeichnen(namen[0]);

    feld.querySelectorAll(".emoji-reiter-knopf").forEach((knopf) =>
      knopf.addEventListener("click", () => {
        feld.querySelectorAll(".emoji-reiter-knopf").forEach((k) =>
          k.classList.remove("aktiv"));
        knopf.classList.add("aktiv");
        zeichnen(knopf.dataset.gruppe);
      }));

    liste.addEventListener("click", (e) => {
      const knopf = e.target.closest(".emoji");
      if (knopf) emojiEinfuegen(knopf.textContent);
    });
    return feld;
  }

  // An der Schreibmarke einfuegen, nicht stumpf anhaengen
  function emojiEinfuegen(zeichen) {
    const feld = $("input");
    const von = feld.selectionStart ?? feld.value.length;
    const bis = feld.selectionEnd ?? feld.value.length;
    feld.value = feld.value.slice(0, von) + zeichen + feld.value.slice(bis);
    const neu = von + zeichen.length;
    feld.setSelectionRange(neu, neu);
    feld.focus();
    feld.dispatchEvent(new Event("input"));
  }

  // ---------- Empfehlungen ----------
  // Jeder schreibt seine eigene; es gibt bewusst keine gemeinsame Note, die
  // sich mitteln liesse. Ein Tipp von jemandem, den man kennt, ist mehr wert
  // als ein Durchschnitt aus tausend Sternen.
  const TIPP_ARTEN = {
    film: "🎬 Film", kino: "🍿 Kino", restaurant: "🍽 Restaurant",
    bar: "🍺 Bar", cafe: "☕ Café", hotel: "🛏 Hotel",
    ausflug: "🥾 Ausflug", musik: "🎵 Musik", buch: "📖 Buch",
    sonstiges: "✨ Sonstiges",
  };
  let tippFilter = "";

  const sterneHtml = (n) =>
    `<span class="sterne" title="${n} von 5">${"★".repeat(n)}`
    + `<span class="leer">${"★".repeat(5 - n)}</span></span>`;

  // ---------- Empfehlungen in der Naehe ----------
  // Der eigene Standort bleibt im Speicher dieses Fensters. Gerechnet wird
  // hier im Browser - die Tipps bringen ihre Koordinaten ohnehin mit, also
  // muss der Server nie erfahren, wo man gerade ist.
  let meinOrt = null;
  let tippUmkreis = 0;          // Kilometer, 0 heisst: alle
  const UMKREISE = [0, 5, 25, 100];

  /** Luftlinie in Kilometern (Haversine). */
  function entfernungKm(a, b) {
    const R = 6371;
    const rad = (g) => g * Math.PI / 180;
    const dLat = rad(b.lat - a.lat);
    const dLon = rad(b.lon - a.lon);
    const x = Math.sin(dLat / 2) ** 2
      + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(x)));
  }

  const entfernungText = (km) =>
    km < 1 ? `${Math.round(km * 1000)} m`
           : km < 10 ? `${km.toFixed(1)} km`
                     : `${Math.round(km)} km`;

  async function standortFuerUmkreis() {
    const knopf = $("tipp-ort");
    if (knopf) knopf.textContent = "Standort wird bestimmt …";
    try {
      const gefunden = await standortHolen();
      meinOrt = {lat: gefunden.lat, lon: gefunden.lon};
      if (!tippUmkreis) tippUmkreis = 25;
    } catch (err) {
      toast(err.message);
    }
    renderTipps();
  }

  async function tippsLaden() {
    const res = await api("/api/tipps");
    if (!res.ok) return;
    const d = await res.json();
    state.tipps = d.tipps || [];
    renderTipps();
  }

  function renderTipps() {
    const liste = $("tipp-liste");
    if (!liste) return;
    const alle = state.tipps || [];

    // Entfernung dranschreiben, sobald der eigene Standort bekannt ist
    const mitWeg = alle.map((t) => Object.assign({}, t, {
      km: meinOrt && t.ort ? entfernungKm(meinOrt, t.ort) : null,
    }));
    let gezeigt = tippFilter ? mitWeg.filter((t) => t.art === tippFilter) : mitWeg;
    let ohneOrt = 0;
    if (meinOrt && tippUmkreis) {
      // Ohne Koordinaten laesst sich nicht sagen, ob es in der Naehe ist -
      // solche Empfehlungen fallen heraus, aber nicht stillschweigend.
      ohneOrt = gezeigt.filter((t) => t.km === null).length;
      gezeigt = gezeigt.filter((t) => t.km !== null && t.km <= tippUmkreis)
        .sort((a, b) => a.km - b.km);
    }

    const vorhanden = [...new Set(alle.map((t) => t.art))]
      .filter((a) => TIPP_ARTEN[a]);
    $("tipp-filter").innerHTML = vorhanden.length > 1
      ? `<button class="mini-btn ${tippFilter ? "" : "an"}" data-art="">Alle</button>`
        + vorhanden.map((a) =>
            `<button class="mini-btn ${tippFilter === a ? "an" : ""}"
                     data-art="${a}">${esc(TIPP_ARTEN[a])}</button>`).join("")
      : "";
    $("tipp-filter").querySelectorAll("[data-art]").forEach((b) =>
      b.addEventListener("click", () => { tippFilter = b.dataset.art; renderTipps(); }));

    // Zweite Zeile: Umkreis. Erst wenn es ueberhaupt Empfehlungen mit Ort gibt.
    const naehe = $("tipp-naehe");
    const mitOrt = alle.filter((t) => t.ort).length;
    if (naehe) {
      if (!mitOrt) {
        naehe.innerHTML = "";
      } else if (!meinOrt) {
        naehe.innerHTML = '<button class="mini-btn" id="tipp-ort">'
          + '📍 In meiner Nähe</button>';
        naehe.querySelector("#tipp-ort")
          .addEventListener("click", standortFuerUmkreis);
      } else {
        naehe.innerHTML = UMKREISE.map((km) =>
          `<button class="mini-btn ${tippUmkreis === km ? "an" : ""}"
                   data-km="${km}">${km ? `${km} km` : "Überall"}</button>`).join("")
          + '<button class="mini-btn" id="tipp-ort-neu" title="Standort neu bestimmen">↻</button>';
        naehe.querySelectorAll("[data-km]").forEach((b) =>
          b.addEventListener("click", () => {
            tippUmkreis = parseInt(b.dataset.km, 10);
            renderTipps();
          }));
        naehe.querySelector("#tipp-ort-neu")
          .addEventListener("click", standortFuerUmkreis);
      }
    }

    if (!gezeigt.length) {
      liste.innerHTML = `<div class="abschnitt-leer">${
        meinOrt && tippUmkreis
          ? `In ${tippUmkreis} km ist nichts dabei.${
              ohneOrt ? ` ${ohneOrt} ohne Ortsangabe nicht berücksichtigt.` : ""}`
          : alle.length ? "Zu diesem Filter gibt es nichts."
                        : "Noch keine Empfehlung. Sag, was gut war."}</div>`;
      reiterZahlen();
      renderKarten();
      return;
    }
    liste.innerHTML = gezeigt.map((t) => `<div class="tipp anklickbar" data-id="${t.id}">
      <div class="tp-kopf">
        <span class="tp-art">${esc(TIPP_ARTEN[t.art] || t.art)}</span>
        ${sterneHtml(t.sterne)}
        ${t.km !== null ? `<span style="flex:1"></span>
          <span class="tp-weg">${entfernungText(t.km)}</span>` : ""}
      </div>
      <div class="tp-titel">${esc(t.titel)}</div>
      ${t.ort_text ? `<div class="tp-ort">📍 ${esc(t.ort_text)}</div>` : ""}
      ${t.text ? `<div class="tp-text">${esc(t.text)}</div>` : ""}
      <div class="tp-fuss">
        ${avatarHtml("u", t.user_id, t.name, t.avatar, "winzig")}
        <span class="tp-von">${esc(t.name)}${t.meiner ? " (du)" : ""}</span>
        <span style="flex:1"></span>
        <button class="mini-btn ${t.ich_merke ? "an" : ""}" data-merken="${t.id}"
          >${t.ich_merke ? "Gemerkt" : "Merken"}${
            t.gemerkt.length ? ` · ${t.gemerkt.length}` : ""}</button>
        ${t.meiner ? `<button class="mini-btn" data-bearbeiten="${t.id}">Ändern</button>`
                   : ""}
      </div>
    </div>`).join("")
      + (ohneOrt ? `<div class="abschnitt-leer">${ohneOrt} ${
          ohneOrt === 1 ? "Empfehlung hat" : "Empfehlungen haben"} keinen Ort und
          ${ohneOrt === 1 ? "steht" : "stehen"} deshalb nicht in dieser Liste.</div>`
        : "");

    reiterZahlen();
    renderKarten();
    liste.querySelectorAll("[data-merken]").forEach((b) =>
      b.addEventListener("click", async (e) => {
        e.stopPropagation();
        const res = await api(`/api/tipps/${b.dataset.merken}/merken`,
                              {method: "POST"});
        if (!res.ok) { toast("Das ging nicht."); return; }
        await tippsLaden();
      }));
    liste.querySelectorAll("[data-bearbeiten]").forEach((b) =>
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        const t = (state.tipps || []).find(
          (x) => x.id === parseInt(b.dataset.bearbeiten, 10));
        if (t) tippDialog(t);
      }));
    liste.querySelectorAll(".tipp").forEach((k) =>
      k.addEventListener("click", (e) => {
        if (e.target.closest(".mini-btn")) return;
        tippAnsicht(parseInt(k.dataset.id, 10));
      }));
  }

  /** Ein Tipp in ganzer Groesse - mit Strassenkarte, wenn ein Ort dranhaengt. */
  async function tippAnsicht(tippId) {
    const t = (state.tipps || []).find((x) => x.id === tippId);
    if (!t) { toast("Diese Empfehlung ist nicht mehr da."); return; }
    const osm = t.ort
      ? `https://www.openstreetmap.org/?mlat=${t.ort.lat}&mlon=${t.ort.lon}`
        + `#map=17/${t.ort.lat}/${t.ort.lon}`
      : null;
    const root = modal(`<div class="karten-kopf"><h2>${esc(t.titel)}</h2>
      <span style="flex:1"></span>
      <button class="icon-btn" id="m-cancel">✕</button></div>
      <div class="tp-kopf"><span class="tp-art">${
        esc(TIPP_ARTEN[t.art] || t.art)}</span>${sterneHtml(t.sterne)}</div>
      ${t.file_id ? `<img class="ev-bild" alt="" src="${BASE}/files/${t.file_id}">` : ""}
      ${t.ort_text ? `<div class="tp-ort">📍 ${esc(t.ort_text)}</div>` : ""}
      ${t.text ? `<div class="tp-text">${esc(t.text)}</div>` : ""}
      ${t.ort ? '<div class="ortswahl" id="tp-karte-flaeche"></div>' : ""}
      <div class="tp-fuss">
        ${avatarHtml("u", t.user_id, t.name, t.avatar, "klein")}
        <span class="tp-von">Empfohlen von ${esc(t.name)}${t.meiner ? " (du)" : ""}</span>
      </div>
      ${t.gemerkt.length ? `<div class="tp-gemerkt">${t.gemerkt.map((m) =>
        avatarHtml("u", m.id, m.name, m.avatar, "winzig")).join("")}
        <span>${t.gemerkt.length === 1 ? "1 hat es sich gemerkt"
                                       : `${t.gemerkt.length} haben es sich gemerkt`}</span>
        </div>` : ""}
      <div class="row">
        <button class="btn ghost" id="tp-a-merken">${
          t.ich_merke ? "Nicht mehr merken" : "Merken"}</button>
        ${osm ? `<a class="btn ghost" id="tp-a-osm" target="_blank"
           rel="noopener noreferrer" href="${osm}"
           style="text-align:center;text-decoration:none;line-height:2.2">In Karten öffnen</a>` : ""}
        ${t.meiner ? '<button class="btn" id="tp-a-aendern">Ändern</button>' : ""}
      </div>`);
    root.querySelector(".modal").classList.add("wide", "hoch");
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    if (t.ort) {
      karteZeichnen(root.querySelector("#tp-karte-flaeche"),
                    [{lat: t.ort.lat, lon: t.ort.lon,
                      name: t.ort_text || t.titel, art: "tipp"}]);
    }
    root.querySelector("#tp-a-merken").addEventListener("click", async () => {
      const res = await api(`/api/tipps/${t.id}/merken`, {method: "POST"});
      if (!res.ok) { toast("Das ging nicht."); return; }
      await tippsLaden();
      closeModal();
    });
    const aendern = root.querySelector("#tp-a-aendern");
    if (aendern) aendern.addEventListener("click", () => tippDialog(t));
  }

  function tippDialog(vorhanden) {
    const aendern = !!vorhanden;
    let ort = aendern && vorhanden.ort
      ? {lat: vorhanden.ort.lat, lon: vorhanden.ort.lon} : null;
    let bildDatei = null;
    let bildId = aendern ? vorhanden.file_id : null;
    let sterne = aendern ? vorhanden.sterne : 0;

    const root = modal(`<h2>${aendern ? "Empfehlung ändern" : "Empfehlung"}</h2>
      <div class="field"><label for="tp-art">Was ist es?</label>
        <select id="tp-art">${Object.entries(TIPP_ARTEN).map(([k, txt]) =>
          `<option value="${k}" ${aendern && vorhanden.art === k ? "selected" : ""}
            >${txt}</option>`).join("")}</select></div>
      <div class="field"><label for="tp-titel">Name</label>
        <input id="tp-titel" autocomplete="off" placeholder="Ristorante Bella"
               value="${aendern ? esc(vorhanden.titel) : ""}"></div>
      <div class="field"><label>Wie war es?</label>
        <div class="stern-wahl" id="tp-sterne">${[1, 2, 3, 4, 5].map((n) =>
          `<button type="button" class="stern ${n <= sterne ? "an" : ""}"
                   data-n="${n}">★</button>`).join("")}</div></div>
      <div class="field"><label for="tp-ort">Wo</label>
        <input id="tp-ort" autocomplete="off" placeholder="Hauptstraße 4"
               value="${aendern ? esc(vorhanden.ort_text) : ""}">
        <div class="row schmal">
          <button class="btn ghost klein" type="button" id="tp-karte">Auf der Karte wählen</button>
          <button class="btn ghost klein" type="button" id="tp-hier">Aktueller Ort</button>
        </div>
        <div class="ortswahl" id="tp-kartenwahl" hidden></div>
        <div class="ev-ortstand"><span class="hint" id="tp-ortstand"></span>
          <button class="mini-btn" type="button" id="tp-ort-weg" hidden>Ort entfernen</button></div>
      </div>
      <div class="field"><label for="tp-text">Was sollte man wissen?</label>
        <textarea id="tp-text" rows="3">${aendern ? esc(vorhanden.text) : ""}</textarea></div>
      <div class="field"><label>Bild</label>
        <div class="row schmal">
          <button class="btn ghost klein" type="button" id="tp-bild">Bild wählen</button>
          <button class="btn ghost klein" type="button" id="tp-bild-weg"
                  ${bildId ? "" : "hidden"}>Bild entfernen</button></div>
        <span class="hint" id="tp-bild-name">${bildId ? "Ein Bild ist hinterlegt." : ""}</span></div>
      <div class="row">${aendern
        ? '<button class="btn ghost" id="tp-weg">Löschen</button>'
        : '<button class="btn ghost" id="m-cancel">Abbrechen</button>'}
      <button class="btn" id="tp-ok">${aendern ? "Speichern" : "Empfehlen"}</button></div>`);
    root.querySelector(".modal").classList.add("hoch");
    const abbruch = root.querySelector("#m-cancel");
    if (abbruch) abbruch.addEventListener("click", closeModal);

    root.querySelectorAll(".stern").forEach((b) =>
      b.addEventListener("click", () => {
        sterne = parseInt(b.dataset.n, 10);
        root.querySelectorAll(".stern").forEach((x) =>
          x.classList.toggle("an", parseInt(x.dataset.n, 10) <= sterne));
      }));

    const stand = root.querySelector("#tp-ortstand");
    const wegKnopf = root.querySelector("#tp-ort-weg");
    const ortAnzeigen = () => {
      stand.textContent = ort
        ? `Ort gesetzt: ${ort.lat.toFixed(5)}, ${ort.lon.toFixed(5)}`
        : "Noch kein Punkt auf der Karte.";
      wegKnopf.hidden = !ort;
    };
    ortAnzeigen();
    wegKnopf.addEventListener("click", () => {
      ort = null; ortAnzeigen();
      root.querySelector("#tp-kartenwahl").hidden = true;
    });
    root.querySelector("#tp-karte").addEventListener("click", () => {
      const box = root.querySelector("#tp-kartenwahl");
      if (!box.hidden) { box.hidden = true; return; }
      box.hidden = false;
      ortsWaehler(box, ort, (neu) => { ort = neu; ortAnzeigen(); });
    });
    root.querySelector("#tp-hier").addEventListener("click", async () => {
      stand.textContent = "Standort wird bestimmt …";
      try {
        const gefunden = await standortHolen();
        ort = {lat: gefunden.lat, lon: gefunden.lon};
        ortAnzeigen();
      } catch (err) { stand.textContent = err.message; }
    });

    root.querySelector("#tp-bild").addEventListener("click", () => {
      const feld = document.createElement("input");
      feld.type = "file";
      feld.accept = "image/*";
      feld.addEventListener("change", () => {
        bildDatei = feld.files[0] || null;
        root.querySelector("#tp-bild-name").textContent =
          bildDatei ? bildDatei.name : "";
        root.querySelector("#tp-bild-weg").hidden = !bildDatei && !bildId;
      });
      feld.click();
    });
    root.querySelector("#tp-bild-weg").addEventListener("click", () => {
      bildDatei = null; bildId = null;
      root.querySelector("#tp-bild-name").textContent = "Kein Bild.";
      root.querySelector("#tp-bild-weg").hidden = true;
    });

    const weg = root.querySelector("#tp-weg");
    if (weg) weg.addEventListener("click", async () => {
      if (!confirm("Diese Empfehlung löschen?")) return;
      const res = await api(`/api/tipps/${vorhanden.id}`, {method: "DELETE"});
      if (!res.ok) { toast("Das ging nicht."); return; }
      closeModal();
      await tippsLaden();
    });

    root.querySelector("#tp-ok").addEventListener("click", async () => {
      const titel = root.querySelector("#tp-titel").value.trim();
      if (!titel) { toast("Es fehlt der Name."); return; }
      if (!sterne) { toast("Wie viele Sterne gibst du?"); return; }
      const knopf = root.querySelector("#tp-ok");
      knopf.disabled = true;
      try {
        if (bildDatei) {
          const fd = new FormData();
          fd.append("file", bildDatei);
          const hoch = await api("/api/upload", {method: "POST", body: fd});
          const daten = await hoch.json().catch(() => ({}));
          if (!hoch.ok) { toast(daten.error || "Das Bild ging nicht durch."); return; }
          bildId = daten.id;
        }
        const nutzlast = {
          art: root.querySelector("#tp-art").value,
          titel, sterne,
          ort_text: root.querySelector("#tp-ort").value.trim(),
          text: root.querySelector("#tp-text").value.trim(),
          file_id: bildId,
          lat: ort ? ort.lat : null,
          lon: ort ? ort.lon : null,
        };
        const res = aendern
          ? await api(`/api/tipps/${vorhanden.id}`, {method: "PATCH",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify(nutzlast)})
          : await api("/api/tipps", {method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify(nutzlast)});
        const daten = await res.json().catch(() => ({}));
        if (!res.ok) { toast(daten.error || "Das hat nicht geklappt."); return; }
        closeModal();
        await tippsLaden();
      } finally {
        knopf.disabled = false;
      }
    });
  }

  socket.on("tipps_geaendert", () => tippsLaden());
  $("btn-tipp").addEventListener("click", () => tippDialog());

  // ---------- Aussehen ----------
  // Hell, dunkel oder was das Geraet sagt. Die Wahl steht am Geraet: sie
  // sagt nichts ueber die eigenen Daten aus, sondern nur, wie hell der
  // Bildschirm gerade sein soll.
  const THEMEN = [["auto", "Wie das Gerät"], ["hell", "Hell"],
                  ["dunkel", "Dunkel"]];

  function themaLesen() {
    try {
      const wert = localStorage.getItem("chat-thema");
      return THEMEN.some(([k]) => k === wert) ? wert : "auto";
    } catch (err) {
      return "auto";
    }
  }

  function themaSetzen(wert) {
    if (!THEMEN.some(([k]) => k === wert)) wert = "auto";
    try { localStorage.setItem("chat-thema", wert); } catch (err) { /* egal */ }
    if (wert === "auto") document.documentElement.removeAttribute("data-thema");
    else document.documentElement.setAttribute("data-thema", wert);
    // Die Leiste des Browsers soll mitgehen
    // Das Muster nimmt seine Farbe aus dem Aussehen - beim Wechseln neu zeichnen
    if (currentRoom) hintergrundAnwenden(roomById(currentRoom));
    const marke = document.querySelector('meta[name="theme-color"]');
    if (marke) {
      marke.content = getComputedStyle(document.documentElement)
        .getPropertyValue("--bg").trim() || "#0e1416";
    }
  }

  // ---------- Hintergrundmuster ----------
  // Kein hochgeladenes Foto, sondern ein gezeichnetes Muster - so wie bei
  // WhatsApp. Es liegt auf der Unterhaltung selbst, nicht auf der Liste der
  // Nachrichten, und wandert deshalb beim Blaettern nicht mit.
  const MUSTER = {
    punkte: {name: "Punkte", kante: 26,
      pfad: '<circle cx="13" cy="13" r="1.9"/>'},
    karo: {name: "Karo", kante: 34,
      pfad: '<path d="M17 3 L31 17 L17 31 L3 17 Z" fill="none"'
            + ' stroke-width="1.4"/>'},
    wellen: {name: "Wellen", kante: 40,
      pfad: '<path d="M0 20 q10 -9 20 0 q10 9 20 0" fill="none"'
            + ' stroke-width="1.5"/>'},
    kreuze: {name: "Kreuze", kante: 28,
      pfad: '<path d="M14 8 V20 M8 14 H20" stroke-width="1.6"/>'},
    blaetter: {name: "Blätter", kante: 44,
      pfad: '<path d="M22 10 q9 6 0 14 q-9 -8 0 -14 Z" fill="none"'
            + ' stroke-width="1.3"/><path d="M22 12 V22" stroke-width="1"/>'},
    kritzel: {name: "Kritzel", kante: 60,
      pfad: '<circle cx="12" cy="14" r="4.5" fill="none" stroke-width="1.3"/>'
            + '<path d="M34 10 l4 7 -8 0 Z" fill="none" stroke-width="1.3"/>'
            + '<path d="M46 34 q5 -6 9 0" fill="none" stroke-width="1.3"/>'
            + '<path d="M14 42 h11 M19.5 36.5 v11" stroke-width="1.3"/>'
            + '<circle cx="46" cy="14" r="1.8"/>'
            + '<path d="M30 46 q4 -5 8 0 q-4 6 -8 0 Z" fill="none"'
            + ' stroke-width="1.2"/>'},
  };

  /** Das Muster als Bildadresse. Die Farbe kommt aus dem Aussehen, damit es
   *  hell wie dunkel dezent bleibt. */
  function musterBild(name) {
    const m = MUSTER[name];
    if (!m) return "";
    const farbe = getComputedStyle(document.documentElement)
      .getPropertyValue("--musterfarbe").trim() || "rgba(255,255,255,0.06)";
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${m.kante}"`
      + ` height="${m.kante}" viewBox="0 0 ${m.kante} ${m.kante}">`
      + `<g fill="${farbe}" stroke="${farbe}" stroke-linecap="round">`
      + m.pfad + `</g></svg>`;
    return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
  }

  function hintergrundAnwenden(room) {
    // Das Muster sitzt auf der Unterhaltung, nicht auf der Nachrichtenliste -
    // sonst wuerde es beim Blaettern mitwandern.
    const flaeche = document.querySelector(".chat");
    if (!flaeche) return;
    const name = room && room.hintergrund;
    if (name && MUSTER[name]) {
      flaeche.style.backgroundImage = musterBild(name);
      flaeche.style.backgroundRepeat = "repeat";
    } else {
      flaeche.style.backgroundImage = "";
    }
  }

  function musterWaehlen(room, root) {
    const feld = root.querySelector("#hg-wahl");
    if (!feld) return;
    const knopf = (wert, text) =>
      `<button class="muster ${(room.hintergrund || "") === wert ? "aktiv" : ""}"
               type="button" data-muster="${wert}" title="${esc(text)}">${
        wert ? `<span class="muster-probe" data-p="${wert}"></span>`
             : '<span class="muster-leer">Keins</span>'}</button>`;
    feld.innerHTML = knopf("", "Kein Muster")
      + Object.entries(MUSTER).map(([k, m]) => knopf(k, m.name)).join("");
    feld.querySelectorAll(".muster-probe").forEach((p) => {
      p.style.backgroundImage = musterBild(p.dataset.p);
    });
    feld.querySelectorAll("[data-muster]").forEach((b) =>
      b.addEventListener("click", async () => {
        const wert = b.dataset.muster;
        const res = await api(`/api/rooms/${room.id}/hintergrund`, {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({muster: wert}),
        });
        if (!res.ok) { toast("Das ließ sich nicht speichern."); return; }
        room.hintergrund = wert || null;
        hintergrundAnwenden(room);
        feld.querySelectorAll("[data-muster]").forEach((x) =>
          x.classList.toggle("aktiv", x.dataset.muster === wert));
      }));
  }


  /** Auf 1440 Pixel lange Kante bringen - ein Foto vom Telefon hat sonst
   *  mehrere Megabyte, und der Pi soll das nicht lagern muessen. */


  // ---------- Freunde ----------
  // Gegenseitig: eine Anfrage wird erst durch die Zusage der Gegenseite zur
  // Freundschaft. Wer befreundet ist, sieht die Stimmung und die Tipps des
  // anderen - auch ohne gemeinsame Unterhaltung.
  async function freundeDialog() {
    const root = modal(`<h2>Freunde</h2>
      <div id="fr-inhalt"><p class="hint">Wird geladen …</p></div>
      <div class="row"><button class="btn ghost" id="m-cancel">Schließen</button></div>`);
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    await freundeZeichnen(root);
  }

  async function freundeZeichnen(root) {
    const feld = (root || document).querySelector("#fr-inhalt");
    if (!feld) return;
    const res = await api("/api/freunde");
    if (!res.ok) { feld.innerHTML = '<p class="hint">Das ging nicht.</p>'; return; }
    const d = await res.json();

    const zeile = (u, knoepfe) => `<div class="fr-zeile" data-id="${u.id}">
      ${avatarHtml("u", u.id, u.display_name, u.avatar, "klein")}
      <div class="fr-name">${esc(u.display_name)}
        <span class="utag">${esc(u.username)}</span></div>
      <span style="flex:1"></span>${knoepfe}</div>`;

    const gruppe = (titel, leute, knoepfe, leer) => {
      if (!leute.length && !leer) return "";
      return `<div class="fr-gruppe">${esc(titel)}</div>`
        + (leute.length ? leute.map((u) => zeile(u, knoepfe(u))).join("")
                        : `<p class="hint">${esc(leer)}</p>`);
    };

    feld.innerHTML =
      gruppe("Wartet auf deine Antwort", d.eingehend, () =>
        '<button class="mini-btn an" data-ja>Annehmen</button>'
        + '<button class="mini-btn" data-nein>Ablehnen</button>', "")
      + gruppe("Deine Freunde", d.freunde, () =>
        '<button class="mini-btn" data-weg>Entfernen</button>',
        "Noch niemand. Frag unten jemanden an.")
      + gruppe("Angefragt", d.ausgehend, () =>
        '<button class="mini-btn" data-zurueck>Zurücknehmen</button>', "")
      + gruppe("Weitere Personen", d.andere, () =>
        '<button class="mini-btn" data-fragen>Anfragen</button>', "");

    const tat = async (id, methode) => {
      const res = await api(`/api/freunde/${id}`, {method: methode});
      if (!res.ok) {
        const daten = await res.json().catch(() => ({}));
        toast(daten.error || "Das ging nicht.");
        return;
      }
      await loadState();
      await freundeZeichnen(root);
    };
    feld.querySelectorAll(".fr-zeile").forEach((z) => {
      const id = parseInt(z.dataset.id, 10);
      const binde = (was, methode) => {
        const knopf = z.querySelector(`[data-${was}]`);
        if (knopf) knopf.addEventListener("click", () => tat(id, methode));
      };
      binde("ja", "POST");
      binde("fragen", "POST");
      binde("nein", "DELETE");
      binde("weg", "DELETE");
      binde("zurueck", "DELETE");
    });
  }

  // Am Einstellungsknopf sieht man, dass jemand auf Antwort wartet
  function freundeMerker() {
    const knopf = $("btn-freunde");
    if (!knopf) return;
    const offen = state.freund_anfragen || 0;
    knopf.classList.toggle("wartet", offen > 0);
    knopf.title = offen
      ? `${offen} ${offen === 1 ? "Anfrage wartet" : "Anfragen warten"}`
      : "Freunde";
  }

  socket.on("freunde_geaendert", async (d) => {
    await loadState();
    if (d && d.anfrage) toast("Jemand möchte sich mit dir befreunden.");
    const offen = document.querySelector("#fr-inhalt");
    if (offen) freundeZeichnen($("modal-root"));
  });

  $("btn-freunde").addEventListener("click", freundeDialog);

  // ---------- Anrufe ----------
  // Bild und Ton laufen direkt von Gerät zu Gerät, nie über den Pi. Jeder
  // spricht mit jedem einzeln; für eine Familienrunde reicht das und spart
  // einen Medienserver.
  const anruf = {
    room: null,        // laufender eigener Anruf
    art: "audio",
    eigen: null,       // eigener Medienstrom
    peers: new Map(),  // user_id -> {pc, strom}
    stumm: false,
    kameraAus: false,
    beginn: 0,
    uhr: null,
  };
  let eisServer = null;

  async function eisHolen() {
    if (eisServer) return eisServer;
    try {
      const res = await api("/api/anruf/server");
      eisServer = res.ok ? await res.json() : {iceServers: []};
    } catch (err) {
      eisServer = {iceServers: []};
    }
    return eisServer;
  }

  const imAnruf = () => anruf.room !== null;

  function anrufDauer() {
    const s = Math.max(0, Math.round((Date.now() - anruf.beginn) / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  async function medienHolen(art) {
    const wunsch = art === "video"
      ? {audio: true, video: {width: {ideal: 640}, height: {ideal: 480}}}
      : {audio: true, video: false};
    return navigator.mediaDevices.getUserMedia(wunsch);
  }

  function peerAnlegen(uid) {
    if (anruf.peers.has(uid)) return anruf.peers.get(uid);
    const pc = new RTCPeerConnection({
      iceServers: (eisServer && eisServer.iceServers) || [],
    });
    const eintrag = {pc, strom: new MediaStream()};
    anruf.peers.set(uid, eintrag);

    if (anruf.eigen) {
      anruf.eigen.getTracks().forEach((spur) => pc.addTrack(spur, anruf.eigen));
    }
    pc.addEventListener("track", (e) => {
      e.streams[0].getTracks().forEach((spur) => eintrag.strom.addTrack(spur));
      anrufZeichnen();
    });
    pc.addEventListener("icecandidate", (e) => {
      if (e.candidate) {
        socket.emit("anruf_signal", {room_id: anruf.room, an: uid,
                                     art: "eis", daten: e.candidate});
      }
    });
    pc.addEventListener("connectionstatechange", () => {
      if (["failed", "closed"].includes(pc.connectionState)) {
        peerSchliessen(uid);
        anrufZeichnen();
      }
    });
    return eintrag;
  }

  function peerSchliessen(uid) {
    const eintrag = anruf.peers.get(uid);
    if (!eintrag) return;
    try { eintrag.pc.close(); } catch (err) { /* war schon zu */ }
    anruf.peers.delete(uid);
  }

  async function anrufStarten(art) {
    klingelnStoppen();
    if (!currentRoom) return;
    if (imAnruf()) { anrufFensterZeigen(true); return; }
    if (!sichererKontext()) {
      toast("Mikrofon und Kamera gibt der Browser nur über HTTPS frei – öffne "
            + "den Chat über deine externe Adresse.");
      return;
    }
    if (!window.RTCPeerConnection || !navigator.mediaDevices) {
      toast("Dieser Browser kann keine Anrufe.");
      return;
    }
    await eisHolen();
    try {
      anruf.eigen = await medienHolen(art);
    } catch (err) {
      toast(err.name === "NotAllowedError"
        ? "Du hast den Zugriff auf Mikrofon oder Kamera abgelehnt."
        : "Mikrofon oder Kamera wurden nicht gefunden.");
      return;
    }
    anruf.room = currentRoom;
    anruf.art = art;
    anruf.stumm = false;
    anruf.kameraAus = false;
    anruf.beginn = Date.now();
    anrufFensterZeigen(true);

    socket.timeout(8000).emit("anruf_beitreten", {room_id: anruf.room, art},
      async (fehler, antwort) => {
        if (fehler || !antwort || !antwort.ok) {
          toast((antwort && antwort.error) || "Der Anruf kam nicht zustande.");
          anrufBeenden();
          return;
        }
        anruf.art = antwort.art || art;
        // Die schon Anwesenden rufen mich an - ich warte auf ihr Angebot.
        anrufZeichnen();
      });
    anruf.uhr = setInterval(() => {
      const el = $("anruf-dauer");
      if (el) el.textContent = anrufDauer();
    }, 1000);
  }

  // Ein neuer kommt dazu: ich baue die Verbindung zu ihm auf
  socket.on("anruf_neuer", async (d) => {
    if (!imAnruf() || d.room_id !== anruf.room) return;
    const {pc} = peerAnlegen(d.user_id);
    const angebot = await pc.createOffer();
    await pc.setLocalDescription(angebot);
    socket.emit("anruf_signal", {room_id: anruf.room, an: d.user_id,
                                 art: "angebot", daten: angebot});
    anrufZeichnen();
  });

  socket.on("anruf_signal", async (d) => {
    if (!imAnruf() || d.room_id !== anruf.room) return;
    const {pc} = peerAnlegen(d.von);
    try {
      if (d.art === "angebot") {
        await pc.setRemoteDescription(new RTCSessionDescription(d.daten));
        const antwort = await pc.createAnswer();
        await pc.setLocalDescription(antwort);
        socket.emit("anruf_signal", {room_id: anruf.room, an: d.von,
                                     art: "antwort", daten: antwort});
      } else if (d.art === "antwort") {
        await pc.setRemoteDescription(new RTCSessionDescription(d.daten));
      } else if (d.art === "eis") {
        await pc.addIceCandidate(new RTCIceCandidate(d.daten));
      }
    } catch (err) {
      // Eine verspätete Wegbeschreibung ist kein Grund, das Gespräch
      // abzubrechen - sie gehört dann zu einer schon geschlossenen Leitung.
      console.warn("Anruf-Signal nicht verwertbar:", err);
    }
    anrufZeichnen();
  });

  socket.on("anruf_weg", (d) => {
    if (d.room_id !== anruf.room) return;
    peerSchliessen(d.user_id);
    anrufZeichnen();
  });

  socket.on("anruf_abgelehnt", (d) => {
    if (d.room_id !== anruf.room) return;
    const raum = roomById(d.room_id);
    const wer = raum && raum.members.find((m) => m.id === d.user_id);
    toast(`${wer ? wer.display_name : "Jemand"} hat abgelehnt.`);
  });

  // Der Stand eines Anrufs geht an alle im Raum - auch an die, die nicht
  // mitmachen. Daraus wird der Klingelbalken.
  socket.on("anruf_stand", (d) => {
    const raum = roomById(d.room_id);
    if (raum) raum.anruf = (d.wer && d.wer.length) ? d : null;
    if (imAnruf() && d.room_id === anruf.room) {
      if (!d.wer || !d.wer.length) anrufBeenden();
      else anrufZeichnen();
    }
    klingelZeigen();
    renderRooms();
  });

  // ---------- Klingeln ----------
  // Der Ton wird erzeugt, nicht geladen: das spart eine Datei im Add-on und
  // klingt auf jedem Geraet gleich. Ein Browser laesst Ton allerdings erst
  // zu, wenn man die Seite einmal angefasst hat - vorher bleibt es beim
  // Balken und beim Ruettelfeedback.
  let klingelUhr = null;
  let klingelCtx = null;
  let klingelSeit = 0;
  // Nach dieser Zeit hoert es von selbst auf. Ein Anruf, den niemand
  // annimmt, soll nicht endlos laeuten.
  const KLINGEL_MAX_MS = 45000;

  // Ton ist erst erlaubt, nachdem der Mensch die Seite einmal angefasst hat.
  // Deshalb wird der Tonkanal beim ersten Tippen still geoeffnet - dann ist
  // er bereit, wenn spaeter ein Anruf hereinkommt.
  function tonkanalOeffnen() {
    try {
      if (!klingelCtx) klingelCtx = new AudioContext();
      if (klingelCtx.state === "suspended") klingelCtx.resume();
    } catch (err) { /* dann bleibt es beim Balken */ }
  }
  ["pointerdown", "keydown"].forEach((art) =>
    document.addEventListener(art, tonkanalOeffnen, {once: true, capture: true}));

  function tonSchlagen() {
    try {
      if (!klingelCtx) klingelCtx = new AudioContext();
      if (klingelCtx.state === "suspended") klingelCtx.resume();
      const t = klingelCtx.currentTime;
      // Zwei kurze Toene, wie ein Telefon
      [0, 0.42].forEach((versatz) => {
        const o = klingelCtx.createOscillator();
        const g = klingelCtx.createGain();
        o.type = "sine";
        o.frequency.value = 660;
        g.gain.setValueAtTime(0, t + versatz);
        g.gain.linearRampToValueAtTime(0.16, t + versatz + 0.03);
        g.gain.linearRampToValueAtTime(0, t + versatz + 0.34);
        o.connect(g);
        g.connect(klingelCtx.destination);
        o.start(t + versatz);
        o.stop(t + versatz + 0.36);
      });
    } catch (err) { /* ohne Ton bleibt der Balken sichtbar */ }
  }

  function klingelnStarten() {
    if (klingelUhr) return;
    klingelSeit = Date.now();
    const schlag = () => {
      if (Date.now() - klingelSeit > KLINGEL_MAX_MS) { klingelnStoppen(); return; }
      tonSchlagen();
      if (navigator.vibrate) {
        try { navigator.vibrate([320, 180, 320]); } catch (err) { /* egal */ }
      }
    };
    schlag();
    klingelUhr = setInterval(schlag, 2400);
  }

  function klingelnStoppen() {
    if (klingelUhr) { clearInterval(klingelUhr); klingelUhr = null; }
    if (navigator.vibrate) {
      try { navigator.vibrate(0); } catch (err) { /* egal */ }
    }
  }

  /** Der erste laufende Anruf in einer meiner Unterhaltungen, bei dem ich
   *  nicht mitmache - unabhaengig davon, welcher Chat gerade offen ist. */
  function eingehenderAnruf() {
    if (imAnruf()) return null;
    return (state.rooms || []).find((r) =>
      r.anruf && r.anruf.wer && r.anruf.wer.length
      && !r.anruf.wer.includes(ME)) || null;
  }

  let zuletztGeklingelt = null;

  function klingelZeigen() {
    const balken = $("anruf-ruf");
    const raum = eingehenderAnruf();
    balken.hidden = !raum;
    if (!raum) {
      klingelnStoppen();
      zuletztGeklingelt = null;
      return;
    }
    const namen = raum.anruf.wer
      .map((u) => (raum.members.find((m) => m.id === u) || {}).display_name)
      .filter(Boolean).join(", ");
    $("ruf-titel").textContent =
      raum.anruf.art === "video" ? "Videoanruf" : "Anruf";
    $("ruf-sub").textContent = `${raum.name} · ${namen}`;
    // Nur bei einem neuen Anruf von vorn laeuten, nicht bei jeder Meldung
    const kennung = `${raum.id}:${raum.anruf.seit}`;
    if (zuletztGeklingelt !== kennung) {
      zuletztGeklingelt = kennung;
      klingelnStoppen();
      klingelnStarten();
    }
  }

  $("ruf-annehmen").addEventListener("click", async () => {
    const raum = eingehenderAnruf();
    if (!raum) return;
    klingelnStoppen();
    if (currentRoom !== raum.id) await openRoom(raum.id);
    anrufStarten(raum.anruf.art || "audio");
  });

  $("ruf-ablehnen").addEventListener("click", () => {
    const raum = eingehenderAnruf();
    klingelnStoppen();
    $("anruf-ruf").hidden = true;
    if (raum) socket.emit("anruf_ablehnen", {room_id: raum.id});
  });

  function anrufFensterZeigen(an) {
    $("anruf-fenster").hidden = !an;
    if (an) anrufZeichnen();
  }

  // Wer waehrend eines laufenden Anrufs zur Gruppe kam, steht noch nicht in
  // der Mitgliederliste dieses Geraets. Die allgemeine Nutzerliste kennt ihn
  // trotzdem - besser der richtige Name als drei Punkte.
  function anrufPerson(raum, uid) {
    return (raum && raum.members.find((m) => m.id === uid))
      || (state.users || []).find((u) => u.id === uid)
      || {id: uid, display_name: "…"};
  }

  function kachelHtml(uid, eigen) {
    const raum = roomById(anruf.room);
    const person = eigen
      ? {id: ME, display_name: state.me ? state.me.name : "Ich",
         avatar: state.me ? state.me.avatar : null}
      : anrufPerson(raum, uid);
    return `<div class="anruf-kachel" data-wer="${uid}">
      <video autoplay playsinline ${eigen ? "muted" : ""}></video>
      <div class="ak-ersatz">${avatarHtml("u", person.id, person.display_name,
                                          person.avatar, "riesig")}</div>
      <div class="ak-name">${esc(person.display_name)}${eigen ? " (du)" : ""}</div>
    </div>`;
  }

  function anrufZeichnen() {
    if (!imAnruf()) return;
    const feld = $("anruf-kacheln");
    const gewuenscht = [ME, ...anruf.peers.keys()];
    const vorhanden = [...feld.querySelectorAll(".anruf-kachel")]
      .map((k) => parseInt(k.dataset.wer, 10));
    // Nur neu bauen, wenn sich die Runde geändert hat - sonst würde jedes
    // Signal das laufende Bild zurücksetzen.
    if (gewuenscht.length !== vorhanden.length
        || gewuenscht.some((u, i) => u !== vorhanden[i])) {
      feld.innerHTML = gewuenscht
        .map((u) => kachelHtml(u, u === ME)).join("");
      feld.dataset.anzahl = String(gewuenscht.length);
    }
    feld.querySelectorAll(".anruf-kachel").forEach((kachel) => {
      const uid = parseInt(kachel.dataset.wer, 10);
      const video = kachel.querySelector("video");
      const strom = uid === ME ? anruf.eigen
                               : (anruf.peers.get(uid) || {}).strom;
      if (strom && video.srcObject !== strom) video.srcObject = strom;
      const hatBild = strom && strom.getVideoTracks().some((s) => s.enabled);
      kachel.classList.toggle("ohne-bild", !hatBild);
      if (uid !== ME) {
        // Der Name kann nachtraeglich bekannt werden - dann soll er auch
        // ohne Neuaufbau der Kacheln erscheinen.
        const person = anrufPerson(roomById(anruf.room), uid);
        const feld = kachel.querySelector(".ak-name");
        if (feld.textContent !== person.display_name) {
          feld.textContent = person.display_name;
        }
      }
    });
    $("anruf-titel").textContent =
      anruf.art === "video" ? "Videoanruf" : "Anruf";
    $("btn-anruf-stumm").classList.toggle("aus", anruf.stumm);
    $("btn-anruf-stumm").textContent = anruf.stumm ? "🔇" : "🎤";
    const kamera = $("btn-anruf-kamera");
    kamera.hidden = anruf.art !== "video";
    kamera.classList.toggle("aus", anruf.kameraAus);
    kamera.textContent = anruf.kameraAus ? "🚫" : "📷";
  }

  function anrufBeenden() {
    if (!imAnruf()) return;
    const room = anruf.room;
    clearInterval(anruf.uhr);
    anruf.uhr = null;
    [...anruf.peers.keys()].forEach(peerSchliessen);
    if (anruf.eigen) anruf.eigen.getTracks().forEach((s) => s.stop());
    anruf.eigen = null;
    anruf.room = null;
    anrufFensterZeigen(false);
    $("anruf-kacheln").innerHTML = "";
    socket.emit("anruf_verlassen", {room_id: room});
    klingelZeigen();
  }

  $("btn-anruf").addEventListener("click", () => anrufStarten("audio"));
  $("btn-video").addEventListener("click", () => anrufStarten("video"));
  $("btn-anruf-auflegen").addEventListener("click", anrufBeenden);

  $("btn-anruf-stumm").addEventListener("click", () => {
    if (!anruf.eigen) return;
    anruf.stumm = !anruf.stumm;
    anruf.eigen.getAudioTracks().forEach((s) => { s.enabled = !anruf.stumm; });
    anrufZeichnen();
  });

  $("btn-anruf-kamera").addEventListener("click", () => {
    if (!anruf.eigen) return;
    anruf.kameraAus = !anruf.kameraAus;
    anruf.eigen.getVideoTracks().forEach((s) => { s.enabled = !anruf.kameraAus; });
    anrufZeichnen();
  });

  // Wer das Fenster schliesst, soll nicht als stumme Kachel stehen bleiben
  window.addEventListener("beforeunload", () => {
    if (imAnruf()) socket.emit("anruf_verlassen", {room_id: anruf.room});
  });

  // ---------- Sprachnachrichten ----------
  // Aufgenommen wird mit dem, was der Browser selbst mitbringt. Opus in einem
  // WebM-Behälter ist klein und überall zu Hause; Safari kann das nicht und
  // bekommt MP4.
  const TONFORMATE = ["audio/webm;codecs=opus", "audio/webm",
                      "audio/mp4;codecs=mp4a.40.2", "audio/mp4", "audio/ogg"];

  function tonFormat() {
    if (typeof MediaRecorder === "undefined") return null;
    return TONFORMATE.find((f) => {
      try {
        return MediaRecorder.isTypeSupported(f);
      } catch (err) {
        return false;
      }
    }) || "";
  }

  let aufnahme = null;   // {recorder, spur, teile, seit, uhr}

  const dauerText = (sekunden) => {
    const s = Math.max(0, Math.round(sekunden));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  };

  function aufnahmeLeisteZeigen(an) {
    $("aufnahme-leiste").hidden = !an;
    $("composer").classList.toggle("aufnehmend", an);
  }

  async function aufnahmeStarten() {
    if (!currentRoom) { toast("Öffne zuerst eine Unterhaltung."); return; }
    if (aufnahme) return;
    if (!sichererKontext()) {
      toast("Das Mikrofon gibt der Browser nur über HTTPS frei – öffne den "
            + "Chat über deine externe Adresse.");
      return;
    }
    if (!navigator.mediaDevices || tonFormat() === null) {
      toast("Dieser Browser kann keine Sprachnachrichten aufnehmen.");
      return;
    }
    let spur;
    try {
      spur = await navigator.mediaDevices.getUserMedia({audio: true});
    } catch (err) {
      toast(err.name === "NotAllowedError"
        ? "Du hast den Zugriff auf das Mikrofon abgelehnt."
        : "Kein Mikrofon gefunden.");
      return;
    }
    const format = tonFormat();
    const recorder = new MediaRecorder(spur, format ? {mimeType: format} : {});
    const teile = [];
    recorder.addEventListener("dataavailable", (e) => {
      if (e.data && e.data.size) teile.push(e.data);
    });
    aufnahme = {recorder, spur, teile, seit: Date.now(), abgebrochen: false};
    recorder.addEventListener("stop", () => aufnahmeBeenden());
    recorder.start();
    aufnahmeLeisteZeigen(true);
    $("btn-mikro").classList.add("laeuft");
    $("aufnahme-zeit").textContent = "0:00";
    aufnahme.uhr = setInterval(() => {
      const s = (Date.now() - aufnahme.seit) / 1000;
      $("aufnahme-zeit").textContent = dauerText(s);
      // Eine Viertelstunde ist mehr als genug - danach ist es ein Vortrag
      if (s > 900) aufnahmeStoppen();
    }, 200);
  }

  function aufnahmeStoppen(abbrechen = false) {
    if (!aufnahme) return;
    aufnahme.abgebrochen = abbrechen;
    clearInterval(aufnahme.uhr);
    try {
      aufnahme.recorder.stop();
    } catch (err) {
      aufnahmeBeenden();
    }
  }

  async function aufnahmeBeenden() {
    if (!aufnahme) return;
    const {teile, spur, seit, abgebrochen, recorder} = aufnahme;
    aufnahme = null;
    aufnahmeLeisteZeigen(false);
    $("btn-mikro").classList.remove("laeuft");
    // Das Mikrofon wieder freigeben - sonst leuchtet die Anzeige weiter
    spur.getTracks().forEach((t) => t.stop());
    if (abgebrochen || !teile.length) return;
    const sekunden = Math.max(1, Math.round((Date.now() - seit) / 1000));
    const typ = recorder.mimeType || teile[0].type || "audio/webm";
    const endung = typ.includes("mp4") ? "m4a" : typ.includes("ogg") ? "ogg" : "webm";
    const blob = new Blob(teile, {type: typ.split(";")[0]});

    const fd = new FormData();
    fd.append("file", blob, `sprachnachricht.${endung}`);
    const res = await api("/api/upload", {method: "POST", body: fd});
    const daten = await res.json().catch(() => ({}));
    if (!res.ok) { toast(daten.error || "Die Aufnahme ging nicht durch."); return; }
    if (!socket.connected) { toast("Keine Verbindung."); return; }
    socket.timeout(8000).emit("send",
      {room_id: currentRoom, body: "", file_id: daten.id, reply_to: replyTo,
       sprachdauer: sekunden},
      (fehler, antwort) => {
        if (fehler || (antwort && antwort.ok === false)) {
          toast("Die Sprachnachricht ließ sich nicht senden.");
        }
      });
    cancelReply();
  }

  // Ein eigener Abspieler statt <audio controls>: der sieht in jedem Browser
  // anders aus und ist in einer Sprechblase viel zu breit.
  function sprachHtml(datei, sekunden) {
    return `<div class="sprachnachricht" data-dauer="${sekunden || 0}">
      <button class="sn-play" type="button" aria-label="Abspielen">▶</button>
      <div class="sn-balken"><div class="sn-fortschritt"></div></div>
      <span class="sn-zeit">${dauerText(sekunden || 0)}</span>
      <audio preload="none" src="${BASE}/files/${datei.id}"></audio>
    </div>`;
  }

  // Ein Tipp spielt ab, der nächste hält an. Läuft schon etwas anderes, hört
  // das auf - zwei Stimmen gleichzeitig versteht niemand.
  document.addEventListener("click", (e) => {
    const knopf = e.target.closest(".sn-play");
    if (!knopf) return;
    const kasten = knopf.closest(".sprachnachricht");
    const ton = kasten.querySelector("audio");
    if (ton.paused) {
      document.querySelectorAll(".sprachnachricht audio").forEach((a) => {
        if (a !== ton) a.pause();
      });
      ton.play().catch(() => toast("Die Aufnahme ließ sich nicht abspielen."));
    } else {
      ton.pause();
    }
  });

  document.addEventListener("play", (e) => {
    const ton = e.target;
    if (!ton.closest || !ton.closest(".sprachnachricht")) return;
    ton.closest(".sprachnachricht").querySelector(".sn-play").textContent = "❚❚";
  }, true);

  ["pause", "ended"].forEach((art) =>
    document.addEventListener(art, (e) => {
      const kasten = e.target.closest && e.target.closest(".sprachnachricht");
      if (!kasten) return;
      kasten.querySelector(".sn-play").textContent = "▶";
      if (art === "ended") {
        kasten.querySelector(".sn-fortschritt").style.width = "0%";
        kasten.querySelector(".sn-zeit").textContent =
          dauerText(parseInt(kasten.dataset.dauer, 10) || 0);
      }
    }, true));

  document.addEventListener("timeupdate", (e) => {
    const kasten = e.target.closest && e.target.closest(".sprachnachricht");
    if (!kasten) return;
    const ton = e.target;
    // Die aufgezeichnete Länge ist verlässlicher als ton.duration: bei einem
    // WebM-Strom ohne Dauer im Kopf liefert der Browser dort Infinity.
    const gesamt = Number.isFinite(ton.duration) && ton.duration > 0
      ? ton.duration : (parseInt(kasten.dataset.dauer, 10) || 0);
    if (gesamt) {
      kasten.querySelector(".sn-fortschritt").style.width =
        `${Math.min(100, ton.currentTime / gesamt * 100).toFixed(1)}%`;
    }
    kasten.querySelector(".sn-zeit").textContent = dauerText(ton.currentTime);
  }, true);

  $("btn-mikro").addEventListener("click", () => {
    if (aufnahme) aufnahmeStoppen(); else aufnahmeStarten();
  });
  $("aufnahme-senden").addEventListener("click", () => aufnahmeStoppen());
  $("aufnahme-weg").addEventListener("click", () => aufnahmeStoppen(true));

  // ---------- Anhang-Menue ----------
  // Fuenf Knoepfe nebeneinander liessen im Eingabefeld kaum Platz. Alles,
  // was man an eine Unterhaltung haengen kann, steckt jetzt hinter der
  // Heftklammer - so wie bei WhatsApp.
  const TATEN = {
    datei: () => $("file-input").click(),
    ort: () => ortSenden(),
    live: () => liveDialog(),
    abstimmung: () => abstimmungDialog(),
    event: () => terminDialog(),
  };

  let anhangOffen = false;

  function anhangMenueZeigen(offen) {
    anhangOffen = offen;
    const menue = $("anhang-menue");
    menue.hidden = !offen;
    $("btn-anhang").classList.toggle("aktiv", offen);
    if (offen) {
      emojiSchliessen();
      // Das Eingabefeld waechst beim Tippen mit - ein fester Abstand im
      // Stilblatt wuerde das Menue frueher oder spaeter darauflegen.
      menue.style.bottom = ($("composer").offsetHeight + 8) + "px";
    }
  }

  $("btn-anhang").addEventListener("click", (e) => {
    e.stopPropagation();
    anhangMenueZeigen(!anhangOffen);
  });

  $("anhang-menue").addEventListener("click", (e) => {
    const knopf = e.target.closest("[data-tat]");
    if (!knopf) return;
    anhangMenueZeigen(false);
    const tat = TATEN[knopf.dataset.tat];
    if (tat) tat();
  });

  // Danebentippen schliesst - sonst steht das Menue im Weg
  document.addEventListener("click", (e) => {
    if (!anhangOffen) return;
    if (e.target.closest("#anhang-menue") || e.target.closest("#btn-anhang")) return;
    anhangMenueZeigen(false);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && anhangOffen) anhangMenueZeigen(false);
  });

  function emojiSchliessen() {
    if (!emojiOffen) return;
    emojiOffen = false;
    const feld = $("emoji-feld");
    if (feld) feld.hidden = true;
    $("btn-emoji").classList.remove("aktiv");
  }

  $("btn-emoji").addEventListener("click", () => {
    anhangMenueZeigen(false);
    const feld = emojiFeldAufbauen();
    emojiOffen = !emojiOffen;
    feld.hidden = !emojiOffen;
    $("btn-emoji").classList.toggle("aktiv", emojiOffen);
    if (!emojiOffen) $("input").focus();
  });

  $("file-input").addEventListener("change", async (e) => {
    const dateien = [...e.target.files];
    e.target.value = "";
    if (!dateien.length || !currentRoom) return;
    // Mehrere Dateien nacheinander - jede wird eine eigene Nachricht, so wie
    // man es von anderen Messengern kennt.
    const raum = currentRoom;
    // Alle Bilder eines Vorgangs bekommen dieselbe Kennung und erscheinen
    // dadurch als ein Album. Bei einer einzelnen Datei braucht es das nicht.
    const bilder = dateien.filter((d) => (d.type || "").startsWith("image/"));
    const album = bilder.length > 1
      ? "a" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
      : null;
    let fertig = 0;
    for (const datei of dateien) {
      toast(dateien.length > 1
        ? `Lade ${fertig + 1} von ${dateien.length} …` : "Datei wird hochgeladen …");
      const fd = new FormData();
      fd.append("file", datei);
      const res = await api("/api/upload", {method: "POST", body: fd});
      const daten = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast(`${datei.name}: ${daten.error || "Hochladen fehlgeschlagen."}`);
        continue;
      }
      if (currentRoom !== raum) return;   // inzwischen woanders
      send(daten.id, (datei.type || "").startsWith("image/") ? album : null);
      fertig += 1;
    }
    if (dateien.length > 1) toast(`${fertig} von ${dateien.length} gesendet.`);
  });

  // Farben zur Auswahl - dieselben Werte kennt der Server, damit niemand
  // beliebige Angaben unterschiebt.

  // Ein Tipp auf ein Profilbild zeigt es formatfuellend.
  function bildGross(kind, id, name, avatar) {
    const root = modal(avatar
      ? `<img class="gross-bild" src="${BASE}/avatars/${kind}/${id}`
        + `?v=${encodeURIComponent(avatar)}" alt="${esc(name)}">`
        + `<p class="gross-name">${esc(name)}</p>`
      : `<div class="gross-ersatz">${avatarHtml(kind, id, name, null, "riesig")}</div>`
        + `<p class="gross-name">${esc(name)}</p>`
        + '<p class="hint">Für diesen Eintrag gibt es kein Bild.</p>');
    root.querySelector(".modal").classList.add("bildschau");
    root.querySelector(".modal").addEventListener("click", closeModal);
  }

  // Profilbilder neben Nachrichten
  $("messages").addEventListener("click", (e) => {
    const bild = e.target.closest(".msg > .avatar");
    if (!bild) return;
    const msg = bild.closest(".msg");
    const room = roomById(currentRoom);
    const id = parseInt(msg.dataset.id, 10);
    const person = room && room.members.find((x) =>
      x.display_name === msg.querySelector(".author")?.textContent);
    if (person) bildGross("u", person.id, person.display_name, person.avatar);
    void id;
  }, true);

  // Auf Bild oder Namen in der Kopfzeile tippen: Angaben zur Unterhaltung.
  function chatInfo() {
    const room = roomById(currentRoom);
    if (!room) return;
    const root = modal(`<h2>${esc(room.name)}</h2>
      <div class="avatar-vorschau">${raumAvatar(room, "riesig")}</div>
      ${room.is_group ? `<div class="row schmal">
        <button class="btn ghost" id="a-neu">Bild wählen</button>
        ${room.avatar ? '<button class="btn ghost" id="a-weg">Bild entfernen</button>' : ""}
      </div>` : ""}
      <hr class="sep">
      <h2>Hintergrundmuster</h2>
      <p class="hint">Gilt nur für dich – andere sehen ihr eigenes Muster.</p>
      <div class="musterwahl" id="hg-wahl"></div>
      <hr class="sep">
      <div class="row schmal">
        <button class="btn ghost" id="r-leave">Chat löschen</button>
        ${IS_ADMIN ? '<button class="btn ghost del" id="r-kill">Für alle löschen</button>' : ""}
      </div>
      <p class="hint">„Chat löschen" entfernt die Unterhaltung nur bei dir.
        ${IS_ADMIN ? "„Für alle löschen\" entfernt sie mitsamt Nachrichten und Anhängen bei allen." : ""}</p>
      <div class="row"><button class="btn ghost" id="m-cancel">Schließen</button></div>`);
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    root.querySelector(".avatar-vorschau").addEventListener("click", () => {
      if (room.is_group) return bildGross("r", room.id, room.name, room.avatar);
      const other = room.members.find((x) => x.id !== ME) || room.members[0];
      if (other) bildGross("u", other.id, other.display_name, other.avatar);
    });

    root.querySelector("#r-leave").addEventListener("click", async () => {
      if (!confirm(`Unterhaltung „${room.name}“ bei dir löschen?

`
                   + "Die anderen behalten sie. Du siehst den Verlauf danach "
                   + "nicht mehr.")) return;
      const res = await api(`/api/rooms/${room.id}/leave`, {method: "POST"});
      if (!res.ok) { toast("Das hat nicht geklappt."); return; }
      toast("Unterhaltung gelöscht.");
      closeModal();
      raumVerlassen(room.id);
    });
    const kill = root.querySelector("#r-kill");
    if (kill) kill.addEventListener("click", async () => {
      if (!confirm(`Unterhaltung „${room.name}“ für ALLE löschen?

`
                   + "Nachrichten und Anhänge werden endgültig entfernt. "
                   + "Das lässt sich nicht rückgängig machen.")) return;
      const res = await api(`/api/rooms/${room.id}`, {method: "DELETE"});
      if (!res.ok) { toast("Das hat nicht geklappt."); return; }
      toast("Unterhaltung für alle gelöscht.");
      closeModal();
      raumVerlassen(room.id);
    });

    musterWaehlen(room, root);

    const neu = root.querySelector("#a-neu");
    if (neu) neu.addEventListener("click", () =>
      bildWaehlen(`/api/rooms/${room.id}/avatar`, () => {
        closeModal();
        if (currentRoom === room.id) openRoom(room.id);
      }));
    const weg = root.querySelector("#a-weg");
    if (weg) weg.addEventListener("click", async () => {
      const res = await api(`/api/rooms/${room.id}/avatar`, {method: "DELETE"});
      if (!res.ok) { toast("Entfernen fehlgeschlagen."); return; }
      toast("Gruppenbild entfernt.");
      closeModal();
      await loadState();
      if (currentRoom === room.id) openRoom(room.id);
    });
  }

  $("room-avatar").addEventListener("click", chatInfo);
  $("room-title").addEventListener("click", chatInfo);

  function raumVerlassen(id) {
    state.rooms = state.rooms.filter((r) => r.id !== id);
    if (currentRoom === id) {
      currentRoom = null;
      $("app").classList.remove("room-open");
      $("chat-header").hidden = true;
      $("composer").hidden = true;
      $("messages").innerHTML =
        '<div class="empty">Wähle links eine Unterhaltung.</div>';
    }
    renderRooms();
    loadState();
  }

  $("btn-back").addEventListener("click", () => {
    $("app").classList.remove("room-open");
    currentRoom = null;
  });

  // ---------- Modals ----------
  function modal(html) {
    kartenAbbauen();
    const root = $("modal-root");
    root.innerHTML = `<div class="modal-bg"><div class="modal">${html}</div></div>`;
    root.querySelector(".modal-bg").addEventListener("click", (e) => {
      if (e.target.classList.contains("modal-bg")) root.innerHTML = "";
    });
    return root;
  }
  const closeModal = () => {
    kartenAbbauen();
    $("modal-root").innerHTML = "";
  };

  $("btn-new").addEventListener("click", () => {
    const others = state.users.filter((u) => u.id !== ME && u.active !== false);
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
    const cands = state.users.filter((u) => !inRoom.has(u.id) && u.active !== false);
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
    const meinBild = avatarHtml("u", ME, B.dataset.name, state.me && state.me.avatar, "riesig");
    const root = modal(`<h2>Einstellungen</h2>
      <div class="mein-bild">
        <div class="avatar-vorschau">${meinBild}</div>
        <div class="row schmal"><button class="btn ghost" id="me-bild">Bild wählen</button>
        ${state.me && state.me.avatar ? '<button class="btn ghost" id="me-bild-weg">Entfernen</button>' : ""}</div>
      </div>
      <div class="field"><label>Aktuelles Passwort</label><input id="p-old" type="password"></div>
      <div class="field"><label>Neues Passwort</label><input id="p-new" type="password"></div>
      <button class="btn" id="p-ok">Passwort ändern</button>
      <hr class="sep">
      <h2>Aussehen</h2>
      <div class="kf-zeile" id="thema-wahl"></div>
      <hr class="sep">
      <h2>Karten</h2>
      <p class="hint">Die Umrisskarte steckt im Add-on und fragt niemanden.
        Für Straßen holt die Live- und Terminansicht Kacheln von
        OpenStreetMap – das ist die einzige Stelle, an der dieser Chat etwas
        von einem fremden Server lädt.</p>
      <label class="check"><input type="checkbox" id="k-kacheln"
        ${kachelnErlaubt() ? "checked" : ""}> Straßenkarte verwenden</label>
      ${IS_ADMIN ? `<hr class="sep">
        <h2>Benutzer verwalten</h2>
        <div id="u-list" class="user-list"><p class="hint">Wird geladen …</p></div>
        <button class="btn ghost" id="u-new">+ Neues Konto</button>
        <hr class="sep">
        <h2>Home Assistant</h2>
        <p class="hint">Mit diesem Token schickt eine Automation Nachrichten
          in den Chat. Behandle es wie ein Passwort.</p>
        <div class="token-zeile">
          <input id="ha-token" readonly value="wird geladen …">
          <button class="btn ghost" id="ha-kopieren">Kopieren</button>
        </div>
        <p class="hint" id="ha-herkunft"></p>` : ""}
      <div class="row"><button class="btn ghost" id="m-cancel">Schließen</button>
      <a class="btn ghost" style="text-align:center;text-decoration:none;line-height:2.2" href="${BASE}/logout">Abmelden</a></div>`);
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    root.querySelector("#me-bild").addEventListener("click", () =>
      bildWaehlen("/api/me/avatar", () => { closeModal(); $("btn-settings").click(); }));
    const meinBildWeg = root.querySelector("#me-bild-weg");
    if (meinBildWeg) meinBildWeg.addEventListener("click", async () => {
      const res = await api("/api/me/avatar", {method: "DELETE"});
      if (!res.ok) { toast("Entfernen fehlgeschlagen."); return; }
      toast("Bild entfernt.");
      await loadState();
      closeModal();
      $("btn-settings").click();
    });
    const themaFeld = root.querySelector("#thema-wahl");
    const themaZeichnen = () => {
      const jetzt = themaLesen();
      themaFeld.innerHTML = THEMEN.map(([wert, text]) =>
        `<button class="mini-btn ${jetzt === wert ? "an" : ""}"
                 data-thema="${wert}">${text}</button>`).join("");
      themaFeld.querySelectorAll("[data-thema]").forEach((b) =>
        b.addEventListener("click", () => {
          themaSetzen(b.dataset.thema);
          themaZeichnen();
        }));
    };
    themaZeichnen();
    root.querySelector("#k-kacheln").addEventListener("change", async (e) => {
      const an = e.target.checked;
      const res = await api("/api/me/karten", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({kacheln: an}),
      });
      if (!res.ok) { toast("Das ließ sich nicht speichern."); e.target.checked = !an; return; }
      if (state.me) state.me.kacheln = an;
      toast(an ? "Straßenkarte eingeschaltet."
               : "Es bleibt bei der Umrisskarte.");
    });
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
      zeigeToken(root);
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
    const alle = await res.json();
    const antraege = alle.filter((u) => u.pending);
    const users = alle.filter((u) => !u.pending);
    // Der letzte verbliebene Administrator darf sich nicht selbst entmachten -
    // dann gaebe es niemanden mehr, der Konten verwaltet.
    const letzterAdmin = users.filter((u) => u.is_admin && u.active).length <= 1;
    const antragsHtml = antraege.length ? `<div class="antraege">
      <h3>Zugangsanträge <span class="chip warn">${antraege.length}</span></h3>
      ${antraege.map((u) => `<div class="urow antrag" data-id="${u.id}">
        <div class="uinfo">
          <span class="uname">${esc(u.display_name)}</span>
          <span class="utag">@${esc(u.username)}</span>
          ${u.email ? `<a class="kontakt" href="mailto:${esc(u.email)}">${esc(u.email)}</a>` : ""}
          ${u.phone ? `<a class="kontakt" href="tel:${esc(u.phone)}">${esc(u.phone)}</a>` : ""}
          ${u.note ? `<span class="begruendung">${esc(u.note)}</span>` : ""}
        </div>
        <div class="uacts">
          <button class="act ok" data-act="approve">Freigeben</button>
          <button class="act del" data-act="reject">Ablehnen</button>
        </div>
      </div>`).join("")}
    </div>` : "";
    box.innerHTML = antragsHtml + users.map((u) => {
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
    }).join("") || (antragsHtml ? "" : '<p class="hint">Es gibt noch keine weiteren Konten.</p>');

    box.querySelectorAll(".act").forEach((btn) => btn.addEventListener("click", async () => {
      const row = btn.closest(".urow");
      const id = parseInt(row.dataset.id, 10);
      const user = alle.find((u) => u.id === id);
      const json = (body) => ({method: "PATCH",
                               headers: {"Content-Type": "application/json"},
                               body: JSON.stringify(body)});
      let ok = false;
      if (btn.dataset.act === "approve") {
        ok = await adminCall(`/api/users/${id}/approve`, {method: "POST"},
                             "Zugang freigegeben.");
      } else if (btn.dataset.act === "reject") {
        const antrag = alle.find((u) => u.id === id);
        if (!confirm(`Antrag von „${antrag.display_name}“ ablehnen?

`
                     + "Das Konto wird dabei entfernt."))
          return;
        ok = await adminCall(`/api/users/${id}`, {method: "DELETE"},
                             "Antrag abgelehnt.");
      } else if (btn.dataset.act === "pw") {
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

  async function zeigeToken(root) {
    const feld = root.querySelector("#ha-token");
    const herkunft = root.querySelector("#ha-herkunft");
    const res = await api("/api/token");
    if (!res.ok) { feld.value = "nicht verfügbar"; return; }
    const daten = await res.json();
    feld.value = daten.token;
    herkunft.textContent = daten.aus_option
      ? "Stammt aus der Add-on-Option api_token."
      : "Wurde beim ersten Start erzeugt und liegt in /data/api_token.txt. "
        + "Du kannst stattdessen die Add-on-Option api_token setzen.";
    root.querySelector("#ha-kopieren").addEventListener("click", async () => {
      feld.select();
      try {
        // Nur über HTTPS verfügbar - unter Ingress läuft es über http,
        // dann bleibt der markierte Text zum Kopieren von Hand.
        await navigator.clipboard.writeText(feld.value);
        toast("Token kopiert.");
      } catch (err) {
        toast("Bitte von Hand kopieren – der Text ist markiert.");
      }
    });
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
  let auswahlModus = false;
  const auswahl = new Set();

  // Zwei Zugaenge: aus der Seitenleiste ueber alle Unterhaltungen, aus dem
  // Chat nur diese eine. Auf dem Handy ist die Seitenleiste verdeckt, sobald
  // ein Chat offen ist - ohne den zweiten Knopf waere die Uebersicht dort
  // gar nicht erreichbar.
  // Der Medien-Knopf unten links ist entfallen. Der in der Kopfzeile oeffnet
  // denselben Dialog, und dort steht "Alle Unterhaltungen" zur Auswahl.
  $("btn-room-media").addEventListener("click", () => {
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
      <div class="media-leiste">
        <button class="act" id="md-auswahl">Auswählen</button>
        <span id="md-zahl" class="hint inline"></span>
        <span style="flex:1"></span>
        <button class="act" id="md-alle" hidden>Alle</button>
        <button class="act del" id="md-weg" hidden>Löschen</button>
      </div>
      <div id="md-body" class="media-body"><p class="hint">Wird geladen …</p></div>
      <div class="row"><button class="btn ghost" id="m-cancel">Schließen</button></div>`);
    root.querySelector(".modal").classList.add("wide");
    root.querySelector("#m-cancel").addEventListener("click", closeModal);
    root.querySelector("#md-room").addEventListener("change", (e) => {
      medienRaum = parseInt(e.target.value, 10);
      auswahl.clear();
      ladeMedien(root);
    });

    root.querySelector("#md-auswahl").addEventListener("click", () => {
      auswahlModus = !auswahlModus;
      auswahl.clear();
      auswahlAnzeigen(root);
      ladeMedien(root);
    });

    root.querySelector("#md-alle").addEventListener("click", () => {
      const kaesten = root.querySelectorAll("[data-id][data-loeschbar='1']");
      const alleDrin = [...kaesten].every((k) =>
        auswahl.has(parseInt(k.dataset.id, 10)));
      kaesten.forEach((k) => {
        const id = parseInt(k.dataset.id, 10);
        if (alleDrin) auswahl.delete(id); else auswahl.add(id);
        k.classList.toggle("gewaehlt", !alleDrin);
      });
      auswahlAnzeigen(root);
    });

    root.querySelector("#md-weg").addEventListener("click", async () => {
      if (!auswahl.size) return;
      if (!confirm(`${auswahl.size} ${auswahl.size === 1 ? "Datei" : "Dateien"} `
                   + "endgültig löschen?\n\n"
                   + "Sie verschwinden aus den Unterhaltungen und vom Server.")) return;
      const res = await api("/api/media/delete", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ids: [...auswahl]}),
      });
      const daten = await res.json().catch(() => ({}));
      if (!res.ok) { toast(daten.error || "Löschen fehlgeschlagen."); return; }
      toast(daten.abgelehnt
        ? `${daten.geloescht} gelöscht, ${daten.abgelehnt} nicht erlaubt.`
        : `${daten.geloescht} ${daten.geloescht === 1 ? "Datei" : "Dateien"} gelöscht.`);
      auswahl.clear();
      auswahlAnzeigen(root);
      ladeMedien(root);
      if (currentRoom) openRoom(currentRoom);
    });

    auswahlAnzeigen(root);
    ladeMedien(root);
  }

  function auswahlAnzeigen(root) {
    const knopf = root.querySelector("#md-auswahl");
    knopf.textContent = auswahlModus ? "Fertig" : "Auswählen";
    knopf.classList.toggle("ok", auswahlModus);
    root.querySelector("#md-alle").hidden = !auswahlModus;
    root.querySelector("#md-weg").hidden = !auswahlModus || !auswahl.size;
    root.querySelector("#md-zahl").textContent =
      auswahlModus && auswahl.size ? `${auswahl.size} ausgewählt` : "";
    root.querySelector("#md-body").classList.toggle("waehlbar", auswahlModus);
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
    const istBild = (m) => (m.mime || "").startsWith("image/");
    const istVideo = (m) => (m.mime || "").startsWith("video/");
    const bilder = alle.filter((m) => istBild(m) || istVideo(m));
    const dateien = alle.filter((m) => !istBild(m) && !istVideo(m));
    const raumName = (id) => roomById(id)?.name || "Unterhaltung";
    const herkunft = (m) => `${esc(m.author)} · ${medienRaum ? "" : esc(raumName(m.room_id)) + " · "}${shortTime(m.at)}`;

    box.innerHTML = `
      ${bilder.length ? `<div class="media-grid">${bilder.map((m) => `
        <figure class="media-cell ${auswahl.has(m.id) ? "gewaehlt" : ""}"
                data-id="${m.id}" data-loeschbar="${m.can_delete ? 1 : 0}">
          ${istVideo(m)
            ? `<video src="${BASE}/files/${m.id}" preload="metadata" controls
                      playsinline></video>`
            : `<a href="${BASE}/files/${m.id}" target="_blank" rel="noopener">
                <img src="${BASE}/files/${m.id}" alt="${esc(m.name)}" loading="lazy">
              </a>`}
          <figcaption>${herkunft(m)}</figcaption>
          ${m.can_delete ? '<button class="media-del" data-act="del" title="Löschen">✕</button>' : ""}
        </figure>`).join("")}</div>` : ""}
      ${dateien.length ? `<div class="media-files">${dateien.map((m) => `
        <div class="media-row ${auswahl.has(m.id) ? "gewaehlt" : ""}"
             data-id="${m.id}" data-loeschbar="${m.can_delete ? 1 : 0}">
          <a class="file-link" href="${BASE}/files/${m.id}?dl=1">📄 <span>${esc(m.name)}</span>
            <span class="fsize">${fileSize(m.size)}</span></a>
          <span class="media-meta">${herkunft(m)}</span>
          ${m.can_delete ? '<button class="act del" data-act="del">Löschen</button>' : ""}
        </div>`).join("")}</div>` : ""}`;

    // Im Auswahlmodus markiert ein Klick die Kachel, statt sie zu oeffnen.
    box.querySelectorAll("[data-id]").forEach((kasten) => {
      kasten.addEventListener("click", (e) => {
        if (!auswahlModus) return;
        e.preventDefault();
        e.stopPropagation();
        if (kasten.dataset.loeschbar !== "1") {
          toast("Fremde Dateien darf nur ein Administrator löschen.");
          return;
        }
        const id = parseInt(kasten.dataset.id, 10);
        if (auswahl.has(id)) auswahl.delete(id); else auswahl.add(id);
        kasten.classList.toggle("gewaehlt", auswahl.has(id));
        auswahlAnzeigen(root);
      });
    });

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
    if (!sichererKontext()) {
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
    state.me = data.me;
    state.online = new Set(data.online);
    state.live = data.live || [];
    state.stimmung = data.stimmung || [];
    state.freunde = data.freunde || [];
    state.freund_anfragen = data.freund_anfragen || 0;
    renderRooms();
    renderKarten();
    renderStimmung();
    pingPlanen();
    if (imAnruf()) anrufZeichnen();
    klingelZeigen();
    freundeMerker();
  }

  // Die Restzeiten laufen ab, ohne dass der Server etwas schickt. Einmal je
  // Minute neu zeichnen genuegt - abgelaufene Eintraege fallen dabei heraus.
  setInterval(() => { renderKarten(); renderStimmung(); }, 60000);


  document.querySelectorAll(".reiter-knopf").forEach((b) =>
    b.addEventListener("click", () => reiterSetzen(b.dataset.reiter)));
  reiterSetzen(aktiverReiter);

  themaSetzen(themaLesen());
  weltkarteLaden();
  terminLaden();
  tippsLaden();
  loadState().then(() => {
    const wanted = parseInt(new URLSearchParams(location.search).get("room"), 10);
    if (wanted && roomById(wanted)) openRoom(wanted);
  });
})();
