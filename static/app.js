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
  lastBook: null,
  lastComic: null,
  drawnItems: {},
  lettering: null,
};

// ---------------------------------------------------------------- setup

async function boot() {
  const st = await (await fetch(`/api/state?sandbox=${IS_SANDBOX ? 1 : 0}`)).json();
  state.name = st.name || "";
  if (st.bug_locked) {
    showProtectiveBug(st.bug_code || "ERR-G42");
    return;
  }
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
    <button type="button" class="hero-pill" data-new-kind="story_jam_novel">100-page comic (talk plot first)</button>
    <button type="button" class="hero-pill" data-new-kind="how_to_tutorial">How-to guide</button>
    <button type="button" class="hero-pill" data-new-kind="minecraft_diary">Minecraft diary</button>
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

// ---------- Tutor-Controlled Center Green Microphone (16 kHz WAV short-clip capture) ----------
const centerMic = {
  open: false,
  recording: false,
  purpose: "word",
  targetWord: "",
  sentence: "",
  prompt: "",
  chunks: [],
  speechFrames: 0,
  silentFramesAfterSpeech: 0,
  totalFrames: 0,
  waitTimer: null,
  maxTimer: null,
  stream: null,
  ctx: null,
  node: null,
};

function encodeWav16k(int16Chunks) {
  let samples = 0;
  for (const c of int16Chunks) samples += c.length;
  const byteLen = samples * 2;
  const buf = new ArrayBuffer(44 + byteLen);
  const dv = new DataView(buf);
  const wStr = (off, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(off + i, s.charCodeAt(i)); };
  wStr(0, "RIFF");
  dv.setUint32(4, 36 + byteLen, true);
  wStr(8, "WAVE");
  wStr(12, "fmt ");
  dv.setUint32(16, 16, true);
  dv.setUint16(20, 1, true);
  dv.setUint16(22, 1, true);
  dv.setUint32(24, 16000, true);
  dv.setUint32(28, 32000, true);
  dv.setUint16(32, 2, true);
  dv.setUint16(34, 16, true);
  wStr(36, "data");
  dv.setUint32(40, byteLen, true);
  const out16 = new Int16Array(buf, 44, samples);
  let pos = 0;
  for (const c of int16Chunks) {
    out16.set(c, pos);
    pos += c.length;
  }
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 8192) {
    bin += String.fromCharCode(...bytes.subarray(i, i + 8192));
  }
  return "data:audio/wav;base64," + btoa(bin);
}

function stopCenterMic(sendClip = false) {
  clearInterval(centerMic.waitTimer);
  clearTimeout(centerMic.maxTimer);
  centerMic.waitTimer = null;
  centerMic.maxTimer = null;
  const wasRec = centerMic.recording;
  const chunks = centerMic.chunks.slice();
  const hadSpeech = centerMic.speechFrames >= 2;
  const meta = { purpose: centerMic.purpose, target_word: centerMic.targetWord, sentence: centerMic.sentence };

  centerMic.open = false;
  centerMic.recording = false;
  centerMic.chunks = [];
  state.micOn = false;
  try { centerMic.stream && centerMic.stream.getTracks().forEach((t) => t.stop()); } catch (_) {}
  try { centerMic.ctx && centerMic.ctx.close(); } catch (_) {}
  centerMic.stream = centerMic.ctx = centerMic.node = null;

  const ov = $("centerMic");
  if (ov) ov.hidden = true;
  const ring = $("centerMicRing");
  if (ring) ring.style.transform = "scale(1)";

  if (sendClip && wasRec && chunks.length > 0 && hadSpeech) {
    setAsk("Listening to what you said…", null);
    const wavB64 = encodeWav16k(chunks);
    send({ type: "voice_clip", wav_b64: wavB64, ...meta });
  }
}

