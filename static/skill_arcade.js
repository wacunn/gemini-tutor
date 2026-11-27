// Skill Arcade — 6 Next-Gen Ontario Grade 3-4 Interactive Games (OLED Canvas2D + Yoga Stylus + WebAudio)

const PARAMS = new URLSearchParams(location.search);
const IS_SANDBOX = PARAMS.get("sandbox") === "1";
const IS_EMBEDDED = PARAMS.get("embedded") === "1" || window.self !== window.top;
const START_GAME = PARAMS.get("game") || "";

const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// --------------------------------------------------------------------------- Procedural WebAudio SFX

const SFX = (() => {
  let ctx = null;
  let muted = false;
  function ac() {
    if (muted) return null;
    if (!ctx) {
      const C = window.AudioContext || window.webkitAudioContext;
      if (C) ctx = new C();
    }
    if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  }
  function tone(freq, dur, type = "sine", vol = 0.14, freqEnd = null, delay = 0) {
    const c = ac();
    if (!c) return;
    const t0 = c.currentTime + delay;
    const osc = c.createOscillator();
    const g = c.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t0);
    if (freqEnd) osc.frequency.exponentialRampToValueAtTime(Math.max(30, freqEnd), t0 + dur);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.linearRampToValueAtTime(vol, t0 + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(g);
    g.connect(c.destination);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
  }
  return {
    get muted() { return muted; },
    toggle() { muted = !muted; return muted; },
    ok() {
      tone(523.25, 0.11, "triangle", 0.14);
      tone(659.25, 0.14, "triangle", 0.14, null, 0.07);
      tone(783.99, 0.2, "sine", 0.12, null, 0.14);
    },
    bad() {
      tone(210, 0.18, "sawtooth", 0.1, 130);
    },
    slice() {
      tone(980, 0.16, "sawtooth", 0.12, 240);
      tone(1320, 0.14, "sine", 0.1, 1760, 0.05);
    },
    hammer() {
      tone(220, 0.22, "triangle", 0.18, 95);
      tone(880, 0.28, "sine", 0.11, 660, 0.01);
      tone(1318, 0.22, "sine", 0.07, null, 0.03);
    },
    laser() {
      tone(840, 0.14, "square", 0.09, 190);
      tone(420, 0.12, "triangle", 0.1, 120, 0.04);
    },
    powerup() {
      [440, 554.37, 659.25, 880].forEach((f, i) => tone(f, 0.18, "triangle", 0.12, null, i * 0.055));
    },
    keyTick() { tone(620, 0.035, "triangle", 0.05, 500); },
    keyErr() { tone(165, 0.09, "sawtooth", 0.08, 120); },
    highlight() { tone(587.33, 0.12, "sine", 0.11, 880); },
    victory() {
      [523.25, 659.25, 783.99, 1046.5, 1318.5].forEach((f, i) => tone(f, 0.26, "triangle", 0.13, null, i * 0.08));
    },
  };
})();

// --------------------------------------------------------------------------- Ambient OLED Background & Shared FX Canvas

const FX = (() => {
  const bg = $("bgCanvas");
  const fx = $("fxCanvas");
  const bgCtx = bg.getContext("2d");
  const fxCtx = fx.getContext("2d");
  let W = 0, H = 0;
  const stars = [];
  const particles = [];
  const trails = [];
  const floats = [];

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth;
    H = window.innerHeight;
    for (const c of [bg, fx]) {
      c.width = Math.floor(W * dpr);
      c.height = Math.floor(H * dpr);
      c.style.width = W + "px";
      c.style.height = H + "px";
    }
    bgCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    fxCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  window.addEventListener("resize", resize);

  for (let i = 0; i < 65; i++) {
    stars.push({
      x: Math.random() * 1800,
      y: Math.random() * 1100,
      r: 0.7 + Math.random() * 1.8,
      vx: (Math.random() - 0.5) * 0.16,
      vy: -0.06 - Math.random() * 0.18,
      hue: [195, 270, 160, 38][i % 4],
      a: 0.2 + Math.random() * 0.5,
    });
  }

  function loop() {
    // Subtle dark nebula backdrop
    bgCtx.fillStyle = "#060913";
    bgCtx.fillRect(0, 0, W, H);
    const g1 = bgCtx.createRadialGradient(W * 0.18, H * 0.14, 10, W * 0.18, H * 0.14, W * 0.5);
    g1.addColorStop(0, "rgba(56, 189, 248, 0.08)");
    g1.addColorStop(1, "transparent");
    bgCtx.fillStyle = g1;
    bgCtx.fillRect(0, 0, W, H);

    const g2 = bgCtx.createRadialGradient(W * 0.85, H * 0.78, 10, W * 0.85, H * 0.78, W * 0.45);
    g2.addColorStop(0, "rgba(168, 85, 247, 0.08)");
    g2.addColorStop(1, "transparent");
    bgCtx.fillStyle = g2;
    bgCtx.fillRect(0, 0, W, H);

    for (const s of stars) {
      s.x += s.vx;
      s.y += s.vy;
      if (s.y < -10) { s.y = H + 10; s.x = Math.random() * W; }
      if (s.x < -10) s.x = W + 10;
      if (s.x > W + 10) s.x = -10;
      bgCtx.fillStyle = `hsla(${s.hue}, 90%, 72%, ${s.a})`;
      bgCtx.beginPath();
      bgCtx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      bgCtx.fill();
    }

    // Active FX layer
    fxCtx.clearRect(0, 0, W, H);
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.x += p.vx;
      p.y += p.vy;
      p.vy += p.g;
      p.life -= p.decay;
      if (p.life <= 0) { particles.splice(i, 1); continue; }
      fxCtx.save();
      fxCtx.globalAlpha = Math.max(0, p.life);
      fxCtx.fillStyle = p.color;
      fxCtx.shadowColor = p.color;
      fxCtx.shadowBlur = 10;
      fxCtx.beginPath();
      fxCtx.arc(p.x, p.y, p.r * p.life, 0, Math.PI * 2);
      fxCtx.fill();
      fxCtx.restore();
    }

    for (let i = trails.length - 1; i >= 0; i--) {
      const tr = trails[i];
      tr.life -= 0.06;
      if (tr.life <= 0) { trails.splice(i, 1); continue; }
      fxCtx.save();
      fxCtx.globalAlpha = tr.life;
      fxCtx.strokeStyle = tr.color;
      fxCtx.lineWidth = 6 * tr.life;
      fxCtx.lineCap = "round";
      fxCtx.shadowColor = tr.color;
      fxCtx.shadowBlur = 18;
      fxCtx.beginPath();
      tr.pts.forEach((pt, idx) => idx === 0 ? fxCtx.moveTo(pt.x, pt.y) : fxCtx.lineTo(pt.x, pt.y));
      fxCtx.stroke();
      fxCtx.restore();
    }

    for (let i = floats.length - 1; i >= 0; i--) {
      const f = floats[i];
      f.y -= 1.3;
      f.life -= 0.022;
      if (f.life <= 0) { floats.splice(i, 1); continue; }
      fxCtx.save();
      fxCtx.globalAlpha = Math.min(1, f.life * 1.4);
      fxCtx.font = "700 20px 'Google Sans', sans-serif";
      fxCtx.textAlign = "center";
      fxCtx.fillStyle = f.color;
      fxCtx.shadowColor = "rgba(0,0,0,0.85)";
      fxCtx.shadowBlur = 8;
      fxCtx.fillText(f.text, f.x, f.y);
      fxCtx.restore();
    }
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  return {
    burst(x, y, color = "#38bdf8", count = 26) {
      for (let i = 0; i < count; i++) {
        const ang = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.4;
        const spd = 2.4 + Math.random() * 6.5;
        particles.push({
          x, y,
          vx: Math.cos(ang) * spd,
          vy: Math.sin(ang) * spd - 1.5,
          g: 0.14,
          r: 2.5 + Math.random() * 4,
          color,
          life: 1,
          decay: 0.02 + Math.random() * 0.02,
        });
      }
    },
    burstEl(el, color = "#38bdf8", count = 24) {
      if (!el) return;
      const r = el.getBoundingClientRect();
      this.burst(r.left + r.width / 2, r.top + r.height / 2, color, count);
    },
    slash(pts, color = "#38bdf8") {
      if (pts.length >= 2) trails.push({ pts: pts.slice(), color, life: 1 });
    },
    floatText(x, y, text, color = "#facc15") {
      floats.push({ x, y, text, color, life: 1 });
    },
    floatEl(el, text, color = "#facc15") {
      if (!el) return;
      const r = el.getBoundingClientRect();
      this.floatText(r.left + r.width / 2, r.top + 8, text, color);
    },
  };
})();

// --------------------------------------------------------------------------- Global Arcade State & Lifecycle

const App = {
  hubData: null,
  currentGameId: null,
  cleanups: [],
  score: 0,
  combo: 0,
  startedAt: 0,
};

function addCleanup(fn) { App.cleanups.push(fn); }
function runCleanups() {
  while (App.cleanups.length) {
    try { App.cleanups.pop()(); } catch (_) {}
  }
}

function setHud({ visible = false, step = 1, total = 6, score = 0, combo = 0, title = "Skill Arcade" }) {
  $("saHudCenter").hidden = !visible;
  $("saBrandTitle").innerHTML = `<span class="sa-brand-dot"></span><span>${esc(title)}</span>`;
  $("saBackBtn").textContent = visible ? "← All 6 Games" : (IS_EMBEDDED ? "← Return to Tutor" : "← Back to Studio");
  if (!visible) return;
  const pct = Math.max(0, Math.min(100, (step / Math.max(1, total)) * 100));
  $("saProgFill").style.width = `${pct}%`;
  $("saProgLabel").textContent = `${Math.min(step, total)} / ${total}`;
  $("saScorePill").textContent = `${score} PTS`;
  if (combo >= 2) {
    $("saComboPill").hidden = false;
    $("saComboPill").textContent = `🔥 x${combo}`;
  } else {
    $("saComboPill").hidden = true;
  }
}

