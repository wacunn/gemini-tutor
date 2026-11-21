// Gemini tutor front end: composer (type / pen / talk), live voice, and a canvas the tutor fills on the fly.

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const IS_SANDBOX = new URLSearchParams(location.search).get("sandbox") === "1";

const state = {
  name: "",
  sandbox: IS_SANDBOX,
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
  styleDrawerOpen: null,
  lastServerEpoch: 0,
  micOneShot: false,
  heardKidSpeech: false,
};

// ---------------------------------------------------------------- setup

async function boot() {
  const st = await (await fetch(`/api/state?sandbox=${IS_SANDBOX ? 1 : 0}`)).json();
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
  if (IS_SANDBOX) {
    $("sandboxBanner").hidden = false;
    $("sandboxLink").hidden = true;
    $("exitSandboxLink").hidden = false;
    $("helloText").textContent = "Parent Sandbox";
  } else {
    $("helloText").textContent = `Hi ${st.name}`;
  }
  renderHeroStarters(st.projects || []);
  wireSidebar();
  $("input").focus();
}

function toggleSidebar(open) {
  const sb = $("sidebar");
  const bd = $("sidebarBackdrop");
  const show = typeof open === "boolean" ? open : !sb.classList.contains("open");
  sb.classList.toggle("open", show);
  sb.setAttribute("aria-hidden", String(!show));
  bd.hidden = !show;
  if (show) refreshSidebar();
}

function sideItemHtml(p) {
  const meta = p.progress_label || `${p.panel_count || 0}p`;
  return `<div class="side-item" data-open-proj="${esc(p.id)}">
    <div class="side-item-main">
      <div class="side-item-title">${esc(p.title)}</div>
      <div class="side-item-sub">${esc(meta)}</div>
    </div>
    <div class="side-item-acts" onclick="event.stopPropagation()">
      <a href="${esc(p.pdf_url)}" target="_blank" title="Download PDF">PDF</a>
      <button type="button" data-ren-proj="${esc(p.id)}" data-cur-title="${esc(p.title)}" title="Rename">✎</button>
      <button type="button" class="del" data-del-proj="${esc(p.id)}" data-cur-title="${esc(p.title)}" title="Delete">×</button>
    </div>
  </div>`;
}

function sideActHtml(a) {
  return `<div class="side-item" data-open-act="${esc(a.id)}">
    <div class="side-item-main">
      <div class="side-item-title">${esc(a.title || "Mini-Game")}</div>
      <div class="side-item-sub">Mini-game</div>
    </div>
    <div class="side-item-acts" onclick="event.stopPropagation()">
      <button type="button" class="del" data-del-act="${esc(a.id)}" data-cur-title="${esc(a.title || "Game")}" title="Delete">×</button>
    </div>
  </div>`;
}