async function startCenterMicRecording() {
  if (!centerMic.open || centerMic.recording) return;
  clearInterval(centerMic.waitTimer);
  centerMic.waitTimer = null;
  stopPlayback();
  try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (_) {}
  try {
    centerMic.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
  } catch (e) {
    $("centerMicCard")?.classList.add("waiting");
    $("centerMicStatus").textContent = "Tap the green mic to allow microphone (or click Type instead)";
    return;
  }
  if (!centerMic.open) {
    try { centerMic.stream.getTracks().forEach((t) => t.stop()); } catch (_) {}
    return;
  }
  centerMic.ctx = new (window.AudioContext || window.webkitAudioContext)();
  await centerMic.ctx.audioWorklet.addModule("/static/mic-worklet.js");
  const src = centerMic.ctx.createMediaStreamSource(centerMic.stream);
  centerMic.node = new AudioWorkletNode(centerMic.ctx, "mic-processor");
  centerMic.chunks = [];
  centerMic.speechFrames = 0;
  centerMic.silentFramesAfterSpeech = 0;
  centerMic.totalFrames = 0;
  centerMic.recording = true;
  state.micOn = true;

  $("centerMicCard")?.classList.remove("waiting");
  $("centerMicStatus").textContent = "● Mic is ON — speak now!";
  $("centerMicDone").hidden = false;

  const isIntake = centerMic.purpose === "oral_intake" || centerMic.purpose === "story_jam";
  const silenceCutoff = centerMic.purpose === "word" ? 24 : isIntake ? 50 : 36;
  centerMic.node.port.onmessage = (e) => {
    if (!centerMic.recording) return;
    const pcmCopy = new Int16Array(e.data.pcm);
    const lvl = Number(e.data.level) || 0;
    centerMic.chunks.push(pcmCopy);
    centerMic.totalFrames++;
    const ring = $("centerMicRing");
    if (ring) ring.style.transform = `scale(${(1 + Math.min(0.45, lvl * 6.5)).toFixed(2)})`;

    if (lvl > 0.014) {
      centerMic.speechFrames++;
      centerMic.silentFramesAfterSpeech = 0;
      if (centerMic.speechFrames >= 2) {
        $("centerMicStatus").textContent = "● Hearing you…";
      }
    } else if (centerMic.speechFrames >= 3) {
      centerMic.silentFramesAfterSpeech++;
      if (centerMic.silentFramesAfterSpeech >= silenceCutoff) {
        stopCenterMic(true);
      }
    }
  };
  const mute = centerMic.ctx.createGain();
  mute.gain.value = 0;
  src.connect(centerMic.node).connect(mute).connect(centerMic.ctx.destination);

  clearTimeout(centerMic.maxTimer);
  centerMic.maxTimer = setTimeout(() => {
    if (centerMic.open) stopCenterMic(centerMic.speechFrames >= 2);
  }, (centerMic.purpose === "oral_intake" || centerMic.purpose === "story_jam") ? 28000 : 12000);
}

function showCenterMic(cfg) {
  stopCenterMic(false);
  begin();
  centerMic.open = true;
  centerMic.purpose = cfg.purpose || "word";
  centerMic.targetWord = cfg.target_word || "";
  centerMic.sentence = cfg.sentence || "";
  centerMic.prompt = cfg.prompt || "Say it out loud";

  $("centerMicTitle").textContent = centerMic.prompt;
  $("centerMicDone").hidden = true;
  $("centerMic").hidden = false;

  // Wait briefly for the tutor's spoken prompt to finish so we don't record the tutor's own voice!
  let waitedTicks = 0;
  if (tutorAudible()) {
    $("centerMicCard")?.classList.add("waiting");
    $("centerMicStatus").textContent = "Get ready — mic turns ON right as I finish asking… (or tap green mic now)";
  } else {
    $("centerMicStatus").textContent = "● Turning mic ON…";
  }
  centerMic.waitTimer = setInterval(() => {
    waitedTicks++;
    if (!centerMic.open) {
      clearInterval(centerMic.waitTimer);
      return;
    }
    // Give 350ms for first PCM audio packet to arrive, then wait until tutor finishes speaking (24s safety cap)
    if ((waitedTicks >= 3 && !tutorAudible()) || waitedTicks >= 200) {
      clearInterval(centerMic.waitTimer);
      centerMic.waitTimer = null;
      startCenterMicRecording();
    }
  }, 120);
}

$("centerMicBtn").onclick = () => {
  if (!centerMic.recording) startCenterMicRecording();
  else stopCenterMic(true);
};
$("centerMicDone").onclick = () => stopCenterMic(true);
$("centerMicDismiss").onclick = () => {
  stopCenterMic(false);
  input.focus();
};

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
  stopCenterMic(false);
  begin();
  const ms = state.typing.first ? Math.round(performance.now() - state.typing.first) : 0;
  addKid(esc(text));
  document.getElementById("item-starters")?.remove();
  send({ type: "text", text, ms, backspaces: state.typing.backspaces });
  input.value = "";
  input.style.height = "auto";
  $("sendBtn").hidden = true;
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
  const cleaned = String(text || "")
    .replace(/\b(?:no\s+speech(?:\s+detected)?|inaudible|silence|background\s+noise)\b[.\s!]*/gi, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
  let el = document.getElementById("tutor-" + turn);
  if (!cleaned) {
    if (el) el.remove();
    return;
  }
  if (!el) {
    el = document.createElement("div");
    el.className = "msg tutor speaking";
    el.id = "tutor-" + turn;
    el.innerHTML = `<svg class="spark"><use href="#spark"/></svg><div class="text"></div>`;
    stream.appendChild(el);
  }
  el.querySelector(".text").textContent = cleaned;
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
      state.drawnItems[it.id] = it;
      const target = `draw:${it.id}`;
      const el = upsertInline(
        it.id,
        renderComicPanelUnit({
          target,
          badge: "COMIC PANEL",
          src: it.status === "done" ? it.src : null,
          status: it.status,
          caption: it.caption ?? "",
          dialogue: it.dialogue || [],
          verified: true,
          canRemove: false,
          extraClass: "stream-comic",
        })
      );
      wireComicPanels(el);
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
          addKid(esc(b.textContent));
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
      state.lastBook = it;
      const tabLbl = it.proj_kind === "how_to_tutorial" ? "Guide · PDF" : "Book · PDF";
      const pane = canvasPane("book", tabLbl, renderBookProject(it));
      wireBookPane(pane, it);
      break;
    }
    case "comic": {
      state.lastComic = it;
      const pane = canvasPane("comic", "Comic", renderComic(it));
      wireComicPanels(pane);
      break;
    }
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