function addPoints(base, el = null, color = "#38bdf8") {
  App.combo += 1;
  const mult = Math.min(4, 1 + Math.floor((App.combo - 1) / 2));
  const pts = base * mult;
  App.score += pts;
  $("saScorePill").textContent = `${App.score} PTS`;
  if (App.combo >= 2) {
    $("saComboPill").hidden = false;
    $("saComboPill").textContent = `🔥 x${App.combo}`;
  }
  if (el) {
    FX.burstEl(el, color, 22);
    FX.floatEl(el, `+${pts}${App.combo >= 2 ? ` 🔥x${App.combo}` : ""}`, "#facc15");
  }
  return pts;
}

function resetCombo() {
  App.combo = 0;
  $("saComboPill").hidden = true;
}

function renderBankPill(arc) {
  const pill = $("saBankPill");
  if (!arc || !arc.visible) {
    pill.hidden = true;
    return;
  }
  const availMin = Math.floor((Number(arc.game_seconds_available) || 0) / 60);
  const chunkMin = Math.floor((Number(arc.committed_work_seconds) || 0) / 60);
  const mpp = Number(arc.minutes_per_point) || 15;
  pill.hidden = false;
  pill.textContent = arc.parent_override_active
    ? `🔓 Free Play · ${chunkMin}/${mpp}m`
    : (availMin > 0 ? `🎮 ${availMin}m ready · ${chunkMin}/${mpp}m` : `⭐ ${chunkMin}/${mpp}m toward game time`);
}

// --------------------------------------------------------------------------- Hub Loading & Rendering

async function loadHub() {
  runCleanups();
  App.currentGameId = null;
  $("saSummaryModal").hidden = true;
  $("saGameStage").hidden = true;
  $("saHubView").hidden = false;
  setHud({ visible: false, title: "Skill Arcade" });

  const r = await fetch(`/api/skill-games/hub?sandbox=${IS_SANDBOX ? 1 : 0}`);
  const d = await r.json();
  App.hubData = d;

  $("saSandboxTag").hidden = !IS_SANDBOX;
  $("saAiToggleWrap").hidden = !d.ai_available;
  renderBankPill(d.arcade);

  $("saHeroHeading").textContent = `Ready, ${d.child_name}? Pick a Mission`;
  $("saStatsStrip").innerHTML = `
    <div class="sa-stat-chip"><div class="v">Tier ${d.mastery_tier}</div><div class="k">Ontario Mastery</div></div>
    <div class="sa-stat-chip"><div class="v">${d.spelling_due}</div><div class="k">Spelling Due</div></div>
    <div class="sa-stat-chip"><div class="v">${d.total_runs}</div><div class="k">Missions Cleared</div></div>`;

  $("saGameGrid").innerHTML = d.games.map((g) => {
    const stars = [1, 2, 3].map((n) => `<span class="${g.mastery_stars >= n ? "" : "off"}">★</span>`).join("");
    const best = g.id === "typing_arena" && g.best_wpm > 0
      ? `Best: ${g.best_wpm} WPM`
      : (g.best_score > 0 ? `Best: ${g.best_score} pts (${g.best_accuracy}%)` : g.est_minutes);
    return `
      <button type="button" class="sa-card ${g.recommended ? "recommended" : ""}" data-launch="${esc(g.id)}"
        style="--card-accent:${g.accent};--card-glow:${g.glow}">
        <div class="sa-card-top">
          <div class="sa-card-icon">${g.icon}</div>
          ${g.recommended ? `<span class="sa-rec-badge">★ Recommended</span>` : `<span class="sa-tag">${esc(g.est_minutes)}</span>`}
        </div>
        <h2>${esc(g.title)}</h2>
        <div class="sa-card-sub">${esc(g.subtitle)}</div>
        <div class="sa-card-reason">▸ ${esc(g.reason)}</div>
        <div class="sa-card-tags">${(g.skill_badges || []).map((b) => `<span class="sa-tag">${esc(b)}</span>`).join("")}</div>
        <div class="sa-card-foot">
          <span>${esc(g.controls)}</span>
          <span style="display:flex;align-items:center;gap:8px"><span class="sa-stars">${stars}</span><span>${esc(best)}</span></span>
        </div>
      </button>`;
  }).join("");

  $("saGameGrid").querySelectorAll("[data-launch]").forEach((btn) => {
    btn.onclick = () => startGame(btn.dataset.launch, $("saUseAi").checked);
  });
}

async function startGame(gameId, useAi = false) {
  runCleanups();
  App.currentGameId = gameId;
  App.score = 0;
  App.combo = 0;
  App.startedAt = performance.now();

  $("saSummaryModal").hidden = true;
  $("saLoadingText").textContent = useAi
    ? "Gemini is crafting a fresh world-themed mission pack…"
    : "Loading your personalized mission…";
  $("saLoading").hidden = false;

  try {
    const r = await fetch("/api/skill-games/pack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: gameId, use_ai: useAi, sandbox: IS_SANDBOX ? 1 : 0 }),
    });
    const pack = await r.json();
    $("saLoading").hidden = true;
    $("saHubView").hidden = true;
    $("saGameStage").hidden = false;
    $("saGameStage").innerHTML = "";
    setHud({ visible: true, step: 1, total: pack.items.length, score: 0, combo: 0, title: pack.game.title });

    if (gameId === "sentence_surgery") runSentenceSurgery(pack);
    else if (gameId === "word_forge") runWordForge(pack);
    else if (gameId === "homophone_asteroids") runHomophoneAsteroids(pack);
    else if (gameId === "sentence_stretch") runSentenceStretch(pack);
    else if (gameId === "typing_arena") runTypingArena(pack);
    else if (gameId === "clue_detective") runClueDetective(pack);
  } catch (err) {
    $("saLoading").hidden = true;
    alert("Could not load mission: " + err);
    loadHub();
  }
}

