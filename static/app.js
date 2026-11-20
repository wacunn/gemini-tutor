// Gemini tutor front end: composer (type / pen / talk), live voice, and a canvas the tutor fills on the fly.

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const state = {
  name: "",
  ws: null,
  wsOpen: false,
  queue: [],
  started: false,
  startTime: 0,
  notes: { twelve: false, fifteen: false },
  micOn: false,
  phones: false,
  inputTarget: null,
  askPrompt: "",
  typing: { first: 0, backspaces: 0 },
  canvas: { tabs: {}, active: null },
};

// ---------------------------------------------------------------- setup

async function boot() {
  const st = await (await fetch("/api/state")).json();
  state.name = st.name || "";
  if (!st.name || !st.has_key) {
    $("setup").hidden = false;
    $("keyRow").hidden = !!st.has_key;
    $("sVoice").innerHTML = st.voices.map(([v, d]) => `<option value="${v}">${v} (${d})</option>`).join("");
    if (st.name) $("sName").value = st.name;
    $("setupForm").onsubmit = async (e) => {
      e.preventDefault();
      await fetch("/api/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: $("sName").value,
          grade: Number($("sGrade").value) || 3,
          parent_title: $("sParent").value,
          voice: $("sVoice").value,
          note: $("sNote").value,
          api_key: $("sKey").value || null,
        }),
      });
      location.reload();
    };
    return;
  }
  $("app").hidden = false;
  $("helloText").textContent = `Hi ${st.name}`;
  renderHeroStarters(st.projects || []);
  $("input").focus();
  fetch("/api/prewarm", { method: "POST" }).catch(() => {});
}

function renderHeroStarters(savedProjects) {
  const box = $("heroStarters");
  if (!box) return;
  let html = "";
  if (savedProjects.length) {
    html += `<div><div class="starter-group-label">Continue Saved Book</div><div class="starter-row">` +
      savedProjects.map((p) =>
        `<div class="starter-card" data-open-proj="${esc(p.id)}"><div class="st-title">${esc(p.title)}</div><div class="st-sub">${p.panel_count} panel(s) saved · Click to continue (or <a href="${esc(p.pdf_url)}" target="_blank" onclick="event.stopPropagation()" style="color:var(--blue)">Download PDF</a>)</div></div>`
      ).join("") + `</div></div>`;
  }
  html += `<div><div class="starter-group-label">Long-Term Books (Save Progress &amp; Export PDF)</div><div class="starter-row">
    <button type="button" class="starter-card" data-tap="Start a Full Comic Book (Save & PDF)"><div class="st-title">Full Comic Book (PDF Book)</div><div class="st-sub">Plan Beginning → Middle → End, then zoom in up to 100 panels with dialogue</div></button>
    <button type="button" class="starter-card" data-tap="Illustrated Monster/Invention Codex (PDF)"><div class="st-title">Illustrated Codex (PDF Book)</div><div class="st-sub">Multi-session field guide of creatures, bosses, or contraptions</div></button>
  </div></div>
  <div><div class="starter-group-label">Quick Today (~10 Min)</div><div class="starter-row">
    <button type="button" class="starter-card" data-tap="Quick 3-Panel Strip (10 min)"><div class="st-title">Quick 3-Panel Strip</div><div class="st-sub">Fast setup, twist, and payoff</div></button>
    <button type="button" class="starter-card" data-tap="Build a Live Mini-Game (10 min)"><div class="st-title">Build a Live Mini-Game</div><div class="st-sub">Code a playable sentence-driven game on the spot</div></button>
  </div></div>`;
  box.innerHTML = html;
  box.querySelectorAll("[data-open-proj]").forEach((el) => {
    el.onclick = () => {
      begin();
      addKid(`Continue “${esc(el.querySelector(".st-title")?.textContent || "Book")}”`);
      send({ type: "open_project", id: el.dataset.openProj });
    };
  });
  box.querySelectorAll("[data-tap]").forEach((el) => {
    el.onclick = () => {
      begin();
      addKid(esc(el.querySelector(".st-title")?.textContent || el.dataset.tap));
      send({ type: "tap", value: el.dataset.tap, prompt: "Starter menu" });
    };
  });
}

// ---------------------------------------------------------------- socket