function findCaptionForTarget(target) {
  if (!target) return "";
  if (target.startsWith("spine:") && state.lastBook?.spine) {
    const sp = state.lastBook.spine;
    const beat = target.split(":")[1];
    if (beat === "beginning") return sp.beginning_caption ?? sp.beginning ?? "";
    if (beat === "end") return sp.end_caption ?? sp.end ?? "";
    if (beat.startsWith("middle_")) {
      const idx = Number(beat.split("_")[1]);
      const mb = (sp.middle_beats || [])[idx];
      return mb ? (mb.caption ?? mb.text ?? "") : "";
    }
  }
  if (target.startsWith("panel:") && state.lastBook?.chapters) {
    const pnum = Number(target.split(":")[1]);
    for (const ch of state.lastBook.chapters) {
      for (const p of ch.panels || []) {
        if (Number(p.number) === pnum) return p.caption ?? "";
      }
    }
  }
  if (target.startsWith("strip:") && state.lastComic?.panels) {
    const idx = Number(target.split(":")[1]);
    return state.lastComic.panels[idx]?.caption ?? "";
  }
  if (target.startsWith("draw:")) {
    const did = target.split(":")[1];
    return state.drawnItems[did]?.caption ?? "";
  }
  return "";
}

function defaultLetteringTarget() {
  if (state.lastBook?.chapters) {
    let lastP = null;
    for (const ch of state.lastBook.chapters) {
      for (const p of ch.panels || []) lastP = p.number;
    }
    if (lastP) return `panel:${lastP}`;
  }
  if (state.lastBook?.spine) {
    const sp = state.lastBook.spine;
    const mbs = sp.middle_beats || [];
    if (mbs.length) return `spine:middle_${mbs.length - 1}`;
    if (sp.end) return "spine:end";
    if (sp.beginning) return "spine:beginning";
  }
  if (state.lastComic?.panels?.length) {
    let idx = 0;
    state.lastComic.panels.forEach((p, i) => {
      if (p.src || p.caption) idx = i;
    });
    return `strip:${idx}`;
  }
  const drawIds = Object.keys(state.drawnItems || {});
  if (drawIds.length) return `draw:${drawIds[drawIds.length - 1]}`;
  return "";
}

function openLetteringState(target, tab = "bubble", opts = {}) {
  const effTarget = target || defaultLetteringTarget();
  if (!effTarget) return;
  const curCap = findCaptionForTarget(effTarget);
  state.lettering = {
    target: effTarget,
    tab: tab === "caption" ? "caption" : "bubble",
    kind: opts.kind || "speech",
    speaker: opts.speaker ?? "",
    text: opts.text ?? "",
    caption: opts.caption !== undefined ? opts.caption : curCap,
    editBubbleId: opts.editBubbleId || "",
    fix: opts.fix || null,
  };
  refreshLetteringHost(effTarget, true);
}

function refreshLetteringHost(target, focusInput = false) {
  if (!target) return;
  if ((target.startsWith("spine:") || target.startsWith("panel:")) && state.lastBook) {
    const tabLbl = state.lastBook.proj_kind === "how_to_tutorial" ? "Guide · PDF" : "Book · PDF";
    const pane = canvasPane("book", tabLbl, renderBookProject(state.lastBook));
    wireBookPane(pane, state.lastBook);
  } else if (target.startsWith("strip:") && state.lastComic) {
    const pane = canvasPane("comic", "Comic", renderComic(state.lastComic));
    wireComicPanels(pane);
  } else if (target.startsWith("draw:")) {
    const did = target.split(":")[1];
    if (state.drawnItems[did]) renderItem(state.drawnItems[did]);
  }
  if (focusInput && state.lettering?.target === target) {
    setTimeout(() => {
      const tray = document.querySelector(`[data-let-tray="${CSS.escape(target)}"]`);
      if (tray) {
        tray.scrollIntoView({ behavior: "smooth", block: "nearest" });
        const inp = tray.querySelector(".let-main");
        if (inp) inp.focus();
      }
    }, 30);
  }
}

function renderPanelComicBar(target, hasArt, verified, canRemove, hasCap) {
  if (!target) return "";
  const isProjectTarget = target.startsWith("spine:") || target.startsWith("panel:");
  const btns = [
    `<button type="button" class="comic-act-btn primary-let" data-open-let="${esc(target)}" data-let-tab="bubble" title="Add a speech, shout, or thought bubble onto this panel">💬 + Speech Bubble</button>`,
    `<button type="button" class="comic-act-btn" data-open-let="${esc(target)}" data-let-tab="caption" title="Add, edit, or hide the yellow narrator caption box">✎ ${hasCap ? "Caption" : "+ Caption"}</button>`,
  ];
  if (isProjectTarget && hasArt && !verified) {
    btns.push(`<button type="button" class="mini-art-btn ok" data-art-ok="${esc(target)}" title="Picture matches my story">✓ Right</button>`);
  }
  if (isProjectTarget && hasArt) {
    btns.push(`<button type="button" class="mini-art-btn" data-art-fix="${esc(target)}" title="Fix or redraw this picture">↻ Fix art</button>`);
  }
  if (canRemove) {
    btns.push(`<button type="button" class="mini-art-btn del" data-art-del="${esc(target)}" title="Remove this beat">✕ Remove</button>`);
  }
  return `<div class="panel-comic-bar">${btns.join("")}</div>`;
}