async function finishGame(result) {
  runCleanups();
  const elapsedSec = Math.max(5, Math.round((performance.now() - App.startedAt) / 1000));
  const payload = {
    game_id: App.currentGameId,
    score: App.score,
    correct: result.correct,
    total: result.total,
    active_seconds: elapsedSec,
    wpm: result.wpm || 0,
    cpm: result.cpm || 0,
    production_passed: !!result.production_passed,
    production_sentence: result.production_sentence || "",
    word_results: result.word_results || [],
    skill_hits: result.skill_hits || {},
    sandbox: IS_SANDBOX ? 1 : 0,
  };

  const r = await fetch("/api/skill-games/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const d = await r.json();
  SFX.victory();
  FX.burst(window.innerWidth * 0.5, window.innerHeight * 0.3, "#facc15", 45);
  FX.burst(window.innerWidth * 0.35, window.innerHeight * 0.35, "#38bdf8", 32);
  FX.burst(window.innerWidth * 0.65, window.innerHeight * 0.35, "#10b981", 32);

  renderBankPill(d.arcade);
  if (IS_EMBEDDED) {
    try { window.parent.postMessage({ __skillArcadeUpdated: d }, "*"); } catch (_) {}
  }

  const stars = [1, 2, 3].map((n) => `<span style="opacity:${d.stars >= n ? 1 : 0.22}">★</span>`).join("");
  $("saSumStars").innerHTML = stars;
  $("saSumTitle").textContent = d.stars === 3 ? "Flawless Mastery!" : (d.stars === 2 ? "Strong Mission!" : "Good Practice Run!");

  const m3 = payload.wpm > 0
    ? `<div class="sa-sum-metric"><div class="v">${payload.wpm} WPM</div><div class="k">Speed</div></div>`
    : `<div class="sa-sum-metric"><div class="v">${payload.correct}/${payload.total}</div><div class="k">Hits</div></div>`;
  $("saSumMetrics").innerHTML = `
    <div class="sa-sum-metric"><div class="v">${d.score}</div><div class="k">Score</div></div>
    <div class="sa-sum-metric"><div class="v">${d.accuracy}%</div><div class="k">Accuracy</div></div>
    ${m3}`;

  const rew = $("saSumReward");
  if (d.arcade_reward?.visible && d.arcade_reward?.message) {
    rew.hidden = false;
    rew.textContent = d.arcade_reward.message;
  } else {
    rew.hidden = true;
  }

  const lines = [];
  if (d.srs_updates?.length) {
    const up = d.srs_updates.map((u) => `<b>${esc(u.word)}</b> → Box ${u.box}/5 ${u.first_try ? "✓" : "(review tomorrow)"}`).join(" · ");
    lines.push(`<div>🧠 <b>Leitner Spelling Deck:</b> ${up}</div>`);
  }
  if (d.skills_boosted?.length) {
    lines.push(`<div>📈 <b>Ontario Report Card Boosted:</b> ${d.skills_boosted.map((s) => `<span class="sa-tag">${esc(s)}</span>`).join(" ")}</div>`);
  }
  if (payload.production_sentence) {
    lines.push(`<div>✍️ <b>Your Boss Sentence:</b> “${esc(payload.production_sentence)}”</div>`);
  }
  if (!lines.length) {
    lines.push(`<div>📊 Progress saved to your Ontario Grade 3–4 Report Card (Tier ${d.mastery_tier}).</div>`);
  }
  $("saSumDetails").innerHTML = lines.join("");

  $("saPlayAiBtn").hidden = !(App.hubData?.ai_available && ["homophone_asteroids", "typing_arena", "sentence_stretch", "clue_detective"].includes(App.currentGameId));
  $("saSummaryModal").hidden = false;
}

// ===========================================================================
// GAME 1: ⚔️ SENTENCE SURGERY (Stylus Slash Run-Ons + Fragments + Dialogue)
// ===========================================================================

function runSentenceSurgery(pack) {
  const stage = $("saGameStage");
  const items = pack.items;
  let idx = 0;
  let correct = 0;
  const skillHits = {};

  function trackSkill(sid, ok) {
    skillHits[sid] = skillHits[sid] || { correct: 0, total: 0 };
    skillHits[sid].total += 1;
    if (ok) skillHits[sid].correct += 1;
  }

  function renderStep() {
    if (idx >= items.length) {
      finishGame({ correct, total: items.length, skill_hits: skillHits, production_passed: true });
      return;
    }
    const it = items[idx];
    setHud({ visible: true, step: idx + 1, total: items.length, score: App.score, combo: App.combo, title: "Sentence Surgery" });

    if (it.mode === "runon") {
      stage.innerHTML = `
        <div class="sa-panel">
          <div class="sa-mission-banner">
            <span class="sa-mission-tag">✂️ STYLUS SLASH · RUN-ON REPAIR</span>
            <span class="sa-tag">Swipe your Lenovo pen or tap a glowing gap!</span>
          </div>
          <div class="sa-prompt-text">${esc(it.prompt)}</div>
        </div>
        <div class="ss-slash-arena" id="ssArena">
          <canvas class="ss-slash-canvas" id="ssSlashCanvas"></canvas>
          <div class="ss-word-row" id="ssWordRow"></div>
        </div>
        <div class="sa-feedback idle" id="ssFb">Drag a slash right across the spot where Sentence 1 ends and Sentence 2 begins!</div>`;

      const row = $("ssWordRow");
      it.words.forEach((w, wi) => {
        const sp = document.createElement("span");
        sp.className = "ss-word";
        sp.textContent = w;
        sp.dataset.wi = wi;
        row.appendChild(sp);
        if (wi < it.words.length - 1) {
          const gap = document.createElement("button");
          gap.type = "button";
          gap.className = "ss-gap";
          gap.dataset.gap = wi;
          gap.title = "Slash or tap here";
          gap.textContent = "┆";
          gap.onclick = () => checkSlice(wi, gap);
          row.appendChild(gap);
        }
      });

      let locked = false;
      let missed = false;

      function checkSlice(gapIdx, gapEl) {
        if (locked) return;
        if (gapIdx === it.split_after) {
          locked = true;
          SFX.slice();
          gapEl.classList.add("sliced");
          gapEl.textContent = ". |";
          const nextWord = row.querySelector(`[data-wi="${gapIdx + 1}"]`);
          if (nextWord) {
            nextWord.textContent = nextWord.textContent.charAt(0).toUpperCase() + nextWord.textContent.slice(1);
            nextWord.style.borderColor = "#10b981";
            nextWord.style.color = "#6ee7b7";
          }
          if (!missed) correct += 1;
          trackSkill(it.skill, !missed);
          addPoints(missed ? 60 : 120, gapEl, "#38bdf8");
          const fb = $("ssFb");
          fb.className = "sa-feedback ok";
          fb.innerHTML = `<span>✂️ <b>Clean slice!</b> ${esc(it.fixed)} — ${esc(it.explain)}</span><button type="button" class="sa-btn emerald" id="ssNextBtn">Next →</button>`;
          $("ssNextBtn").onclick = () => { idx += 1; renderStep(); };
        } else {
          missed = true;
          resetCombo();
          SFX.bad();
          gapEl.style.borderColor = "#fb7185";
          setTimeout(() => { gapEl.style.borderColor = ""; }, 400);
          const fb = $("ssFb");
          fb.className = "sa-feedback bad";
          fb.textContent = "Not quite there — read the first part out loud to hear where the first complete thought finishes!";
        }
      }

      // Wire real PointerEvent stylus / mouse slash gesture across the arena!
      const arena = $("ssArena");
      const cv = $("ssSlashCanvas");
      const c2 = cv.getContext("2d");
      function sizeCv() {
        const r = arena.getBoundingClientRect();
        cv.width = Math.max(1, Math.floor(r.width));
        cv.height = Math.max(1, Math.floor(r.height));
      }
      sizeCv();
      let drawing = false;
      let pts = [];
      let screenPts = [];

      const onDown = (e) => {
        if (locked) return;
        drawing = true;
        const r = arena.getBoundingClientRect();
        pts = [{ x: e.clientX - r.left, y: e.clientY - r.top }];
        screenPts = [{ x: e.clientX, y: e.clientY }];
        cv.setPointerCapture?.(e.pointerId);
      };
      const onMove = (e) => {
        if (!drawing || locked) return;
        const r = arena.getBoundingClientRect();
        const evts = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
        for (const ev of evts) {
          pts.push({ x: ev.clientX - r.left, y: ev.clientY - r.top });
          screenPts.push({ x: ev.clientX, y: ev.clientY });
        }
        c2.clearRect(0, 0, cv.width, cv.height);
        c2.strokeStyle = "#38bdf8";
        c2.lineWidth = 4;
        c2.lineCap = "round";
        c2.shadowColor = "#38bdf8";
        c2.shadowBlur = 14;
        c2.beginPath();
        pts.forEach((p, i) => i === 0 ? c2.moveTo(p.x, p.y) : c2.lineTo(p.x, p.y));
        c2.stroke();
      };
      const onUp = () => {
        if (!drawing) return;
        drawing = false;
        c2.clearRect(0, 0, cv.width, cv.height);
        if (screenPts.length >= 2) {
          FX.slash(screenPts, "#38bdf8");
          // Find which gap bounding box the slash crossed (or tapped closest to)
          const gaps = [...row.querySelectorAll(".ss-gap")];
          let bestGap = null;
          let bestDist = 42;
          for (const g of gaps) {
            const gr = g.getBoundingClientRect();
            const gx = gr.left + gr.width / 2;
            const gy = gr.top + gr.height / 2;
            for (const sp of screenPts) {
              const d = Math.hypot(sp.x - gx, sp.y - gy);
              if (d < bestDist) { bestDist = d; bestGap = g; }
            }
          }
          if (bestGap) checkSlice(Number(bestGap.dataset.gap), bestGap);
        }
        pts = [];
        screenPts = [];
      };

      cv.addEventListener("pointerdown", onDown);
      cv.addEventListener("pointermove", onMove);
      cv.addEventListener("pointerup", onUp);
      cv.addEventListener("pointercancel", onUp);
    } else if (it.mode === "fragment") {
      stage.innerHTML = `
        <div class="sa-panel">
          <div class="sa-mission-banner">
            <span class="sa-mission-tag">🔧 FRAGMENT CIRCUIT REPAIR</span>
            <span class="sa-tag">Missing: ${esc(it.missing)}</span>
          </div>
          <div class="sa-prompt-text">${esc(it.prompt)}</div>
          <div style="margin-top:14px;padding:16px 18px;border-radius:14px;background:rgba(251,113,133,0.12);border:1.5px dashed #fb7185;font-size:1.25rem;font-weight:700;color:#fecdd3">
            ⚠️ “${esc(it.broken)}”
          </div>
        </div>
        <div class="sa-choice-list" id="ssChoices"></div>
        <div class="sa-feedback idle" id="ssFb">Choose the repair that creates a full Who + Does What sentence!</div>`;

      let locked = false;
      let missed = false;
      const box = $("ssChoices");
      it.choices.forEach((ch) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "sa-choice-btn";
        b.textContent = ch.text;
        b.onclick = () => {
          if (locked) return;
          if (ch.ok) {
            locked = true;
            b.classList.add("ok");
            SFX.ok();
            if (!missed) correct += 1;
            trackSkill(it.skill, !missed);
            addPoints(missed ? 60 : 120, b, "#10b981");
            const fb = $("ssFb");
            fb.className = "sa-feedback ok";
            fb.innerHTML = `<span>⚡ <b>Circuit Repaired!</b> ${esc(it.explain)}</span><button type="button" class="sa-btn emerald" id="ssNextBtn">Next →</button>`;
            $("ssNextBtn").onclick = () => { idx += 1; renderStep(); };
          } else {
            missed = true;
            resetCombo();
            b.classList.add("bad");
            SFX.bad();
            const fb = $("ssFb");
            fb.className = "sa-feedback bad";
            fb.textContent = ch.why || "Still a fragment — check who is doing what!";
          }
        };
        box.appendChild(b);
      });
    } else {
      // Mechanics / Dialogue token tap repair
      const bugTotal = it.tokens.filter((t) => t.bug).length;
      let bugsFixed = 0;
      let cleanTaps = 0;
      stage.innerHTML = `
        <div class="sa-panel">
          <div class="sa-mission-banner">
            <span class="sa-mission-tag">💬 MECHANICS &amp; DIALOGUE STAMP</span>
            <span class="sa-tag" id="ssBugCount">Bugs left: ${bugTotal}</span>
          </div>
          <div class="sa-prompt-text">${esc(it.prompt)}</div>
        </div>
        <div class="sa-panel" style="display:flex;flex-wrap:wrap;gap:10px;justify-content:center;padding:28px 20px" id="ssTokenWrap"></div>
        <div class="sa-feedback idle" id="ssFb">Tap each word that needs a capital letter, apostrophe, quotation mark, comma, or end mark!</div>`;

      const wrap = $("ssTokenWrap");
      it.tokens.forEach((tk) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "ss-token-btn";
        b.textContent = tk.raw;
        let done = false;
        b.onclick = () => {
          if (done) return;
          if (tk.bug) {
            done = true;
            bugsFixed += 1;
            b.textContent = tk.fix;
            b.classList.add("fixed");
            SFX.ok();
            addPoints(50, b, "#10b981");
            $("ssBugCount").textContent = `Bugs left: ${bugTotal - bugsFixed}`;
            const fb = $("ssFb");
            fb.className = "sa-feedback ok";
            if (bugsFixed >= bugTotal) {
              const cleanRun = cleanTaps === 0;
              if (cleanRun) correct += 1;
              trackSkill(it.skill, cleanRun);
              fb.innerHTML = `<span>✅ <b>All bugs stamped!</b> ${esc(it.explain)}</span><button type="button" class="sa-btn emerald" id="ssNextBtn">Next →</button>`;
              $("ssNextBtn").onclick = () => { idx += 1; renderStep(); };
            } else {
              fb.textContent = `Fixed! ${tk.hint || ""} (${bugTotal - bugsFixed} bug${bugTotal - bugsFixed === 1 ? "" : "s"} left!)`;
            }
          } else {
            cleanTaps += 1;
            resetCombo();
            SFX.bad();
            b.classList.add("shake");
            setTimeout(() => b.classList.remove("shake"), 360);
            const fb = $("ssFb");
            fb.className = "sa-feedback bad";
            fb.textContent = `"${tk.raw}" is already clean! Check capitals, contractions, quotes, or the end of the sentence.`;
          }
        };
        wrap.appendChild(b);
      });
    }
  }
  renderStep();
}