function connect() {
  if (state.ws) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/live`);
  ws.binaryType = "arraybuffer";
  state.ws = ws;
  ws.onopen = () => {
    state.wsOpen = true;
    state.queue.splice(0).forEach((m) => ws.send(m));
  };
  ws.onmessage = (ev) => {
    if (ev.data instanceof ArrayBuffer) return playPcm(ev.data);
    handle(JSON.parse(ev.data));
  };
  ws.onclose = () => {
    state.ws = null;
    state.wsOpen = false;
    if (state.started && !state.ended) {
      setTimeout(() => {
        if (!state.ws && !state.ended) connect();
      }, 1500);
    }
  };
}

function send(obj) {
  const msg = typeof obj === "string" || obj instanceof ArrayBuffer ? obj : JSON.stringify(obj);
  if (state.wsOpen) state.ws.send(msg);
  else if (!(obj instanceof ArrayBuffer)) state.queue.push(msg);
}

function begin() {
  ensureAudio();
  connect();
  if (!state.started) {
    state.started = true;
    state.startTime = Date.now();
    document.body.classList.remove("fresh");
    $("endBtn").hidden = false;
    setInterval(tick, 1000);
  }
}

function tick() {
  const s = Math.floor((Date.now() - state.startTime) / 1000);
  $("timer").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  if (s >= 720 && !state.notes.twelve) {
    state.notes.twelve = true;
    send({ type: "app_note", text: "About 3 minutes left. Start heading toward a good stopping point and leave a reason to come back." });
  }
  if (s >= 900 && !state.notes.fifteen) {
    state.notes.fifteen = true;
    send({ type: "app_note", text: "15 minutes are up. Wrap up in a sentence or two and save anything worth keeping." });
  }
}

// ---------------------------------------------------------------- audio out

let playCtx = null;
let nextTime = 0;
const sources = new Set();

function ensureAudio() {
  if (!playCtx) {
    playCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
  }
  if (playCtx.state === "suspended") playCtx.resume();
}

function playPcm(buf) {
  if (!playCtx || buf.byteLength < 2) return;
  const i16 = new Int16Array(buf, 0, Math.floor(buf.byteLength / 2));
  const f32 = new Float32Array(i16.length);
  for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;
  const ab = playCtx.createBuffer(1, f32.length, 24000);
  ab.copyToChannel(f32, 0);
  const src = playCtx.createBufferSource();
  src.buffer = ab;
  src.connect(playCtx.destination);
  const t = Math.max(playCtx.currentTime + 0.03, nextTime);
  src.start(t);
  nextTime = t + ab.duration;
  sources.add(src);
  src.onended = () => sources.delete(src);
}

function stopPlayback() {
  sources.forEach((s) => {
    try { s.stop(); } catch (_) {}
  });
  sources.clear();
  nextTime = playCtx ? playCtx.currentTime : 0;
}

const tutorAudible = () => playCtx && playCtx.currentTime < nextTime + 0.25;

// ---------------------------------------------------------------- mic

let micCtx = null, micStream = null, micNode = null;

async function micStart() {
  begin();
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
  } catch (e) {
    toast("Microphone isn't available here. On an iPad over Wi-Fi, typing and the pen still work.");
    return;
  }
  micCtx = new (window.AudioContext || window.webkitAudioContext)();
  await micCtx.audioWorklet.addModule("/static/mic-worklet.js");
  const src = micCtx.createMediaStreamSource(micStream);
  micNode = new AudioWorkletNode(micCtx, "mic-processor");
  micNode.port.onmessage = (e) => {
    if (!state.micOn) return;
    if (!state.phones && tutorAudible()) return; // half-duplex unless headphones
    send(e.data.pcm);
  };
  const mute = micCtx.createGain();
  mute.gain.value = 0;
  src.connect(micNode).connect(mute).connect(micCtx.destination);
  state.micOn = true;
  $("micBtn").classList.add("on");
  send({ type: "mic_started" });
}

function micStop() {
  state.micOn = false;
  $("micBtn").classList.remove("on");
  try { micStream && micStream.getTracks().forEach((t) => t.stop()); } catch (_) {}
  try { micCtx && micCtx.close(); } catch (_) {}
  micStream = micCtx = micNode = null;
  send({ type: "mic_paused" });
}

setInterval(() => {
  const g = $("glow");
  if (!g) return;
  g.classList.toggle("speaking", !!tutorAudible());
  g.classList.toggle("listening", state.micOn && !tutorAudible());
  document.querySelectorAll(".msg.tutor.speaking").forEach((m) => {
    if (!tutorAudible()) m.classList.remove("speaking");
  });
}, 120);

// ---------------------------------------------------------------- composer

const input = $("input");
function coverWordCard() {
  const wc = document.querySelector("#item-word .word-card");
  if (wc && !wc.classList.contains("covered")) {
    wc.classList.add("covered");
    const st = wc.querySelector(".ccc-status");
    if (st) st.textContent = "Covered — write from memory";
  }
}
input.addEventListener("input", () => {
  coverWordCard();
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 200) + "px";
  $("sendBtn").hidden = !input.value.trim();
  $("micBtn").hidden = !!input.value.trim();
});
input.addEventListener("keydown", (e) => {
  if (!state.typing.first && e.key.length === 1) state.typing.first = performance.now();
  if (e.key === "Backspace") state.typing.backspaces++;
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendText();
  }
});
$("sendBtn").onclick = sendText;
$("micBtn").onclick = () => (state.micOn ? micStop() : micStart());
$("penBtn").onclick = () => openPen(state.askPrompt || "Write here");
$("phonesBtn").onclick = () => {
  state.phones = !state.phones;
  $("phonesBtn").setAttribute("aria-pressed", String(state.phones));
};
$("endBtn").onclick = endSession;

function sendText() {
  const text = input.value.trim();
  if (!text) return;
  begin();
  const ms = state.typing.first ? Math.round(performance.now() - state.typing.first) : 0;
  addKid(esc(text));
  send({ type: "text", text, ms, backspaces: state.typing.backspaces });
  input.value = "";
  input.style.height = "auto";
  $("sendBtn").hidden = true;
  $("micBtn").hidden = false;
  state.typing = { first: 0, backspaces: 0 };
  clearAsk();
}

function setAsk(text, mode) {
  state.askPrompt = text || "";
  $("ask").hidden = !text;
  $("askText").textContent = text || "";
  const c = $("composer");
  c.classList.toggle("wants", !!mode);
  ["penBtn", "micBtn"].forEach((id) => $(id).classList.remove("highlight"));
  if (mode === "pen") $("penBtn").classList.add("highlight");
  if (mode === "talk") $("micBtn").classList.add("highlight");
}

function clearAsk() {
  setAsk("", null);
}

// ---------------------------------------------------------------- pen

const pen = { ctx: null, drawing: false, strokes: 0, prompt: "" };

function openPen(prompt) {
  begin();
  coverWordCard();
  $("penSheet").hidden = false;
  $("penPrompt").textContent = prompt || "Write here";
  pen.prompt = prompt || "";
  const c = $("penCanvas");
  const r = c.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  c.width = r.width * dpr;
  c.height = r.height * dpr;
  pen.ctx = c.getContext("2d");
  pen.ctx.scale(dpr, dpr);
  pen.ctx.lineCap = "round";
  pen.ctx.lineJoin = "round";
  pen.ctx.strokeStyle = "#1f1f1f";
  pen.strokes = 0;
}

(function wirePen() {
  const c = $("penCanvas");
  const pos = (e) => {
    const r = c.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top, p: e.pressure > 0 ? e.pressure : 0.5 };
  };
  c.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    c.setPointerCapture(e.pointerId);
    pen.drawing = true;
    pen.strokes++;
    const p = pos(e);
    pen.ctx.lineWidth = 2.5 + p.p * 4;
    pen.ctx.beginPath();
    pen.ctx.moveTo(p.x, p.y);
  });
  c.addEventListener("pointermove", (e) => {
    if (!pen.drawing) return;
    const p = pos(e);
    pen.ctx.lineWidth = 2.5 + p.p * 4;
    pen.ctx.lineTo(p.x, p.y);
    pen.ctx.stroke();
  });
  const end = () => (pen.drawing = false);
  c.addEventListener("pointerup", end);
  c.addEventListener("pointercancel", end);
  $("penClear").onclick = () => {
    pen.ctx.clearRect(0, 0, c.width, c.height);
    pen.strokes = 0;
  };
  $("penCancel").onclick = () => ($("penSheet").hidden = true);
  $("penDone").onclick = () => {
    if (!pen.strokes) return ($("penSheet").hidden = true);
    const out = document.createElement("canvas");
    out.width = c.width;
    out.height = c.height;
    const o = out.getContext("2d");
    o.fillStyle = "#ffffff";
    o.fillRect(0, 0, out.width, out.height);
    o.drawImage(c, 0, 0);
    const png = out.toDataURL("image/png");
    $("penSheet").hidden = true;
    const ph = addKid(`<img src="${png}" alt="handwriting"><span class="muted">Reading…</span>`);
    ph.dataset.pending = "pen";
    send({ type: "pen", png_b64: png, prompt: pen.prompt });
    clearAsk();
  };
})();

// ---------------------------------------------------------------- stream

const stream = $("stream");

function scrollDown() {
  const c = $("convo");
  requestAnimationFrame(() => (c.scrollTop = c.scrollHeight));
}

function addKid(html, id) {
  const el = document.createElement("div");
  el.className = "msg kid";
  if (id) el.id = id;
  el.innerHTML = `<div class="bubble">${html}</div>`;
  stream.appendChild(el);
  scrollDown();
  return el;
}

function upsertTutor(turn, text) {
  let el = document.getElementById("tutor-" + turn);
  if (!el) {
    el = document.createElement("div");
    el.className = "msg tutor speaking";
    el.id = "tutor-" + turn;
    el.innerHTML = `<svg class="spark"><use href="#spark"/></svg><div class="text"></div>`;
    stream.appendChild(el);
  }
  el.querySelector(".text").textContent = text;
  scrollDown();
}

function upsertKidSpoken(turn, text) {
  let el = document.getElementById("kid-" + turn);
  if (!el) {
    el = addKid("", "kid-" + turn);
    el.querySelector(".bubble").classList.add("spoken");
  }
  el.querySelector(".bubble").textContent = text;
  scrollDown();
}

function upsertInline(id, html, cls = "") {
  let el = document.getElementById("item-" + id);
  if (!el) {
    el = document.createElement("div");
    el.id = "item-" + id;
    stream.appendChild(el);
  }
  el.className = "item " + cls;
  el.innerHTML = html;
  scrollDown();
  return el;
}

function renderItem(it) {
  switch (it.kind) {
    case "image": {
      const art = it.status === "done" ? `<img src="${esc(it.src)}" alt="">` : it.status === "failed" ? `<div class="cap">Couldn't draw that one.</div>` : `<div class="shimmer"></div>`;
      upsertInline(it.id, `<div class="image-item">${art}${it.caption ? `<div class="cap">${esc(it.caption)}</div>` : ""}</div>`);
      break;
    }
    case "card":
      upsertInline(it.id, `<div class="card">${it.title ? `<h3>${esc(it.title)}</h3>` : ""}<div class="card-text">${esc(it.text)}</div></div>`);
      break;
    case "choices": {
      const el = upsertInline(it.id, `<div class="choices">${it.prompt ? `<div class="prompt">${esc(it.prompt)}</div>` : ""}${it.options.map((o) => `<button class="chip">${esc(o)}</button>`).join("")}</div>`);
      el.querySelectorAll(".chip").forEach((b) => {
        b.onclick = () => {
          el.querySelectorAll(".chip").forEach((x) => (x.disabled = true));
          b.classList.add("picked");
          begin();
          send({ type: "tap", value: b.textContent, prompt: it.prompt });
        };
      });
      break;
    }
    case "word": {
      const el = upsertInline("word", `<div class="word-card"><div class="parts">${it.parts.map((p) => `<span class="part">${esc(p)}</span>`).join('<span class="plus">+</span>')}</div>${it.note ? `<div class="note">${esc(it.note)}</div>` : ""}<div class="ccc-row"><button class="ccc-btn" type="button">Cover &amp; write</button><span class="ccc-status muted" style="font-size:.85rem">Covers when you start typing</span></div></div>`);
      const btn = el.querySelector(".ccc-btn");
      if (btn) btn.onclick = () => { coverWordCard(); input.focus(); };
      setTimeout(coverWordCard, 6500);
      break;
    }
    case "saved":
      upsertInline(it.id, `<div class="saved"><svg style="width:20px;height:20px"><use href="#spark"/></svg><span>Saved “${esc(it.title)}”</span><a href="${esc(it.url)}" target="_blank">Open</a> · <a href="/api/piece/${esc(it.id)}/pdf" target="_blank">Download PDF</a></div>`);
      break;
    case "book_project":
      canvasPane("book", "Book · PDF", renderBookProject(it));
      break;
    case "comic":
      canvasPane("comic", "Comic", renderComic(it));
      break;
    case "page":
      canvasPane("page", "Page", `<div class="page">${it.segments.map((s) => `<p class="${s.author === "kid" ? "kid" : ""}">${esc(s.text)}</p>`).join("")}</div>`);
      break;
    case "activity": {
      const pane = canvasPane("activity", it.title || "Game", "");
      const frame = document.createElement("iframe");
      frame.className = "activity-frame";
      frame.setAttribute("sandbox", "allow-scripts");
      frame.srcdoc = it.html;
      frame.id = "activityFrame";
      pane.innerHTML = "";
      pane.appendChild(frame);
      setTimeout(() => frame.focus(), 300);
      break;
    }
  }
}