function renderLetteringTray(target) {
  const L = state.lettering;
  if (!L || L.target !== target) return "";
  const isBub = L.tab !== "caption";
  const fix = L.fix;
  const fixHtml = fix
    ? `<div class="let-fix-box">
        <div>${esc(fix.message || "Quick check:")}</div>
        ${(fix.options || []).length
          ? `<div class="let-fix-chips">${fix.options
              .map((o) => `<button type="button" class="let-fix-chip" data-let-fix-pick="${esc(o)}">${esc(o)}</button>`)
              .join("")}</div>`
          : ""}
      </div>`
    : "";

  const bodyHtml = isBub
    ? `<div class="let-style-row">
        <button type="button" class="let-kind-btn ${L.kind === "speech" ? "on" : ""}" data-let-kind="speech">💬 Speech</button>
        <button type="button" class="let-kind-btn ${L.kind === "shout" ? "on" : ""}" data-let-kind="shout">💥 SHOUT!</button>
        <button type="button" class="let-kind-btn ${L.kind === "thought" ? "on" : ""}" data-let-kind="thought">💭 Thought</button>
        <span class="muted" style="font-size:.75rem;margin-left:auto">Drag bubbles on the art to move them!</span>
      </div>
      <div class="let-inputs">
        <input type="text" class="let-speaker" placeholder="Who? (optional)" value="${esc(L.speaker || "")}" maxlength="26">
        <input type="text" class="let-main" placeholder="What does the bubble say? (e.g. What is that smell?!)" value="${esc(L.text || "")}" maxlength="160">
        <button type="button" class="let-mic-btn" data-let-mic="${esc(target)}" title="Say the dialogue line out loud">🎤</button>
        <button type="button" class="let-save-btn" data-let-save-bub="${esc(target)}">${L.editBubbleId ? "Update Bubble" : "Put on Panel"}</button>
      </div>`
    : `<div class="let-inputs">
        <input type="text" class="let-main" placeholder="Yellow comic caption box (e.g. Meanwhile, on Earth...)" value="${esc(L.caption || "")}" maxlength="300">
        <button type="button" class="let-save-btn" data-let-save-cap="${esc(target)}">Save Caption</button>
        <button type="button" class="comic-act-btn" data-let-clear-cap="${esc(target)}" title="Remove caption box so only art & speech bubbles show">Hide Caption</button>
      </div>`;

  return `<div class="lettering-tray" data-let-tray="${esc(target)}">
    <div class="lettering-tabs">
      <div class="let-tab-group">
        <button type="button" class="let-tab ${isBub ? "on" : ""}" data-let-switch="bubble">💬 Speech Bubble</button>
        <button type="button" class="let-tab ${!isBub ? "on" : ""}" data-let-switch="caption">✎ Caption Box</button>
      </div>
      <button type="button" class="text-btn" style="padding:2px 8px;font-size:.8rem" data-let-close="1">✕</button>
    </div>
    ${bodyHtml}
    ${fixHtml}
  </div>`;
}

function renderComicPanelUnit(opts) {
  const target = opts.target || "";
  const badge = opts.badge || "";
  const src = opts.src || null;
  const status = opts.status || "";
  const cap = String(opts.caption ?? "").trim();
  const hasCap = cap.length > 0;
  const bubs = Array.isArray(opts.dialogue) ? opts.dialogue : [];
  const cls = status === "drawing" ? "art drawing" : "art";
  const artInner = src
    ? `<img src="${esc(src)}" alt="" draggable="false">`
    : status === "failed"
    ? `<div style="display:grid;place-items:center;height:100%;color:#666;padding:12px">Couldn't draw that one—tap Fix art to retry.</div>`
    : status === "drawing"
    ? `<div class="shimmer" style="height:100%"></div>`
    : `<div style="display:grid;place-items:center;height:100%;color:#888;font-size:.9rem">Panel ready</div>`;

  const bubsHtml = bubs
    .map(
      (d, idx) => `<div class="comic-bubble ${esc(d.kind || "speech")}"
        data-bub-id="${esc(d.id || `bub_${idx}`)}"
        data-bub-target="${esc(target)}"
        data-bub-speaker="${esc(d.speaker || "")}"
        data-bub-text="${esc(d.text || "")}"
        data-bub-kind="${esc(d.kind || "speech")}"
        style="left:${Number(d.x ?? 12)}%;top:${Number(d.y ?? 10)}%"
        title="Drag anywhere on the panel · Click to edit">
        <span class="bub-body">${d.speaker ? `<strong>${esc(d.speaker)}:</strong> ` : ""}${esc(d.text || "")}</span>
        <button type="button" class="bub-del" data-del-bub="${esc(d.id || `bub_${idx}`)}" data-bub-target="${esc(target)}" title="Remove bubble">✕</button>
      </div>`
    )
    .join("");

  return `<div class="comic-unit ${esc(opts.extraClass || "")}" data-comic-unit="${esc(target)}">
    <div class="panel">
      <div class="${cls}" data-art-stage="${esc(target)}">
        ${badge ? `<span class="panel-badge">${esc(badge)}</span>` : ""}
        ${bubsHtml}
        ${artInner}
      </div>
      ${hasCap ? `<div class="caption" data-edit-cap="${esc(target)}" title="Click to edit or hide caption">${esc(cap)}</div>` : ""}
    </div>
    ${renderPanelComicBar(target, !!src || status === "drawing", !!opts.verified, !!opts.canRemove, hasCap)}
    ${renderLetteringTray(target)}
  </div>`;
}