// ===========================================================================
// GAME 2: 🔥 WORD FORGE (Obsidian Anvil + Morphology + Cover-Copy-Compare SRS)
// ===========================================================================

function runWordForge(pack) {
  const stage = $("saGameStage");
  const items = pack.items;
  let idx = 0;
  let correct = 0;
  const wordResults = [];
  let forgedCount = 0;
  let hammerFlash = 0;

  stage.innerHTML = `
    <div class="wf-canvas-wrap"><canvas id="wfCanvas"></canvas></div>
    <div class="sa-panel" id="wfBody"></div>
    <div class="sa-feedback idle" id="wfFb">Snap the right Prefix + Base + Suffix runes onto the anvil!</div>`;

  // Animated 60fps Canvas2D Obsidian Forge + Relic Assembly
  const cv = $("wfCanvas");
  const ctx = cv.getContext("2d");
  const embers = Array.from({ length: 34 }, () => ({
    x: Math.random(),
    y: Math.random(),
    vy: 0.004 + Math.random() * 0.008,
    r: 1.5 + Math.random() * 2.8,
    a: 0.4 + Math.random() * 0.6,
  }));
  let rafId = 0;
  function drawForge() {
    const r = cv.parentElement.getBoundingClientRect();
    if (cv.width !== Math.floor(r.width) || cv.height !== Math.floor(r.height)) {
      cv.width = Math.max(1, Math.floor(r.width));
      cv.height = Math.max(1, Math.floor(r.height));
    }
    const W = cv.width, H = cv.height;
    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, "#0b0914");
    g.addColorStop(0.65, "#1a0e14");
    g.addColorStop(1, "#3b130a");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    // Molten furnace glow
    const glow = ctx.createRadialGradient(W * 0.5, H * 0.95, 10, W * 0.5, H * 0.95, W * 0.42);
    glow.addColorStop(0, `rgba(249, 115, 22, ${0.45 + hammerFlash * 0.4})`);
    glow.addColorStop(1, "transparent");
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, W, H);

    // Rising embers
    for (const e of embers) {
      e.y -= e.vy * (1 + hammerFlash * 3);
      if (e.y < 0) { e.y = 1.05; e.x = 0.15 + Math.random() * 0.7; }
      ctx.fillStyle = `rgba(251, 146, 60, ${e.a * e.y})`;
      ctx.beginPath();
      ctx.arc(e.x * W, e.y * H, e.r, 0, Math.PI * 2);
      ctx.fill();
    }

    // Enchanted Diamond Pickaxe / Relic progress segments
    const segs = items.length;
    const cx = W * 0.5, cy = H * 0.48;
    const barW = Math.min(460, W - 80);
    const sx = cx - barW / 2;
    ctx.font = "700 13px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#fdba74";
    ctx.textAlign = "center";
    ctx.fillText(`ENCHANTED RELIC FORGE · ${forgedCount} / ${segs} RUNES LOCKED`, cx, 26);

    for (let i = 0; i < segs; i++) {
      const sw = (barW - (segs - 1) * 10) / segs;
      const bx = sx + i * (sw + 10);
      const lit = i < forgedCount;
      ctx.save();
      ctx.fillStyle = lit ? "#22d3ee" : "rgba(51, 65, 85, 0.55)";
      ctx.strokeStyle = lit ? "#a5f3fc" : "rgba(148, 163, 184, 0.3)";
      ctx.lineWidth = 2;
      if (lit) { ctx.shadowColor = "#22d3ee"; ctx.shadowBlur = 18; }
      ctx.beginPath();
      ctx.roundRect(bx, cy - 18, sw, 36, 10);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = lit ? "#060913" : "#64748b";
      ctx.font = "700 15px 'Google Sans', sans-serif";
      ctx.fillText(lit ? "💎" : `${i + 1}`, bx + sw / 2, cy + 5);
      ctx.restore();
    }

    // Anvil silhouette at bottom
    ctx.fillStyle = "#1e293b";
    ctx.beginPath();
    ctx.moveTo(cx - 80, H - 12);
    ctx.lineTo(cx + 80, H - 12);
    ctx.lineTo(cx + 55, H - 34);
    ctx.lineTo(cx + 95, H - 52);
    ctx.lineTo(cx - 95, H - 52);
    ctx.lineTo(cx - 55, H - 34);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = hammerFlash > 0.05 ? "#facc15" : "rgba(249, 115, 22, 0.45)";
    ctx.lineWidth = 2;
    ctx.stroke();

    hammerFlash *= 0.9;
    rafId = requestAnimationFrame(drawForge);
  }
  rafId = requestAnimationFrame(drawForge);
  addCleanup(() => cancelAnimationFrame(rafId));

  const RULES = [
    { id: "keep", label: "Keep Base Clean" },
    { id: "double", label: "Double Consonant (1-1-1)" },
    { id: "drop_e", label: "Drop Silent -e" },
    { id: "y_to_i", label: "Change y → i" },
  ];

  function renderWord() {
    if (idx >= items.length) {
      finishGame({ correct, total: items.length, word_results: wordResults, production_passed: true });
      return;
    }
    const it = items[idx];
    setHud({ visible: true, step: idx + 1, total: items.length, score: App.score, combo: App.combo, title: "Word Forge" });
    const body = $("wfBody");
    const fb = $("wfFb");
    fb.className = "sa-feedback idle";
    fb.textContent = "Step 1: Snap the glowing morpheme runes together!";

    const neededParts = [];
    if (it.prefix) neededParts.push({ part: "prefix", label: "Prefix" });
    neededParts.push({ part: "base", label: "Base" });
    if (it.suffix) neededParts.push({ part: "suffix", label: "Suffix" });
    const filled = {};

    body.innerHTML = `
      <div class="sa-mission-banner">
        <span class="sa-mission-tag">🔥 ${esc(it.unit)}</span>
        ${it.from_deck ? `<span class="sa-tag" style="color:#fdba74;border:1px solid rgba(249,115,22,0.4)">Leitner Box ${it.box}/5</span>` : ""}
      </div>
      <div class="wf-anvil-slots" id="wfSlots"></div>
      <div class="wf-rune-tray" id="wfTray"></div>
      <div id="wfStep2" hidden></div>`;

    function drawSlots() {
      $("wfSlots").innerHTML = neededParts.map((p, pi) => {
        const val = filled[p.part];
        return `${pi > 0 ? '<span class="wf-plus">+</span>' : ""}<div class="wf-slot ${val ? "filled" : ""}">${esc(val || p.label)}</div>`;
      }).join("");
    }
    drawSlots();

    const tray = $("wfTray");
    it.tiles.forEach((tile) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "wf-rune";
      b.textContent = tile.text;
      b.onclick = () => {
        if (!tile.correct) {
          resetCombo();
          SFX.bad();
          b.style.borderColor = "#fb7185";
          fb.className = "sa-feedback bad";
          fb.textContent = `Not '${tile.text}' — look at the other ${tile.part} rune!`;
          return;
        }
        filled[tile.part] = tile.text;
        b.classList.add("used");
        SFX.hammer();
        hammerFlash = 0.7;
        FX.burstEl(b, "#f97316", 16);
        drawSlots();
        if (neededParts.every((p) => filled[p.part])) {
          showRulePick();
        }
      };
      tray.appendChild(b);
    });

    function showRulePick() {
      const s2 = $("wfStep2");
      s2.hidden = false;
      fb.className = "sa-feedback idle";
      fb.textContent = "Step 2: Which spelling rule fuses these runes?";
      s2.innerHTML = `
        <div style="text-align:center;font-weight:600;color:#fed7aa;margin-bottom:8px">Choose the Forge Rule before we drop the furnace shield:</div>
        <div class="wf-rule-row" id="wfRuleRow"></div>`;
      RULES.forEach((rl) => {
        const rb = document.createElement("button");
        rb.type = "button";
        rb.className = "sa-btn ghost";
        rb.style.padding = "12px";
        rb.textContent = rl.label;
        rb.onclick = () => {
          if (rl.id === it.rule) {
            SFX.powerup();
            addPoints(40, rb, "#f97316");
            showMemoryStrike();
          } else {
            resetCombo();
            SFX.bad();
            rb.style.borderColor = "#fb7185";
            fb.className = "sa-feedback bad";
            fb.textContent = `Hint: ${it.note}`;
          }
        };
        $("wfRuleRow").appendChild(rb);
      });
    }

    function showMemoryStrike() {
      // Cover-Copy-Compare: hide the runes and spell the fused word from memory!
      $("wfSlots").hidden = true;
      $("wfTray").hidden = true;
      const s2 = $("wfStep2");
      s2.innerHTML = `
        <div class="wf-memory-box">
          <div style="font-weight:700;color:#fdba74">🔒 MEMORY FORGE — Runes Hidden!</div>
          <div style="font-size:0.9rem;color:#cbd5e1;text-align:center">${esc(it.note)}</div>
          <input type="text" id="wfMemInput" class="wf-input" placeholder="Type fused word…" autocomplete="off" spellcheck="false" />
          <div class="wf-diff" id="wfDiff"></div>
          <button type="button" class="sa-btn primary" id="wfStrikeBtn">⚒️ Strike the Anvil!</button>
        </div>`;
      fb.className = "sa-feedback idle";
      fb.textContent = "Step 3: Type the fused word cleanly from memory to lock it in your Leitner deck!";

      const inp = $("wfMemInput");
      inp.focus();
      let hadMiss = false;

      const submitWord = () => {
        const typed = inp.value.trim().toLowerCase();
        if (!typed) return;
        if (typed === it.word.toLowerCase()) {
          SFX.hammer();
          hammerFlash = 1.0;
          forgedCount += 1;
          if (!hadMiss) correct += 1;
          wordResults.push({ word: it.word, first_try: !hadMiss, wrote: typed });
          addPoints(hadMiss ? 60 : 140, inp, "#22d3ee");
          fb.className = "sa-feedback ok";
          fb.innerHTML = `<span>💎 <b>FORGED: ${esc(it.word)}!</b> ${!hadMiss ? "First-try mastery — Leitner box upgraded!" : "Clean fix — locked in for review!"}</span><button type="button" class="sa-btn emerald" id="wfNextBtn">Next Rune →</button>`;
          $("wfStrikeBtn").disabled = true;
          inp.disabled = true;
          $("wfNextBtn").onclick = () => { idx += 1; renderWord(); };
        } else {
          hadMiss = true;
          resetCombo();
          SFX.bad();
          // Show exact letter-by-letter comparison so the child learns the exact letter!
          const target = it.word.toLowerCase();
          let diffHtml = "";
          for (let i = 0; i < target.length; i++) {
            const okChar = typed[i] === target[i];
            diffHtml += `<span class="${okChar ? "ok" : "miss"}">${esc(target[i])}</span>`;
          }
          $("wfDiff").innerHTML = diffHtml;
          fb.className = "sa-feedback bad";
          fb.textContent = "Look at the underlined letter(s) above, then type the full word cleanly!";
          inp.value = "";
          inp.focus();
        }
      };

      $("wfStrikeBtn").onclick = submitWord;
      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); submitWord(); }
      });
    }
  }
  renderWord();
}