function renderBookProject(b) {
  const sp = b.spine || {};
  const hasSpine = b.proj_kind === "epic_graphic_novel" || sp.beginning || sp.middle || sp.end;
  const spineHtml = hasSpine
    ? `<div class="spine-box">
        <div class="spine-beat"><strong>Act I · Beginning:</strong> ${sp.beginning ? esc(sp.beginning) : '<span class="muted">Mapping now…</span>'}</div>
        <div class="spine-beat"><strong>Act II · Middle (But/When):</strong> ${sp.middle ? esc(sp.middle) : '<span class="muted">Up next…</span>'}</div>
        <div class="spine-beat"><strong>Act III · End (So/Finally):</strong> ${sp.end ? esc(sp.end) : '<span class="muted">Up next…</span>'}</div>
      </div>`
    : "";

  const chHtml = (b.chapters || [])
    .map((ch) => {
      const pList = ch.panels || [];
      if (!pList.length) return "";
      const cells = pList
        .map((p) => {
          const art = p.src ? `<img src="${esc(p.src)}" alt="">` : "";
          const cls = p.status === "drawing" ? "art drawing" : "art";
          const bubs = (p.dialogue || [])
            .map((d) => `<div class="bubble-overlay">${d.speaker ? `<strong>${esc(d.speaker)}:</strong> ` : ""}${esc(d.text)}</div>`)
            .join("");
          return `<div class="panel"><div class="${cls}"><span class="num" style="background:#111;color:#fff;padding:2px 8px;border-radius:4px;font-size:.95rem;top:6px;left:6px">${p.number || ""}</span>${bubs ? `<div class="bubbles">${bubs}</div>` : ""}${art}</div><div class="caption">${esc(p.caption || "")}</div></div>`;
        })
        .join("");
      return `<div class="ch-label">${esc(ch.title || "Chapter " + ch.number)}</div><div class="comic-grid">${cells}</div>`;
    })
    .join("");

  return `<div class="book-head">
      <div><div class="comic-title" style="margin:0">${esc(b.title || "Untitled Book")}</div>
      <div class="muted" style="font-size:.86rem">${b.panel_count || 0} panel(s) auto-saved · Progresses across sessions</div></div>
      <div class="book-actions">
        <a class="text-btn" href="${esc(b.web_url)}" target="_blank">Web view</a>
        <a class="btn-primary" href="${esc(b.pdf_url)}" target="_blank">Download PDF</a>
      </div>
    </div>
    ${spineHtml}
    ${chHtml || '<div class="muted" style="padding:12px 2px">Panels will appear here as soon as your Story Spine locks in. You can download an updated PDF at any stage!</div>'}`;
}