function submitActiveLettering(tray, target) {
  const L = state.lettering;
  if (!L || L.target !== target) return;
  if (L.tab === "caption") {
    const capVal = tray.querySelector(".let-main")?.value ?? "";
    L.caption = capVal;
    send({ type: "comic_lettering", target, action: "set_caption", caption: capVal });
  } else {
    const spkVal = tray.querySelector(".let-speaker")?.value ?? "";
    const txtVal = tray.querySelector(".let-main")?.value ?? "";
    L.speaker = spkVal;
    L.text = txtVal;
    send({
      type: "comic_lettering",
      target,
      action: L.editBubbleId ? "edit_bubble" : "add_bubble",
      bubble_id: L.editBubbleId || undefined,
      speaker: spkVal,
      text: txtVal,
      kind: L.kind || "speech",
    });
  }
}

function wireComicPanels(root) {
  if (!root) return;
  root.querySelectorAll("[data-open-let]").forEach((btn) => {
    btn.onclick = () => {
      openLetteringState(btn.dataset.openLet, btn.dataset.letTab || "bubble");
    };
  });
  root.querySelectorAll("[data-edit-cap]").forEach((capEl) => {
    capEl.onclick = () => {
      openLetteringState(capEl.dataset.editCap, "caption");
    };
  });
  root.querySelectorAll(".bub-del").forEach((delBtn) => {
    delBtn.onclick = (e) => {
      e.stopPropagation();
      send({
        type: "comic_lettering",
        target: delBtn.dataset.bubTarget,
        action: "delete_bubble",
        bubble_id: delBtn.dataset.delBub,
      });
    };
  });

  // Drag-to-position + click-to-edit on every comic speech bubble
  root.querySelectorAll(".comic-bubble").forEach((bubEl) => {
    bubEl.onpointerdown = (e) => {
      if (e.target.closest(".bub-del")) return;
      const stage = bubEl.closest("[data-art-stage]");
      if (!stage) return;
      e.preventDefault();
      bubEl.setPointerCapture(e.pointerId);
      const rect = stage.getBoundingClientRect();
      const startX = e.clientX;
      const startY = e.clientY;
      const origLeft = parseFloat(bubEl.style.left) || 12;
      const origTop = parseFloat(bubEl.style.top) || 10;
      let moved = false;
      let curX = origLeft;
      let curY = origTop;

      const onMove = (ev) => {
        const dx = ev.clientX - startX;
        const dy = ev.clientY - startY;
        if (Math.hypot(dx, dy) > 5) moved = true;
        if (!moved) return;
        curX = Math.max(2, Math.min(82, origLeft + (dx / Math.max(1, rect.width)) * 100));
        curY = Math.max(2, Math.min(76, origTop + (dy / Math.max(1, rect.height)) * 100));
        bubEl.style.left = `${Math.round(curX)}%`;
        bubEl.style.top = `${Math.round(curY)}%`;
      };
      const onUp = () => {
        bubEl.removeEventListener("pointermove", onMove);
        bubEl.removeEventListener("pointerup", onUp);
        if (moved) {
          send({
            type: "comic_lettering",
            target: bubEl.dataset.bubTarget,
            action: "move_bubble",
            bubble_id: bubEl.dataset.bubId,
            x: Math.round(curX),
            y: Math.round(curY),
          });
        } else {
          openLetteringState(bubEl.dataset.bubTarget, "bubble", {
            editBubbleId: bubEl.dataset.bubId,
            speaker: bubEl.dataset.bubSpeaker || "",
            text: bubEl.dataset.bubText || "",
            kind: bubEl.dataset.bubKind || "speech",
          });
        }
      };
      bubEl.addEventListener("pointermove", onMove);
      bubEl.addEventListener("pointerup", onUp);
    };
  });

  // Wire active inline lettering tray controls
  root.querySelectorAll("[data-let-tray]").forEach((tray) => {
    const target = tray.dataset.letTray;
    const syncDraft = () => {
      if (!state.lettering || state.lettering.target !== target) return;
      if (state.lettering.tab === "caption") {
        state.lettering.caption = tray.querySelector(".let-main")?.value ?? "";
      } else {
        state.lettering.speaker = tray.querySelector(".let-speaker")?.value ?? "";
        state.lettering.text = tray.querySelector(".let-main")?.value ?? "";
      }
    };
    tray.querySelectorAll("input").forEach((inp) => {
      inp.oninput = syncDraft;
      inp.onkeydown = (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          submitActiveLettering(tray, target);
        }
      };
    });
    tray.querySelectorAll("[data-let-switch]").forEach((tb) => {
      tb.onclick = () => {
        syncDraft();
        state.lettering.tab = tb.dataset.letSwitch;
        state.lettering.fix = null;
        refreshLetteringHost(target, true);
      };
    });
    tray.querySelectorAll("[data-let-kind]").forEach((kb) => {
      kb.onclick = () => {
        syncDraft();
        state.lettering.kind = kb.dataset.letKind;
        refreshLetteringHost(target, true);
      };
    });
    const closeBtn = tray.querySelector("[data-let-close]");
    if (closeBtn) {
      closeBtn.onclick = () => {
        state.lettering = null;
        refreshLetteringHost(target, false);
      };
    }
    const saveBub = tray.querySelector("[data-let-save-bub]");
    if (saveBub) saveBub.onclick = () => submitActiveLettering(tray, target);
    const saveCap = tray.querySelector("[data-let-save-cap]");
    if (saveCap) saveCap.onclick = () => submitActiveLettering(tray, target);
    const clrCap = tray.querySelector("[data-let-clear-cap]");
    if (clrCap) {
      clrCap.onclick = () => {
        send({ type: "comic_lettering", target, action: "set_caption", caption: "", force: true });
      };
    }
    const micBtn = tray.querySelector("[data-let-mic]");
    if (micBtn) {
      micBtn.onclick = () => {
        syncDraft();
        begin();
        send({ type: "request_dialogue_mic", target });
      };
    }
    tray.querySelectorAll("[data-let-fix-pick]").forEach((chip) => {
      chip.onclick = () => {
        syncDraft();
        const picked = chip.dataset.letFixPick || "";
        const fix = state.lettering?.fix || {};
        const mainInp = tray.querySelector(".let-main");
        if (!mainInp) return;
        let nextVal = mainInp.value;
        if (fix.issue === "spelling" && fix.wrote) {
          const escW = fix.wrote.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
          nextVal = nextVal.replace(new RegExp(`\\b${escW}\\b`, "i"), picked);
        } else {
          nextVal = picked;
        }
        mainInp.value = nextVal;
        syncDraft();
        state.lettering.fix = null;
        const firstAlpha = (nextVal.match(/[A-Za-z]/) || [""])[0];
        const capOk = !firstAlpha || firstAlpha === firstAlpha.toUpperCase();
        const endOk = /[.!?…]["”')\]]*$/.test(nextVal.trim());
        if (capOk && endOk) {
          submitActiveLettering(tray, target);
        } else {
          refreshLetteringHost(target, true);
        }
      };
    });
  });
}