// ===========================================================================
// GAME 3: ☄️ HOMOPHONE & VERB ASTEROIDS (60fps Canvas2D Turret + Boss Sentence)
// ===========================================================================

function runHomophoneAsteroids(pack) {
  const stage = $("saGameStage");
  const items = pack.items;
  let wave = 0;
  let correct = 0;
  let waveMissed = false;
  const trickyWords = [];
  const skillHits = {};

  stage.innerHTML = `
    <div class="ast-hud" id="astHud">Loading radar…</div>
    <div class="ast-canvas-wrap" id="astWrap"><canvas id="astCanvas"></canvas></div>
    <div id="astBossArea" hidden></div>
    <div class="sa-feedback idle" id="astFb">Tap the right asteroid or press <b>1</b>, <b>2</b>, or <b>3</b> to fire the orbital plasma cannon!</div>`;

  const cv = $("astCanvas");
  const ctx = cv.getContext("2d");
  let W = 800, H = 390;
  let rocks = [];
  let beams = [];
  let shards = [];
  let turretAngle = -Math.PI / 2;
  let shieldFlash = 0;
  let rafId = 0;
  let active = true;
  let bossMode = false;

  const starField = Array.from({ length: 70 }, () => ({
    x: Math.random(), y: Math.random(), s: 0.8 + Math.random() * 1.8, v: 0.0008 + Math.random() * 0.0018,
  }));

  function sizeCanvas() {
    const r = $("astWrap").getBoundingClientRect();
    W = Math.max(300, Math.floor(r.width));
    H = Math.max(280, Math.floor(r.height));
    cv.width = W;
    cv.height = H;
  }
  sizeCanvas();

  function spawnWave() {
    if (wave >= items.length) {
      enterBossWave();
      return;
    }
    waveMissed = false;
    const it = items[wave];
    setHud({ visible: true, step: wave + 1, total: items.length + 1, score: App.score, combo: App.combo, title: "Homophone & Verb Asteroids" });
    const parts = it.sentence.split("___");
    $("astHud").innerHTML = `${esc(parts[0] || "")}<span class="ast-blank">?</span>${esc(parts[1] || "")}`;

    const lanes = [W * 0.22, W * 0.5, W * 0.78];
    rocks = it.options.map((opt, i) => ({
      idx: i,
      word: opt,
      ok: opt === it.answer,
      x: lanes[i],
      y: 44 + (i === 1 ? -18 : 8),
      r: 46,
      vy: 0.36 + Math.min(0.28, wave * 0.03),
      rot: Math.random() * Math.PI * 2,
      vrot: (Math.random() - 0.5) * 0.015,
      verts: Array.from({ length: 9 }, (_, vi) => 0.82 + ((vi * 17 + i * 7) % 5) * 0.06),
      alive: true,
      redFlash: 0,
    }));
  }

  function shootRock(rockIdx) {
    if (!active || bossMode) return;
    const rock = rocks[rockIdx];
    if (!rock || !rock.alive) return;
    const it = items[wave];
    const tx = W / 2, ty = H - 36;
    turretAngle = Math.atan2(rock.y - ty, rock.x - tx);
    beams.push({ x1: tx, y1: ty, x2: rock.x, y2: rock.y, color: rock.ok ? "#38bdf8" : "#fb7185", life: 1 });

    if (rock.ok) {
      rock.alive = false;
      SFX.laser();
      // Shatter into neon shards
      for (let k = 0; k < 22; k++) {
        const a = Math.random() * Math.PI * 2;
        const sp = 2 + Math.random() * 5.5;
        shards.push({ x: rock.x, y: rock.y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp, r: 3 + Math.random() * 5, color: "#c084fc", life: 1 });
      }
      if (!waveMissed) correct += 1;
      else trickyWords.push(it.answer);
      skillHits[it.skill] = skillHits[it.skill] || { correct: 0, total: 0 };
      skillHits[it.skill].total += 1;
      if (!waveMissed) skillHits[it.skill].correct += 1;

      addPoints(waveMissed ? 60 : 120, $("astHud"), "#a855f7");
      const fb = $("astFb");
      fb.className = "sa-feedback ok";
      fb.textContent = `💥 Direct Hit! ${it.explain}`;
      const parts = it.sentence.split("___");
      $("astHud").innerHTML = `${esc(parts[0] || "")}<span class="ast-blank" style="border-color:#10b981;color:#6ee7b7">${esc(it.answer)}</span>${esc(parts[1] || "")}`;
      rocks.forEach((r) => { r.alive = false; });
      setTimeout(() => { wave += 1; spawnWave(); }, 950);
    } else {
      waveMissed = true;
      rock.redFlash = 1;
      resetCombo();
      SFX.bad();
      const fb = $("astFb");
      fb.className = "sa-feedback bad";
      fb.textContent = `Shield deflection! "${rock.word}" doesn't fit here — read the sentence clues carefully!`;
    }
  }

  function enterBossWave() {
    bossMode = true;
    const bossWord = trickyWords[0] || items[items.length - 1].answer;
    setHud({ visible: true, step: items.length + 1, total: items.length + 1, score: App.score, combo: App.combo, title: "BOSS WAVE · Dreadnought" });
    $("astWrap").hidden = true;
    $("astHud").innerHTML = `👾 <b>DREADNOUGHT BOSS SHIELD ACTIVE!</b> Use the word <span class="ast-blank">${esc(bossWord)}</span> in your own complete sentence!`;
    const boss = $("astBossArea");
    boss.hidden = false;
    boss.innerHTML = `
      <div class="boss-box">
        <div style="font-weight:700;color:#e9d5ff;font-size:1.05rem">⚡ Type 1 Homework-Standard sentence (Capital letter + end mark + “${esc(bossWord)}”) to vaporize the Boss!</div>
        <input type="text" id="astBossInput" class="sa-sentence-input" placeholder="Write your boss counter-attack sentence here…" autocomplete="off" />
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <button type="button" class="sa-btn primary" id="astBossFire">🚀 Fire Orbital Cannon!</button>
        </div>
      </div>`;
    const inp = $("astBossInput");
    inp.focus();
    const fire = async () => {
      const txt = inp.value.trim();
      if (!txt) return;
      const r = await fetch("/api/skill-games/check-sentence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: txt, required_word: bossWord, require_because: false }),
      });
      const chk = await r.json();
      const fb = $("astFb");
      if (chk.ok) {
        SFX.powerup();
        addPoints(250, inp, "#a855f7");
        fb.className = "sa-feedback ok";
        fb.textContent = "💥 BOSS VAPORIZED! Awesome original sentence!";
        setTimeout(() => {
          finishGame({
            correct: correct + 1,
            total: items.length + 1,
            production_passed: true,
            production_sentence: txt,
            skill_hits: skillHits,
          });
        }, 700);
      } else {
        SFX.bad();
        fb.className = "sa-feedback bad";
        fb.textContent = chk.feedback;
      }
    };
    $("astBossFire").onclick = fire;
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); fire(); } });
  }

  function loop() {
    if (!active) return;
    sizeCanvas();
    ctx.fillStyle = "#040610";
    ctx.fillRect(0, 0, W, H);

    // Parallax stars
    for (const s of starField) {
      s.y += s.v;
      if (s.y > 1) { s.y = 0; s.x = Math.random(); }
      ctx.fillStyle = "rgba(226, 232, 240, 0.55)";
      ctx.fillRect(s.x * W, s.y * H, s.s, s.s);
    }

    // Shield dome at bottom
    ctx.save();
    ctx.strokeStyle = shieldFlash > 0.05 ? "#fb7185" : "rgba(56, 189, 248, 0.45)";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(W / 2, H + 110, 185, Math.PI * 1.15, Math.PI * 1.85);
    ctx.stroke();
    ctx.restore();
    shieldFlash *= 0.92;

    // Asteroids
    for (const rk of rocks) {
      if (!rk.alive) continue;
      rk.y += rk.vy;
      rk.rot += rk.vrot;
      if (rk.y > H - 72) {
        // Bounce safely back to top so ADHD focus isn't punished by sudden game-over!
        rk.y = 32;
        shieldFlash = 0.85;
      }
      ctx.save();
      ctx.translate(rk.x, rk.y);
      ctx.save();
      ctx.rotate(rk.rot);
      ctx.beginPath();
      rk.verts.forEach((v, vi) => {
        const a = (Math.PI * 2 * vi) / rk.verts.length;
        const px = Math.cos(a) * rk.r * v;
        const py = Math.sin(a) * rk.r * v;
        if (vi === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      });
      ctx.closePath();
      ctx.fillStyle = rk.redFlash > 0.1 ? "rgba(251,113,133,0.32)" : "rgba(30, 27, 75, 0.92)";
      ctx.strokeStyle = rk.redFlash > 0.1 ? "#fb7185" : "#a855f7";
      ctx.lineWidth = 2.5;
      ctx.shadowColor = rk.redFlash > 0.1 ? "#fb7185" : "#a855f7";
      ctx.shadowBlur = 14;
      ctx.fill();
      ctx.stroke();
      ctx.restore();
      rk.redFlash *= 0.9;

      // Keycap badge & word label
      ctx.font = "700 18px 'Google Sans', sans-serif";
      ctx.fillStyle = "#f8fafc";
      ctx.textAlign = "center";
      ctx.fillText(rk.word, 0, 5);
      ctx.font = "700 11px 'JetBrains Mono', monospace";
      ctx.fillStyle = "#c084fc";
      ctx.fillText(`[${rk.idx + 1}]`, 0, -20);
      ctx.restore();
    }

    // Plasma beams
    for (let i = beams.length - 1; i >= 0; i--) {
      const bm = beams[i];
      bm.life -= 0.1;
      if (bm.life <= 0) { beams.splice(i, 1); continue; }
      ctx.save();
      ctx.globalAlpha = bm.life;
      ctx.strokeStyle = bm.color;
      ctx.lineWidth = 6 * bm.life;
      ctx.shadowColor = bm.color;
      ctx.shadowBlur = 20;
      ctx.beginPath();
      ctx.moveTo(bm.x1, bm.y1);
      ctx.lineTo(bm.x2, bm.y2);
      ctx.stroke();
      ctx.restore();
    }

    // Explosion shards
    for (let i = shards.length - 1; i >= 0; i--) {
      const sh = shards[i];
      sh.x += sh.vx;
      sh.y += sh.vy;
      sh.life -= 0.035;
      if (sh.life <= 0) { shards.splice(i, 1); continue; }
      ctx.save();
      ctx.globalAlpha = sh.life;
      ctx.fillStyle = sh.color;
      ctx.fillRect(sh.x - sh.r / 2, sh.y - sh.r / 2, sh.r, sh.r);
      ctx.restore();
    }

    // Turret
    ctx.save();
    ctx.translate(W / 2, H - 32);
    ctx.rotate(turretAngle + Math.PI / 2);
    ctx.fillStyle = "#38bdf8";
    ctx.shadowColor = "#38bdf8";
    ctx.shadowBlur = 14;
    ctx.fillRect(-6, -30, 12, 28);
    ctx.beginPath();
    ctx.arc(0, 0, 18, 0, Math.PI * 2);
    ctx.fillStyle = "#0f172a";
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 3;
    ctx.fill();
    ctx.stroke();
    ctx.restore();

    rafId = requestAnimationFrame(loop);
  }

  const onPointer = (e) => {
    const r = cv.getBoundingClientRect();
    const px = e.clientX - r.left;
    const py = e.clientY - r.top;
    for (const rk of rocks) {
      if (rk.alive && Math.hypot(px - rk.x, py - rk.y) <= rk.r + 16) {
        shootRock(rk.idx);
        return;
      }
    }
  };
  const onKey = (e) => {
    if (bossMode) return;
    if (e.key === "1") shootRock(0);
    else if (e.key === "2") shootRock(1);
    else if (e.key === "3") shootRock(2);
  };
  cv.addEventListener("pointerdown", onPointer);
  window.addEventListener("keydown", onKey);
  addCleanup(() => {
    active = false;
    cancelAnimationFrame(rafId);
    window.removeEventListener("keydown", onKey);
  });

  spawnWave();
  rafId = requestAnimationFrame(loop);
}