async function refreshSidebar() {
  const lib = await (await fetch(`/api/library?sandbox=${IS_SANDBOX ? 1 : 0}`)).json();
  const listEl = $("sideList");
  const rows = [
    ...(lib.projects || []).map(sideItemHtml),
    ...(lib.activities || []).map(sideActHtml),
  ];
  listEl.innerHTML = rows.length ? rows.join("") : '<div class="muted" style="padding:8px 14px;font-size:.86rem">No saved books yet.</div>';
  listEl.querySelectorAll("[data-open-proj]").forEach((el) => {
    el.onclick = () => {
      toggleSidebar(false);
      begin();
      addKid(`Open “${esc(el.querySelector(".side-item-title")?.textContent || "Book")}”`);
      send({ type: "open_project", id: el.dataset.openProj });
    };
  });
  listEl.querySelectorAll("[data-open-act]").forEach((el) => {
    el.onclick = () => {
      toggleSidebar(false);
      begin();
      addKid(`Open “${esc(el.querySelector(".side-item-title")?.textContent || "Game")}”`);
      send({ type: "open_activity_saved", id: el.dataset.openAct });
    };
  });
  listEl.querySelectorAll("[data-ren-proj]").forEach((btn) => {
    btn.onclick = async () => {
      const next = prompt("New title:", btn.dataset.curTitle || "");
      if (!next || !next.trim()) return;
      await fetch(`/api/project/${encodeURIComponent(btn.dataset.renProj)}/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: next.trim() }),
      });
      if (state.wsOpen) send({ type: "rename_project", id: btn.dataset.renProj, title: next.trim() });
      refreshSidebar();
      refreshHeroShelf();
    };
  });
  listEl.querySelectorAll("[data-del-proj]").forEach((btn) => {
    btn.onclick = async () => {
      if (!confirm(`Delete “${btn.dataset.curTitle || "this book"}”?`)) return;
      await fetch(`/api/project/${encodeURIComponent(btn.dataset.delProj)}?sandbox=${IS_SANDBOX ? 1 : 0}`, { method: "DELETE" });
      refreshSidebar();
      refreshHeroShelf();
    };
  });
  listEl.querySelectorAll("[data-del-act]").forEach((btn) => {
    btn.onclick = async () => {
      if (!confirm(`Delete “${btn.dataset.curTitle || "Game"}”?`)) return;
      await fetch(`/api/activity/${encodeURIComponent(btn.dataset.delAct)}?sandbox=${IS_SANDBOX ? 1 : 0}`, { method: "DELETE" });
      refreshSidebar();
    };
  });
}

async function refreshHeroShelf() {
  const st = await (await fetch(`/api/state?sandbox=${IS_SANDBOX ? 1 : 0}`)).json();
  renderHeroStarters(st.projects || []);
}

function renderHeroStarters(savedProjects) {
  const box = $("heroStarters");
  if (!box) return;
  const contPill = savedProjects.length
    ? `<button type="button" class="hero-pill" data-open-hero="${esc(savedProjects[0].id)}">Continue “${esc(savedProjects[0].title)}”</button>`
    : "";
  box.innerHTML = `${contPill}
    <button type="button" class="hero-pill" data-new-kind="epic_graphic_novel">Comic book</button>
    <button type="button" class="hero-pill" data-new-kind="epic_codex">Fact codex</button>
    <button type="button" class="hero-pill" data-new-kind="medium_pitch">Persuasive pitch</button>
    <button type="button" class="hero-pill" data-new-kind="quick_game">Mini-game</button>`;
  const heroOpen = box.querySelector("[data-open-hero]");
  if (heroOpen) {
    heroOpen.onclick = () => {
      begin();
      addKid(esc(heroOpen.textContent));
      send({ type: "open_project", id: heroOpen.dataset.openHero });
    };
  }
  box.querySelectorAll("[data-new-kind]").forEach((el) => {
    el.onclick = () => {
      begin();
      addKid(esc(el.textContent));
      send({ type: "new_project", kind: el.dataset.newKind, title: "" });
    };
  });
}

function wireSidebar() {
  $("menuBtn").onclick = () => toggleSidebar();
  $("sideClose").onclick = () => toggleSidebar(false);
  $("sidebarBackdrop").onclick = () => toggleSidebar(false);
  $("sideNewList").querySelectorAll("[data-new-kind]").forEach((btn) => {
    btn.onclick = () => {
      toggleSidebar(false);
      begin();
      addKid(esc(btn.textContent.replace(/^\+\s*/, "")));
      send({ type: "new_project", kind: btn.dataset.newKind, title: "" });
    };
  });
}

// ---------------------------------------------------------------- socket

function connect() {
  if (state.ws) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/live${IS_SANDBOX ? "?test=1" : ""}`);
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
  state.micOneShot = false;
  state.heardKidSpeech = false;
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
let peekTimer = null;
function coverWordCard() {
  const wc = document.querySelector("#item-word .word-card");
  if (wc && !wc.classList.contains("covered")) {
    wc.classList.add("covered");
    const btn = wc.querySelector(".ccc-btn");
    if (btn) btn.textContent = "Peek (3s)";
    const st = wc.querySelector(".ccc-status");
    if (st) st.textContent = "Covered — fix it in your sentence below";
  }
}
function toggleWordCardPeek() {
  const wc = document.querySelector("#item-word .word-card");
  if (!wc) return;
  if (!wc.classList.contains("covered")) {
    coverWordCard();
    input.focus();
    return;
  }
  wc.classList.remove("covered");
  const btn = wc.querySelector(".ccc-btn");
  if (btn) btn.textContent = "Cover & write";
  const st = wc.querySelector(".ccc-status");
  if (st) st.textContent = "Peeking (3s)…";
  clearTimeout(peekTimer);
  peekTimer = setTimeout(coverWordCard, 3200);
  input.focus();
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
  document.getElementById("item-starters")?.remove();
  send({ type: "text", text, ms, backspaces: state.typing.backspaces });
  input.value = "";
  input.style.height = "auto";
  $("sendBtn").hidden = true;
  $("micBtn").hidden = false;
  state.typing = { first: 0, backspaces: 0 };
  setAsk("Reading your line…", null);
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

const pen = { ctx: null, gctx: null, drawing: false, strokes: 0, prompt: "", tool: "pen", spot: null, w: 0, h: 0, dpr: 1 };

function setPenTool(tool) {
  pen.tool = tool === "erase" ? "erase" : "pen";
  $("penDrawBtn")?.classList.toggle("active-tool", pen.tool === "pen");
  $("penEraseBtn")?.classList.toggle("active-tool", pen.tool === "erase");
  const c = $("penCanvas");
  if (c) c.style.cursor = pen.tool === "erase" ? "cell" : "crosshair";
}

function drawPrimaryLinesOn(ctx, w, h, spot) {
  ctx.save();
  ctx.fillStyle = "#fbfaf7";
  ctx.fillRect(0, 0, w, h);

  // Subtle pink left margin rule like real primary composition paper
  const marginX = 56;
  ctx.strokeStyle = "rgba(226, 145, 155, 0.45)";
  ctx.lineWidth = 1.2;
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(marginX, 0);
  ctx.lineTo(marginX, h);
  ctx.stroke();

  const rows = [
    { top: h * 0.10, bot: h * 0.46 },
    { top: h * 0.56, bot: h * 0.92 },
  ];
  ctx.font = "500 11px 'Google Sans Text', -apple-system, sans-serif";
  ctx.textBaseline = "middle";

  for (const r of rows) {
    const band = r.bot - r.top;
    const skyY = r.top;
    const fenceY = r.top + band * 0.36;
    const grassY = r.top + band * 0.74;
    const wormY = r.bot;

    // Sky line (top solid blue)
    ctx.setLineDash([]);
    ctx.strokeStyle = "#5a9be6";
    ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.moveTo(marginX, skyY); ctx.lineTo(w - 14, skyY); ctx.stroke();
    ctx.fillStyle = "#3b78c2";
    ctx.fillText("Sky", 8, skyY);

    // Fence line (middle dashed blue)
    ctx.setLineDash([7, 6]);
    ctx.strokeStyle = "#7ab0ec";
    ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(marginX, fenceY); ctx.lineTo(w - 14, fenceY); ctx.stroke();
    ctx.fillStyle = "#568ac9";
    ctx.fillText("Fence", 8, fenceY);

    // Grass line (solid green baseline)
    ctx.setLineDash([]);
    ctx.strokeStyle = "#3d9b5c";
    ctx.lineWidth = 2.1;
    ctx.beginPath(); ctx.moveTo(marginX, grassY); ctx.lineTo(w - 14, grassY); ctx.stroke();
    ctx.fillStyle = "#2b7a45";
    ctx.fillText("Grass", 8, grassY);

    // Worm line (descender brown line)
    ctx.strokeStyle = "#cfa07a";
    ctx.lineWidth = 1.3;
    ctx.beginPath(); ctx.moveTo(marginX, wormY); ctx.lineTo(w - 14, wormY); ctx.stroke();
    ctx.fillStyle = "#a36c42";
    ctx.fillText("Worm", 8, wormY);
  }

  // Optional single-letter confusion spotlight (shown to child, never exported to vision PNG)
  if (spot && typeof spot.x === "number" && typeof spot.y === "number") {
    const sx = Math.max(marginX + 20, Math.min(w - 28, spot.x * w));
    const sy = Math.max(26, Math.min(h - 26, spot.y * h));
    ctx.fillStyle = "rgba(253, 214, 99, 0.25)";
    ctx.strokeStyle = "#d97706";
    ctx.lineWidth = 2.2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.arc(sx, sy, 28, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    if (spot.label) {
      ctx.setLineDash([]);
      ctx.font = "600 12px 'Google Sans Text', sans-serif";
      const tw = ctx.measureText(spot.label).width + 12;
      const bx = Math.max(marginX + 4, Math.min(w - tw - 6, sx - tw / 2));
      const by = Math.max(6, sy - 48);
      ctx.fillStyle = "#fef3c7";
      ctx.strokeStyle = "#d97706";
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.roundRect(bx, by, tw, 20, 6);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#92400e";
      ctx.fillText(spot.label, bx + 6, by + 10);
    }
  }
  ctx.restore();
}

function openPen(prompt, opts = {}) {
  begin();
  coverWordCard();
  const keep = !!(opts && opts.keepStrokes && pen.strokes > 0);
  let savedBitmap = null;
  const c = $("penCanvas");
  const gc = $("penGuideCanvas");
  if (keep && c.width > 0 && c.height > 0) {
    savedBitmap = document.createElement("canvas");
    savedBitmap.width = c.width;
    savedBitmap.height = c.height;
    savedBitmap.getContext("2d").drawImage(c, 0, 0);
  }
  $("penSheet").hidden = false;
  $("penPrompt").textContent = prompt || "Write here";
  pen.prompt = prompt || "";
  pen.spot = (opts && opts.spot) || null;
  const r = c.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  pen.w = r.width;
  pen.h = r.height;
  pen.dpr = dpr;

  gc.width = r.width * dpr;
  gc.height = r.height * dpr;
  pen.gctx = gc.getContext("2d");
  pen.gctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  drawPrimaryLinesOn(pen.gctx, r.width, r.height, pen.spot);

  c.width = r.width * dpr;
  c.height = r.height * dpr;
  pen.ctx = c.getContext("2d");
  if (savedBitmap) {
    pen.ctx.drawImage(savedBitmap, 0, 0, c.width, c.height);
  } else {
    pen.strokes = 0;
  }
  pen.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  pen.ctx.lineCap = "round";
  pen.ctx.lineJoin = "round";
  setPenTool(keep && pen.spot ? "erase" : "pen");
}

(function wirePen() {
  const c = $("penCanvas");
  const pos = (e) => {
    const r = c.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top, p: e.pressure > 0 ? e.pressure : 0.5 };
  };
  $("penDrawBtn").onclick = () => setPenTool("pen");
  $("penEraseBtn").onclick = () => setPenTool("erase");
  c.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    c.setPointerCapture(e.pointerId);
    pen.drawing = true;
    pen.strokes++;
    if (pen.spot) {
      pen.spot = null;
      drawPrimaryLinesOn(pen.gctx, pen.w, pen.h, null);
    }
    const p = pos(e);
    if (pen.tool === "erase") {
      pen.ctx.globalCompositeOperation = "destination-out";
      pen.ctx.lineWidth = 22;
    } else {
      pen.ctx.globalCompositeOperation = "source-over";
      pen.ctx.strokeStyle = "#1f1f1f";
      pen.ctx.lineWidth = 2.6 + p.p * 3.6;
    }
    pen.ctx.beginPath();
    pen.ctx.moveTo(p.x, p.y);
  });
  c.addEventListener("pointermove", (e) => {
    if (!pen.drawing) return;
    const p = pos(e);
    if (pen.tool !== "erase") pen.ctx.lineWidth = 2.6 + p.p * 3.6;
    pen.ctx.lineTo(p.x, p.y);
    pen.ctx.stroke();
  });
  const end = () => {
    pen.drawing = false;
    if (pen.ctx) pen.ctx.globalCompositeOperation = "source-over";
  };
  c.addEventListener("pointerup", end);
  c.addEventListener("pointercancel", end);
  $("penClear").onclick = () => {
    pen.ctx.save();
    pen.ctx.setTransform(1, 0, 0, 1, 0, 0);
    pen.ctx.clearRect(0, 0, c.width, c.height);
    pen.ctx.restore();
    pen.strokes = 0;
    pen.spot = null;
    drawPrimaryLinesOn(pen.gctx, pen.w, pen.h, null);
    setPenTool("pen");
  };
  $("penCancel").onclick = () => ($("penSheet").hidden = true);
  $("penDone").onclick = () => {
    if (!pen.strokes) return ($("penSheet").hidden = true);
    const out = document.createElement("canvas");
    out.width = c.width;
    out.height = c.height;
    const o = out.getContext("2d");
    o.save();
    o.scale(pen.dpr, pen.dpr);
    drawPrimaryLinesOn(o, pen.w, pen.h, null);
    o.restore();
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
  const cleaned = String(text || "").replace(/\b(?:no\s+speech(?:\s+detected)?|inaudible|silence|background\s+noise)\b[.\s!]*/gi, " ").trim();
  if (!cleaned) return;
  state.heardKidSpeech = true;
  text = cleaned;
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

function insertStarter(text) {
  const t = String(text || "").replace(/(…|\.\.\.)\s*$/, "").trimEnd() + " ";
  input.value = t;
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 200) + "px";
  $("sendBtn").hidden = false;
  $("micBtn").hidden = true;
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
}

function renderItem(it) {
  switch (it.kind) {
    case "starters": {
      const el = upsertInline("starters", `<div class="starters">${(it.options || []).map((o) => `<button type="button" class="chip starter-chip">${esc(o)}</button>`).join("")}</div>`);
      el.querySelectorAll(".starter-chip").forEach((b) => (b.onclick = () => insertStarter(b.textContent)));
      break;
    }
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
      const el = upsertInline("word", `<div class="word-card"><div class="parts">${it.parts.map((p) => `<span class="part">${esc(p)}</span>`).join('<span class="plus">+</span>')}</div>${it.note ? `<div class="note">${esc(it.note)}</div>` : ""}<div class="ccc-row"><button class="ccc-btn" type="button">Cover &amp; write</button><span class="ccc-status muted" style="font-size:.85rem">Covers automatically when you type</span></div></div>`);
      const btn = el.querySelector(".ccc-btn");
      if (btn) btn.onclick = toggleWordCardPeek;
      break;
    }
    case "saved":
      upsertInline(it.id, `<div class="saved"><svg style="width:20px;height:20px"><use href="#spark"/></svg><span>Saved “${esc(it.title)}”</span><a href="${esc(it.url)}" target="_blank">Open</a> · <a href="/api/piece/${esc(it.id)}/pdf" target="_blank">Download PDF</a></div>`);
      break;
    case "book_project": {
      const pane = canvasPane("book", "Book · PDF", renderBookProject(it));
      wireBookPane(pane, it);
      break;
    }
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

function renderArtMiniActs(target, hasArt, verified, canRemove) {
  if (!target) return "";
  const btns = [];
  if (hasArt && !verified) {
    btns.push(`<button type="button" class="mini-art-btn ok" data-art-ok="${esc(target)}" title="Picture matches my story">✓ Right</button>`);
  }
  if (hasArt) {
    btns.push(`<button type="button" class="mini-art-btn" data-art-fix="${esc(target)}" title="Fix or redraw this picture">↻ Fix art</button>`);
  }
  if (canRemove) {
    btns.push(`<button type="button" class="mini-art-btn del" data-art-del="${esc(target)}" title="Remove this beat">✕ Remove</button>`);
  }
  return btns.length ? `<div class="art-mini-acts">${btns.join("")}</div>` : "";
}

function renderSpineRow(label, text, src, status, placeholder, target = "", verified = false, canRemove = false) {
  const thumb = src
    ? `<div class="spine-thumb"><img src="${esc(src)}" alt=""></div>`
    : status === "drawing"
    ? `<div class="spine-thumb drawing"><div class="shimmer" style="height:100%"></div></div>`
    : `<div class="spine-thumb empty"><span>Art unlocks</span></div>`;
  const miniActs = text ? renderArtMiniActs(target, !!src, !!verified, canRemove) : "";
  return `<div class="spine-row-card">
    <div class="spine-beat">
      <strong>${esc(label)}</strong>
      <div style="margin-top:4px">${text ? esc(text) : `<span class="muted">${esc(placeholder)}</span>`}</div>
      ${miniActs}
    </div>
    ${thumb}
  </div>`;
}

function wireBookPane(pane, it) {
  const sw = pane.querySelector("[data-switch-book]");
  if (sw) sw.onclick = () => toggleSidebar(true);
  const rn = pane.querySelector("[data-rename-cur]");
  if (rn) {
    rn.onclick = () => {
      const next = prompt("Book title:", it.title || "");
      if (next && next.trim()) send({ type: "rename_project", id: it.id, title: next.trim() });
    };
  }
  const stBtn = pane.querySelector("[data-toggle-styles]");
  if (stBtn) {
    stBtn.onclick = () => {
      const dr = pane.querySelector(".style-drawer");
      const nowOpen = dr ? dr.hidden : true;
      state.styleDrawerOpen = nowOpen;
      if (dr) dr.hidden = !nowOpen;
    };
  }
  pane.querySelectorAll("[data-pick-style]").forEach((card) => {
    card.onclick = () => {
      const key = card.dataset.pickStyle;
      state.styleDrawerOpen = false;
      send({ type: "set_style", style_key: key });
    };
  });
  pane.querySelectorAll("[data-art-ok]").forEach((btn) => {
    btn.onclick = () => {
      begin();
      send({ type: "art_feedback", target: btn.dataset.artOk, ok: true });
    };
  });
  pane.querySelectorAll("[data-art-fix]").forEach((btn) => {
    btn.onclick = () => {
      begin();
      addKid("↻ Fix this picture");
      send({ type: "art_feedback", target: btn.dataset.artFix, ok: false });
    };
  });
  pane.querySelectorAll("[data-art-del]").forEach((btn) => {
    btn.onclick = () => {
      if (!confirm("Remove this beat from your book?")) return;
      begin();
      send({ type: "art_feedback", target: btn.dataset.artDel, remove: true });
    };
  });
}

function renderBookProject(b) {
  const sp = b.spine || {};
  const mbeats = Array.isArray(sp.middle_beats) ? sp.middle_beats : [];
  const hasSpine = b.proj_kind === "epic_graphic_novel" || sp.beginning || sp.end || mbeats.length;
  const midRowsHtml = mbeats.length
    ? mbeats
        .map((mb, i) => renderSpineRow(`Middle Twist #${i + 1}`, mb.text, mb.src, mb.status, "What else happens in the middle?", `spine:middle_${i}`, !!mb.verified, true))
        .join("")
    : renderSpineRow("Middle Twists (Add as many as you want!)", "", null, null, "After your Finale, pack the middle with wild twists & obstacles!");

  const spineHtml = hasSpine
    ? `<div class="spine-box">
        ${renderSpineRow("The Beginning · Kickoff (Cover Art)", sp.beginning, sp.beginning_src || b.cover_src, sp.beginning_status, "Write the kickoff to unlock your Cover Art!", "spine:beginning", !!sp.beginning_verified, false)}
        ${midRowsHtml}
        ${renderSpineRow("The Big Finale · Payoff (End of Book)", sp.end, sp.end_src, sp.end_status, "Jump to the end—how does the whole story pay off?", "spine:end", !!sp.end_verified, false)}
      </div>`
    : "";

  const codexLiveHtml =
    b.proj_kind === "epic_codex" && (b.codex_sketch_src || b.codex_sketch_status === "drawing" || (b.codex_draft_sentences || []).length)
      ? `<div class="spine-box">
          <div class="spine-row-card">
            <div class="spine-beat">
              <strong>Active Codex Specimen Draft</strong>
              ${b.codex_sketch_caption ? `<div class="muted" style="font-size:.84rem;margin-top:3px">Inference: “${esc(b.codex_sketch_caption)}”</div>` : ""}
              ${(b.codex_draft_sentences || []).length
                ? `<div style="margin-top:8px">${b.codex_draft_sentences.map((s, idx) => `<div><span class="muted">${idx + 1}/3:</span> ${esc(s)}</div>`).join("")}</div>`
                : `<div class="muted" style="margin-top:6px">Drafting 3-sentence Encyclopedia Entry…</div>`}
            </div>
            ${b.codex_sketch_src
              ? `<div class="spine-thumb"><img src="${esc(b.codex_sketch_src)}" alt=""></div>`
              : b.codex_sketch_status === "drawing"
              ? `<div class="spine-thumb drawing"><div class="shimmer" style="height:100%"></div></div>`
              : ""}
          </div>
        </div>`
      : "";

  const stepsDone =
    (sp.beginning ? 1 : 0) + mbeats.length + (sp.end ? 1 : 0) + (b.panel_count || 0);
  const stepsGoal = b.proj_kind === "epic_graphic_novel" ? Math.max(5, stepsDone + 1) : (b.target_panels || 4);
  const pct = Math.min(100, Math.round((stepsDone / Math.max(1, stepsGoal)) * 100));
  const progHtml = `<div class="book-prog"><div class="book-prog-fill" style="width:${pct}%"></div></div>`;

  const styles = Array.isArray(b.art_styles) ? b.art_styles : [];
  const showStyles = state.styleDrawerOpen === null ? stepsDone === 0 : !!state.styleDrawerOpen;
  const stylesHtml = styles.length
    ? `<div class="style-drawer" ${showStyles ? "" : "hidden"}>
        <div class="muted" style="font-size:.82rem;margin-bottom:8px">Pick your comic art style (click any example):</div>
        <div class="style-grid">
          ${styles
            .map(
              (s) => `<button type="button" class="style-card ${s.key === b.style_key ? "selected" : ""}" data-pick-style="${esc(s.key)}">
                <img src="${esc(s.sample)}" alt="${esc(s.label)}" loading="lazy">
                <div class="style-card-meta">
                  <div class="style-card-title">${esc(s.label)}</div>
                  <div class="style-card-vibe">${esc(s.vibe)}</div>
                </div>
              </button>`
            )
            .join("")}
        </div>
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
          const pActs = renderArtMiniActs(`panel:${p.number}`, !!p.src, !!p.verified, true);
          return `<div class="panel"><div class="${cls}"><span class="num" style="background:#111;color:#fff;padding:2px 8px;border-radius:4px;font-size:.95rem;top:6px;left:6px">${p.number || ""}</span>${bubs ? `<div class="bubbles">${bubs}</div>` : ""}${art}</div><div class="caption">${esc(p.caption || "")}${pActs}</div></div>`;
        })
        .join("");
      return `<div class="ch-label">${esc(ch.title || "Chapter " + ch.number)}</div><div class="comic-grid">${cells}</div>`;
    })
    .join("");

  return `<div class="book-head">
      <div>
        <div class="comic-title" style="margin:0;display:flex;align-items:center;gap:10px">
          <span>${esc(b.title || "Untitled Book")}</span>
          <button type="button" class="text-btn" style="font-size:.82rem;padding:4px 8px" data-rename-cur="1" title="Rename this book">✎ Rename</button>
        </div>
        <div class="muted" style="font-size:.86rem">${esc(b.progress_label || `${b.panel_count || 0} panel(s)`)} · Style: ${esc(b.style_label || "Notebook Ink Doodle")}${b.sandbox ? " (Sandbox)" : ""}</div>
      </div>
      <div class="book-actions">
        <button type="button" class="pill-btn" data-toggle-styles="1">Art Style</button>
        <button type="button" class="pill-btn" data-switch-book="1">Switch / New</button>
        <a class="text-btn" href="${esc(b.web_url)}" target="_blank">Web view</a>
        <a class="btn-primary" href="${esc(b.pdf_url)}" target="_blank">Download PDF</a>
      </div>
    </div>
    ${progHtml}
    ${stylesHtml}
    ${spineHtml}
    ${codexLiveHtml}
    ${chHtml || '<div class="muted" style="padding:8px 2px">Each completed beat unlocks live artwork right here and updates your downloadable PDF immediately!</div>'}`;
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
    case "tutor_fallback_speech":
      upsertTutor(m.turn, m.text);
      if (!tutorAudible() && window.speechSynthesis && m.text) {
        try {
          window.speechSynthesis.cancel();
          const u = new SpeechSynthesisUtterance(m.text);
          u.rate = 1.03;
          window.speechSynthesis.speak(u);
        } catch (_) {}
      }
      break;
    case "turn_complete":
      if (state.micOn && state.micOneShot && state.heardKidSpeech) {
        micStop();
      }
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
    case "reward":
      if (m.label) showRewardBadge(m.label);
      break;
    case "input": {
      if (typeof m.epoch === "number") {
        if (m.epoch < state.lastServerEpoch) break;
        state.lastServerEpoch = m.epoch;
      }
      const modeNorm = m.mode === "talk_word" ? "talk" : m.mode;
      setAsk(m.prompt, modeNorm);
      const userAlreadyTyping = input.value.trim().length > 0;
      if (typeof m.prefill === "string") {
        if (!userAlreadyTyping) {
          input.value = m.prefill;
          input.style.height = "auto";
          input.style.height = Math.min(input.scrollHeight, 200) + "px";
          $("sendBtn").hidden = !input.value.trim();
          $("micBtn").hidden = !!input.value.trim();
          let selStart = input.value.length;
          let selEnd = input.value.length;
          if (m.select_word) {
            const escRe = String(m.select_word).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
            const match = new RegExp(`\\b${escRe}\\b`, "i").exec(input.value) || new RegExp(escRe, "i").exec(input.value);
            if (match) {
              selStart = match.index;
              selEnd = match.index + match[0].length;
            }
          } else if (typeof m.cursor_pos === "number") {
            selStart = selEnd = Math.max(0, Math.min(input.value.length, m.cursor_pos));
          }
          input.setSelectionRange(selStart, selEnd);
        } else if (m.prefill.trim() && m.prefill.trim() !== input.value.trim()) {
          // NEVER overwrite what the child is currently typing! Offer a harmless 1-tap restore chip instead.
          const el = upsertInline("saved-draft", `<div class="choices"><button type="button" class="chip">Load earlier line to edit (“${esc(m.prefill.slice(0, 38))}${m.prefill.length > 38 ? "…" : ""}”)</button></div>`);
          const b = el.querySelector("button");
          if (b) {
            b.onclick = () => {
              input.value = m.prefill;
              input.dispatchEvent(new Event("input"));
              input.focus();
              el.remove();
            };
          }
        }
      }
      if (m.mode === "type" && !userAlreadyTyping) input.focus();
      if (m.hint_pen) $("penBtn").classList.add("highlight");
      if (m.mode === "talk_word" || m.mode === "talk") {
        state.micOneShot = true;
        state.heardKidSpeech = false;
        if (!state.micOn) micStart();
      }
      if (m.mode === "pen") openPen(m.prompt, { keepStrokes: !!m.keep_strokes, spot: m.spot || null });
      break;
    }
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

function playRewardChime() {
  try {
    ensureAudio();
    if (!playCtx) return;
    const now = playCtx.currentTime;
    [523.25, 659.25].forEach((freq, idx) => {
      const osc = playCtx.createOscillator();
      const gain = playCtx.createGain();
      osc.type = "triangle";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.001, now + idx * 0.09);
      gain.gain.exponentialRampToValueAtTime(0.06, now + idx * 0.09 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + idx * 0.09 + 0.24);
      osc.connect(gain).connect(playCtx.destination);
      osc.start(now + idx * 0.09);
      osc.stop(now + idx * 0.09 + 0.25);
    });
  } catch (_) {}
}

function showRewardBadge(label) {
  playRewardChime();
  const el = document.createElement("div");
  el.className = "reward-pill";
  el.textContent = label;
  stream.appendChild(el);
  scrollDown();
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