function renderComic(c) {
  const panels = c.panels
    .map((p, i) => {
      const art = p.src ? `<img src="${esc(p.src)}" alt="">` : "";
      const cls = p.status === "drawing" ? "art drawing" : "art";
      return `<div class="panel"><div class="${cls}">${art || `<span class="num">${i + 1}</span>`}</div><div class="caption">${esc(p.caption || "")}</div></div>`;
    })
    .join("");
  return `<div class="comic-title">${esc(c.title || "")}</div><div class="comic-grid">${panels}</div>`;
}

// ---------------------------------------------------------------- canvas (comic / page / game)

function canvasPane(key, label, html) {
  $("canvas").hidden = false;
  let pane = state.canvas.tabs[key];
  if (!pane) {
    pane = document.createElement("div");
    pane.className = "canvas-pane";
    $("canvasBody").appendChild(pane);
    state.canvas.tabs[key] = pane;
    const b = document.createElement("button");
    b.textContent = label;
    b.dataset.key = key;
    b.onclick = () => showTab(key);
    $("canvasTabs").appendChild(b);
  } else {
    const b = $("canvasTabs").querySelector(`[data-key="${key}"]`);
    if (b) b.textContent = label;
  }
  if (html) pane.innerHTML = html;
  showTab(key);
  return pane;
}

