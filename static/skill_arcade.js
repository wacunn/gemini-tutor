// Starblade Arcade v2.2 — Stealth-School & Closed-Loop ZPD Adaptive Arenas (60fps 2x-DPR OLED + Lenovo Yoga Stylus)

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

// --------------------------------------------------------------------------- Crisp 2x DPR Canvas & Geometry Helpers

function fitCanvas(cv, ctx, fallbackW = 300, fallbackH = 140) {
  const host = cv.parentElement || cv;
  const r = host.getBoundingClientRect();
  const W = Math.max(fallbackW, Math.floor(r.width));
  const H = Math.max(fallbackH, Math.floor(r.height));
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const bw = Math.floor(W * dpr);
  const bh = Math.floor(H * dpr);
  if (cv.width !== bw || cv.height !== bh) {
    cv.width = bw;
    cv.height = bh;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { W, H, dpr };
}

function segmentHitsRect(x1, y1, x2, y2, rect, pad = 6) {
  const minX = rect.left - pad;
  const maxX = rect.right + pad;
  const minY = rect.top - pad;
  const maxY = rect.bottom + pad;
  // Cohen-Sutherland / Liang-Barsky parametric clipping for exact segment-box intersection
  let t0 = 0, t1 = 1;
  const dx = x2 - x1, dy = y2 - y1;
  const checks = [
    [-dx, x1 - minX],
    [dx, maxX - x1],
    [-dy, y1 - minY],
    [dy, maxY - y1],
  ];
  for (const [p, q] of checks) {
    if (Math.abs(p) < 1e-8) {
      if (q < 0) return false;
    } else {
      const t = q / p;
      if (p < 0) {
        if (t > t1) return false;
        if (t > t0) t0 = t;
      } else {
        if (t < t0) return false;
        if (t < t1) t1 = t;
      }
    }
  }
  return t0 <= t1;
}

function setFeedback(el, kind, html, btn = null) {
  if (!el) return;
  el.className = `sa-feedback ${kind}`;
  el.innerHTML = `<span class="sa-fb-msg">${html}</span>${btn ? `<button type="button" class="sa-btn ${btn.cls || "emerald"}" id="${btn.id}">${esc(btn.label)}</button>` : ""
    }`;
  if (btn && btn.onClick && $(btn.id)) {
    $(btn.id).onclick = btn.onClick;
  }
}

// --------------------------------------------------------------------------- Spoken Voice Narration (Web Speech API)

const VOICE = (() => {
  let enabled = true;
  let cachedVoice = null;
  function pickVoice() {
    if (!("speechSynthesis" in window)) return null;
    const vs = window.speechSynthesis.getVoices() || [];
    if (!vs.length) return null;
    const pref = [
      /Microsoft Aria/i, /Microsoft Guy/i, /Microsoft Jenny/i, /Microsoft Zira/i,
      /Samantha/i, /Google US English/i, /Daniel/i, /Alex/i,
    ];
    for (const rx of pref) {
      const m = vs.find((v) => rx.test(v.name) && /^en/i.test(v.lang));
      if (m) return m;
    }
    return vs.find((v) => /^en/i.test(v.lang)) || vs[0];
  }
  if ("speechSynthesis" in window) {
    window.speechSynthesis.onvoiceschanged = () => { cachedVoice = pickVoice(); };
    cachedVoice = pickVoice();
  }
  return {
    get enabled() { return enabled; },
    toggle() {
      enabled = !enabled;
      if (!enabled) this.stop();
      return enabled;
    },
    stop() {
      if ("speechSynthesis" in window) {
        try { window.speechSynthesis.cancel(); } catch (_) { }
      }
    },
    speak(text, { force = false, rate = 0.94 } = {}) {
      if (!("speechSynthesis" in window)) return;
      if (!enabled && !force) return;
      const clean = String(text || "").replace(/\s+/g, " ").trim();
      if (!clean) return;
      try {
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(clean);
        u.rate = rate;
        u.pitch = 1.0;
        const v = cachedVoice || pickVoice();
        if (v) u.voice = v;
        window.speechSynthesis.speak(u);
      } catch (_) { }
    },
  };
})();

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
    if (ctx && ctx.state === "suspended") ctx.resume().catch(() => { });
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
    bad() { tone(210, 0.18, "sawtooth", 0.1, 125); },
    shieldBounce() { tone(180, 0.22, "sawtooth", 0.12, 90); tone(310, 0.14, "triangle", 0.08, 190, 0.03); },
    slice() {
      tone(1040, 0.16, "sawtooth", 0.12, 220);
      tone(1320, 0.14, "sine", 0.1, 1820, 0.05);
    },
    hammer() {
      tone(180, 0.24, "triangle", 0.2, 75);
      tone(920, 0.3, "sine", 0.12, 620, 0.01);
      tone(1480, 0.24, "sine", 0.08, 1100, 0.025);
    },
    laser() {
      tone(880, 0.14, "square", 0.08, 180);
      tone(440, 0.13, "triangle", 0.11, 110, 0.04);
    },
    hyperbeam() {
      tone(220, 0.55, "sawtooth", 0.14, 1280);
      tone(440, 0.55, "triangle", 0.12, 1760, 0.05);
      tone(110, 0.65, "sine", 0.16, 55, 0.25);
    },
    stamp() {
      tone(145, 0.2, "triangle", 0.22, 55);
      tone(660, 0.16, "sine", 0.1, 880, 0.07);
    },
    powerup() {
      [440, 554.37, 659.25, 880].forEach((f, i) => tone(f, 0.18, "triangle", 0.12, null, i * 0.055));
    },
    keyTick() { tone(640, 0.032, "triangle", 0.05, 510); },
    keyErr() { tone(160, 0.09, "sawtooth", 0.08, 115); },
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
  let fxDirty = false;
  let lastBgTick = 0;
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

  for (let i = 0; i < 60; i++) {
    stars.push({
      x: Math.random() * 1800, y: Math.random() * 1100,
      r: 0.7 + Math.random() * 1.8, vx: (Math.random() - 0.5) * 0.15,
      vy: -0.06 - Math.random() * 0.17, hue: [195, 270, 160, 38][i % 4],
      a: 0.2 + Math.random() * 0.45,
    });
  }

  function loop(ts) {
    // Battery-friendly: throttle ambient nebula to ~30fps while a 60fps game canvas is running
    const bgInterval = App.currentGameId ? 33 : 16;
    if (ts - lastBgTick >= bgInterval) {
      lastBgTick = ts;
      bgCtx.fillStyle = "#060913";
      bgCtx.fillRect(0, 0, W, H);
      const g1 = bgCtx.createRadialGradient(W * 0.18, H * 0.14, 10, W * 0.18, H * 0.14, W * 0.5);
      g1.addColorStop(0, "rgba(56, 189, 248, 0.08)"); g1.addColorStop(1, "transparent");
      bgCtx.fillStyle = g1; bgCtx.fillRect(0, 0, W, H);

      const g2 = bgCtx.createRadialGradient(W * 0.85, H * 0.78, 10, W * 0.85, H * 0.78, W * 0.45);
      g2.addColorStop(0, "rgba(168, 85, 247, 0.08)"); g2.addColorStop(1, "transparent");
      bgCtx.fillStyle = g2; bgCtx.fillRect(0, 0, W, H);

      for (const s of stars) {
        s.x += s.vx; s.y += s.vy;
        if (s.y < -10) { s.y = H + 10; s.x = Math.random() * W; }
        if (s.x < -10) s.x = W + 10;
        if (s.x > W + 10) s.x = -10;
        bgCtx.fillStyle = `hsla(${s.hue}, 90%, 72%, ${s.a})`;
        bgCtx.beginPath(); bgCtx.arc(s.x, s.y, s.r, 0, Math.PI * 2); bgCtx.fill();
      }
    }

    // Skip FX redraw completely when idle!
    const hasFx = particles.length || trails.length || floats.length;
    if (hasFx || fxDirty) {
      fxCtx.clearRect(0, 0, W, H);
      fxDirty = hasFx > 0;

      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i];
        p.x += p.vx; p.y += p.vy; p.vy += p.g; p.life -= p.decay;
        if (p.life <= 0) { particles.splice(i, 1); continue; }
        fxCtx.save();
        fxCtx.globalAlpha = Math.max(0, p.life);
        fxCtx.fillStyle = p.color; fxCtx.shadowColor = p.color; fxCtx.shadowBlur = 10;
        fxCtx.beginPath(); fxCtx.arc(p.x, p.y, p.r * p.life, 0, Math.PI * 2); fxCtx.fill();
        fxCtx.restore();
      }

      for (let i = trails.length - 1; i >= 0; i--) {
        const tr = trails[i];
        tr.life -= 0.055;
        if (tr.life <= 0) { trails.splice(i, 1); continue; }
        fxCtx.save();
        fxCtx.globalAlpha = tr.life;
        fxCtx.strokeStyle = tr.color;
        fxCtx.lineWidth = (tr.width || 6) * tr.life;
        fxCtx.lineCap = "round";
        fxCtx.shadowColor = tr.color; fxCtx.shadowBlur = 18;
        fxCtx.beginPath();
        tr.pts.forEach((pt, idx) => idx === 0 ? fxCtx.moveTo(pt.x, pt.y) : fxCtx.lineTo(pt.x, pt.y));
        fxCtx.stroke();
        fxCtx.restore();
      }

      for (let i = floats.length - 1; i >= 0; i--) {
        const f = floats[i];
        f.y -= 1.3; f.life -= 0.022;
        if (f.life <= 0) { floats.splice(i, 1); continue; }
        fxCtx.save();
        fxCtx.globalAlpha = Math.min(1, f.life * 1.4);
        fxCtx.font = "700 20px 'Google Sans', sans-serif";
        fxCtx.textAlign = "center";
        fxCtx.fillStyle = f.color;
        fxCtx.shadowColor = "rgba(0,0,0,0.85)"; fxCtx.shadowBlur = 8;
        fxCtx.fillText(f.text, f.x, f.y);
        fxCtx.restore();
      }
    }
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  return {
    burst(x, y, color = "#38bdf8", count = 26) {
      fxDirty = true;
      for (let i = 0; i < count; i++) {
        const ang = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.4;
        const spd = 2.4 + Math.random() * 6.5;
        particles.push({
          x, y, vx: Math.cos(ang) * spd, vy: Math.sin(ang) * spd - 1.5,
          g: 0.14, r: 2.5 + Math.random() * 4, color, life: 1, decay: 0.02 + Math.random() * 0.02,
        });
      }
    },
    burstEl(el, color = "#38bdf8", count = 24) {
      if (!el) return;
      const r = el.getBoundingClientRect();
      this.burst(r.left + r.width / 2, r.top + r.height / 2, color, count);
    },
    slash(pts, color = "#38bdf8", width = 6) {
      if (pts.length >= 2) { fxDirty = true; trails.push({ pts: pts.slice(), color, width, life: 1 }); }
    },
    floatText(x, y, text, color = "#facc15") {
      fxDirty = true;
      floats.push({ x, y, text, color, life: 1 });
    },
    floatEl(el, text, color = "#facc15") {
      if (!el) return;
      const r = el.getBoundingClientRect();
      this.floatText(r.left + r.width / 2, r.top + 8, text, color);
    },
  };
})();

// --------------------------------------------------------------------------- Global State, Anti-AFK Clock & Safe Timers

const App = {
  hubData: null,
  currentGameId: null,
  cleanups: [],
  timers: new Set(),
  score: 0,
  combo: 0,
  sector: 1,
  overclock: false,
  worldsTouched: false,
  penDetected: false,   // Persists across all games & rounds on Lenovo Yoga!
  forgeUsePen: false,   // Remembers Yoga Pen tab choice across words in Obsidian Forge!
  activeSeconds: 0,
  stepStartedAt: 0,
  hiddenAt: 0,
};

document.addEventListener("visibilitychange", () => {
  if (!App.currentGameId) return;
  if (document.hidden) {
    App.hiddenAt = performance.now();
  } else if (App.hiddenAt) {
    const pausedMs = performance.now() - App.hiddenAt;
    App.stepStartedAt += pausedMs;
    App.hiddenAt = 0;
  }
});

function beginStepClock() {
  App.stepStartedAt = performance.now();
  App.hiddenAt = 0;
}

function commitStepClock(capSeconds = 40) {
  if (!App.stepStartedAt) return;
  const now = document.hidden && App.hiddenAt ? App.hiddenAt : performance.now();
  const dt = Math.max(0, (now - App.stepStartedAt) / 1000);
  App.activeSeconds += Math.min(capSeconds, dt);
  App.stepStartedAt = performance.now();
}

function addCleanup(fn) { App.cleanups.push(fn); }
function safeTimeout(fn, ms) {
  const id = setTimeout(() => {
    App.timers.delete(id);
    fn();
  }, ms);
  App.timers.add(id);
  return id;
}

function runCleanups() {
  VOICE.stop();
  for (const id of App.timers) clearTimeout(id);
  App.timers.clear();
  while (App.cleanups.length) {
    try { App.cleanups.pop()(); } catch (_) { }
  }
}

function setHud({ visible = false, step = 1, total = 6, score = 0, combo = 0, sector = null, overclock = null, title = "Starblade Arcade", aiPack = false }) {
  $("saHudCenter").hidden = !visible;
  const aiChip = aiPack ? ` <span class="sa-tag" style="color:#e9d5ff;background:rgba(168,85,247,0.22);border:1px solid rgba(168,85,247,0.45)">🌌 My Worlds</span>` : "";
  $("saBrandTitle").innerHTML = `<span class="sa-brand-dot"></span><span>${esc(title)}</span>${aiChip}`;
  $("saBackBtn").textContent = visible ? "← Arenas" : (IS_EMBEDDED ? "← Studio" : "← Studio");
  if (!visible) return;
  if (sector !== null) App.sector = sector;
  if (overclock !== null) App.overclock = overclock;
  const pct = Math.max(0, Math.min(100, (step / Math.max(1, total)) * 100));
  $("saProgFill").style.width = `${pct}%`;
  $("saProgLabel").textContent = `${Math.min(step, total)} / ${total}`;
  const tp = $("saTierPill");
  if (tp) {
    tp.textContent = App.overclock ? `⚡ OVERCLOCK S${App.sector}` : `SECTOR ${App.sector}`;
    tp.classList.toggle("overclock", !!App.overclock);
  }
  $("saScorePill").textContent = `${score} PTS`;
  if (combo >= 2) {
    $("saComboPill").hidden = false;
    $("saComboPill").textContent = `🔥 x${combo}`;
  } else {
    $("saComboPill").hidden = true;
  }
}