// ===========================================================================
// GAME 4: ⚡ SENTENCE STRETCH LAB (Compound/Complex Bridges + Vivid Verbs)
// ===========================================================================

function runSentenceStretch(pack) {
  const stage = $("saGameStage");
  const items = pack.items;
  let idx = 0;
  let correct = 0;
  const skillHits = {};

  function renderStep() {
    if (idx >= items.length) {
      finishGame({ correct, total: items.length, skill_hits: skillHits, production_passed: true });
      return;
    }
    const it = items[idx];
    setHud({ visible: true, step: idx + 1, total: items.length, score: App.score, combo: App.combo, title: "Sentence Stretch Lab" });
    let hadMiss = false;
    let chosenBridge = null;
    let chosenVerb = null;

    const hlVerb = (txt) => txt.replace(new RegExp(`\\b(${it.weak_verb.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})\\b`, "i"),
      '<span class="st-weak-verb" id="stWeakSpan">$1</span>');

    stage.innerHTML = `
      <div class="sa-panel">
        <div class="st-meter-wrap">
          <div class="st-meter-bar"><div class="st-meter-fill" id="stMeterFill"></div></div>
          <div class="st-meter-label" id="stMeterLbl">LEVEL 1 · CHOPPY</div>
        </div>
        <div class="sa-prompt-text" id="stStepPrompt">Step 1: Snap the right connector bridge to fuse these two choppy sentences!</div>
      </div>
      <div class="st-rails" id="stRails">
        ${it.front_connector ? `<div class="st-bridge-slot" id="stBridgeSlot">Connector?</div>` : ""}
        <div class="st-clause">${hlVerb(esc(it.clause_a))}</div>
        ${!it.front_connector ? `<div class="st-bridge-slot" id="stBridgeSlot">Bridge?</div>` : ""}
        <div class="st-clause">${hlVerb(esc(it.clause_b))}</div>
      </div>
      <div class="sa-panel" id="stControls">
        <div style="text-align:center;color:#94a3b8;font-size:0.9rem">Pick the logical connector:</div>
        <div class="st-pill-row" id="stBridgeRow"></div>
      </div>
      <div class="sa-feedback idle" id="stFb">Choose a connector that matches the real cause, timing, or contrast!</div>`;

    const bRow = $("stBridgeRow");
    it.bridges.forEach((br) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sa-btn ghost";
      b.style.fontSize = "1.05rem";
      b.style.padding = "11px 22px";
      b.textContent = it.front_connector ? br.word.charAt(0).toUpperCase() + br.word.slice(1) : br.word;
      b.onclick = () => {
        if (chosenBridge) return;
        const fb = $("stFb");
        if (br.ok) {
          chosenBridge = br.word;
          SFX.powerup();
          addPoints(75, b, "#10b981");
          $("stBridgeSlot").textContent = it.front_connector ? br.word.charAt(0).toUpperCase() + br.word.slice(1) : br.word;
          $("stBridgeSlot").classList.add("locked");
          $("stMeterFill").style.width = "68%";
          $("stMeterLbl").textContent = `LEVEL 2 · ${br.kind.toUpperCase()}`;
          fb.className = "sa-feedback ok";
          fb.textContent = `⚡ Nice bridge! ${br.why} Now upgrade the weak yellow verb!`;
          showVerbUpgrade();
        } else {
          hadMiss = true;
          resetCombo();
          SFX.bad();
          b.style.borderColor = "#fb7185";
          fb.className = "sa-feedback bad";
          fb.textContent = br.why;
        }
      };
      bRow.appendChild(b);
    });

    function showVerbUpgrade() {
      $("stStepPrompt").textContent = `Step 2: Swap the weak verb “${it.weak_verb}” for a vivid Grade 4 action verb to hit OVERDRIVE!`;
      $("stControls").innerHTML = `
        <div style="text-align:center;color:#fde68a;font-size:0.95rem;font-weight:600">Pick a vivid upgrade for “${esc(it.weak_verb)}”:</div>
        <div class="st-pill-row" id="stVerbRow"></div>`;
      const vRow = $("stVerbRow");
      it.verb_upgrades.forEach((vu) => {
        const vb = document.createElement("button");
        vb.type = "button";
        vb.className = "sa-btn ghost";
        vb.style.fontSize = "1.05rem";
        vb.style.padding = "11px 22px";
        vb.textContent = vu.word;
        vb.onclick = () => {
          if (chosenVerb) return;
          const fb = $("stFb");
          if (vu.ok) {
            chosenVerb = vu.word;
            SFX.powerup();
            if (!hadMiss) correct += 1;
            skillHits[it.skill] = skillHits[it.skill] || { correct: 0, total: 0 };
            skillHits[it.skill].total += 1;
            if (!hadMiss) skillHits[it.skill].correct += 1;
            skillHits["B2.4_vocabulary"] = skillHits["B2.4_vocabulary"] || { correct: 0, total: 0 };
            skillHits["B2.4_vocabulary"].total += 1;
            if (!hadMiss) skillHits["B2.4_vocabulary"].correct += 1;

            addPoints(hadMiss ? 60 : 120, vb, "#facc15");
            $("stMeterFill").style.width = "100%";
            $("stMeterLbl").textContent = "⚡ OVERDRIVE 100%!";
            const ws = $("stWeakSpan");
            if (ws) {
              ws.textContent = vu.word;
              ws.style.borderColor = "#10b981";
              ws.style.color = "#6ee7b7";
              ws.style.background = "rgba(16,185,129,0.22)";
            }
            $("stControls").innerHTML = `
              <div style="text-align:center;font-size:1.2rem;font-weight:700;color:#6ee7b7">
                ⚡ ${esc(it.target_example)}
              </div>`;
            fb.className = "sa-feedback ok";
            fb.innerHTML = `<span>🔥 <b>OVERDRIVE UNLOCKED!</b> Look how much stronger that sentence reads!</span><button type="button" class="sa-btn emerald" id="stNextBtn">Next Lab →</button>`;
            $("stNextBtn").onclick = () => { idx += 1; renderStep(); };
          } else {
            hadMiss = true;
            resetCombo();
            SFX.bad();
            vb.style.borderColor = "#fb7185";
            fb.className = "sa-feedback bad";
            fb.textContent = `"${vu.word}" is still a sleepy weak verb — pick one that creates a sharper picture!`;
          }
        };
        vRow.appendChild(vb);
      });
    }
  }
  renderStep();
}