function renderSpinePlaceholder(label, placeholder) {
  return `<div class="spine-row-card" style="grid-column: 1 / -1">
    <div class="spine-beat">
      <strong>${esc(label)}</strong>
      <div style="margin-top:4px"><span class="muted">${esc(placeholder)}</span></div>
    </div>
    <div class="spine-thumb empty"><span>Comic panel unlocks</span></div>
  </div>`;
}

function wireBookPane(pane, it) {
  wireComicPanels(pane);
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
  pane.querySelectorAll("[data-jam-write]").forEach((btn) => {
    btn.onclick = () => {
      begin();
      addKid("Start writing Panel 1 →");
      send({ type: "story_jam_mode", action: "start_writing" });
    };
  });
  pane.querySelectorAll("[data-step-del]").forEach((btn) => {
    btn.onclick = () => {
      if (!confirm("Remove this step from your guide?")) return;
      begin();
      send({ type: "art_feedback", target: btn.dataset.stepDel, remove: true });
    };
  });
}

function renderHowToGuideProject(b) {
  const allSteps = [];
  for (const ch of b.chapters || []) {
    for (const p of ch.panels || []) allSteps.push(p);
  }
  const stepsDone = allSteps.length;
  const stepsGoal = Math.max(4, b.target_panels || 8);
  const pct = Math.min(100, Math.round((stepsDone / Math.max(1, stepsGoal)) * 100));
  const progHtml = `<div class="book-prog"><div class="book-prog-fill" style="width:${pct}%"></div></div>`;
  const stepsHtml = allSteps.length
    ? `<div class="howto-step-list">${allSteps
        .map(
          (st, idx) => `<div class="howto-step-card">
            <span class="howto-step-num">STEP ${Number(st.number || idx + 1)}</span>
            <div class="howto-step-text">${esc(st.caption || st.scene || "")}</div>
            <button type="button" class="howto-step-del" data-step-del="panel:${Number(st.number || idx + 1)}" title="Remove step">✕</button>
          </div>`
        )
        .join("")}</div>`
    : `<div style="color:#5f6368;font-size:.96rem;padding:8px 2px">${
        b.stage === "tutorial_topic"
          ? "Type what your How-To Guide is about on the left to start your guide."
          : "Write Step 1 on the left—each complete sentence appears here as a numbered step."
      }</div>`;

  return `<div class="book-head">
      <div>
        <div class="comic-title" style="margin:0;display:flex;align-items:center;gap:10px">
          <span>${esc(b.title || "Untitled How-To Guide")}</span>
          <button type="button" class="text-btn" style="font-size:.82rem;padding:4px 8px" data-rename-cur="1" title="Rename guide">✎ Rename</button>
        </div>
        <div class="muted" style="font-size:.86rem">${esc(b.progress_label || `${stepsDone} step(s)`)}${b.sandbox ? " (Sandbox)" : ""}</div>
      </div>
      <div class="book-actions">
        <button type="button" class="pill-btn" data-switch-book="1">Switch / New</button>
        <a class="text-btn" href="${esc(b.web_url)}" target="_blank">Web view</a>
        <a class="btn-primary" href="${esc(b.pdf_url)}" target="_blank">Download PDF</a>
      </div>
    </div>
    ${progHtml}
    <div class="howto-doc">
      <div class="howto-doc-head">
        <div class="howto-eyebrow">How-To Guide · ${stepsDone} step${stepsDone === 1 ? "" : "s"}</div>
        <h2 class="howto-doc-title">${esc(b.title || "Untitled How-To Guide")}</h2>
        <div class="howto-doc-by">Written by ${esc(b.author || "Author")}${b.audience ? ` · For ${esc(b.audience)}` : ""}</div>
      </div>
      ${stepsHtml}
    </div>`;
}