function showTab(key) {
  state.canvas.active = key;
  Object.entries(state.canvas.tabs).forEach(([k, p]) => (p.hidden = k !== key));
  $("canvasTabs").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.key === key));
}

function removeCanvas(key) {
  const p = state.canvas.tabs[key];
  if (!p) return;
  p.remove();
  delete state.canvas.tabs[key];
  const b = $("canvasTabs").querySelector(`[data-key="${key}"]`);
  if (b) b.remove();
  const rest = Object.keys(state.canvas.tabs);
  if (rest.length) showTab(rest[rest.length - 1]);
  else $("canvas").hidden = true;
}

window.addEventListener("message", (e) => {
  const frame = $("activityFrame");
  if (!frame || e.source !== frame.contentWindow) return;
  const m = e.data;
  if (!m || !m.__tutor) return;
  if (m.type === "activity_event" || m.type === "activity_error") send({ type: m.type, data: m.data });
});

// ---------------------------------------------------------------- server events

function handle(m) {
  switch (m.type) {
    case "ready":
      break;
    case "tutor_caption":
      upsertTutor(m.turn, m.text);
      break;
    case "kid_caption":
      upsertKidSpoken(m.turn, m.text);
      break;
    case "interrupted":
      stopPlayback();
      break;
    case "turn_complete":
      break;
    case "item":
      renderItem(m.item);
      break;
    case "remove":
      if (m.id === "activity") removeCanvas("activity");
      else document.getElementById("item-" + m.id)?.remove();
      break;
    case "cover_word":
      coverWordCard();
      break;
    case "goal":
      if (m.text) {
        $("goalPill").hidden = false;
        $("goalPill").textContent = m.text;
      }
      break;
    case "input":
      setAsk(m.prompt, m.mode);
      if (typeof m.prefill === "string") {
        input.value = m.prefill;
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 200) + "px";
        $("sendBtn").hidden = !input.value.trim();
        $("micBtn").hidden = !!input.value.trim();
        input.setSelectionRange(input.value.length, input.value.length);
      }
      if (m.mode === "type") input.focus();
      if (m.mode === "pen") openPen(m.prompt);
      break;
    case "kid_pen": {
      const ph = stream.querySelector('[data-pending="pen"]');
      const html = `<img src="${esc(m.image)}" alt="">${esc(m.text || "")}`;
      if (ph) {
        ph.querySelector(".bubble").innerHTML = html;
        delete ph.dataset.pending;
      } else addKid(html);
      break;
    }
    case "building":
      $("building").hidden = false;
      $("buildingText").textContent = `Making “${m.title}”`;
      break;
    case "build_progress":
      break;
    case "build_done":
      $("building").hidden = true;
      break;
    case "to_activity": {
      const f = $("activityFrame");
      if (f) f.contentWindow.postMessage({ __tutor: true, type: "to_activity", data: m.data }, "*");
      break;
    }
    case "status":
      toast(m.message);
      break;
    case "error":
      toast(m.message);
      break;
  }
}

function toast(text) {
  const el = document.createElement("div");
  el.className = "msg tutor";
  el.innerHTML = `<svg class="spark"><use href="#spark"/></svg><div class="text" style="color:var(--muted)">${esc(text)}</div>`;
  stream.appendChild(el);
  scrollDown();
}

function endSession() {
  state.ended = true;
  send({ type: "end" });
  if (state.micOn) micStop();
  stopPlayback();
  setTimeout(() => state.ws && state.ws.close(), 300);
  toast("Saved. See you next time.");
  $("endBtn").hidden = true;
}

boot();