// Live Mid-Round ZPD Director: escalates on 2-hit streaks, scaffolds down on 2-miss stumbles,
// aligns EVERY upcoming item to the active ZPD tier, and tracks exact `playedIds` for `seen_ids` reconciliation!
function createZpdDirector(pack) {
  const startTier = Math.max(1, Math.min(3, Number(pack.adaptive?.start_tier) || 1));
  const reserves = {
    1: (pack.reserve_by_tier?.["1"] || []).slice(),
    2: (pack.reserve_by_tier?.["2"] || []).slice(),
    3: (pack.reserve_by_tier?.["3"] || []).slice(),
  };
  const usedIds = new Set((pack.items || []).map((x) => x.id));
  const playedIds = [];
  const subskillHits = {};
  let tier = startTier;
  let peakTier = startTier;
  let hitStreak = 0;
  let missStreak = 0;
  App.sector = tier;
  App.overclock = false;

  function swapUpcomingIfBetter(itemsArr, nextIdx, desiredTier) {
    if (!itemsArr || nextIdx < 0 || nextIdx >= itemsArr.length) return;
    const curNext = itemsArr[nextIdx];
    const curNextTier = Number(curNext?.tier) || 2;
    if (curNextTier === desiredTier) return;
    const bucket = reserves[desiredTier] || [];
    const pickIdx = bucket.findIndex((cand) => !usedIds.has(cand.id) && (!curNext?.mode || cand.mode === curNext.mode));
    const idxToUse = pickIdx >= 0 ? pickIdx : bucket.findIndex((cand) => !usedIds.has(cand.id));
    if (idxToUse >= 0) {
      const replacement = bucket.splice(idxToUse, 1)[0];
      usedIds.add(replacement.id);
      itemsArr[nextIdx] = replacement;
    }
  }

  return {
    get tier() { return tier; },
    get peakTier() { return peakTier; },
    get subskillHits() { return subskillHits; },
    get playedIds() { return playedIds; },
    record(item, cleanFirstTry, nextIdx = -1, itemsArr = null) {
      if (item?.id && !playedIds.includes(item.id)) {
        playedIds.push(item.id);
      }
      const sub = item?.subskill;
      if (sub) {
        subskillHits[sub] = subskillHits[sub] || { correct: 0, total: 0 };
        subskillHits[sub].total += 1;
        if (cleanFirstTry) subskillHits[sub].correct += 1;
      }
      if (cleanFirstTry) {
        hitStreak += 1;
        missStreak = 0;
        if (hitStreak >= 2 && tier < 3) {
          tier += 1;
          peakTier = Math.max(peakTier, tier);
          hitStreak = 0;
          App.sector = tier;
          App.overclock = true;
          const tp = $("saTierPill");
          if (tp) {
            tp.textContent = `⚡ OVERCLOCK S${tier}`;
            tp.classList.add("overclock");
            FX.floatEl(tp, `⚡ SECTOR ${tier} UNLOCKED!`, "#facc15");
          }
        }
      } else {
        missStreak += 1;
        hitStreak = 0;
        if (missStreak >= 2 && tier > 1) {
          tier -= 1;
          missStreak = 0;
          App.sector = tier;
          App.overclock = false;
          const tp = $("saTierPill");
          if (tp) {
            tp.textContent = `SECTOR ${tier}`;
            tp.classList.remove("overclock");
          }
        }
      }
      // Always align the upcoming item toward the active ZPD `tier` on EVERY step (never snap back to T1!)
      swapUpcomingIfBetter(itemsArr, nextIdx, tier);
    },
  };
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

const BANK_UNIT_LABEL = {
  sentence_surgery: "streams",
  word_forge: "blades",
  homophone_asteroids: "waves",
  sentence_stretch: "cores",
  typing_arena: "laps",
  clue_detective: "dossiers",
};

async function loadHub() {
  runCleanups();
  App.currentGameId = null;
  $("saSummaryModal").hidden = true;
  $("saGameStage").hidden = true;
  $("saHubView").hidden = false;
  setHud({ visible: false, title: "Starblade Arcade" });

  let d;
  try {
    const r = await fetch(`/api/skill-games/hub?sandbox=${IS_SANDBOX ? 1 : 0}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    d = await r.json();
  } catch (e) {
    $("saGameGrid").innerHTML = `
      <div class="sa-panel" style="grid-column:1/-1;text-align:center;padding:28px">
        <div style="font-size:1.1rem;font-weight:700;margin-bottom:8px">Starblade Arcade Offline</div>
        <div style="color:var(--muted);margin-bottom:14px">Tap Retry once the local app is ready.</div>
        <button type="button" class="sa-btn primary" id="saHubRetryBtn">Retry</button>
      </div>`;
    const rb = $("saHubRetryBtn");
    if (rb) rb.onclick = () => loadHub();
    return;
  }
  App.hubData = d;

  $("saSandboxTag").hidden = !IS_SANDBOX;
  $("saAiToggleWrap").hidden = !d.ai_available;
  if (!App.worldsTouched && d.auto_worlds_ready && PARAMS.get("ai") !== "0") {
    $("saUseAi").checked = true;
  }
  renderBankPill(d.arcade);

  $("saHeroHeading").textContent = `Pick Your Arena, ${d.child_name}`;
  const thirdStat = d.runes_ready > 0
    ? `<div class="sa-stat-chip"><div class="v">🔥 ${d.runes_ready}</div><div class="k">Runes Ready</div></div>`
    : `<div class="sa-stat-chip"><div class="v">${d.total_runs}</div><div class="k">Runs Cleared</div></div>`;
  $("saStatsStrip").innerHTML = `
    <div class="sa-stat-chip"><div class="v">${esc(d.rank_title || "Cadet")}</div><div class="k">Rank ${d.rank_level || 1}</div></div>
    <div class="sa-stat-chip"><div class="v">🔥 ${d.streak_days || 0}d</div><div class="k">Streak</div></div>
    ${thirdStat}`;

  $("saGameGrid").innerHTML = d.games.map((g) => {
    const stars = [1, 2, 3].map((n) => `<span class="${g.mastery_stars >= n ? "" : "off"}">★</span>`).join("");
    const unit = BANK_UNIT_LABEL[g.id] || "missions";
    const best = g.id === "typing_arena" && g.best_wpm > 0
      ? `Best: ${g.best_wpm} WPM`
      : (g.best_score > 0 ? `${g.best_score} pts` : `${g.bank_size} ${unit}`);
    return `
      <button type="button" class="sa-card ${g.recommended ? "recommended" : ""}" data-launch="${esc(g.id)}"
        style="--card-accent:${g.accent};--card-glow:${g.glow}">
        <div class="sa-card-top">
          <div class="sa-card-icon">${g.icon}</div>
          ${g.recommended ? `<span class="sa-rec-badge">★ Hot Drop</span>` : `<span class="sa-tag">${esc(g.est_minutes)}</span>`}
        </div>
        <h2>${esc(g.title)}</h2>
        <div class="sa-card-sub">${esc(g.subtitle)}</div>
        <div class="sa-card-reason">${esc(g.status_pill || "")}</div>
        <div class="sa-card-foot">
          <span>${esc(g.controls)}</span>
          <span class="sa-card-foot-right"><span class="sa-stars">${stars}</span><span>${esc(best)}</span></span>
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
  App.activeSeconds = 0;
  beginStepClock();

  $("saSummaryModal").hidden = true;
  $("saLoadingText").textContent = useAi
    ? "Warping into your story world…"
    : "Powering up arena…";
  $("saLoading").hidden = false;

  try {
    const r = await fetch("/api/skill-games/pack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: gameId, use_ai: useAi, sandbox: IS_SANDBOX ? 1 : 0 }),
    });
    if (!r.ok) throw new Error(await r.text());
    const pack = await r.json();
    $("saLoading").hidden = true;
    $("saHubView").hidden = true;
    $("saGameStage").hidden = false;
    $("saGameStage").innerHTML = "";
    const startSec = Number(pack.adaptive?.start_tier) || 1;
    setHud({ visible: true, step: 1, total: pack.items.length, score: 0, combo: 0, sector: startSec, overclock: false, title: pack.game.title, aiPack: !!pack.ai_generated });

    if (gameId === "sentence_surgery") runSentenceSurgery(pack);
    else if (gameId === "word_forge") runWordForge(pack);
    else if (gameId === "homophone_asteroids") runHomophoneAsteroids(pack);
    else if (gameId === "sentence_stretch") runSentenceStretch(pack);
    else if (gameId === "typing_arena") runTypingArena(pack);
    else if (gameId === "clue_detective") runClueDetective(pack);
  } catch (err) {
    $("saLoading").hidden = true;
    alert("Could not launch arena: " + err);
    loadHub();
  }
}

async function finishGame(result) {
  commitStepClock(40);
  const gameId = App.currentGameId;
  runCleanups();
  const activeSec = Math.max(5, Math.round(result.active_seconds || App.activeSeconds));
  const payload = {
    game_id: gameId,
    score: App.score,
    correct: result.correct,
    total: result.total,
    active_seconds: activeSec,
    wpm: result.wpm || 0,
    cpm: result.cpm || 0,
    production_passed: !!result.production_passed,
    production_sentence: result.production_sentence || "",
    word_results: result.word_results || [],
    skill_hits: result.skill_hits || {},
    subskill_hits: result.subskill_hits || {},
    char_errors: result.char_errors || {},
    word_outcomes: result.word_outcomes || [],
    played_ids: result.played_ids || [],
    peak_tier: result.peak_tier || App.sector || 1,
    sandbox: IS_SANDBOX ? 1 : 0,
  };

  let d;
  try {
    const r = await fetch("/api/skill-games/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    d = await r.json();
  } catch (err) {
    d = { ok: false, stars: 0, accuracy: Math.round((100 * payload.correct) / Math.max(1, payload.total)), score: payload.score, srs_updates: [], stealth_badges: [], rank_title: "Cadet", zpd_sector: 1, arcade_reward: null };
  }

  if (d.accuracy >= 65) {
    SFX.victory();
    FX.burst(window.innerWidth * 0.5, window.innerHeight * 0.3, "#facc15", 45);
    FX.burst(window.innerWidth * 0.32, window.innerHeight * 0.35, "#38bdf8", 32);
    FX.burst(window.innerWidth * 0.68, window.innerHeight * 0.35, "#10b981", 32);
  } else {
    SFX.ok();
  }

  if (d.arcade) renderBankPill(d.arcade);
  if (IS_EMBEDDED) {
    try { window.parent.postMessage({ __skillArcadeUpdated: d }, "*"); } catch (_) { }
  }

  const stars = [1, 2, 3].map((n) => `<span style="opacity:${d.stars >= n ? 1 : 0.22}">★</span>`).join("");
  $("saSumStars").innerHTML = stars;
  $("saSumTitle").textContent = d.stars === 3
    ? "S-Rank Clear!"
    : (d.stars === 2 ? "Arena Cleared!" : (d.accuracy >= 65 ? "Sector Secured!" : "Shields Low — Aim for 65%+!"));

  const m3 = payload.wpm > 0
    ? `<div class="sa-sum-metric"><div class="v">${payload.wpm} WPM</div><div class="k">Top Speed</div></div>`
    : `<div class="sa-sum-metric"><div class="v">${payload.correct}/${payload.total}</div><div class="k">Clean Hits</div></div>`;
  $("saSumMetrics").innerHTML = `
    <div class="sa-sum-metric"><div class="v">${d.score}</div><div class="k">Score</div></div>
    <div class="sa-sum-metric"><div class="v">${d.accuracy}%</div><div class="k">Precision</div></div>
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
    const up = d.srs_updates.map((u) => `<b>${esc(u.word)}</b> → Vault ${u.box}/5 ${u.first_try ? "✓" : "(re-forge next run)"}`).join(" · ");
    lines.push(`<div>🗡️ <b>Rune Vault:</b> ${up}</div>`);
  }
  if (d.stealth_badges?.length) {
    lines.push(`<div>⚡ <b>Upgrades:</b> ${d.stealth_badges.map((b) => `<span class="sa-tag">${esc(b)}</span>`).join(" ")}</div>`);
  }
  if (payload.production_sentence) {
    lines.push(`<div>💥 <b>Finishing Strike:</b> “${esc(payload.production_sentence)}”</div>`);
  }
  if (!lines.length) {
    lines.push(d.accuracy >= 65
      ? `<div>🚀 Rank: <b>${esc(d.rank_title || "Cadet")}</b> · Sector ${d.zpd_sector || 1} Ready</div>`
      : `<div>💡 Hit 65%+ precision next run to unlock higher sectors and bank bonus time!</div>`);
  }
  $("saSumDetails").innerHTML = lines.join("");

  $("saPlayAiBtn").hidden = !App.hubData?.ai_available;
  $("saSummaryModal").hidden = false;
}

// ===========================================================================
// GAME 1: ⚔️ SENTENCE SURGERY (2x DPR Cyber Bay + True Segment-Intersect Stylus Slash & Tap!)
// ===========================================================================

function runSentenceSurgery(pack) {
  const stage = $("saGameStage");
  const items = pack.items;
  const zpd = createZpdDirector(pack);
  let idx = 0;
  let correct = 0;
  let repairedCases = 0;
  let caseHealthy = false;
  let laserFlash = 0;
  const skillHits = {};

  stage.innerHTML = `
    <div class="sa-scene-wrap" style="border-color:rgba(56,189,248,0.4)"><canvas id="ssSceneCv"></canvas></div>
    <div id="ssStepHost" style="display:flex;flex-direction:column;gap:12px"></div>`;

  const scv = $("ssSceneCv");
  const sctx = scv.getContext("2d");
  let active = true;
  let rafId = 0;
  let t0 = 0;

  function drawCyberBay() {
    if (!active) return;
    const { W, H } = fitCanvas(scv, sctx, 300, 110);
    t0 += 0.04;

    const bgG = sctx.createLinearGradient(0, 0, 0, H);
    bgG.addColorStop(0, "#050b18"); bgG.addColorStop(1, "#0a172c");
    sctx.fillStyle = bgG; sctx.fillRect(0, 0, W, H);

    sctx.strokeStyle = "rgba(56, 189, 248, 0.09)";
    sctx.lineWidth = 1;
    const stepG = 28;
    const offX = (t0 * 10) % stepG;
    for (let x = -offX; x < W; x += stepG) { sctx.beginPath(); sctx.moveTo(x, 0); sctx.lineTo(x, H); sctx.stroke(); }
    for (let y = 0; y < H; y += stepG) { sctx.beginPath(); sctx.moveTo(0, y); sctx.lineTo(W, y); sctx.stroke(); }

    // Crisp 2x DPR Sentence Integrity EKG Waveform
    sctx.save();
    const waveColor = caseHealthy ? "#10b981" : "#fb7185";
    sctx.strokeStyle = waveColor; sctx.shadowColor = waveColor; sctx.shadowBlur = 12; sctx.lineWidth = 2.4;
    sctx.beginPath();
    for (let x = 20; x < W - 20; x += 5) {
      const p = x * 0.03 - t0 * 2.4;
      const y = caseHealthy
        ? H * 0.58 + Math.sin(p) * 13
        : H * 0.58 + Math.sin(p * 1.9) * 10 + ((Math.sin(p * 7.3) > 0.85) ? -20 : 0);
      if (x === 20) sctx.moveTo(x, y); else sctx.lineTo(x, y);
    }
    sctx.stroke();
    sctx.restore();

    // Overhead Laser Scalpel Arm
    const armX = W * 0.5 + Math.sin(t0 * 0.9) * (W * 0.24);
    sctx.save();
    sctx.fillStyle = "#1e293b"; sctx.strokeStyle = "#38bdf8"; sctx.lineWidth = 2;
    sctx.fillRect(armX - 18, 0, 36, 22); sctx.strokeRect(armX - 18, 0, 36, 22);
    sctx.beginPath(); sctx.moveTo(armX - 10, 22); sctx.lineTo(armX + 10, 22); sctx.lineTo(armX, 38); sctx.closePath();
    sctx.fillStyle = "#38bdf8"; sctx.fill();

    if (laserFlash > 0.04) {
      sctx.strokeStyle = `rgba(56, 189, 248, ${laserFlash})`;
      sctx.shadowColor = "#38bdf8"; sctx.shadowBlur = 24; sctx.lineWidth = 8 * laserFlash;
      sctx.beginPath(); sctx.moveTo(armX, 38); sctx.lineTo(W * 0.5, H); sctx.stroke();
    }
    sctx.restore();

    sctx.font = "700 12px 'JetBrains Mono', monospace";
    sctx.fillStyle = caseHealthy ? "#6ee7b7" : "#fda4af";
    sctx.textAlign = "left";
    sctx.fillText(caseHealthy ? "STATUS: STREAM STABILIZED ✓" : "STATUS: STREAM FAULT DETECTED", 18, 22);

    sctx.textAlign = "right";
    sctx.fillStyle = "#7dd3fc";
    sctx.fillText(`REPAIRED: ${repairedCases} / ${items.length}`, W - 18, 22);

    for (let i = 0; i < items.length; i++) {
      const cx = W - 18 - (items.length - 1 - i) * 20;
      sctx.fillStyle = i < repairedCases ? "#10b981" : "rgba(148,163,184,0.25)";
      sctx.beginPath(); sctx.arc(cx - 5, 38, 5.5, 0, Math.PI * 2); sctx.fill();
    }

    laserFlash *= 0.88;
    rafId = requestAnimationFrame(drawCyberBay);
  }
  rafId = requestAnimationFrame(drawCyberBay);
  addCleanup(() => { active = false; cancelAnimationFrame(rafId); });

  let stepCleanup = null;
  addCleanup(() => { if (stepCleanup) { stepCleanup(); stepCleanup = null; } });

  function trackSkill(sid, ok) {
    skillHits[sid] = skillHits[sid] || { correct: 0, total: 0 };
    skillHits[sid].total += 1;
    if (ok) skillHits[sid].correct += 1;
  }

  function renderStep() {
    VOICE.stop();
    if (stepCleanup) { stepCleanup(); stepCleanup = null; }
    if (idx >= items.length) {
      finishGame({ correct, total: items.length, skill_hits: skillHits, subskill_hits: zpd.subskillHits, played_ids: zpd.playedIds, peak_tier: zpd.peakTier, production_passed: false });
      return;
    }
    beginStepClock();
    caseHealthy = false;
    const it = items[idx];
    const host = $("ssStepHost");
    setHud({ visible: true, step: idx + 1, total: items.length, score: App.score, combo: App.combo, title: "Cyber Blade", aiPack: !!pack.ai_generated });

    const spokenSample = it.mode === "runon"
      ? it.words.join(" ")
      : (it.mode === "fragment" ? it.broken : it.tokens.map((t) => t.fix).join(" "));

    if (it.mode === "runon") {
      host.innerHTML = `
        <div class="sa-panel">
          <div class="sa-mission-banner">
            <span class="sa-mission-tag">✂️ LASER SLASH · SPLIT STREAM</span>
            <button type="button" class="sa-speak-btn" id="ssSpeakBtn">🔊 Read Aloud</button>
          </div>
          <div class="sa-prompt-text">${esc(it.prompt)}</div>
        </div>
        <div class="ss-slash-arena" id="ssArena">
          <canvas class="ss-slash-canvas" id="ssSlashCanvas"></canvas>
          <div class="ss-word-row" id="ssWordRow"></div>
        </div>
        <div class="sa-feedback idle" id="ssFb"><span class="sa-fb-msg">Slash your pen (or tap the glowing seam) right between Thought 1 and Thought 2!</span></div>`;

      $("ssSpeakBtn").onclick = () => VOICE.speak(spokenSample, { force: true });

      const row = $("ssWordRow");
      const gapEls = [];
      it.words.forEach((w, wi) => {
        const sp = document.createElement("span");
        sp.className = "ss-word";
        sp.textContent = w;
        sp.dataset.wi = wi;
        row.appendChild(sp);
        if (wi < it.words.length - 1) {
          const gap = document.createElement("span");
          gap.className = "ss-gap";
          gap.dataset.gap = wi;
          gap.textContent = "┆";
          row.appendChild(gap);
          gapEls.push(gap);
        }
      });

      let locked = false;
      let missed = false;

      function checkSlice(gapIdx, gapEl) {
        if (locked) return;
        if (gapIdx === it.split_after) {
          locked = true;
          commitStepClock(40);
          caseHealthy = true;
          repairedCases += 1;
          laserFlash = 1.0;
          SFX.slice();
          gapEl.classList.remove("hot");
          gapEl.classList.add("sliced");
          gapEl.textContent = ".  |";
          row.querySelectorAll(".ss-word").forEach((el) => {
            const wi = Number(el.dataset.wi);
            el.style.transform = wi <= gapIdx ? "translateX(-8px)" : "translateX(8px)";
          });
          const nextWord = row.querySelector(`[data-wi="${gapIdx + 1}"]`);
          if (nextWord) {
            nextWord.textContent = nextWord.textContent.charAt(0).toUpperCase() + nextWord.textContent.slice(1);
            nextWord.style.borderColor = "#10b981";
            nextWord.style.color = "#6ee7b7";
          }
          if (!missed) correct += 1;
          trackSkill(it.skill, !missed);
          zpd.record(it, !missed, idx + 1, items);
          addPoints(missed ? 60 : 120, gapEl, "#38bdf8");
          setFeedback($("ssFb"), "ok", `✂️ <b>Clean laser slice!</b> ${esc(it.fixed)} — ${esc(it.explain)}`, {
            id: "ssNextBtn", label: "Next Stream →", onClick: () => { idx += 1; renderStep(); },
          });
        } else {
          missed = true;
          resetCombo();
          SFX.bad();
          gapEl.style.borderColor = "#fb7185";
          safeTimeout(() => { gapEl.style.borderColor = ""; }, 420);
          setFeedback($("ssFb"), "bad", "Not quite there — tap <b>🔊 Read Aloud</b> to hear where Thought 1 finishes!");
        }
      }

      const arena = $("ssArena");
      const cv = $("ssSlashCanvas");
      const c2 = cv.getContext("2d");
      let dims = fitCanvas(cv, c2, 240, 80);
      const ro = new ResizeObserver(() => { dims = fitCanvas(cv, c2, 240, 80); });
      ro.observe(arena);
      stepCleanup = () => ro.disconnect();

      let activePid = null;
      let pts = [];
      let screenPts = [];

      const findHoveredGap = (cx, cy) => {
        let best = null, bestD = 32;
        for (const g of gapEls) {
          const gr = g.getBoundingClientRect();
          const gx = gr.left + gr.width / 2, gy = gr.top + gr.height / 2;
          const d = Math.hypot(cx - gx, cy - gy);
          if (d < bestD) { bestD = d; best = g; }
        }
        return best;
      };

      cv.addEventListener("pointerdown", (e) => {
        if (locked) return;
        if (e.pointerType === "pen") App.penDetected = true;
        if (App.penDetected && e.pointerType === "touch") return; // Palm rejection
        if (activePid !== null) return;
        activePid = e.pointerId;
        cv.setPointerCapture?.(e.pointerId);
        const r = arena.getBoundingClientRect();
        pts = [{ x: e.clientX - r.left, y: e.clientY - r.top }];
        screenPts = [{ x: e.clientX, y: e.clientY }];
      });

      cv.addEventListener("pointermove", (e) => {
        if (locked) return;
        // Hover highlight for mouse/stylus before pressing
        if (activePid === null) {
          const hg = findHoveredGap(e.clientX, e.clientY);
          gapEls.forEach((g) => g.classList.toggle("hot", g === hg));
          return;
        }
        if (e.pointerId !== activePid) return;
        const r = arena.getBoundingClientRect();
        const evts = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
        for (const ev of evts) {
          pts.push({ x: ev.clientX - r.left, y: ev.clientY - r.top });
          screenPts.push({ x: ev.clientX, y: ev.clientY });
        }
        c2.clearRect(0, 0, dims.W, dims.H);
        c2.strokeStyle = "#38bdf8";
        c2.lineWidth = 4.5; c2.lineCap = "round";
        c2.shadowColor = "#38bdf8"; c2.shadowBlur = 16;
        c2.beginPath();
        pts.forEach((p, i) => i === 0 ? c2.moveTo(p.x, p.y) : c2.lineTo(p.x, p.y));
        c2.stroke();
      });

      const onUp = (e) => {
        if (e.pointerId !== activePid) return;
        activePid = null;
        c2.clearRect(0, 0, dims.W, dims.H);
        gapEls.forEach((g) => g.classList.remove("hot"));

        if (screenPts.length >= 1) {
          let hitGap = null;
          if (screenPts.length >= 2) {
            FX.slash(screenPts, "#38bdf8", 7);
            // Exact geometric line-segment-to-gap-rect intersection so fast stylus slashes NEVER miss!
            for (let i = 0; i < screenPts.length - 1 && !hitGap; i++) {
              const p1 = screenPts[i], p2 = screenPts[i + 1];
              for (const g of gapEls) {
                if (segmentHitsRect(p1.x, p1.y, p2.x, p2.y, g.getBoundingClientRect(), 8)) {
                  hitGap = g;
                  break;
                }
              }
            }
          }
          // Single-tap or near-gap fallback — makes tapping ANY divider work 100% reliably!
          if (!hitGap) {
            const last = screenPts[screenPts.length - 1];
            hitGap = findHoveredGap(last.x, last.y);
          }
          if (hitGap) checkSlice(Number(hitGap.dataset.gap), hitGap);
        }
        pts = [];
        screenPts = [];
      };
      cv.addEventListener("pointerup", onUp);
      cv.addEventListener("pointercancel", onUp);
      cv.addEventListener("pointerleave", () => { if (activePid === null) gapEls.forEach((g) => g.classList.remove("hot")); });
    } else if (it.mode === "fragment") {
      host.innerHTML = `
        <div class="sa-panel">
          <div class="sa-mission-banner">
            <span class="sa-mission-tag">🔧 CIRCUIT REPAIR · MISSING ${esc(String(it.missing || "ACTION").toUpperCase())}</span>
            <button type="button" class="sa-speak-btn" id="ssSpeakBtn">🔊 Read Aloud</button>
          </div>
          <div class="sa-prompt-text">${esc(it.prompt)}</div>
          <div style="margin-top:12px;padding:14px 18px;border-radius:14px;background:rgba(251,113,133,0.12);border:1.5px dashed #fb7185;font-size:1.18rem;font-weight:700;color:#fecdd3">
            ⚠️ “${esc(it.broken)}”
          </div>
        </div>
        <div class="sa-choice-list" id="ssChoices"></div>
        <div class="sa-feedback idle" id="ssFb"><span class="sa-fb-msg">Snap in the power module that locks in Who + Does What!</span></div>`;

      $("ssSpeakBtn").onclick = () => VOICE.speak(spokenSample, { force: true });
      let locked = false;
      let missed = false;
      it.choices.forEach((ch) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "sa-choice-btn";
        b.textContent = ch.text;
        b.onclick = () => {
          if (locked) return;
          if (ch.ok) {
            locked = true;
            commitStepClock(40);
            caseHealthy = true;
            repairedCases += 1;
            laserFlash = 1.0;
            b.classList.add("ok");
            SFX.ok();
            if (!missed) correct += 1;
            trackSkill(it.skill, !missed);
            zpd.record(it, !missed, idx + 1, items);
            addPoints(missed ? 60 : 120, b, "#10b981");
            setFeedback($("ssFb"), "ok", `⚡ <b>Circuit Powered!</b> ${esc(it.explain)}`, {
              id: "ssNextBtn", label: "Next Stream →", onClick: () => { idx += 1; renderStep(); },
            });
          } else {
            missed = true;
            resetCombo();
            b.classList.add("bad");
            SFX.bad();
            setFeedback($("ssFb"), "bad", esc(ch.why || "Still incomplete — check who is doing what!"));
          }
        };
        $("ssChoices").appendChild(b);
      });
    } else {
      const bugTotal = it.tokens.filter((t) => t.bug).length;
      let bugsFixed = 0;
      let cleanTaps = 0;
      host.innerHTML = `
        <div class="sa-panel">
          <div class="sa-mission-banner">
            <span class="sa-mission-tag">🛡️ SECURITY SEALS · <span id="ssBugCount">${bugTotal} BUGS LEFT</span></span>
            <button type="button" class="sa-speak-btn" id="ssSpeakBtn">🔊 Read Aloud</button>
          </div>
          <div class="sa-prompt-text">${esc(it.prompt)}</div>
        </div>
        <div class="sa-panel" style="display:flex;flex-wrap:wrap;gap:10px;justify-content:center;padding:24px 20px" id="ssTokenWrap"></div>
        <div class="sa-feedback idle" id="ssFb"><span class="sa-fb-msg">Tap each glitched word to lock capitals, apostrophes, quotes, commas, or end marks!</span></div>`;

      $("ssSpeakBtn").onclick = () => VOICE.speak(spokenSample, { force: true });
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
            laserFlash = 0.8;
            b.textContent = tk.fix;
            b.classList.add("fixed");
            SFX.ok();
            addPoints(50, b, "#10b981");
            $("ssBugCount").textContent = `${bugTotal - bugsFixed} BUG${bugTotal - bugsFixed === 1 ? "" : "S"} LEFT`;
            if (bugsFixed >= bugTotal) {
              commitStepClock(40);
              caseHealthy = true;
              repairedCases += 1;
              const cleanRun = cleanTaps === 0;
              if (cleanRun) correct += 1;
              trackSkill(it.skill, cleanRun);
              zpd.record(it, cleanRun, idx + 1, items);
              setFeedback($("ssFb"), "ok", `✅ <b>All bugs sealed!</b> ${esc(it.explain)}`, {
                id: "ssNextBtn", label: "Next Stream →", onClick: () => { idx += 1; renderStep(); },
              });
            } else {
              setFeedback($("ssFb"), "ok", `Sealed! ${esc(tk.hint || "")} (${bugTotal - bugsFixed} left!)`);
            }
          } else {
            cleanTaps += 1;
            resetCombo();
            SFX.bad();
            b.classList.add("shake");
            safeTimeout(() => b.classList.remove("shake"), 360);
            setFeedback($("ssFb"), "bad", `“${esc(tk.raw)}” is already clean! Check capitals, apostrophes, quotes, commas, or end marks.`);
          }
        };
        $("ssTokenWrap").appendChild(b);
      });
    }
  }
  renderStep();
}

// ===========================================================================
// GAME 2: 🔥 WORD FORGE (Right-Side-Up Swinging Hammer + No Spoilers + Yoga Pen!)
// ===========================================================================

function runWordForge(pack) {
  const stage = $("saGameStage");
  const items = pack.items;
  const zpd = createZpdDirector(pack);
  let idx = 0;
  let correct = 0;
  const wordResults = [];
  let forgedCount = 0;
  let hammerPhase = 0;
  let shake = 0;
  const forgeSparks = [];

  stage.innerHTML = `
    <div class="wf-canvas-wrap"><canvas id="wfCanvas"></canvas></div>
    <div class="sa-panel" id="wfBody"></div>
    <div class="sa-feedback idle" id="wfFb"><span class="sa-fb-msg">Listen to the sentence, then snap the matching runes onto the anvil!</span></div>`;

  const cv = $("wfCanvas");
  const ctx = cv.getContext("2d");
  const embers = Array.from({ length: 38 }, () => ({
    x: Math.random(), y: Math.random(),
    vy: 0.004 + Math.random() * 0.008, r: 1.4 + Math.random() * 2.6, a: 0.35 + Math.random() * 0.65,
  }));
  let rafId = 0;
  let active = true;
  let dims = { W: 800, H: 196 };

  function triggerHammerStrike(big = false) {
    hammerPhase = 1.0;
    shake = big ? 10 : 5;
    const { W, H } = dims;
    const cnt = big ? 48 : 24;
    for (let i = 0; i < cnt; i++) {
      const a = -Math.PI * 0.1 - Math.random() * Math.PI * 0.8;
      const sp = (big ? 4 : 2.5) + Math.random() * (big ? 7.5 : 4.5);
      forgeSparks.push({
        x: W * 0.5, y: H - 56,
        vx: Math.cos(a) * sp, vy: Math.sin(a) * sp,
        life: 1, color: i % 3 === 0 ? "#fef08a" : (i % 3 === 1 ? "#fb923c" : "#38bdf8"),
      });
    }
  }

  function drawEnchantedBlade(cx, cy, stages, timeS) {
    const x0 = cx - 145;
    ctx.save();
    // Crisp holographic blueprint silhouette so even stage 0 looks intentional and cool!
    ctx.strokeStyle = "rgba(56, 189, 248, 0.35)";
    ctx.fillStyle = "rgba(56, 189, 248, 0.05)";
    ctx.setLineDash([5, 5]);
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.moveTo(x0 + 82, cy - 13); ctx.lineTo(x0 + 270, cy - 13); ctx.lineTo(x0 + 302, cy);
    ctx.lineTo(x0 + 270, cy + 13); ctx.lineTo(x0 + 82, cy + 13); ctx.closePath();
    ctx.fill(); ctx.stroke();
    ctx.setLineDash([]);

    if (stages >= 1) {
      ctx.fillStyle = "#475569"; ctx.strokeStyle = "#cbd5e1"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(x0 + 10, cy, 12, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#38bdf8"; ctx.beginPath(); ctx.arc(x0 + 10, cy, 4.5, 0, Math.PI * 2); ctx.fill();
    }
    if (stages >= 2) {
      ctx.fillStyle = "#78350f"; ctx.strokeStyle = "#d97706"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.roundRect(x0 + 22, cy - 7, 52, 14, 4); ctx.fill(); ctx.stroke();
      ctx.strokeStyle = "#f59e0b";
      for (let gx = x0 + 29; gx < x0 + 70; gx += 10) { ctx.beginPath(); ctx.moveTo(gx, cy - 6); ctx.lineTo(gx + 5, cy + 6); ctx.stroke(); }
    }
    if (stages >= 3) {
      ctx.fillStyle = "#f59e0b"; ctx.strokeStyle = "#fef08a"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.roundRect(x0 + 72, cy - 26, 16, 52, 5); ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#10b981"; ctx.shadowColor = "#10b981"; ctx.shadowBlur = 12;
      ctx.beginPath(); ctx.arc(x0 + 80, cy, 6, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur = 0;
    }
    if (stages >= 4) {
      const bg = ctx.createLinearGradient(x0 + 88, cy - 13, x0 + 88, cy + 13);
      bg.addColorStop(0, "#bae6fd"); bg.addColorStop(0.5, "#38bdf8"); bg.addColorStop(1, "#0284c7");
      ctx.fillStyle = bg; ctx.strokeStyle = "#e0f2fe"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.roundRect(x0 + 88, cy - 13, 95, 26, 2); ctx.fill(); ctx.stroke();
    }
    if (stages >= 5) {
      const bg2 = ctx.createLinearGradient(x0 + 183, cy - 13, x0 + 183, cy + 13);
      bg2.addColorStop(0, "#e0f2fe"); bg2.addColorStop(0.5, "#22d3ee"); bg2.addColorStop(1, "#0369a1");
      ctx.fillStyle = bg2; ctx.strokeStyle = "#f0f9ff"; ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x0 + 183, cy - 13); ctx.lineTo(x0 + 268, cy - 13); ctx.lineTo(x0 + 302, cy);
      ctx.lineTo(x0 + 268, cy + 13); ctx.lineTo(x0 + 183, cy + 13); ctx.closePath();
      ctx.fill(); ctx.stroke();
    }
    if (stages >= 6) {
      ctx.strokeStyle = `rgba(192, 132, 252, ${0.55 + Math.sin(timeS * 6) * 0.35})`;
      ctx.shadowColor = "#a855f7"; ctx.shadowBlur = 24; ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(x0 + 86, cy - 16); ctx.lineTo(x0 + 270, cy - 16); ctx.lineTo(x0 + 308, cy);
      ctx.lineTo(x0 + 270, cy + 16); ctx.lineTo(x0 + 86, cy + 16); ctx.closePath();
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawForge() {
    if (!active) return;
    dims = fitCanvas(cv, ctx, 300, 160);
    const { W, H } = dims;
    const nowS = performance.now() * 0.001;
    const sx = shake > 0.2 ? (Math.random() - 0.5) * shake : 0;
    const sy = shake > 0.2 ? (Math.random() - 0.5) * shake : 0;
    shake *= 0.84;

    ctx.save();
    ctx.translate(sx, sy);

    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, "#0b0813"); g.addColorStop(0.55, "#1d1016"); g.addColorStop(1, "#451408");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

    ctx.strokeStyle = "rgba(255, 255, 255, 0.045)"; ctx.lineWidth = 1;
    for (let row = 0; row < 7; row++) {
      const y = row * 30; const off = (row % 2) * 30;
      for (let x = -off; x < W; x += 60) ctx.strokeRect(x, y, 60, 30);
    }

    const pulse = 0.44 + Math.sin(nowS * 5) * 0.08 + hammerPhase * 0.35;
    const glow = ctx.createRadialGradient(W * 0.5, H * 0.96, 12, W * 0.5, H * 0.96, W * 0.44);
    glow.addColorStop(0, `rgba(251, 146, 60, ${Math.min(0.95, pulse)})`);
    glow.addColorStop(0.5, "rgba(234, 88, 12, 0.22)"); glow.addColorStop(1, "transparent");
    ctx.fillStyle = glow; ctx.fillRect(0, 0, W, H);

    for (const e of embers) {
      e.y -= e.vy * (1 + hammerPhase * 2.5);
      if (e.y < 0) { e.y = 1.05; e.x = 0.1 + Math.random() * 0.8; }
      ctx.fillStyle = `rgba(253, 186, 116, ${e.a * e.y})`;
      ctx.beginPath(); ctx.arc(e.x * W, e.y * H, e.r, 0, Math.PI * 2); ctx.fill();
    }

    ctx.font = "700 12px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#fdba74"; ctx.textAlign = "center";
    ctx.fillText(`OBSIDIAN FORGE · ENCHANTED BLADE ${forgedCount}/${items.length}`, W * 0.5, 20);

    drawEnchantedBlade(W * 0.5, H * 0.36, forgedCount, nowS);

    // Anvil + Glowing Hot Metal Ingot Billet on top!
    const cx = W * 0.5;
    ctx.save();
    ctx.fillStyle = "#fb923c"; ctx.shadowColor = "#f97316"; ctx.shadowBlur = 18;
    ctx.beginPath(); ctx.roundRect(cx - 28, H - 64, 56, 12, 4); ctx.fill();
    ctx.restore();

    ctx.fillStyle = "#1e293b";
    ctx.strokeStyle = hammerPhase > 0.1 ? "#facc15" : "rgba(251, 146, 60, 0.55)";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(cx - 82, H - 8); ctx.lineTo(cx + 82, H - 8);
    ctx.lineTo(cx + 54, H - 32); ctx.lineTo(cx + 106, H - 52);
    ctx.lineTo(cx - 98, H - 52); ctx.lineTo(cx - 54, H - 32);
    ctx.closePath();
    ctx.fill(); ctx.stroke();

    // FIXED HAMMER TRIG: handle extends in -X, so POSITIVE angle lifts the hammer UP above the anvil!
    // Rest = +0.58 rad (cocked UP in the air), Slam swings DOWN to -0.02 rad right onto the glowing ingot!
    const restAngle = 0.58;
    const slamAngle = hammerPhase > 0
      ? restAngle - Math.sin(hammerPhase * Math.PI) * 0.62
      : restAngle + Math.sin(nowS * 2.2) * 0.05;
    ctx.save();
    ctx.translate(cx + 124, H - 58);
    ctx.rotate(slamAngle);
    ctx.fillStyle = "#92400e"; ctx.strokeStyle = "#f59e0b"; ctx.lineWidth = 1.6;
    ctx.fillRect(-108, -5, 108, 10); ctx.strokeRect(-108, -5, 108, 10);
    ctx.fillStyle = "#475569"; ctx.strokeStyle = hammerPhase > 0.2 ? "#fef08a" : "#cbd5e1"; ctx.lineWidth = 2.2;
    ctx.beginPath(); ctx.roundRect(-128, -22, 34, 44, 5); ctx.fill(); ctx.stroke();
    ctx.restore();

    for (let i = forgeSparks.length - 1; i >= 0; i--) {
      const sp = forgeSparks[i];
      sp.x += sp.vx; sp.y += sp.vy; sp.vy += 0.24; sp.life -= 0.032;
      if (sp.life <= 0) { forgeSparks.splice(i, 1); continue; }
      ctx.save();
      ctx.globalAlpha = sp.life;
      ctx.fillStyle = sp.color; ctx.shadowColor = sp.color; ctx.shadowBlur = 10;
      ctx.fillRect(sp.x - 2, sp.y - 2, 4.5, 4.5);
      ctx.restore();
    }

    ctx.restore();
    if (hammerPhase > 0) hammerPhase = Math.max(0, hammerPhase - 0.07);
    rafId = requestAnimationFrame(drawForge);
  }
  rafId = requestAnimationFrame(drawForge);
  addCleanup(() => { active = false; cancelAnimationFrame(rafId); });

  let penCleanup = null;
  addCleanup(() => { if (penCleanup) { penCleanup(); penCleanup = null; } });

  const RULES = [
    { id: "keep", label: "Keep Base Clean" },
    { id: "double", label: "Double Last Letter" },
    { id: "drop_e", label: "Drop Silent -e" },
    { id: "y_to_i", label: "Flip y → i" },
  ];

  function renderWord() {
    VOICE.stop();
    if (penCleanup) { penCleanup(); penCleanup = null; }
    if (idx >= items.length) {
      finishGame({ correct, total: items.length, word_results: wordResults, subskill_hits: zpd.subskillHits, played_ids: zpd.playedIds, peak_tier: zpd.peakTier, production_passed: true });
      return;
    }
    beginStepClock();
    const it = items[idx];
    let roundMissed = false;
    setHud({ visible: true, step: idx + 1, total: items.length, score: App.score, combo: App.combo, title: "Obsidian Forge", aiPack: !!pack.ai_generated });
    const body = $("wfBody");
    const fb = $("wfFb");

    VOICE.speak(`${it.word}. ${it.context_sentence || ""}`);

    const neededParts = [];
    if (it.prefix) neededParts.push({ part: "prefix", label: "Starter" });
    neededParts.push({ part: "base", label: "Base" });
    if (it.suffix) neededParts.push({ part: "suffix", label: "Ending" });
    const filled = {};

    body.innerHTML = `
      <div class="sa-mission-banner">
        <span class="sa-mission-tag">🔥 ${esc(it.unit)}</span>
        <div style="display:flex;gap:8px;align-items:center">
          ${it.from_deck ? `<span class="sa-tag" style="color:#fdba74;border:1px solid rgba(249,115,22,0.4)">Vault ${it.box}/5</span>` : ""}
          <button type="button" class="sa-speak-btn" id="wfHearBtn">🔊 Hear Word</button>
        </div>
      </div>
      <div class="wf-context-bar">“${esc(it.blanked_sentence || it.context_sentence || "")}”</div>
      <div class="wf-anvil-slots" id="wfSlots"></div>
      <div class="wf-rune-tray" id="wfTray"></div>
      <div id="wfStep2" hidden></div>`;

    $("wfHearBtn").onclick = () => VOICE.speak(`${it.word}. ${it.context_sentence || ""}`, { force: true });

    if (it.direct_memory || !it.tiles?.length) {
      showMemoryStrike();
      return;
    }

    setFeedback(fb, "idle", "Step 1: Listen to the word & sentence above, then snap the matching runes onto the anvil!");

    function drawSlots() {
      $("wfSlots").innerHTML = neededParts.map((p, pi) => {
        const val = filled[p.part];
        return `${pi > 0 ? '<span class="wf-plus">+</span>' : ""}<div class="wf-slot ${val ? "filled" : ""}">${esc(val || p.label)}</div>`;
      }).join("");
    }
    drawSlots();

    const partName = (pt) => (pt === "prefix" ? "starter" : (pt === "suffix" ? "ending" : "base"));
    const runeBtns = [];
    it.tiles.forEach((tile) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "wf-rune";
      b.textContent = tile.text;
      b.onclick = () => {
        if (!tile.correct) {
          roundMissed = true;
          resetCombo();
          SFX.bad();
          b.style.borderColor = "#fb7185";
          setFeedback(fb, "bad", `Not '${esc(tile.text)}' — tap <b>🔊 Hear Word</b> and pick the matching ${partName(tile.part)} rune!`);
          return;
        }
        filled[tile.part] = tile.text;
        b.classList.add("used");
        SFX.hammer();
        triggerHammerStrike(false);
        FX.burstEl(b, "#f97316", 16);
        drawSlots();
        if (neededParts.every((p) => filled[p.part])) {
          runeBtns.forEach((rb) => { rb.disabled = true; rb.classList.add("used"); });
          showRulePick();
        }
      };
      runeBtns.push(b);
      $("wfTray").appendChild(b);
    });

    function showRulePick() {
      const s2 = $("wfStep2");
      s2.hidden = false;
      setFeedback(fb, "idle", "Step 2: Which Forge Rule locks these runes together?");
      s2.innerHTML = `
        <div style="text-align:center;font-weight:600;color:#fed7aa;margin-bottom:8px">Choose the Forge Rule before the furnace shutter drops:</div>
        <div class="wf-rule-row" id="wfRuleRow"></div>`;
      RULES.forEach((rl) => {
        const rb = document.createElement("button");
        rb.type = "button";
        rb.className = "sa-btn ghost";
        rb.style.padding = "11px";
        rb.textContent = rl.label;
        rb.onclick = () => {
          if (rl.id === it.rule) {
            SFX.powerup();
            addPoints(40, rb, "#f97316");
            showMemoryStrike();
          } else {
            roundMissed = true;
            resetCombo();
            SFX.bad();
            rb.style.borderColor = "#fb7185";
            setFeedback(fb, "bad", esc(it.memory_hint || "Check how the base word ends before locking on this ending!"));
          }
        };
        $("wfRuleRow").appendChild(rb);
      });
    }

    function showMemoryStrike() {
      $("wfSlots").hidden = true;
      $("wfTray").hidden = true;
      const canPen = !!App.hubData?.ai_available;
      const startInPen = canPen && App.forgeUsePen;
      const s2 = $("wfStep2");
      s2.hidden = false;
      s2.innerHTML = `
        <div class="wf-memory-box" style="padding:14px">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:center">
            <span style="font-weight:700;color:#fdba74">🔒 MEMORY FORGE — Strike It From Memory!</span>
            <button type="button" class="sa-speak-btn" id="wfSpeakWord">🔊 Word</button>
            <button type="button" class="sa-speak-btn" id="wfSpeakSent">🔊 Sentence</button>
          </div>
          <div style="font-size:0.86rem;color:#cbd5e1;text-align:center">${esc(it.memory_hint || "Strike every letter cleanly from memory!")}</div>
          ${canPen ? `
          <div class="wf-mode-tabs">
            <button type="button" class="wf-mode-tab ${!startInPen ? "on" : ""}" id="wfTabType">⌨️ Type It</button>
            <button type="button" class="wf-mode-tab ${startInPen ? "on" : ""}" id="wfTabPen">✏️ Write with Yoga Pen</button>
          </div>` : ""}
          <div id="wfTypePane" ${startInPen ? "hidden" : ""} style="display:flex;flex-direction:column;align-items:center;gap:8px;width:100%">
            <input type="text" id="wfMemInput" class="wf-input" placeholder="Type fused word…" autocomplete="off" spellcheck="false" />
            <button type="button" class="sa-btn primary" id="wfStrikeBtn">⚒️ Strike the Anvil!</button>
          </div>
          <div id="wfPenPane" ${!startInPen ? "hidden" : ""} style="display:flex;flex-direction:column;align-items:center;gap:6px;width:100%">
            <div class="wf-pen-stage" id="wfPenStage">
              <canvas id="wfPenGuide"></canvas>
              <canvas id="wfPenInk"></canvas>
            </div>
            <div class="wf-pen-legend">
              <span style="color:#38bdf8">Sky</span> · <span style="color:#94a3b8">Fence</span> ·
              <span style="color:#34d399">Grass</span> · <span style="color:#d97706">Worm</span>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center">
              <button type="button" class="sa-btn ghost" id="wfPenClear">Clear Pad</button>
              <button type="button" class="sa-btn primary" id="wfPenStrike">⚒️ Read Pen &amp; Strike!</button>
            </div>
          </div>
          <div class="wf-diff" id="wfDiff"></div>
        </div>`;

      setFeedback(fb, "idle", canPen
        ? "Listen to the word, then type it OR write it with your Lenovo pen from memory!"
        : "Listen to the word, then type the fused word cleanly from memory!");

      VOICE.speak(`Forge the word: ${it.word}. ${it.context_sentence || ""}`);
      $("wfSpeakWord").onclick = () => VOICE.speak(it.word, { force: true, rate: 0.86 });
      $("wfSpeakSent").onclick = () => VOICE.speak(it.context_sentence || it.word, { force: true, rate: 0.92 });

      const inp = $("wfMemInput");
      if (!startInPen) inp.focus();
      let memMissed = false;
      let wordDone = false;

      function evaluateAttempt(typedRaw) {
        if (wordDone) return;
        const typed = String(typedRaw || "").trim().toLowerCase();
        if (!typed) return;
        if (typed === it.word.toLowerCase()) {
          wordDone = true;
          commitStepClock(40);
          SFX.hammer();
          triggerHammerStrike(true);
          forgedCount += 1;
          const cleanWholeWord = !roundMissed && !memMissed;
          if (cleanWholeWord) correct += 1;
          const partsStr = [it.prefix, it.base, it.suffix].filter(Boolean).join(" + ") || it.word;
          wordResults.push({
            word: it.word, first_try: !memMissed, wrote: typed,
            parts: partsStr, note: it.note || "", unit: it.unit || "Rune Lock Forge",
          });
          zpd.record(it, cleanWholeWord, idx + 1, items);
          addPoints(cleanWholeWord ? 150 : 65, s2, "#22d3ee");
          setFeedback(fb, "ok",
            `💎 <b>FORGED: ${esc(it.word)}!</b> ${esc(it.note || "")} ${!memMissed ? "(Vault Tier upgraded!)" : "(Queued for next forge!)"}`,
            { id: "wfNextBtn", label: "Next Rune →", onClick: () => { idx += 1; renderWord(); } });
          $("wfStrikeBtn").disabled = true;
          inp.disabled = true;
          if ($("wfPenStrike")) $("wfPenStrike").disabled = true;
        } else {
          memMissed = true;
          roundMissed = true;
          resetCombo();
          SFX.bad();
          const target = it.word.toLowerCase();
          let diffHtml = "";
          for (let i = 0; i < target.length; i++) {
            const okChar = typed[i] === target[i];
            diffHtml += `<span class="${okChar ? "ok" : "miss"}">${esc(target[i])}</span>`;
          }
          $("wfDiff").innerHTML = diffHtml;
          setFeedback(fb, "bad", `Read “${esc(typed)}” — check the underlined letter(s) above and re-forge cleanly!`);
          inp.value = "";
          if (!App.forgeUsePen) inp.focus();
        }
      }

      $("wfStrikeBtn").onclick = () => evaluateAttempt(inp.value);
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); evaluateAttempt(inp.value); } });

      if (canPen) {
        let penInited = false;
        let hasInk = false;
        let penDims = { W: 520, H: 128 };

        const initPenPad = () => {
          if (penInited) return;
          penInited = true;
          const stEl = $("wfPenStage");
          const gCv = $("wfPenGuide");
          const iCv = $("wfPenInk");
          const gc = gCv.getContext("2d");
          const ic = iCv.getContext("2d");

          const paintGuides = () => {
            penDims = fitCanvas(gCv, gc, 300, 110);
            fitCanvas(iCv, ic, 300, 110);
            const { W: pw, H: ph } = penDims;
            gc.fillStyle = "#fbfaf5";
            gc.fillRect(0, 0, pw, ph);
            const drawLine = (y, col, dash = []) => {
              gc.save(); gc.strokeStyle = col; gc.lineWidth = 1.5; gc.setLineDash(dash);
              gc.beginPath(); gc.moveTo(0, y); gc.lineTo(pw, y); gc.stroke(); gc.restore();
            };
            drawLine(ph * 0.22, "#60a5fa");
            drawLine(ph * 0.50, "#94a3b8", [7, 7]);
            drawLine(ph * 0.78, "#22c55e");
            drawLine(ph * 0.93, "#b45309", [3, 5]);
          };
          paintGuides();

          const ro = new ResizeObserver(() => {
            if (!hasInk) paintGuides();
          });
          ro.observe(stEl);
          penCleanup = () => ro.disconnect();

          let activePid = null;
          let last = null;
          iCv.addEventListener("pointerdown", (e) => {
            if (e.pointerType === "pen") App.penDetected = true;
            if (App.penDetected && e.pointerType === "touch") return; // Persistent 360° palm rejection
            if (activePid !== null) return;
            activePid = e.pointerId;
            iCv.setPointerCapture?.(e.pointerId);
            const br = iCv.getBoundingClientRect();
            last = { x: e.clientX - br.left, y: e.clientY - br.top };
          });
          iCv.addEventListener("pointermove", (e) => {
            if (e.pointerId !== activePid) return;
            const br = iCv.getBoundingClientRect();
            const isErase = e.button === 5 || (e.buttons & 32);
            const evts = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
            for (const ev of evts) {
              const nx = ev.clientX - br.left;
              const ny = ev.clientY - br.top;
              const press = ev.pressure > 0 ? ev.pressure : 0.5;
              ic.save();
              if (isErase) {
                ic.globalCompositeOperation = "destination-out";
                ic.lineWidth = 22;
              } else {
                ic.strokeStyle = "#0f172a";
                ic.lineWidth = 2.4 + press * 3.6;
                hasInk = true;
              }
              ic.lineCap = "round";
              ic.beginPath();
              if (last) ic.moveTo(last.x, last.y); else ic.moveTo(nx, ny);
              ic.lineTo(nx, ny);
              ic.stroke();
              ic.restore();
              last = { x: nx, y: ny };
            }
          });
          const endStroke = (e) => {
            if (e.pointerId !== activePid) return; // Palm lift NEVER cancels active stylus stroke!
            activePid = null;
            last = null;
          };
          iCv.addEventListener("pointerup", endStroke);
          iCv.addEventListener("pointercancel", endStroke);

          $("wfPenClear").onclick = () => { ic.clearRect(0, 0, penDims.W, penDims.H); hasInk = false; };
          $("wfPenStrike").onclick = async () => {
            if (!hasInk) {
              setFeedback(fb, "bad", "Write the word on the paper first with your Lenovo pen!");
              return;
            }
            const btn = $("wfPenStrike");
            btn.disabled = true;
            btn.textContent = "Reading pen…";
            const outCv = document.createElement("canvas");
            outCv.width = gCv.width; outCv.height = gCv.height;
            const oc = outCv.getContext("2d");
            oc.drawImage(gCv, 0, 0);
            oc.drawImage(iCv, 0, 0);
            try {
              const r = await fetch("/api/skill-games/read-handwriting", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ image_b64: outCv.toDataURL("image/png"), expected_word: it.word }),
              });
              if (!r.ok) throw new Error(`HTTP ${r.status}`);
              const res = await r.json();
              btn.disabled = false;
              btn.textContent = "⚒️ Read Pen & Strike!";
              if (res.ok && res.text) {
                evaluateAttempt(res.text);
                if (!wordDone) { ic.clearRect(0, 0, penDims.W, penDims.H); hasInk = false; }
              } else {
                setFeedback(fb, "bad", esc(res.error || "Could not read handwriting — try writing bigger on the grass line!"));
              }
            } catch (err) {
              btn.disabled = false;
              btn.textContent = "⚒️ Read Pen & Strike!";
              setFeedback(fb, "bad", "Couldn't read handwriting right now — try again or switch to Type It!");
            }
          };
        };

        $("wfTabType").onclick = () => {
          App.forgeUsePen = false;
          $("wfTabType").classList.add("on"); $("wfTabPen").classList.remove("on");
          $("wfTypePane").hidden = false; $("wfPenPane").hidden = true;
          inp.focus();
        };
        $("wfTabPen").onclick = () => {
          App.forgeUsePen = true;
          $("wfTabPen").classList.add("on"); $("wfTabType").classList.remove("on");
          $("wfTypePane").hidden = true; $("wfPenPane").hidden = false;
          requestAnimationFrame(initPenPad);
        };
        if (startInPen) requestAnimationFrame(initPenPad);
      }
    }
  }
  renderWord();
}

// ===========================================================================
// GAME 3: ☄️ STARSHIELD TURRET (2x DPR + Unclipped Meteors + Live Boss!)
// ===========================================================================

function runHomophoneAsteroids(pack) {
  const stage = $("saGameStage");
  const items = pack.items;
  const zpd = createZpdDirector(pack);
  let wave = 0;
  let correct = 0;
  let waveMissed = false;
  const trickyWords = [];
  const wordOutcomes = [];
  const skillHits = {};

  stage.innerHTML = `
    <div class="ast-hud" style="display:flex;align-items:center;justify-content:space-between;gap:12px">
      <div id="astHud" style="flex:1;text-align:center">Loading radar…</div>
      <button type="button" class="sa-speak-btn" id="astSpeakBtn" style="flex-shrink:0">🔊 Read</button>
    </div>
    <div class="ast-canvas-wrap" id="astWrap"><canvas id="astCanvas"></canvas></div>
    <div id="astBossArea" hidden></div>
    <div class="sa-feedback idle" id="astFb"><span class="sa-fb-msg">Tap the right asteroid or press <b>1</b>, <b>2</b>, or <b>3</b> to fire the orbital plasma cannon!</span></div>`;

  const cv = $("astCanvas");
  const ctx = cv.getContext("2d");
  let W = 800, H = 370;
  let rocks = [];
  let beams = [];
  let shards = [];
  let rings = [];
  let turretAngle = -Math.PI / 2;
  let recoil = 0;
  let shieldFlash = 0;
  let shake = 0;
  let rafId = 0;
  let active = true;
  let currentSpoken = "";

  const boss = { active: false, y: -70, hp: 100, dying: false, hyperbeam: 0 };

  $("astSpeakBtn").onclick = () => VOICE.speak(currentSpoken, { force: true });

  const starField = Array.from({ length: 85 }, (_, i) => ({
    x: Math.random(), y: Math.random(),
    s: 0.7 + (i % 3) * 0.75, v: 0.0005 + (i % 3) * 0.0007, a: 0.35 + (i % 4) * 0.16,
  }));

  function syncSize() {
    const d = fitCanvas(cv, ctx, 300, 240);
    W = d.W; H = d.H;
  }
  syncSize();

  function spawnWave() {
    if (!active) return;
    if (wave >= items.length) {
      enterBossWave();
      return;
    }
    beginStepClock();
    waveMissed = false;
    const it = items[wave];
    currentSpoken = it.sentence.replace("___", "blank");
    setHud({ visible: true, step: wave + 1, total: items.length + 1, score: App.score, combo: App.combo, title: "Starshield Turret", aiPack: !!pack.ai_generated });
    const parts = it.sentence.split("___");
    $("astHud").innerHTML = `${esc(parts[0] || "")}<span class="ast-blank">?</span>${esc(parts[1] || "")}`;

    const lanes = [W * 0.21, W * 0.5, W * 0.79];
    // Adaptive speed: smoothly adjusts to live ZPD sector!
    const zpdSpeedScale = zpd.tier === 1 ? 0.84 : (zpd.tier === 3 ? 1.18 : 1.0);
    rocks = it.options.map((opt, i) => ({
      idx: i, word: opt, ok: opt === it.answer,
      x: lanes[i], y: i === 1 ? 58 : 66, r: 44,
      vy: (0.31 + Math.min(0.22, wave * 0.022)) * zpdSpeedScale,
      rot: Math.random() * Math.PI * 2, vrot: (Math.random() - 0.5) * 0.012,
      verts: Array.from({ length: 11 }, (_, vi) => 0.84 + ((vi * 13 + i * 5) % 5) * 0.05),
      craters: [{ a: 0.8 + i, d: 0.45, r: 7 }, { a: 2.9 + i, d: 0.38, r: 5.5 }, { a: 4.7 + i, d: 0.48, r: 4.5 }],
      alive: true, redFlash: 0,
    }));
  }

  function shootRock(rockIdx) {
    if (!active || boss.active) return;
    const rock = rocks[rockIdx];
    if (!rock || !rock.alive) return;
    const it = items[wave];
    const tx = W / 2, ty = H - 38;
    turretAngle = Math.atan2(rock.y - ty, rock.x - tx);
    recoil = 10;
    beams.push({ x1: tx, y1: ty, x2: rock.x, y2: rock.y, color: rock.ok ? "#38bdf8" : "#fb7185", life: 1, w: 7 });

    if (rock.ok) {
      rock.alive = false;
      commitStepClock(35);
      shake = 7;
      SFX.laser();
      rings.push({ x: rock.x, y: rock.y, r: 14, maxR: 84, color: "#c084fc", life: 1 });
      for (let k = 0; k < 28; k++) {
        const a = Math.random() * Math.PI * 2;
        const sp = 2 + Math.random() * 6.5;
        shards.push({
          x: rock.x, y: rock.y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp,
          r: 3 + Math.random() * 5.5, color: k % 2 ? "#c084fc" : "#38bdf8", life: 1,
        });
      }
      if (!waveMissed) correct += 1;
      else trickyWords.push(it.answer);
      wordOutcomes.push({ word: it.answer, ok: !waveMissed });
      skillHits[it.skill] = skillHits[it.skill] || { correct: 0, total: 0 };
      skillHits[it.skill].total += 1;
      if (!waveMissed) skillHits[it.skill].correct += 1;
      zpd.record(it, !waveMissed, wave + 1, items);

      addPoints(waveMissed ? 60 : 120, $("astHud"), "#a855f7");
      setFeedback($("astFb"), "ok", `💥 <b>Direct Hit!</b> ${esc(it.explain)}`);
      const parts = it.sentence.split("___");
      $("astHud").innerHTML = `${esc(parts[0] || "")}<span class="ast-blank" style="border-color:#10b981;color:#6ee7b7">${esc(it.answer)}</span>${esc(parts[1] || "")}`;
      rocks.forEach((r) => { r.alive = false; });
      safeTimeout(() => { wave += 1; spawnWave(); }, 900);
    } else {
      waveMissed = true;
      rock.redFlash = 1;
      resetCombo();
      SFX.bad();
      setFeedback($("astFb"), "bad", `Shield deflection! “${esc(rock.word)}” doesn't fit here — read the sentence clues carefully!`);
    }
  }

  function enterBossWave() {
    beginStepClock();
    boss.active = true;
    boss.y = -65;
    boss.hp = 100;
    const bossWord = trickyWords[0] || items[items.length - 1].answer;
    currentSpoken = `Dreadnought Boss incoming! Write one complete sentence using the word ${bossWord} to fire the hyperbeam.`;
    setHud({ visible: true, step: items.length + 1, total: items.length + 1, score: App.score, combo: App.combo, title: "BOSS WAVE · Dreadnought", aiPack: !!pack.ai_generated });
    $("astWrap").style.height = "255px";
    $("astHud").innerHTML = `👾 <b>DREADNOUGHT BOSS INCOMING!</b> Write 1 real sentence using <span class="ast-blank">${esc(bossWord)}</span> to charge the Hyperbeam!`;
    const bossArea = $("astBossArea");
    bossArea.hidden = false;
    bossArea.innerHTML = `
      <div class="boss-box" style="padding:14px 18px">
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <input type="text" id="astBossInput" class="sa-sentence-input" style="flex:1;min-width:240px"
            placeholder="Type a complete sentence using '${esc(bossWord)}' (Capital + . ! ?)…" autocomplete="off" />
          <button type="button" class="sa-btn primary" id="astBossFire">🚀 Fire Hyperbeam!</button>
        </div>
      </div>`;
    const inp = $("astBossInput");
    inp.focus();

    const fire = async () => {
      const txt = inp.value.trim();
      if (!txt || boss.dying) return;
      const fireBtn = $("astBossFire");
      fireBtn.disabled = true;
      fireBtn.textContent = "Charging…";
      try {
        const r = await fetch("/api/skill-games/check-sentence", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: txt,
            required_word: bossWord,
            require_because: false,
            context_prompt: `Homophone/verb boss wave: student must use '${bossWord}' with its correct meaning and grammar.`,
          }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const chk = await r.json();
        if (chk.ok) {
          boss.dying = true;
          boss.hyperbeam = 1.0;
          boss.hp = 0;
          shake = 16;
          SFX.hyperbeam();
          rings.push({ x: W / 2, y: boss.y, r: 20, maxR: 165, color: "#38bdf8", life: 1 });
          rings.push({ x: W / 2, y: boss.y, r: 10, maxR: 125, color: "#facc15", life: 1 });
          for (let k = 0; k < 110; k++) {
            const a = Math.random() * Math.PI * 2;
            const sp = 2 + Math.random() * 9;
            shards.push({
              x: W / 2 + (Math.random() - 0.5) * 90,
              y: boss.y + (Math.random() - 0.5) * 35,
              vx: Math.cos(a) * sp, vy: Math.sin(a) * sp,
              r: 3 + Math.random() * 6,
              color: ["#facc15", "#a855f7", "#38bdf8", "#fb7185"][k % 4],
              life: 1.1,
            });
          }
          addPoints(250, $("astHud"), "#a855f7");
          setFeedback($("astFb"), "ok", "💥 <b>DREADNOUGHT VAPORIZED!</b> Direct hit on the command core!");
          safeTimeout(() => {
            finishGame({
              correct: correct + 1,
              total: items.length + 1,
              production_passed: true,
              production_sentence: txt,
              skill_hits: skillHits,
              subskill_hits: zpd.subskillHits,
              word_outcomes: wordOutcomes,
              played_ids: zpd.playedIds,
              peak_tier: zpd.peakTier,
            });
          }, 1150);
        } else {
          fireBtn.disabled = false;
          fireBtn.textContent = "🚀 Fire Hyperbeam!";
          SFX.bad();
          setFeedback($("astFb"), "bad", esc(chk.feedback));
        }
      } catch (err) {
        fireBtn.disabled = false;
        fireBtn.textContent = "🚀 Fire Hyperbeam!";
        SFX.bad();
        setFeedback($("astFb"), "bad", "Network hiccup checking your sentence — click Fire Hyperbeam to try again!");
      }
    };
    $("astBossFire").onclick = fire;
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); fire(); } });
  }

  function drawDreadnought(cx, cy, nowS) {
    ctx.save();
    ctx.translate(cx, cy + Math.sin(nowS * 3) * 5);
    if (!boss.dying) {
      ctx.strokeStyle = `rgba(192, 132, 252, ${0.45 + Math.sin(nowS * 6) * 0.25})`;
      ctx.shadowColor = "#a855f7"; ctx.shadowBlur = 22; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.ellipse(0, 0, 128, 48, 0, 0, Math.PI * 2); ctx.stroke();
      ctx.shadowBlur = 0;
    }
    ctx.fillStyle = "#1e1b4b"; ctx.strokeStyle = "#f43f5e"; ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(-108, -10); ctx.lineTo(-54, -32); ctx.lineTo(54, -32); ctx.lineTo(108, -10);
    ctx.lineTo(82, 22); ctx.lineTo(28, 30); ctx.lineTo(-28, 30); ctx.lineTo(-82, 22);
    ctx.closePath(); ctx.fill(); ctx.stroke();

    const cg = ctx.createRadialGradient(0, 2, 2, 0, 2, 22);
    cg.addColorStop(0, "#fef08a"); cg.addColorStop(0.5, "#f43f5e"); cg.addColorStop(1, "transparent");
    ctx.fillStyle = cg; ctx.beginPath(); ctx.arc(0, 2, 22, 0, Math.PI * 2); ctx.fill();

    ctx.fillStyle = "rgba(15, 23, 42, 0.88)"; ctx.fillRect(-75, -50, 150, 10);
    ctx.fillStyle = "#f43f5e"; ctx.fillRect(-75, -50, 150 * (boss.hp / 100), 10);
    ctx.strokeStyle = "#fda4af"; ctx.lineWidth = 1.2; ctx.strokeRect(-75, -50, 150, 10);
    ctx.restore();
  }

  function loop() {
    if (!active) return;
    syncSize();
    const nowS = performance.now() * 0.001;
    const sx = shake > 0.2 ? (Math.random() - 0.5) * shake : 0;
    const sy = shake > 0.2 ? (Math.random() - 0.5) * shake : 0;
    shake *= 0.85;
    recoil *= 0.82;

    ctx.save();
    ctx.translate(sx, sy);

    const spG = ctx.createLinearGradient(0, 0, 0, H);
    spG.addColorStop(0, "#030510"); spG.addColorStop(0.75, "#0b0f26"); spG.addColorStop(1, "#121b38");
    ctx.fillStyle = spG; ctx.fillRect(0, 0, W, H);

    // Ringed gas-giant planet
    ctx.save();
    const px = W * 0.85, py = H * 0.28;
    const pg = ctx.createRadialGradient(px - 16, py - 16, 6, px, py, 48);
    pg.addColorStop(0, "#6366f1"); pg.addColorStop(0.65, "#1e1b4b"); pg.addColorStop(1, "#090a1a");
    ctx.fillStyle = pg; ctx.beginPath(); ctx.arc(px, py, 44, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "rgba(165, 180, 252, 0.38)"; ctx.lineWidth = 4.5;
    ctx.beginPath(); ctx.ellipse(px, py, 78, 17, -0.25, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();

    for (const s of starField) {
      s.y += s.v;
      if (s.y > 1) { s.y = 0; s.x = Math.random(); }
      ctx.fillStyle = `rgba(226, 232, 240, ${s.a})`;
      ctx.fillRect(s.x * W, s.y * H, s.s, s.s);
    }

    // Illuminated Toronto Skyline + CN Tower under a proportional wide orbital shield dome!
    const baseY = H;
    const bldgs = [0.16, 0.22, 0.31, 0.38, 0.60, 0.67, 0.74, 0.81];
    bldgs.forEach((bx, bi) => {
      const bh = 26 + ((bi * 17) % 30);
      const x = W * bx;
      ctx.fillStyle = "#0f172a";
      ctx.fillRect(x, baseY - bh, 26, bh);
      // Glowing miniature skyscraper windows
      ctx.fillStyle = bi % 2 === 0 ? "rgba(250, 204, 21, 0.45)" : "rgba(56, 189, 248, 0.45)";
      for (let wy = baseY - bh + 5; wy < baseY - 4; wy += 7) {
        ctx.fillRect(x + 4, wy, 4, 3); ctx.fillRect(x + 12, wy, 4, 3); ctx.fillRect(x + 19, wy, 3, 3);
      }
    });
    // CN Tower with glowing sky-pod rim
    const cnx = W * 0.27;
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(cnx - 2.5, baseY - 76, 5, 76);
    ctx.beginPath(); ctx.ellipse(cnx, baseY - 52, 11, 4, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#38bdf8";
    ctx.fillRect(cnx - 8, baseY - 53, 16, 2);
    ctx.fillRect(cnx - 1, baseY - 82, 2, 7);

    // Wide Proportional Orbital Shield Dome protecting the full skyline!
    ctx.save();
    ctx.strokeStyle = shieldFlash > 0.05 ? "#fb7185" : "rgba(56, 189, 248, 0.52)";
    ctx.shadowColor = shieldFlash > 0.05 ? "#fb7185" : "#38bdf8";
    ctx.shadowBlur = 16; ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.ellipse(W / 2, H + 12, W * 0.42, 102, 0, Math.PI, 0);
    ctx.stroke();
    ctx.restore();
    shieldFlash *= 0.9;

    if (boss.active) {
      if (boss.y < H * 0.38) boss.y += 2.6;
      if (!boss.dying) drawDreadnought(W / 2, boss.y, nowS);
      if (boss.hyperbeam > 0.02) {
        ctx.save();
        ctx.strokeStyle = `rgba(56, 189, 248, ${boss.hyperbeam})`;
        ctx.shadowColor = "#38bdf8"; ctx.shadowBlur = 35; ctx.lineWidth = 40 * boss.hyperbeam;
        ctx.beginPath(); ctx.moveTo(W / 2, H - 36); ctx.lineTo(W / 2, boss.y); ctx.stroke();
        ctx.strokeStyle = `rgba(255, 255, 255, ${boss.hyperbeam})`; ctx.lineWidth = 14 * boss.hyperbeam;
        ctx.beginPath(); ctx.moveTo(W / 2, H - 36); ctx.lineTo(W / 2, boss.y); ctx.stroke();
        ctx.restore();
        boss.hyperbeam *= 0.93;
      }
    }

    // Shaded Cratered Rocky Asteroids
    for (const rk of rocks) {
      if (!rk.alive) continue;
      rk.y += rk.vy;
      rk.rot += rk.vrot;
      if (rk.y > H - 78) {
        rk.y = 58;
        shieldFlash = 0.95;
        SFX.shieldBounce();
      }

      const tailG = ctx.createLinearGradient(rk.x, rk.y - rk.r * 1.5, rk.x, rk.y);
      tailG.addColorStop(0, "transparent"); tailG.addColorStop(1, "rgba(168, 85, 247, 0.25)");
      ctx.fillStyle = tailG;
      ctx.beginPath();
      ctx.moveTo(rk.x - 14, rk.y - rk.r * 1.5); ctx.lineTo(rk.x + 14, rk.y - rk.r * 1.5);
      ctx.lineTo(rk.x + 26, rk.y); ctx.lineTo(rk.x - 26, rk.y); ctx.closePath(); ctx.fill();

      ctx.save();
      ctx.translate(rk.x, rk.y);
      ctx.save();
      ctx.rotate(rk.rot);
      ctx.beginPath();
      rk.verts.forEach((v, vi) => {
        const a = (Math.PI * 2 * vi) / rk.verts.length;
        const px2 = Math.cos(a) * rk.r * v, py2 = Math.sin(a) * rk.r * v;
        if (vi === 0) ctx.moveTo(px2, py2); else ctx.lineTo(px2, py2);
      });
      ctx.closePath();
      const rg = ctx.createRadialGradient(-10, -12, 6, 0, 0, rk.r);
      if (rk.redFlash > 0.1) { rg.addColorStop(0, "#9f1239"); rg.addColorStop(1, "#3b0712"); }
      else { rg.addColorStop(0, "#4c1d95"); rg.addColorStop(0.55, "#1e1b4b"); rg.addColorStop(1, "#0f172a"); }
      ctx.fillStyle = rg;
      ctx.strokeStyle = rk.redFlash > 0.1 ? "#fb7185" : "#a855f7";
      ctx.lineWidth = 2.4; ctx.shadowColor = ctx.strokeStyle; ctx.shadowBlur = 14;
      ctx.fill(); ctx.stroke(); ctx.shadowBlur = 0;

      ctx.fillStyle = "rgba(10, 12, 26, 0.48)";
      for (const cr of rk.craters) {
        ctx.beginPath(); ctx.arc(Math.cos(cr.a) * rk.r * cr.d, Math.sin(cr.a) * rk.r * cr.d, cr.r, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
      rk.redFlash *= 0.88;

      ctx.font = "700 18px 'Google Sans', sans-serif";
      ctx.fillStyle = "#ffffff"; ctx.textAlign = "center";
      ctx.shadowColor = "rgba(0,0,0,0.9)"; ctx.shadowBlur = 6;
      ctx.fillText(rk.word, 0, 6);
      ctx.font = "700 11px 'JetBrains Mono', monospace";
      ctx.fillStyle = "#e9d5ff";
      ctx.fillText(`[${rk.idx + 1}]`, 0, -18);
      ctx.restore();
    }

    for (let i = rings.length - 1; i >= 0; i--) {
      const rg = rings[i];
      rg.r += (rg.maxR - rg.r) * 0.16; rg.life -= 0.045;
      if (rg.life <= 0) { rings.splice(i, 1); continue; }
      ctx.save(); ctx.globalAlpha = rg.life; ctx.strokeStyle = rg.color; ctx.lineWidth = 4 * rg.life;
      ctx.beginPath(); ctx.arc(rg.x, rg.y, rg.r, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
    }
    for (let i = beams.length - 1; i >= 0; i--) {
      const bm = beams[i];
      bm.life -= 0.1;
      if (bm.life <= 0) { beams.splice(i, 1); continue; }
      ctx.save(); ctx.globalAlpha = bm.life; ctx.strokeStyle = bm.color; ctx.lineWidth = bm.w * bm.life;
      ctx.shadowColor = bm.color; ctx.shadowBlur = 20;
      ctx.beginPath(); ctx.moveTo(bm.x1, bm.y1); ctx.lineTo(bm.x2, bm.y2); ctx.stroke();
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 2.5 * bm.life;
      ctx.beginPath(); ctx.moveTo(bm.x1, bm.y1); ctx.lineTo(bm.x2, bm.y2); ctx.stroke(); ctx.restore();
    }
    for (let i = shards.length - 1; i >= 0; i--) {
      const sh = shards[i];
      sh.x += sh.vx; sh.y += sh.vy; sh.life -= 0.028;
      if (sh.life <= 0) { shards.splice(i, 1); continue; }
      ctx.save(); ctx.globalAlpha = Math.min(1, sh.life); ctx.fillStyle = sh.color;
      ctx.shadowColor = sh.color; ctx.shadowBlur = 8;
      ctx.fillRect(sh.x - sh.r / 2, sh.y - sh.r / 2, sh.r, sh.r); ctx.restore();
    }

    ctx.save();
    ctx.translate(W / 2, H - 32);
    ctx.rotate(turretAngle + Math.PI / 2);
    ctx.fillStyle = "#38bdf8"; ctx.shadowColor = "#38bdf8"; ctx.shadowBlur = 14;
    ctx.fillRect(-10, -34 + recoil, 6, 30); ctx.fillRect(4, -34 + recoil, 6, 30);
    ctx.shadowBlur = 0;
    ctx.beginPath(); ctx.arc(0, 0, 19, 0, Math.PI * 2);
    ctx.fillStyle = "#0f172a"; ctx.strokeStyle = "#38bdf8"; ctx.lineWidth = 3;
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = "#a855f7"; ctx.beginPath(); ctx.arc(0, 0, 6.5, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    ctx.restore();
    rafId = requestAnimationFrame(loop);
  }

  const onPointer = (e) => {
    const r = cv.getBoundingClientRect();
    const px = e.clientX - r.left, py = e.clientY - r.top;
    for (const rk of rocks) {
      if (rk.alive && Math.hypot(px - rk.x, py - rk.y) <= rk.r + 16) { shootRock(rk.idx); return; }
    }
  };
  const onKey = (e) => {
    if (boss.active) return;
    if (e.key === "1") shootRock(0);
    else if (e.key === "2") shootRock(1);
    else if (e.key === "3") shootRock(2);
  };
  cv.addEventListener("pointerdown", onPointer);
  window.addEventListener("keydown", onKey);
  addCleanup(() => { active = false; cancelAnimationFrame(rafId); window.removeEventListener("keydown", onKey); });

  spawnWave();
  rafId = requestAnimationFrame(loop);
}

// ===========================================================================
// GAME 4: ⚡ SENTENCE STRETCH LAB (2x DPR Plasma Reactor + Dynamic Exact-Verb Fusion!)
// ===========================================================================

function buildFusedSentence(it, bridgeWord, bridgeKind, vividVerb) {
  const replaceVerb = (s) => s.replace(new RegExp(`\\b${it.weak_verb.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i"), vividVerb);
  const aRaw = replaceVerb(it.clause_a).trim().replace(/[.!?]+$/, "");
  const bRaw = replaceVerb(it.clause_b).trim();
  const lowercaseStart = (s) => {
    // Lowercase common determiners/pronouns while preserving ANY proper name (including AI World Pack characters!)
    const first = s.split(/\s+/)[0] || "";
    const lowerable = new Set([
      "The", "A", "An", "Our", "My", "His", "Her", "Its", "Their", "Your",
      "We", "They", "He", "She", "It", "You", "This", "That", "These", "Those",
      "Every", "All", "Some", "Many", "Few", "Most", "Several", "Both", "No", "One", "Two", "Three",
    ]);
    if (!lowerable.has(first)) return s;
    return s.charAt(0).toLowerCase() + s.slice(1);
  };
  if (it.front_connector) {
    const capB = bridgeWord.charAt(0).toUpperCase() + bridgeWord.slice(1);
    return `${capB} ${lowercaseStart(aRaw)}, ${lowercaseStart(bRaw)}`;
  }
  const sep = bridgeKind === "compound" ? `, ${bridgeWord} ` : ` ${bridgeWord} `;
  return `${aRaw}${sep}${lowercaseStart(bRaw)}`;
}

function runSentenceStretch(pack) {
  const stage = $("saGameStage");
  const items = pack.items;
  const zpd = createZpdDirector(pack);
  let idx = 0;
  let correct = 0;
  let reactorPower = 30;
  const skillHits = {};

  stage.innerHTML = `
    <div class="sa-scene-wrap" style="border-color:rgba(16,185,129,0.45)"><canvas id="stReactorCv"></canvas></div>
    <div id="stHost" style="display:flex;flex-direction:column;gap:12px"></div>`;

  const rcv = $("stReactorCv");
  const rctx = rcv.getContext("2d");
  let active = true;
  let rafId = 0;
  let smoothPwr = 30;

  function drawReactor() {
    if (!active) return;
    const { W, H } = fitCanvas(rcv, rctx, 300, 110);
    const nowS = performance.now() * 0.001;
    smoothPwr += (reactorPower - smoothPwr) * 0.1;

    rctx.fillStyle = "#060c18"; rctx.fillRect(0, 0, W, H);
    const cy = H * 0.56;
    const lx = W * 0.18, rx = W * 0.82, cx = W * 0.5;
    const over = smoothPwr >= 95;
    const bridged = smoothPwr >= 65;

    rctx.save();
    const beamCol = over ? "#facc15" : (bridged ? "#10b981" : "rgba(56,189,248,0.28)");
    rctx.strokeStyle = beamCol; rctx.shadowColor = beamCol;
    rctx.shadowBlur = over ? 26 : (bridged ? 16 : 4);
    rctx.lineWidth = over ? 7 : (bridged ? 4.5 : 2);
    rctx.beginPath();
    for (let x = lx; x <= rx; x += 10) {
      const jit = bridged ? Math.sin(x * 0.08 - nowS * 12) * (over ? 9 : 4) : (Math.random() - 0.5) * 4;
      if (x === lx) rctx.moveTo(x, cy + jit); else rctx.lineTo(x, cy + jit);
    }
    rctx.stroke();
    rctx.restore();

    for (const [nx, col, lbl] of [[lx, "#38bdf8", "CORE A"], [rx, "#10b981", "CORE B"]]) {
      rctx.save();
      rctx.fillStyle = "#0f172a"; rctx.strokeStyle = col; rctx.lineWidth = 3;
      rctx.shadowColor = col; rctx.shadowBlur = 14;
      rctx.beginPath(); rctx.arc(nx, cy, 32, 0, Math.PI * 2); rctx.fill(); rctx.stroke();
      rctx.shadowBlur = 0;
      rctx.font = "700 9.5px 'JetBrains Mono', monospace"; rctx.fillStyle = col; rctx.textAlign = "center";
      rctx.fillText(lbl, nx, cy + 3.5);
      rctx.restore();
    }

    rctx.save();
    rctx.translate(cx, cy);
    rctx.rotate(nowS * (over ? 3.5 : (bridged ? 1.5 : 0.4)));
    rctx.strokeStyle = over ? "#facc15" : (bridged ? "#34d399" : "#475569");
    rctx.lineWidth = 3; rctx.setLineDash([13, 9]);
    rctx.beginPath(); rctx.arc(0, 0, 38, 0, Math.PI * 2); rctx.stroke();
    rctx.setLineDash([]);
    rctx.restore();

    rctx.save();
    const coreG = rctx.createRadialGradient(cx, cy, 4, cx, cy, 28);
    coreG.addColorStop(0, "#fff"); coreG.addColorStop(0.5, over ? "#facc15" : (bridged ? "#10b981" : "#334155")); coreG.addColorStop(1, "transparent");
    rctx.fillStyle = coreG; rctx.beginPath(); rctx.arc(cx, cy, 28, 0, Math.PI * 2); rctx.fill();
    rctx.font = "700 13px 'JetBrains Mono', monospace";
    rctx.fillStyle = over ? "#fef08a" : (bridged ? "#6ee7b7" : "#94a3b8"); rctx.textAlign = "center";
    rctx.fillText(over ? "⚡ OVERDRIVE 100%!" : `REACTOR POWER: ${Math.round(smoothPwr)}%`, cx, 20);
    rctx.restore();

    rafId = requestAnimationFrame(drawReactor);
  }
  rafId = requestAnimationFrame(drawReactor);
  addCleanup(() => { active = false; cancelAnimationFrame(rafId); });

  function renderStep() {
    VOICE.stop();
    if (idx >= items.length) {
      finishGame({ correct, total: items.length, skill_hits: skillHits, subskill_hits: zpd.subskillHits, played_ids: zpd.playedIds, peak_tier: zpd.peakTier, production_passed: false });
      return;
    }
    beginStepClock();
    reactorPower = 30;
    const it = items[idx];
    setHud({ visible: true, step: idx + 1, total: items.length, score: App.score, combo: App.combo, title: "Reactor Overdrive", aiPack: !!pack.ai_generated });
    let hadMiss = false;
    let chosenBridge = null;
    let chosenKind = "complex";
    let chosenVerb = null;

    const hlVerb = (txt) => txt.replace(new RegExp(`\\b(${it.weak_verb.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})\\b`, "i"),
      '<span class="st-weak-verb">$1</span>');

    $("stHost").innerHTML = `
      <div class="sa-panel">
        <div class="sa-mission-banner" style="margin-bottom:8px">
          <div class="st-meter-wrap" style="flex:1;margin:0">
            <div class="st-meter-bar"><div class="st-meter-fill" id="stMeterFill"></div></div>
            <div class="st-meter-label" id="stMeterLbl">STAGE 1 · UNLINKED</div>
          </div>
          <button type="button" class="sa-speak-btn" id="stSpeakInit">🔊 Read Both</button>
        </div>
        <div class="sa-prompt-text" id="stStepPrompt">Step 1: Snap the right bridge to link these two power cores!</div>
      </div>
      <div class="st-rails" id="stRails">
        ${it.front_connector ? `<div class="st-bridge-slot" id="stBridgeSlot">Starter?</div>` : ""}
        <div class="st-clause">${hlVerb(esc(it.clause_a))}</div>
        ${!it.front_connector ? `<div class="st-bridge-slot" id="stBridgeSlot">Bridge?</div>` : ""}
        <div class="st-clause">${hlVerb(esc(it.clause_b))}</div>
      </div>
      <div class="sa-panel" id="stControls">
        <div style="text-align:center;color:#94a3b8;font-size:0.9rem">Pick the power link:</div>
        <div class="st-pill-row" id="stBridgeRow"></div>
      </div>
      <div class="sa-feedback idle" id="stFb"><span class="sa-fb-msg">Pick the link that matches the real cause, timing, or twist!</span></div>`;

    $("stSpeakInit").onclick = () => VOICE.speak(`${it.clause_a} ${it.clause_b}`, { force: true });

    it.bridges.forEach((br) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sa-btn ghost";
      b.style.fontSize = "1.05rem"; b.style.padding = "11px 22px";
      b.textContent = it.front_connector ? br.word.charAt(0).toUpperCase() + br.word.slice(1) : br.word;
      b.onclick = () => {
        if (chosenBridge) return;
        if (br.ok) {
          chosenBridge = br.word;
          chosenKind = br.kind || "complex";
          reactorPower = 70;
          SFX.powerup();
          addPoints(75, b, "#10b981");
          $("stBridgeSlot").textContent = it.front_connector ? br.word.charAt(0).toUpperCase() + br.word.slice(1) : br.word;
          $("stBridgeSlot").classList.add("locked");
          $("stMeterFill").style.width = "70%";
          $("stMeterLbl").textContent = "STAGE 2 · LINKED";
          setFeedback($("stFb"), "ok", `⚡ <b>Cores linked!</b> ${esc(br.why)} Now supercharge the yellow action word!`);
          showVerbUpgrade();
        } else {
          hadMiss = true;
          resetCombo();
          SFX.bad();
          b.style.borderColor = "#fb7185";
          setFeedback($("stFb"), "bad", esc(br.why));
        }
      };
      $("stBridgeRow").appendChild(b);
    });

    function showVerbUpgrade() {
      $("stStepPrompt").textContent = `Step 2: Swap “${it.weak_verb}” for a high-voltage action word to hit OVERDRIVE!`;
      $("stControls").innerHTML = `
        <div style="text-align:center;color:#fde68a;font-size:0.95rem;font-weight:600">Supercharge “${esc(it.weak_verb)}”:</div>
        <div class="st-pill-row" id="stVerbRow"></div>`;
      it.verb_upgrades.forEach((vu) => {
        const vb = document.createElement("button");
        vb.type = "button";
        vb.className = "sa-btn ghost";
        vb.style.fontSize = "1.05rem"; vb.style.padding = "11px 22px";
        vb.textContent = vu.word;
        vb.onclick = () => {
          if (chosenVerb) return;
          if (vu.ok) {
            chosenVerb = vu.word;
            commitStepClock(40);
            reactorPower = 100;
            SFX.powerup();
            if (!hadMiss) correct += 1;
            skillHits[it.skill] = skillHits[it.skill] || { correct: 0, total: 0 };
            skillHits[it.skill].total += 1;
            if (!hadMiss) skillHits[it.skill].correct += 1;
            skillHits["B2.4_vocabulary"] = skillHits["B2.4_vocabulary"] || { correct: 0, total: 0 };
            skillHits["B2.4_vocabulary"].total += 1;
            if (!hadMiss) skillHits["B2.4_vocabulary"].correct += 1;
            zpd.record(it, !hadMiss, idx + 1, items);

            addPoints(hadMiss ? 60 : 120, vb, "#facc15");
            $("stMeterFill").style.width = "100%";
            $("stMeterLbl").textContent = "⚡ OVERDRIVE 100%!";
            const fused = buildFusedSentence(it, chosenBridge, chosenKind, chosenVerb);
            $("stRails").innerHTML = `<div style="font-size:1.22rem;font-weight:700;color:#6ee7b7;text-align:center">⚡ ${esc(fused)}</div>`;
            $("stControls").innerHTML = `
              <div style="display:flex;justify-content:center;gap:12px;align-items:center">
                <button type="button" class="sa-speak-btn" id="stHearBtn">🔊 Hear Overdrive Line</button>
              </div>`;
            $("stHearBtn").onclick = () => VOICE.speak(fused, { force: true });
            setFeedback($("stFb"), "ok", "🔥 <b>OVERDRIVE UNLOCKED!</b> Twin cores fused at 100% power!", {
              id: "stNextBtn", label: "Next Core →", onClick: () => { idx += 1; renderStep(); },
            });
          } else {
            hadMiss = true;
            resetCombo();
            SFX.bad();
            vb.style.borderColor = "#fb7185";
            setFeedback($("stFb"), "bad", `“${esc(vu.word)}” is low-voltage — pick one that paints a sharp action!`);
          }
        };
        $("stVerbRow").appendChild(vb);
      });
    }
  }
  renderStep();
}

// ===========================================================================
// GAME 5: 🏎️ NEON TURBO TYPING (2x DPR Toronto Highway + Full 5-Row Finger Keyboard!)
// ===========================================================================

const KBD_ROWS = [
  ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-"],
  ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
  ["A", "S", "D", "F", "G", "H", "J", "K", "L", "'"],
  ["Z", "X", "C", "V", "B", "N", "M", ",", ".", "?"],
  ["SPACE"],
];
const FINGER_META = {
  "1": ["L-Pinky", "f-lp"], "!": ["L-Pinky", "f-lp"], Q: ["L-Pinky", "f-lp"], A: ["L-Pinky", "f-lp"], Z: ["L-Pinky", "f-lp"],
  "2": ["L-Ring", "f-lr"], W: ["L-Ring", "f-lr"], S: ["L-Ring", "f-lr"], X: ["L-Ring", "f-lr"],
  "3": ["L-Middle", "f-lm"], E: ["L-Middle", "f-lm"], D: ["L-Middle", "f-lm"], C: ["L-Middle", "f-lm"],
  "4": ["L-Index", "f-li"], "5": ["L-Index", "f-li"], R: ["L-Index", "f-li"], F: ["L-Index", "f-li"], V: ["L-Index", "f-li"], T: ["L-Index", "f-li"], G: ["L-Index", "f-li"], B: ["L-Index", "f-li"],
  "6": ["R-Index", "f-ri"], "7": ["R-Index", "f-ri"], Y: ["R-Index", "f-ri"], H: ["R-Index", "f-ri"], N: ["R-Index", "f-ri"], U: ["R-Index", "f-ri"], J: ["R-Index", "f-ri"], M: ["R-Index", "f-ri"],
  "8": ["R-Middle", "f-rm"], I: ["R-Middle", "f-rm"], K: ["R-Middle", "f-rm"], ",": ["R-Middle", "f-rm"],
  "9": ["R-Ring", "f-rr"], O: ["R-Ring", "f-rr"], L: ["R-Ring", "f-rr"], ".": ["R-Ring", "f-rr"],
  "0": ["R-Pinky", "f-rp"], "-": ["R-Pinky", "f-rp"], P: ["R-Pinky", "f-rp"], "'": ["R-Pinky", "f-rp"], "\"": ["R-Pinky", "f-rp"], "?": ["R-Pinky", "f-rp"],
  SPACE: ["Thumb", "f-th"], " ": ["Thumb", "f-th"],
};
// Maps shifted punctuation to its physical base key on KBD_ROWS so EVERY symbol highlights cleanly!
const SHIFT_KEY_MAP = { "!": "1", "\"": "'", "?": "?" };

function runTypingArena(pack) {
  const stage = $("saGameStage");
  const items = pack.items;
  const zpd = createZpdDirector(pack);
  const targetWpm = Math.max(12, Math.min(55, Number(pack.adaptive?.target_wpm) || 20));
  let totalCharsAll = items.reduce((acc, it) => acc + it.text.length, 0);
  let idx = 0;
  let pos = 0;
  let lapErrors = 0;
  let totalTyped = 0;
  let totalCorrect = 0;
  let firstKeyTs = 0;
  let lastFrameTs = performance.now();
  let currentWpm = 0;
  let currentAcc = 100;
  let errFlash = 0;
  let roadOffset = 0;
  let active = true;
  let rafId = 0;
  const charErrors = {};

  // Live adaptive rival cruisers paced around the player's personal ZPD WPM!
  const rivals = [
    { lane: -0.55, prog: 0.05, wpmMult: 0.78, col: "#f43f5e", passed: false },
    { lane: 0.55, prog: 0.12, wpmMult: 0.93, col: "#a855f7", passed: false },
    { lane: -0.32, prog: 0.19, wpmMult: 1.04, col: "#f59e0b", passed: false },
  ];

  stage.innerHTML = `
    <div class="ty-road-wrap">
      <canvas id="tyCanvas"></canvas>
      <div class="ty-rank" id="tyRank">POS: 4th / 4</div>
      <div class="ty-telemetry">
        <div class="ty-gauge" id="tyWpm">0 WPM</div>
        <div class="ty-gauge" id="tyAcc">100% ACC</div>
      </div>
    </div>
    <div class="sa-panel" style="display:flex;flex-direction:column;gap:10px;padding:16px 20px">
      <div class="sa-mission-banner">
        <span class="sa-mission-tag" id="tyTag">🏎️ RACE LAP 1</span>
        <span class="sa-tag" id="tyFingerTag">Next finger: —</span>
      </div>
      <div class="ty-prompt-box" id="tyPrompt" tabindex="0"></div>
      <div class="ty-kbd" id="tyKbd"></div>
    </div>
    <div class="sa-feedback idle" id="tyFb"><span class="sa-fb-msg">Start typing right away! Keep accuracy <b>≥ 94%</b> for golden Turbo Boost and overtake all 3 rival racers!</span></div>`;

  $("tyKbd").innerHTML = KBD_ROWS.map((row) =>
    `<div class="ty-kbd-row">${row.map((k) => {
      const fCls = (FINGER_META[k] || ["", "f-rp"])[1];
      return `<span class="ty-key ${fCls} ${k === "SPACE" ? "space" : ""}" data-key="${esc(k)}">${k === "SPACE" ? "SPACE" : esc(k)}</span>`;
    }).join("")}</div>`
  ).join("");

  const cv = $("tyCanvas");
  const ctx = cv.getContext("2d");

  function drawRoad() {
    if (!active) return;
    const nowTs = performance.now();
    const dtSec = Math.min(0.05, Math.max(0, (nowTs - lastFrameTs) / 1000));
    lastFrameTs = nowTs;
    const { W, H } = fitCanvas(cv, ctx, 300, 180);
    const horiz = H * 0.44;
    const turbo = currentAcc >= 94 && currentWpm >= 14;
    const speed = 0.015 + Math.min(0.14, currentWpm * 0.0026);
    roadOffset = (roadOffset + speed) % 1;
    const myProg = totalCorrect / Math.max(1, totalCharsAll);

    // Advance rival cruisers dynamically once the race starts (with gentle rubber-banding!)
    if (firstKeyTs && !document.hidden) {
      const baseCps = (targetWpm * 5) / 60;
      for (const rv of rivals) {
        const gap = rv.prog - myProg;
        const band = gap > 0.22 ? 0.55 : (gap < -0.18 ? 1.12 : 1.0);
        const dps = ((baseCps * rv.wpmMult * band) / Math.max(1, totalCharsAll)) * dtSec;
        rv.prog = Math.min(0.985, rv.prog + dps);
      }
    }

    const sky = ctx.createLinearGradient(0, 0, 0, horiz);
    sky.addColorStop(0, "#05040f"); sky.addColorStop(1, turbo ? "#2e1065" : "#111834");
    ctx.fillStyle = sky; ctx.fillRect(0, 0, W, horiz);

    const sunR = 58;
    const sunG = ctx.createLinearGradient(W / 2, horiz - sunR, W / 2, horiz);
    sunG.addColorStop(0, turbo ? "#fef08a" : "#38bdf8");
    sunG.addColorStop(0.55, turbo ? "#f97316" : "#a855f7");
    sunG.addColorStop(1, "#ec4899");
    ctx.save();
    ctx.fillStyle = sunG; ctx.beginPath(); ctx.arc(W / 2, horiz, sunR, Math.PI, 0); ctx.fill();
    ctx.fillStyle = turbo ? "#2e1065" : "#111834";
    for (let s = 1; s <= 4; s++) ctx.fillRect(W / 2 - sunR, horiz - s * 9, sunR * 2, s * 1.1);
    ctx.restore();

    // Toronto Skyline + CN Tower
    ctx.fillStyle = "#080b18";
    const towers = [[0.12, 30, 22], [0.16, 42, 18], [0.22, 26, 26], [0.30, 48, 20], [0.36, 34, 16], [0.62, 38, 20], [0.68, 50, 24], [0.75, 32, 18], [0.81, 44, 22], [0.87, 28, 18]];
    for (const [fx, th, tw] of towers) ctx.fillRect(W * fx, horiz - th, tw, th);
    const cnx = W * 0.43;
    ctx.fillRect(cnx - 2.5, horiz - 78, 5, 78);
    ctx.beginPath(); ctx.ellipse(cnx, horiz - 52, 11, 4, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = turbo ? "#facc15" : "#22d3ee";
    ctx.fillRect(cnx - 1, horiz - 86, 2, 9); ctx.fillRect(cnx - 7, horiz - 53, 14, 2);

    ctx.fillStyle = "#070b1a"; ctx.fillRect(0, horiz, W, H - horiz);

    ctx.strokeStyle = errFlash > 0.1 ? "#fb7185" : (turbo ? "rgba(250,204,21,0.58)" : "rgba(34,211,238,0.44)");
    ctx.lineWidth = 1.5;
    for (let i = -7; i <= 7; i++) {
      ctx.beginPath(); ctx.moveTo(W / 2 + i * 24, horiz); ctx.lineTo(W / 2 + i * 145, H); ctx.stroke();
    }
    for (let j = 0; j < 8; j++) {
      const t = ((j + roadOffset) / 8) ** 2;
      const y = horiz + t * (H - horiz);
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }

    // Turbo FOV speed lines along edges when blazing fast!
    if (turbo) {
      ctx.strokeStyle = "rgba(250, 204, 21, 0.35)"; ctx.lineWidth = 2;
      for (let k = 0; k < 6; k++) {
        const side = k % 2 === 0 ? -1 : 1;
        const p = ((k * 0.23 + roadOffset * 2) % 1);
        const lx = W / 2 + side * (160 + p * (W * 0.36));
        const ly = horiz + p * (H - horiz);
        ctx.beginPath(); ctx.moveTo(lx, ly); ctx.lineTo(lx + side * 26, ly + 14); ctx.stroke();
      }
    }

    let ahead = 0;
    for (const rv of rivals) {
      const rel = rv.prog - myProg;
      if (rel > 0) ahead += 1;
      else if (!rv.passed) {
        rv.passed = true;
        SFX.powerup();
        FX.floatEl($("tyRank"), "🏁 OVERTAKE!", "#facc15");
      }
      if (rel > -0.1 && rel < 0.45) {
        const depth = Math.max(0.05, Math.min(1, 1 - rel / 0.45));
        const ry = horiz + (depth ** 1.7) * (H - horiz - 30);
        const rx = W / 2 + rv.lane * (60 + depth * 210);
        const sc = 0.25 + depth * 0.85;
        ctx.save();
        ctx.translate(rx, ry); ctx.scale(sc, sc);
        ctx.fillStyle = "#111827"; ctx.strokeStyle = rv.col; ctx.lineWidth = 2.5;
        ctx.shadowColor = rv.col; ctx.shadowBlur = 12;
        ctx.beginPath(); ctx.moveTo(0, -16); ctx.lineTo(26, 10); ctx.lineTo(-26, 10); ctx.closePath();
        ctx.fill(); ctx.stroke();
        ctx.fillStyle = rv.col; ctx.fillRect(-10, 10, 20, 4);
        ctx.restore();
      }
    }
    $("tyRank").textContent = `POS: ${["1st 🏆", "2nd", "3rd", "4th"][ahead]} / 4`;

    const cx = W / 2;
    const cy = H - 34 + Math.sin(performance.now() * 0.009) * 2.5;
    ctx.save();
    ctx.fillStyle = errFlash > 0.1 ? "#fb7185" : (turbo ? "#facc15" : "#22d3ee");
    ctx.shadowColor = ctx.fillStyle; ctx.shadowBlur = turbo ? 26 : 14;
    const fl = 12 + Math.min(34, currentWpm * 0.85) + Math.random() * 7;
    for (const ox of [-13, 13]) {
      ctx.beginPath(); ctx.moveTo(cx + ox - 6, cy + 11); ctx.lineTo(cx + ox, cy + 11 + fl); ctx.lineTo(cx + ox + 6, cy + 11); ctx.closePath(); ctx.fill();
    }
    ctx.restore();

    ctx.save();
    ctx.fillStyle = "#0f172a"; ctx.strokeStyle = turbo ? "#facc15" : "#38bdf8"; ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(cx, cy - 25); ctx.lineTo(cx + 38, cy + 11); ctx.lineTo(cx + 18, cy + 16);
    ctx.lineTo(cx - 18, cy + 16); ctx.lineTo(cx - 38, cy + 11); ctx.closePath();
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = turbo ? "#fef08a" : "#38bdf8";
    ctx.beginPath(); ctx.moveTo(cx, cy - 14); ctx.lineTo(cx + 10, cy + 2); ctx.lineTo(cx - 10, cy + 2); ctx.closePath(); ctx.fill();
    ctx.restore();

    errFlash *= 0.85;
    rafId = requestAnimationFrame(drawRoad);
  }
  rafId = requestAnimationFrame(drawRoad);

  function renderPrompt(badNow = false) {
    const it = items[idx];
    const txt = it.text;
    setHud({ visible: true, step: idx + 1, total: items.length, score: App.score, combo: App.combo, title: "Neon Drift: Toronto", aiPack: !!pack.ai_generated });
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
    const normKey = targetChar === " " ? "SPACE" : (SHIFT_KEY_MAP[targetChar] || targetChar.toUpperCase());
    $("tyKbd").querySelectorAll(".ty-key").forEach((el) => el.classList.toggle("next", el.dataset.key === normKey));
    const shiftNeed = /[A-Z!"?]/.test(targetChar);
    const fHint = (FINGER_META[targetChar] || FINGER_META[targetChar.toUpperCase()] || ["R-Pinky"])[0];
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
    if (!firstKeyTs) {
      firstKeyTs = performance.now();
      beginStepClock();
    }

    const target = items[idx].text[pos];
    totalTyped += 1;
    if (e.key === target) {
      totalCorrect += 1;
      pos += 1;
      SFX.keyTick();
      updateMetrics();
      if (pos >= items[idx].text.length) {
        commitStepClock(40);
        const curItem = items[idx];
        zpd.record(curItem, lapErrors <= 2, idx + 1, items);
        // Recompute totalCharsAll immediately after any mid-race ZPD sentence swap so myProg & rival dps stay 100% synced!
        totalCharsAll = items.reduce((acc, it) => acc + it.text.length, 0);
        lapErrors = 0;
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
            char_errors: charErrors,
            subskill_hits: zpd.subskillHits,
            played_ids: zpd.playedIds,
            peak_tier: zpd.peakTier,
            production_passed: currentAcc >= 90,
          });
          return;
        }
        setFeedback($("tyFb"), "ok", `⚡ Lap cleared at <b>${currentWpm} WPM</b> (${currentAcc}% accuracy)! Keep flying!`);
      }
      renderPrompt(false);
    } else {
      lapErrors += 1;
      if (/[A-Z]/.test(target) && e.key === target.toLowerCase()) {
        charErrors.SHIFT = (charErrors.SHIFT || 0) + 1;
      } else if (target && target !== " ") {
        charErrors[target] = (charErrors[target] || 0) + 1;
      }
      errFlash = 1;
      resetCombo();
      SFX.keyErr();
      updateMetrics();
      renderPrompt(true);
    }
  };

  window.addEventListener("keydown", onKeyDown);
  addCleanup(() => { active = false; cancelAnimationFrame(rafId); window.removeEventListener("keydown", onKeyDown); });
  renderPrompt(false);
}

// ===========================================================================
// GAME 6: 🔎 MYSTERY CLUE DETECTIVE (2x DPR Noir Pinboard + Sticky Highlighter + Above-Fold Stamp!)
// ===========================================================================

function runClueDetective(pack) {
  const stage = $("saGameStage");
  const items = pack.items;
  const zpd = createZpdDirector(pack);
  let idx = 0;
  let correct = 0;
  const skillHits = {};
  let lastVerdict = "";
  let stampProgress = 0;
  let caseClosedNow = false;
  let deskShake = 0;

  stage.innerHTML = `
    <div class="sa-scene-wrap" style="border-color:rgba(250,204,21,0.42)"><canvas id="cdDeskCv"></canvas></div>
    <div id="cdHost" style="display:flex;flex-direction:column;gap:10px"></div>`;

  const dcv = $("cdDeskCv");
  const dctx = dcv.getContext("2d");
  const motes = Array.from({ length: 24 }, () => ({ x: Math.random(), y: Math.random(), vx: (Math.random() - 0.5) * 0.001, vy: -0.001 - Math.random() * 0.001, r: 1 + Math.random() * 1.8 }));
  let active = true;
  let rafId = 0;

  function drawDesk() {
    if (!active) return;
    const { W, H } = fitCanvas(dcv, dctx, 300, 110);
    const nowS = performance.now() * 0.001;
    const sx = deskShake > 0.2 ? (Math.random() - 0.5) * deskShake : 0;
    const sy = deskShake > 0.2 ? (Math.random() - 0.5) * deskShake : 0;
    deskShake *= 0.84;

    dctx.save();
    dctx.translate(sx, sy);

    const bg = dctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, "#0b0d17"); bg.addColorStop(1, "#181826");
    dctx.fillStyle = bg; dctx.fillRect(0, 0, W, H);

    // Subtle Noir Pinboard Evidence Cards + Red Detective Strings!
    const pins = [[W * 0.14, H * 0.58], [W * 0.34, H * 0.44], [W * 0.68, H * 0.42], [W * 0.86, H * 0.60]];
    dctx.strokeStyle = "rgba(244, 63, 94, 0.35)"; dctx.lineWidth = 1.6;
    dctx.beginPath();
    pins.forEach(([px, py], i) => i === 0 ? dctx.moveTo(px, py) : dctx.lineTo(px, py));
    dctx.stroke();

    for (const [px, py] of pins) {
      dctx.fillStyle = "rgba(30, 41, 59, 0.75)"; dctx.strokeStyle = "rgba(250, 204, 21, 0.25)"; dctx.lineWidth = 1;
      dctx.beginPath(); dctx.roundRect(px - 32, py - 16, 64, 38, 4); dctx.fill(); dctx.stroke();
      // Fake dossier lines
      dctx.fillStyle = "rgba(148, 163, 184, 0.25)";
      dctx.fillRect(px - 22, py - 4, 44, 3); dctx.fillRect(px - 22, py + 4, 32, 3); dctx.fillRect(px - 22, py + 12, 38, 3);
      // Red thumbtack pin
      dctx.fillStyle = "#f43f5e"; dctx.beginPath(); dctx.arc(px, py - 12, 3.5, 0, Math.PI * 2); dctx.fill();
    }

    const lg = dctx.createRadialGradient(W * 0.5, -10, 10, W * 0.5, H * 0.5, W * 0.45);
    lg.addColorStop(0, "rgba(250, 204, 21, 0.2)"); lg.addColorStop(0.6, "rgba(245, 158, 11, 0.05)"); lg.addColorStop(1, "transparent");
    dctx.fillStyle = lg; dctx.fillRect(0, 0, W, H);

    for (const m of motes) {
      m.x += m.vx; m.y += m.vy;
      if (m.y < 0) { m.y = 1; m.x = Math.random(); }
      dctx.fillStyle = "rgba(254, 240, 138, 0.35)";
      dctx.beginPath(); dctx.arc(m.x * W, m.y * H, m.r, 0, Math.PI * 2); dctx.fill();
    }

    // Sweeping Magnifying Glass Scanner
    const mx = W * 0.5 + Math.sin(nowS * 1.1) * (W * 0.26);
    const my = H * 0.52 + Math.cos(nowS * 1.6) * 10;
    dctx.save();
    dctx.strokeStyle = "#facc15"; dctx.lineWidth = 3.5; dctx.shadowColor = "#facc15"; dctx.shadowBlur = 14;
    dctx.beginPath(); dctx.arc(mx, my, 22, 0, Math.PI * 2); dctx.stroke();
    dctx.fillStyle = "rgba(250, 204, 21, 0.12)"; dctx.fill();
    dctx.beginPath(); dctx.moveTo(mx + 15, my + 15); dctx.lineTo(mx + 32, my + 32); dctx.lineWidth = 6; dctx.lineCap = "round"; dctx.stroke();
    dctx.restore();

    dctx.font = "700 12px 'JetBrains Mono', monospace";
    dctx.fillStyle = "#fde047"; dctx.textAlign = "left";
    dctx.fillText(`DETECTIVE DESK · CASE ${Math.min(idx + 1, items.length)} / ${items.length}`, 18, 22);

    if (caseClosedNow) {
      stampProgress = Math.min(1, stampProgress + 0.12);
      const sc = 2.1 - 1.1 * stampProgress;
      dctx.save();
      dctx.translate(W * 0.5, H * 0.54);
      dctx.rotate(-0.11);
      dctx.scale(sc, sc);
      dctx.globalAlpha = stampProgress;
      dctx.strokeStyle = "#facc15"; dctx.fillStyle = "rgba(250, 204, 21, 0.18)";
      dctx.shadowColor = "#facc15"; dctx.shadowBlur = 22; dctx.lineWidth = 4;
      dctx.beginPath(); dctx.roundRect(-112, -22, 224, 44, 8); dctx.fill(); dctx.stroke();
      dctx.font = "700 21px 'JetBrains Mono', monospace";
      dctx.fillStyle = "#fef08a"; dctx.textAlign = "center";
      dctx.fillText("CASE CLOSED ✓", 0, 7);
      dctx.restore();
    }

    dctx.restore();
    rafId = requestAnimationFrame(drawDesk);
  }
  rafId = requestAnimationFrame(drawDesk);
  addCleanup(() => { active = false; cancelAnimationFrame(rafId); });

  let caseCleanup = null;
  addCleanup(() => { if (caseCleanup) { caseCleanup(); caseCleanup = null; } });

  function renderCase() {
    VOICE.stop();
    if (caseCleanup) { caseCleanup(); caseCleanup = null; }
    if (idx >= items.length) {
      finishGame({
        correct,
        total: items.length,
        production_passed: !!lastVerdict,
        production_sentence: lastVerdict,
        skill_hits: skillHits,
        subskill_hits: zpd.subskillHits,
        played_ids: zpd.playedIds,
        peak_tier: zpd.peakTier,
      });
      return;
    }
    beginStepClock();
    caseClosedNow = false;
    stampProgress = 0;
    const it = items[idx];
    setHud({ visible: true, step: idx + 1, total: items.length, score: App.score, combo: App.combo, title: "Shadow Detective", aiPack: !!pack.ai_generated });
    let clueFound = false;
    let choiceLocked = false;
    let hadMiss = false;

    $("cdHost").innerHTML = `
      <div class="sa-panel" style="padding:14px 18px">
        <div class="sa-mission-banner">
          <span class="sa-mission-tag">🔎 ${esc(it.case_title)}</span>
          <button type="button" class="sa-speak-btn" id="cdSpeakBtn">🔊 Read Casefile</button>
        </div>
        <div class="sa-prompt-text" style="font-size:1.18rem">${esc(it.question)}</div>
      </div>
      <div class="cd-casefile-wrap" id="cdWrap">
        <canvas class="cd-hl-canvas" id="cdHlCv"></canvas>
        <div class="cd-casefile" id="cdFile" style="padding:14px 16px;gap:8px"></div>
      </div>
      <div id="cdStep2" hidden></div>
      <div id="cdStep3" hidden></div>
      <div class="sa-feedback idle" id="cdFb"><span class="sa-fb-msg">Swipe your Lenovo stylus (or mouse) across the exact proof sentence like a glowing highlighter — or tap it!</span></div>`;

    $("cdSpeakBtn").onclick = () => VOICE.speak(`${it.question} ${it.sentences.join(" ")}`, { force: true });

    const file = $("cdFile");
    const lineEls = [];
    it.sentences.forEach((sent, si) => {
      const div = document.createElement("div");
      div.className = "cd-line";
      div.style.padding = "10px 14px";
      div.dataset.si = si;
      div.innerHTML = `<span style="color:#94a3b8;font-family:'JetBrains Mono',monospace;margin-right:8px">[${si + 1}]</span>${esc(sent)}`;
      file.appendChild(div);
      lineEls.push(div);
    });

    const wrap = $("cdWrap");
    const hcv = $("cdHlCv");
    const hctx = hcv.getContext("2d");
    let hlDims = fitCanvas(hcv, hctx, 240, 120);
    const ro = new ResizeObserver(() => { if (!clueFound) hlDims = fitCanvas(hcv, hctx, 240, 120); });
    ro.observe(wrap);
    caseCleanup = () => ro.disconnect();

    function checkLine(si, savedStroke = null) {
      if (clueFound || si < 0 || si >= lineEls.length) return;
      const div = lineEls[si];
      if (si === it.clue_index) {
        clueFound = true;
        div.classList.add("highlighted");
        hcv.style.pointerEvents = "none";
        // Keep the child's glowing yellow highlighter stroke painted right over the proof sentence!
        if (savedStroke && savedStroke.length >= 2) {
          hctx.clearRect(0, 0, hlDims.W, hlDims.H);
          hctx.strokeStyle = "rgba(250, 204, 21, 0.28)";
          hctx.lineWidth = 22; hctx.lineCap = "round"; hctx.lineJoin = "round";
          hctx.beginPath();
          savedStroke.forEach((p, i) => i === 0 ? hctx.moveTo(p.x, p.y) : hctx.lineTo(p.x, p.y));
          hctx.stroke();
        }
        SFX.highlight();
        addPoints(75, div, "#facc15");
        setFeedback($("cdFb"), "ok", "🟡 <b>Evidence highlighted!</b> Now lock in your deduction below.");
        showChoices();
      } else {
        hadMiss = true;
        resetCombo();
        SFX.bad();
        div.classList.add("miss");
        safeTimeout(() => div.classList.remove("miss"), 380);
        setFeedback($("cdFb"), "bad", "That line sets the scene, but doesn't hold the smoking-gun clue. Check the other lines!");
      }
    }

    let activePid = null;
    let hlPts = [];
    let hlScreenPts = [];
    hcv.addEventListener("pointerdown", (e) => {
      if (clueFound) return;
      if (e.pointerType === "pen") App.penDetected = true;
      if (App.penDetected && e.pointerType === "touch") return; // Palm rejection
      if (activePid !== null) return;
      activePid = e.pointerId;
      hcv.setPointerCapture?.(e.pointerId);
      const r = wrap.getBoundingClientRect();
      hlPts = [{ x: e.clientX - r.left, y: e.clientY - r.top }];
      hlScreenPts = [{ x: e.clientX, y: e.clientY }];
    });
    hcv.addEventListener("pointermove", (e) => {
      if (e.pointerId !== activePid || clueFound) return;
      const r = wrap.getBoundingClientRect();
      const evts = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
      for (const ev of evts) {
        hlPts.push({ x: ev.clientX - r.left, y: ev.clientY - r.top });
        hlScreenPts.push({ x: ev.clientX, y: ev.clientY });
      }
      hctx.clearRect(0, 0, hlDims.W, hlDims.H);
      hctx.strokeStyle = "rgba(250, 204, 21, 0.42)";
      hctx.lineWidth = 22; hctx.lineCap = "round"; hctx.lineJoin = "round";
      hctx.beginPath();
      hlPts.forEach((p, i) => i === 0 ? hctx.moveTo(p.x, p.y) : hctx.lineTo(p.x, p.y));
      hctx.stroke();
    });
    const finishHl = (e) => {
      if (e.pointerId !== activePid) return;
      activePid = null;
      const saved = hlPts.slice();
      hctx.clearRect(0, 0, hlDims.W, hlDims.H);
      if (hlScreenPts.length) {
        if (hlScreenPts.length >= 2) FX.slash(hlScreenPts, "rgba(250, 204, 21, 0.7)", 16);
        const counts = new Map();
        for (const sp of hlScreenPts) {
          for (const el of lineEls) {
            const lr = el.getBoundingClientRect();
            if (sp.y >= lr.top && sp.y <= lr.bottom) {
              const sidx = Number(el.dataset.si);
              counts.set(sidx, (counts.get(sidx) || 0) + 1);
            }
          }
        }
        let bestIdx = -1, bestCnt = 0;
        for (const [k, v] of counts.entries()) {
          if (v > bestCnt) { bestCnt = v; bestIdx = k; }
        }
        if (bestIdx >= 0) checkLine(bestIdx, saved);
      }
      hlPts = [];
      hlScreenPts = [];
    };
    hcv.addEventListener("pointerup", finishHl);
    hcv.addEventListener("pointercancel", finishHl);

    function showChoices() {
      const s2 = $("cdStep2");
      s2.hidden = false;
      s2.innerHTML = `<div class="sa-choice-list" id="cdChoices"></div>`;
      it.choices.forEach((ch) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "sa-choice-btn";
        b.style.padding = "12px 16px";
        b.textContent = ch.label;
        b.onclick = () => {
          if (choiceLocked) return;
          if (ch.ok) {
            choiceLocked = true;
            SFX.ok();
            addPoints(65, b, "#10b981");
            // Collapse Step 2 into a sleek 1-line badge so Noir Desk + CASE CLOSED stamp stay 100% ABOVE THE FOLD!
            s2.innerHTML = `<div class="cd-locked-badge">✅ Deduction Locked: <b>${esc(ch.label)}</b> — ${esc(it.explain)}</div>`;
            setFeedback($("cdFb"), "ok", "✍️ Deduction locked! Finish your 1-sentence Case Verdict using <b>because</b> + real proof!");
            showVerdict();
          } else {
            hadMiss = true;
            resetCombo();
            b.classList.add("bad");
            SFX.bad();
            setFeedback($("cdFb"), "bad", esc(ch.why || "Re-read your highlighted clue carefully!"));
          }
        };
        $("cdChoices").appendChild(b);
      });
    }

    function showVerdict() {
      const s3 = $("cdStep3");
      s3.hidden = false;
      s3.innerHTML = `
        <div class="sa-panel" style="padding:14px 16px;border-color:rgba(250,204,21,0.5)">
          <div style="font-weight:700;color:#fde68a;margin-bottom:8px;font-size:0.95rem">✍️ Final Step — Lock in your Final Verdict (prove WHY after “because” + end with a period!):</div>
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
            <input type="text" id="cdVerdictInput" class="sa-sentence-input" style="flex:1;min-width:260px" value="${esc(it.verdict_starter)} " autocomplete="off" />
            <button type="button" class="sa-btn primary" id="cdCloseBtn">⚖️ Stamp CASE CLOSED</button>
          </div>
        </div>`;
      const inp = $("cdVerdictInput");
      inp.focus();
      inp.setSelectionRange(inp.value.length, inp.value.length);

      const submitVerdict = async () => {
        const txt = inp.value.trim();
        if (!txt) return;
        const btn = $("cdCloseBtn");
        btn.disabled = true;
        btn.textContent = "Checking…";
        try {
          const r = await fetch("/api/skill-games/check-sentence", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              text: txt,
              required_word: it.required_word || "",
              require_because: true,
              context_prompt: `Question: ${it.question} | Text proof clue: ${it.sentences[it.clue_index]} | Answer: ${it.explain}`,
            }),
          });
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          const chk = await r.json();
          if (chk.ok) {
            commitStepClock(45);
            caseClosedNow = true;
            deskShake = 12;
            SFX.stamp();
            lastVerdict = txt;
            if (!hadMiss) correct += 1;
            skillHits[it.skill] = skillHits[it.skill] || { correct: 0, total: 0 };
            skillHits[it.skill].total += 1;
            if (!hadMiss) skillHits[it.skill].correct += 1;
            zpd.record(it, !hadMiss, idx + 1, items);
            addPoints(140, inp, "#facc15");
            inp.disabled = true;
            btn.textContent = "✓ Stamped";
            setFeedback($("cdFb"), "ok", "🏆 <b>CASE CLOSED!</b> Airtight evidence!", {
              id: "cdNextBtn", label: "Next Case →", onClick: () => { idx += 1; renderCase(); },
            });
          } else {
            btn.disabled = false;
            btn.textContent = "⚖️ Stamp CASE CLOSED";
            SFX.bad();
            setFeedback($("cdFb"), "bad", esc(chk.feedback));
          }
        } catch (err) {
          btn.disabled = false;
          btn.textContent = "⚖️ Stamp CASE CLOSED";
          SFX.bad();
          setFeedback($("cdFb"), "bad", "Network hiccup checking your verdict — click Stamp CASE CLOSED to try again!");
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
    VOICE.stop();
    try { window.parent.postMessage({ __skillArcadeClose: true }, "*"); } catch (_) { }
  } else {
    VOICE.stop();
    location.href = IS_SANDBOX ? "/?sandbox=1" : "/";
  }
};

$("saVoiceBtn").onclick = () => {
  const on = VOICE.toggle();
  $("saVoiceBtn").classList.toggle("on", on);
  $("saVoiceBtn").textContent = on ? "🗣️" : "🤫";
  $("saVoiceBtn").setAttribute("aria-pressed", String(on));
};

$("saMuteBtn").onclick = () => {
  const m = SFX.toggle();
  $("saMuteBtn").textContent = m ? "🔇" : "🔊";
  $("saMuteBtn").setAttribute("aria-pressed", String(m));
};

$("saUseAi").addEventListener("change", () => { App.worldsTouched = true; });
$("saPlayAgainBtn").onclick = () => startGame(App.currentGameId, $("saUseAi").checked);
$("saPlayAiBtn").onclick = () => startGame(App.currentGameId, true);
$("saReturnHubBtn").onclick = () => loadHub();

loadHub().then(() => {
  if (START_GAME) startGame(START_GAME, $("saUseAi").checked);
});