// ===========================================================================
// GAME 5: 🏎️ NEON TURBO TYPING ARENA (60fps Synthwave Highway + Finger Guide)
// ===========================================================================

const KBD_ROWS = [
  ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
  ["A", "S", "D", "F", "G", "H", "J", "K", "L", "'"],
  ["Z", "X", "C", "V", "B", "N", "M", ",", ".", "!"],
  ["SPACE"],
];
const FINGER_HINT = {
  Q: "L-Pinky", A: "L-Pinky", Z: "L-Pinky",
  W: "L-Ring", S: "L-Ring", X: "L-Ring",
  E: "L-Middle", D: "L-Middle", C: "L-Middle",
  R: "L-Index", F: "L-Index", V: "L-Index", T: "L-Index", G: "L-Index", B: "L-Index",
  Y: "R-Index", H: "R-Index", N: "R-Index", U: "R-Index", J: "R-Index", M: "R-Index",
  I: "R-Middle", K: "R-Middle", ",": "R-Middle",
  O: "R-Ring", L: "R-Ring", ".": "R-Ring",
  P: "R-Pinky", "'": "R-Pinky", "!": "R-Pinky", "?": "R-Pinky", "\"": "R-Pinky",
  " ": "Thumb",
};

function runTypingArena(pack) {
  const stage = $("saGameStage");
  const items = pack.items;
  let idx = 0;
  let pos = 0;
  let totalTyped = 0;
  let totalCorrect = 0;
  let firstKeyTs = 0;
  let currentWpm = 0;
  let currentAcc = 100;
  let errFlash = 0;
  let roadOffset = 0;
  let active = true;
  let rafId = 0;

  stage.innerHTML = `
    <div class="ty-road-wrap">
      <canvas id="tyCanvas"></canvas>
      <div class="ty-telemetry">
        <div class="ty-gauge" id="tyWpm">0 WPM</div>
        <div class="ty-gauge" id="tyAcc">100% ACC</div>
      </div>
    </div>
    <div class="sa-panel" style="display:flex;flex-direction:column;gap:12px">
      <div class="sa-mission-banner">
        <span class="sa-mission-tag" id="tyTag">🏎️ RACE LAP 1</span>
        <span class="sa-tag" id="tyFingerTag">Next finger: —</span>
      </div>
      <div class="ty-prompt-box" id="tyPrompt" tabindex="0"></div>
      <div class="ty-kbd" id="tyKbd"></div>
    </div>
    <div class="sa-feedback idle" id="tyFb">Start typing right away! Keep accuracy <b>≥ 94%</b> to ignite golden Turbo Boost!</div>`;

  // Build visual keyboard
  $("tyKbd").innerHTML = KBD_ROWS.map((row) =>
    `<div class="ty-kbd-row">${row.map((k) =>
      `<span class="ty-key ${k === "SPACE" ? "space" : ""}" data-key="${k}">${k === "SPACE" ? "SPACE" : k}</span>`
    ).join("")}</div>`
  ).join("");

  const cv = $("tyCanvas");
  const ctx = cv.getContext("2d");

  function drawRoad() {
    if (!active) return;
    const r = cv.parentElement.getBoundingClientRect();
    if (cv.width !== Math.floor(r.width) || cv.height !== Math.floor(r.height)) {
      cv.width = Math.max(300, Math.floor(r.width));
      cv.height = Math.max(160, Math.floor(r.height));
    }
    const W = cv.width, H = cv.height;
    const horiz = H * 0.44;
    const turbo = currentAcc >= 94 && currentWpm >= 14;
    const speed = 0.015 + Math.min(0.12, currentWpm * 0.0022);
    roadOffset = (roadOffset + speed) % 1;

    // Sky gradient
    const sky = ctx.createLinearGradient(0, 0, 0, horiz);
    sky.addColorStop(0, "#05040f");
    sky.addColorStop(1, turbo ? "#1e1b4b" : "#0f172a");
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, W, horiz);

    // Synthwave sun
    const sunG = ctx.createRadialGradient(W / 2, horiz, 4, W / 2, horiz, 72);
    sunG.addColorStop(0, turbo ? "#facc15" : "#22d3ee");
    sunG.addColorStop(0.6, turbo ? "rgba(249,115,22,0.55)" : "rgba(168,85,247,0.45)");
    sunG.addColorStop(1, "transparent");
    ctx.fillStyle = sunG;
    ctx.beginPath();
    ctx.arc(W / 2, horiz, 72, Math.PI, 0);
    ctx.fill();

    // Road floor
    ctx.fillStyle = "#080c1c";
    ctx.fillRect(0, horiz, W, H - horiz);

    // Perspective grid lines
    ctx.strokeStyle = errFlash > 0.1 ? "#fb7185" : (turbo ? "rgba(250,204,21,0.55)" : "rgba(34,211,238,0.42)");
    ctx.lineWidth = 1.5;
    for (let i = -7; i <= 7; i++) {
      ctx.beginPath();
      ctx.moveTo(W / 2 + i * 24, horiz);
      ctx.lineTo(W / 2 + i * 135, H);
      ctx.stroke();
    }
    for (let j = 0; j < 7; j++) {
      const t = ((j + roadOffset) / 7) ** 2;
      const y = horiz + t * (H - horiz);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
      ctx.stroke();
    }

    // Sleek Neon Hover-Racer
    const cx = W / 2;
    const cy = H - 36 + Math.sin(performance.now() * 0.008) * 3;
    // Thruster flame
    ctx.save();
    ctx.fillStyle = errFlash > 0.1 ? "#fb7185" : (turbo ? "#facc15" : "#22d3ee");
    ctx.shadowColor = ctx.fillStyle;
    ctx.shadowBlur = turbo ? 26 : 14;
    const fl = 14 + Math.min(34, currentWpm * 0.8) + Math.random() * 8;
    ctx.beginPath();
    ctx.moveTo(cx - 18, cy + 8);
    ctx.lineTo(cx, cy + 8 + fl);
    ctx.lineTo(cx + 18, cy + 8);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    // Racer chassis
    ctx.save();
    ctx.fillStyle = "#0f172a";
    ctx.strokeStyle = turbo ? "#facc15" : "#38bdf8";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(cx, cy - 26);
    ctx.lineTo(cx + 38, cy + 12);
    ctx.lineTo(cx + 18, cy + 16);
    ctx.lineTo(cx - 18, cy + 16);
    ctx.lineTo(cx - 38, cy + 12);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.restore();

    errFlash *= 0.86;
    rafId = requestAnimationFrame(drawRoad);
  }
  rafId = requestAnimationFrame(drawRoad);

  function renderPrompt(badNow = false) {
    const it = items[idx];
    const txt = it.text;
    setHud({ visible: true, step: idx + 1, total: items.length, score: App.score, combo: App.combo, title: "Neon Turbo Typing" });
    $("tyTag").textContent = `🏎️ LAP ${idx + 1}/${items.length} · ${it.tag}`;
    let html = "";
    for (let i = 0; i < txt.length; i++) {
      const ch = txt[i] === " " ? "&nbsp;" : esc(txt[i]);
      if (i < pos) html += `<span class="ty-char done">${ch}</span>`;
      else if (i === pos) html += `<span class="ty-char ${badNow ? "err" : "cur"}">${ch}</span>`;
      else html += `<span class="ty-char todo">${ch}</span>`;
    }
    $("tyPrompt").innerHTML = html;

    const targetChar = txt[pos] || "";
    const normKey = targetChar === " " ? "SPACE" : targetChar.toUpperCase();
    $("tyKbd").querySelectorAll(".ty-key").forEach((el) => {
      el.classList.toggle("next", el.dataset.key === normKey);
    });
    const shiftNeed = /[A-Z!"?]/.test(targetChar);
    const fHint = FINGER_HINT[targetChar.toUpperCase()] || "Pinky";
    $("tyFingerTag").textContent = targetChar
      ? `Next: ${targetChar === " " ? "SPACE" : targetChar} (${shiftNeed ? "Shift + " : ""}${fHint})`
      : "Lap clear!";
  }

  function updateMetrics() {
    if (!firstKeyTs) return;
    const mins = Math.max(0.05, (performance.now() - firstKeyTs) / 60000);
    currentWpm = Math.round((totalCorrect / 5) / mins);
    currentAcc = totalTyped > 0 ? Math.round((100 * totalCorrect) / totalTyped) : 100;
    $("tyWpm").textContent = `${currentWpm} WPM`;
    $("tyAcc").textContent = `${currentAcc}% ACC`;
  }

  const onKeyDown = (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (["Shift", "CapsLock", "Tab", "Escape"].includes(e.key)) return;
    if (e.key.length !== 1) return;
    e.preventDefault();
    if (!firstKeyTs) firstKeyTs = performance.now();

    const target = items[idx].text[pos];
    totalTyped += 1;
    if (e.key === target) {
      totalCorrect += 1;
      pos += 1;
      SFX.keyTick();
      updateMetrics();
      if (pos >= items[idx].text.length) {
        addPoints(150, $("tyPrompt"), "#22d3ee");
        SFX.powerup();
        idx += 1;
        pos = 0;
        if (idx >= items.length) {
          const mins = Math.max(0.08, (performance.now() - firstKeyTs) / 60000);
          const cpm = Math.round(totalCorrect / mins);
          const wpm = Math.round(cpm / 5);
          finishGame({
            correct: totalCorrect,
            total: Math.max(1, totalTyped),
            wpm,
            cpm,
            production_passed: currentAcc >= 90,
          });
          return;
        }
        $("tyFb").className = "sa-feedback ok";
        $("tyFb").textContent = `⚡ Lap cleared at ${currentWpm} WPM (${currentAcc}% accuracy)! Keep flying!`;
      }
      renderPrompt(false);
    } else {
      errFlash = 1;
      resetCombo();
      SFX.keyErr();
      updateMetrics();
      renderPrompt(true);
    }
  };

  window.addEventListener("keydown", onKeyDown);
  addCleanup(() => {
    active = false;
    cancelAnimationFrame(rafId);
    window.removeEventListener("keydown", onKeyDown);
  });
  renderPrompt(false);
}