function renderBookProject(b) {
  if (b.proj_kind === "how_to_tutorial") {
    return renderHowToGuideProject(b);
  }
  const sp = b.spine || {};
  const mbeats = Array.isArray(sp.middle_beats) ? sp.middle_beats : [];
  const hasSpine = b.proj_kind === "epic_graphic_novel" || sp.beginning || sp.end || mbeats.length;

  let spineHtml = "";
  if (hasSpine) {
    const cards = [];
    if (sp.beginning || sp.beginning_src || sp.beginning_status === "drawing") {
      cards.push(
        renderComicPanelUnit({
          target: "spine:beginning",
          badge: "COVER · KICKOFF",
          src: sp.beginning_src || b.cover_src,
          status: sp.beginning_status,
          caption: sp.beginning_caption !== undefined ? sp.beginning_caption : (sp.beginning || ""),
          dialogue: sp.beginning_dialogue || [],
          verified: !!sp.beginning_verified,
          canRemove: false,
          extraClass: !mbeats.length && !sp.end ? "spine-hero" : "",
        })
      );
    } else {
      cards.push(renderSpinePlaceholder("Step 1 · The Beginning (Cover & Kickoff Panel)", "Write the kickoff sentence to unlock your Cover Comic Panel!"));
    }

    if (mbeats.length) {
      mbeats.forEach((mb, i) => {
        cards.push(
          renderComicPanelUnit({
            target: `spine:middle_${i}`,
            badge: `MIDDLE TWIST #${i + 1}`,
            src: mb.src,
            status: mb.status,
            caption: mb.caption !== undefined ? mb.caption : (mb.text || ""),
            dialogue: mb.dialogue || [],
            verified: !!mb.verified,
            canRemove: true,
          })
        );
      });
    } else if (sp.beginning && sp.end) {
      cards.push(renderSpinePlaceholder("Step 3 · Middle Twists (Add as many panels as you want!)", "Add wild middle twists & speech bubbles between your Kickoff and Finale!"));
    }

    if (sp.end || sp.end_src || sp.end_status === "drawing") {
      cards.push(
        renderComicPanelUnit({
          target: "spine:end",
          badge: "BIG FINALE",
          src: sp.end_src,
          status: sp.end_status,
          caption: sp.end_caption !== undefined ? sp.end_caption : (sp.end || ""),
          dialogue: sp.end_dialogue || [],
          verified: !!sp.end_verified,
          canRemove: false,
        })
      );
    } else if (sp.beginning) {
      cards.push(renderSpinePlaceholder("Step 2 · The Big Finale (End of Book Panel)", "Jump to the very end—how does the whole story pay off?"));
    }

    spineHtml = `<div class="spine-grid">${cards.join("")}</div>`;
  }

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

  const intakePillars = Array.isArray(b.intake_pillars) ? b.intake_pillars : [];
  const pillarsHtml = intakePillars
    .map((p) => {
      const cls = p.locked ? "intake-pillar locked" : p.needs_link ? "intake-pillar needs-link" : "intake-pillar";
      const icon = p.locked ? "✓" : p.needs_link ? "⚠" : "○";
      const tag = p.tag ? `<span class="intake-pillar-tag">${esc(p.tag)}</span>` : "";
      return `<div class="${cls}"><span><strong>${icon}</strong> ${esc(p.label || "")}</span>${tag}</div>`;
    })
    .join("");
  const gapHtml = b.intake_gap_pair
    ? `<div class="intake-gap-alert">⚠ Missing cause-and-effect link: <strong>${esc(b.intake_gap_pair)}</strong></div>`
    : "";
  const intakeHtml = b.oral_intake_active
    ? `<div class="intake-status-card">
        <div class="intake-top-row">
          <div>
            <strong style="color:#8ab4f8">Story Logic Check Before Panel 1 (${Number(b.intake_score || 0)}/4 connected)</strong>
            <div class="muted" style="font-size:.83rem;margin-top:2px">Every beat must connect by cause and effect (<em>because / so / but</em>)—not random things in a row.</div>
          </div>
          ${b.intake_can_start_writing ? `<button type="button" class="let-save-btn" data-jam-write="1">Start writing Panel 1 →</button>` : ""}
        </div>
        ${pillarsHtml ? `<div class="intake-pillar-grid">${pillarsHtml}</div>` : ""}
        ${gapHtml}
      </div>`
    : "";

  const stepsDone =
    (sp.beginning ? 1 : 0) + mbeats.length + (sp.end ? 1 : 0) + (b.panel_count || 0);
  const stepsGoal = (b.proj_kind === "epic_graphic_novel" || b.proj_kind === "story_jam_novel") ? Math.max(5, stepsDone + 1) : (b.target_panels || 4);
  const pct = Math.min(100, Math.round((stepsDone / Math.max(1, stepsGoal)) * 100));
  const progHtml = `<div class="book-prog"><div class="book-prog-fill" style="width:${pct}%"></div></div>`;

  const styles = Array.isArray(b.art_styles) ? b.art_styles : [];
  const showStyles = state.styleDrawerOpen === null ? (stepsDone === 0 && !b.oral_intake_active) : !!state.styleDrawerOpen;
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
        .map((p) =>
          renderComicPanelUnit({
            target: `panel:${p.number}`,
            badge: p.badge || `PANEL ${p.number || ""}`,
            src: p.src,
            status: p.status,
            caption: p.caption ?? "",
            dialogue: p.dialogue || [],
            verified: !!p.verified,
            canRemove: true,
          })
        )
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
    ${intakeHtml}
    ${spineHtml}
    ${codexLiveHtml}
    ${chHtml || '<div class="muted" style="padding:8px 2px">Tip: Click <b>💬 + Speech Bubble</b> or <b>✎ Caption</b> under any panel to add comic dialogue, shout bubbles, or edit captions!</div>'}`;
}

function renderComic(c) {
  const panels = (c.panels || [])
    .map((p, i) =>
      renderComicPanelUnit({
        target: `strip:${i}`,
        badge: `PANEL ${i + 1}`,
        src: p.src,
        status: p.status,
        caption: p.caption ?? "",
        dialogue: p.dialogue || [],
        verified: true,
        canRemove: false,
      })
    )
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
    case "tutor_clear":
      document.getElementById("tutor-" + m.turn)?.remove();
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
    case "tutor_mic":
      if (m.action === "on") showCenterMic(m);
      else stopCenterMic(false);
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
    case "open_comic_lettering":
      openLetteringState(m.target || "", m.tab || "bubble", {
        speaker: m.prefill_speaker || "",
        text: m.prefill_text || "",
        fix: m.fix || null,
      });
      break;
    case "comic_lettering_fix":
      if (state.lettering && (!m.target || state.lettering.target === m.target)) {
        state.lettering.fix = m.fix || null;
        refreshLetteringHost(state.lettering.target, true);
      } else {
        openLetteringState(m.target || "", m.mode === "caption" ? "caption" : "bubble", { fix: m.fix || null });
      }
      break;
    case "comic_lettering_saved":
      if (state.lettering && (!m.target || state.lettering.target === m.target)) {
        const tgt = state.lettering.target;
        state.lettering = null;
        refreshLetteringHost(tgt, false);
      }
      showRewardBadge(m.action === "set_caption" ? "✎ Comic Caption Updated!" : m.action === "delete_bubble" ? "Bubble Removed" : "💬 Speech Bubble Added!");
      break;
    case "lettering_voice_fill":
      if (m.text) {
        const tgt = m.target || state.lettering?.target || "";
        const curTab = state.lettering?.tab || "bubble";
        openLetteringState(tgt, curTab, {
          speaker: state.lettering?.speaker || "",
          text: curTab === "bubble" ? m.text : (state.lettering?.text || ""),
          caption: curTab === "caption" ? m.text : undefined,
          editBubbleId: state.lettering?.editBubbleId || "",
        });
      }
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
          let selStart = input.value.length;
          let selEnd = input.value.length;
          if (Array.isArray(m.select_range) && m.select_range.length === 2) {
            selStart = Math.max(0, Math.min(input.value.length, Number(m.select_range[0]) || 0));
            selEnd = Math.max(selStart, Math.min(input.value.length, Number(m.select_range[1]) || 0));
          } else if (m.select_word) {
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
    case "protective_bug":
      showProtectiveBug(m.code || "ERR-G42");
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

function showProtectiveBug(code) {
  state.ended = true;
  stopCenterMic(false);
  if (state.micOn) micStop();
  stopPlayback();
  try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (_) {}
  try { state.ws && state.ws.close(); } catch (_) {}
  $("app").hidden = true;
  $("setup").hidden = true;
  if ($("bugCode")) $("bugCode").textContent = `Error ${code || "ERR-G42"}`;
  $("bugScreen").hidden = false;
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