// ===========================================================================
// GAME 6: 🔎 MYSTERY CLUE DETECTIVE (Stylus Highlight + Deduction + Verdict)
// ===========================================================================

function runClueDetective(pack) {
  const stage = $("saGameStage");
  const items = pack.items;
  let idx = 0;
  let correct = 0;
  const skillHits = {};
  let lastVerdict = "";

  function renderCase() {
    if (idx >= items.length) {
      finishGame({
        correct,
        total: items.length,
        production_passed: !!lastVerdict,
        production_sentence: lastVerdict,
        skill_hits: skillHits,
      });
      return;
    }
    const it = items[idx];
    setHud({ visible: true, step: idx + 1, total: items.length, score: App.score, combo: App.combo, title: "Mystery Clue Detective" });
    let clueFound = false;
    let choiceLocked = false;
    let hadMiss = false;

    stage.innerHTML = `
      <div class="sa-panel">
        <div class="sa-mission-banner">
          <span class="sa-mission-tag">🔎 ${esc(it.case_title)}</span>
          <span class="sa-tag">Step 1: Highlight the proof sentence with your stylus or mouse!</span>
        </div>
        <div class="sa-prompt-text">${esc(it.question)}</div>
      </div>
      <div class="cd-casefile" id="cdFile"></div>
      <div id="cdStep2" hidden></div>
      <div id="cdStep3" hidden></div>
      <div class="sa-feedback idle" id="cdFb">Tap or swipe your stylus across the exact sentence that proves the answer!</div>`;

    const file = $("cdFile");
    it.sentences.forEach((sent, si) => {
      const div = document.createElement("div");
      div.className = "cd-line";
      div.innerHTML = `<span style="color:#94a3b8;font-family:'JetBrains Mono',monospace;margin-right:8px">[${si + 1}]</span>${esc(sent)}`;
      div.onclick = () => {
        if (clueFound) return;
        const fb = $("cdFb");
        if (si === it.clue_index) {
          clueFound = true;
          div.classList.add("highlighted");
          SFX.highlight();
          addPoints(75, div, "#facc15");
          fb.className = "sa-feedback ok";
          fb.textContent = "🟡 Evidence highlighted! Now lock in your deduction below.";
          showChoices();
        } else {
          hadMiss = true;
          resetCombo();
          SFX.bad();
          div.classList.add("miss");
          setTimeout(() => div.classList.remove("miss"), 380);
          fb.className = "sa-feedback bad";
          fb.textContent = "That line sets the scene, but doesn't hold the smoking-gun clue. Check the other lines!";
        }
      };
      file.appendChild(div);
    });

    function showChoices() {
      const s2 = $("cdStep2");
      s2.hidden = false;
      s2.innerHTML = `<div class="sa-choice-list" id="cdChoices"></div>`;
      it.choices.forEach((ch) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "sa-choice-btn";
        b.textContent = ch.label;
        b.onclick = () => {
          if (choiceLocked) return;
          const fb = $("cdFb");
          if (ch.ok) {
            choiceLocked = true;
            b.classList.add("ok");
            SFX.ok();
            addPoints(65, b, "#10b981");
            fb.className = "sa-feedback ok";
            fb.textContent = `✅ Deduction locked! ${it.explain} Now write your 1-sentence Case Verdict!`;
            showVerdict();
          } else {
            hadMiss = true;
            resetCombo();
            b.classList.add("bad");
            SFX.bad();
            fb.className = "sa-feedback bad";
            fb.textContent = ch.why || "Re-read your highlighted clue carefully!";
          }
        };
        $("cdChoices").appendChild(b);
      });
    }

    function showVerdict() {
      const s3 = $("cdStep3");
      s3.hidden = false;
      s3.innerHTML = `
        <div class="sa-panel" style="border-color:rgba(250,204,21,0.5)">
          <div style="font-weight:700;color:#fde68a;margin-bottom:8px">✍️ Final Step — Stamp Case Closed with a Causal Verdict (use “because” + period!):</div>
          <input type="text" id="cdVerdictInput" class="sa-sentence-input" value="${esc(it.verdict_starter)} " autocomplete="off" />
          <div style="display:flex;justify-content:flex-end;margin-top:10px">
            <button type="button" class="sa-btn primary" id="cdCloseBtn">⚖️ Stamp CASE CLOSED</button>
          </div>
        </div>`;
      const inp = $("cdVerdictInput");
      inp.focus();
      inp.setSelectionRange(inp.value.length, inp.value.length);

      const submitVerdict = async () => {
        const txt = inp.value.trim();
        if (!txt) return;
        const r = await fetch("/api/skill-games/check-sentence", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: txt, required_word: it.required_word || "", require_because: true }),
        });
        const chk = await r.json();
        const fb = $("cdFb");
        if (chk.ok) {
          SFX.powerup();
          lastVerdict = txt;
          if (!hadMiss) correct += 1;
          skillHits[it.skill] = skillHits[it.skill] || { correct: 0, total: 0 };
          skillHits[it.skill].total += 1;
          if (!hadMiss) skillHits[it.skill].correct += 1;
          addPoints(140, inp, "#facc15");
          fb.className = "sa-feedback ok";
          fb.innerHTML = `<span>🏆 <b>CASE CLOSED!</b> Airtight evidence!</span><button type="button" class="sa-btn emerald" id="cdNextBtn">Next Case →</button>`;
          inp.disabled = true;
          $("cdCloseBtn").disabled = true;
          $("cdNextBtn").onclick = () => { idx += 1; renderCase(); };
        } else {
          SFX.bad();
          fb.className = "sa-feedback bad";
          fb.textContent = chk.feedback;
        }
      };
      $("cdCloseBtn").onclick = submitVerdict;
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); submitVerdict(); } });
    }
  }
  renderCase();
}

// --------------------------------------------------------------------------- Global Wiring & Boot

$("saBackBtn").onclick = () => {
  if (App.currentGameId) {
    loadHub();
  } else if (IS_EMBEDDED) {
    try { window.parent.postMessage({ __skillArcadeClose: true }, "*"); } catch (_) {}
  } else {
    location.href = IS_SANDBOX ? "/?sandbox=1" : "/";
  }
};

$("saMuteBtn").onclick = () => {
  const m = SFX.toggle();
  $("saMuteBtn").textContent = m ? "🔇" : "🔊";
  $("saMuteBtn").setAttribute("aria-pressed", String(m));
};

$("saPlayAgainBtn").onclick = () => startGame(App.currentGameId, $("saUseAi").checked);
$("saPlayAiBtn").onclick = () => startGame(App.currentGameId, true);
$("saReturnHubBtn").onclick = () => loadHub();

loadHub().then(() => {
  if (START_GAME) startGame(START_GAME, false);
});
