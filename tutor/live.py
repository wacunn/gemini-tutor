"""Bridges one browser WebSocket to a Gemini Live session and enforces the synchronous Pedagogical Controller.

Browser -> server:  binary = 16 kHz mono PCM16 mic audio
                    text   = JSON (typed text, pen images, taps, activity events, control)
Server -> browser:  binary = 24 kHz mono PCM16 tutor audio
                    text   = JSON UI events (captions, goal badge, canvas items, input requests)
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time
import traceback
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

from . import blackboard, builder, controller, curriculum_tracker, guardian, media, observers, projects, thinking
from .config import DATA, LIVE_FALLBACK_MODELS, LIVE_MODEL, api_key, genai_client
from .prompt import TOOL_SPECS, build_system_prompt, opening_message
from .record import (
    SessionLog,
    list_activities,
    load_activity,
    load_learner,
    new_id,
    now_iso,
    read_session,
    save_activity,
    save_learner,
    save_piece,
)

# Latest observer state per active session, for the parent's live view.
LIVE: dict[str, dict[str, Any]] = {}


_NOISE_RE = re.compile(
    r"(?:[<\[\(\{]\s*)?\b(?:no\s+speech(?:\s+detected)?|inaudible|background\s+noise|silence)\b[.\s!]*(?:[>\]\)\}])?",
    re.I,
)


def _clean_transcript(raw: str) -> str:
    """Strips control tags and all 'no speech detected' / 'silence' / 'inaudible' markers anywhere in the string."""
    s = re.sub(r"<[^>]*>|\{[^}]*\}|\[[^\]]*\]", " ", raw or "")
    s = re.sub(r"[<{[][^>}\]]*$", "", s)  # strip any trailing half-open tag while streaming
    s = _NOISE_RE.sub(" ", s)
    s = re.sub(r"\s{2,}", " ", s)
    if not s.strip(" .,!?-"):
        return ""
    return s


def _tool_declarations() -> list[types.Tool]:
    decls = []
    for spec in TOOL_SPECS:
        props = {k: types.Schema(type=types.Type.STRING, description=d) for k, (_, d) in spec["params"].items()}
        params = types.Schema(type=types.Type.OBJECT, properties=props, required=spec["required"]) if props else None
        decls.append(types.FunctionDeclaration(name=spec["name"], description=spec["description"], parameters=params))
    return [types.Tool(function_declarations=decls)]


class TutorSession:
    def __init__(self, ws: WebSocket, test_mode: bool = False):
        self.ws = ws
        self.test_mode = test_mode
        self.rec = load_learner()
        self.name = self.rec.get("name") or "the student"
        self.id = new_id("test" if test_mode else "sess")
        self.log = SessionLog(self.id, test_mode=test_mode)
        self.ctrl = controller.SessionController(self.rec, test_mode=test_mode)
        self.ctrl.pause_for_art_check = True
        self.live: Any = None
        self.send_lock = asyncio.Lock()
        self.closed = False
        self.resume_handle: str | None = None
        self.started = time.time()

        # conversation state
        self.kid_raw_buf = ""
        self.kid_buf = ""
        self.tutor_raw_buf = ""
        self.tutor_buf = ""
        self.turn = 0
        self.kid_turn_id = 0
        self.spoke_since_kid = False
        self.tutor_busy = False
        self.pending: list[tuple[str, bytes | None]] = []
        self.silent_context: list[str] = []
        self.first_input_sent = False
        self.ready = asyncio.Event()
        self.opening_ideas: list[dict[str, Any]] = self._load_opening_ideas()

        # canvas state
        self.page: list[dict[str, str]] = []
        self.comic: dict[str, Any] | None = None
        self.drawn_items: dict[str, dict[str, Any]] = {}
        self.lettering_tries: dict[str, int] = {}
        self.current_card: dict[str, str] | None = None
        self.activity: dict[str, Any] | None = None
        self.build_task: asyncio.Task | None = None
        self.input_target: str | None = None
        self.last_activity_event = 0.0
        self.bg: set[asyncio.Task] = set()

        # observers
        self.stats = observers.WritingStats()
        self.tracker_state: dict[str, Any] = {}
        self.critic_state: dict[str, Any] = {}
        self.kid_events = 0
        self.observed_at_events = 0
        self.last_check_note = ""
        self.turns_judged = 0
        self.turns_ok = 0
        self.last_flawed_words: set[str] = set()
        self.tried: list[str] = []
        self.inventing = False

    def _load_opening_ideas(self) -> list[dict[str, Any]]:
        try:
            f = DATA / "opening_ideas.json"
            if f.exists():
                d = json.loads(f.read_text(encoding="utf-8"))
                if time.time() - d.get("made", 0) < 6 * 3600:
                    return d.get("ideas", [])[:3]
        except Exception:
            pass
        return []

    def _learner_notes_text(self) -> str:
        return "\n".join(f"- {n['note']}" for n in self.rec.get("parent_notes", []))

    # ---------- plumbing ----------

    async def ui(self, msg: dict[str, Any]) -> None:
        if self.closed:
            return
        try:
            await self.ws.send_text(json.dumps(msg))
        except Exception:
            self.closed = True

    async def ui_audio(self, data: bytes) -> None:
        if self.closed:
            return
        try:
            await self.ws.send_bytes(data)
        except Exception:
            self.closed = True

    def spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self.bg.add(t)
        t.add_done_callback(self.bg.discard)

    async def _emit_fallback_speech(self, fallback_text: str) -> None:
        clean_fb = (fallback_text or "").strip()
        if not clean_fb or self.closed:
            return
        self.turn += 1
        self.spoke_since_kid = True
        self.log.add("tutor_said", text=clean_fb, fallback=True)
        await self.ui({"type": "tutor_fallback_speech", "turn": self.turn, "text": clean_fb})
        await self.ui({"type": "turn_complete", "kid_turn": self.kid_turn_id})

    async def _speech_watchdog(self, expected_kid_turn: int, fallback_text: str) -> None:
        await asyncio.sleep(4.2)
        if (
            not self.closed
            and self.kid_turn_id == expected_kid_turn
            and not self.spoke_since_kid
            and not self.tutor_busy
            and fallback_text
        ):
            await self._emit_fallback_speech(fallback_text)

    async def _send_content(self, text: str, image: bytes | None = None, spoken_fallback: str = "") -> None:
        if not self.ready.is_set():
            try:
                await asyncio.wait_for(self.ready.wait(), timeout=1.2)
            except asyncio.TimeoutError:
                await self._emit_fallback_speech(spoken_fallback)
                return
        if not self.live:
            await self._emit_fallback_speech(spoken_fallback)
            return
        parts = [types.Part(text=text)]
        if image:
            parts.append(types.Part.from_bytes(data=media.small_jpeg(image), mime_type="image/jpeg"))
        my_turn = self.kid_turn_id
        sent_ok = False
        async with self.send_lock:
            if self.live:
                try:
                    await asyncio.wait_for(
                        self.live.send_client_content(turns=types.Content(role="user", parts=parts), turn_complete=True),
                        timeout=3.0,
                    )
                    sent_ok = True
                except Exception as e:
                    blackboard.QUOTA.note_error("live_send", e)
                    self.log.add("error", where="send_content", error=str(e))
        if not sent_ok:
            await self._emit_fallback_speech(spoken_fallback)
        elif spoken_fallback:
            self.spawn(self._speech_watchdog(my_turn, spoken_fallback))

    def opening(self) -> str:
        if self.opening_ideas:
            self.log.add("ideas", situation="opening (pre-generated)", focus="", ideas=self.opening_ideas)
        elif not self.inventing and blackboard.QUOTA.allow_background():
            self.inventing = True
            self.spawn(self._invent("Session starting; generate 3 intrinsically-integrated sentence mechanics.", "B3.1 complete sentences"))
        return opening_message(self.rec, self.opening_ideas)

    def recent_exchange(self, n: int = 10) -> str:
        from .review import _transcript

        events = [
            e
            for e in read_session(self.id, test_mode=self.test_mode)
            if e.get("kind") in ("kid_said", "tutor_said", "kid_typed", "kid_wrote", "kid_tapped", "tool")
        ]
        return _transcript(events[-n:], self.name)

    async def audit_tutor_turn(self) -> None:
        """Scores every completed tutor turn for the parent dashboard and queues silent correction ONLY if off-track."""
        if not blackboard.QUOTA.allow_background():
            return
        try:
            recent = self.recent_exchange(8)
            if "Tutor:" not in recent:
                return
            ctrl_summary = (
                f"phase={self.ctrl.phase}, rung={self.ctrl.rung}, goal={self.ctrl.goal_done}/{self.ctrl.goal_target}, "
                f"last_kid_kind={self.ctrl.last_kid_kind}, hint_step={self.ctrl.hint_step}, avoidance={self.ctrl.avoidance_streak}"
            )
            out = await asyncio.wait_for(
                asyncio.to_thread(
                    observers.turn_coach,
                    recent,
                    self.mechanic_desc(),
                    self.last_check_note,
                    self._learner_notes_text(),
                    ctrl_summary,
                ),
                timeout=8,
            )
        except Exception:
            return
        if not out:
            return
        self.turns_judged += 1
        ok = bool(out.get("last_turn_ok"))
        if ok:
            self.turns_ok += 1
        self.log.add("turn_coach", **out)
        if not self.test_mode:
            LIVE.setdefault(self.id, {})["turns"] = {"judged": self.turns_judged, "educational": self.turns_ok, "last": out}
        if not ok and out.get("next_move"):
            self.silent_context.append(f"[Auditor note for next turn: {out['next_move']}]")

    async def apply_controller_ui(self, ui_actions: list[dict[str, Any]], epoch: int | None = None) -> None:
        ep = epoch if epoch is not None else self.ctrl.blackboard.current_epoch()
        for act in ui_actions:
            out_act = {**act, "epoch": ep} if act.get("type") == "input" else act
            await self.ui(out_act)
            if act.get("type") == "item":
                it = act.get("item", {})
                if it.get("kind") == "card":
                    self.current_card = {"title": it.get("title", ""), "text": it.get("text", "")}
                self.log.add(
                    "ctrl_ui",
                    ui_kind=it.get("kind"),
                    title=it.get("title") or it.get("word") or it.get("prompt", ""),
                    detail=it.get("text") or (" + ".join(it.get("parts", [])) + " | " + it.get("note", "") if it.get("parts") else "") or " | ".join(it.get("options", [])),
                )
            elif act.get("type") == "input":
                self.log.add("ctrl_ui", ui_kind="input", title=act.get("prompt", ""), detail=f"prefill={act.get('prefill','')!r}")

    async def auto_render_sentence(self, sentence: str) -> str:
        """Immediately starts rendering the current book panel, comic panel, or scene image as soon as a complete sentence is verified."""
        if self.activity:
            return ""
        self.ctrl.draw_unlocked = False  # Prevent duplicate LLM draw tool call for this same sentence

        # Persistent Multi-Session Book / Graphic Novel / Codex Project!
        if self.ctrl.project:
            proj = self.ctrl.project
            pnum, _ = projects.add_panel_to_project(proj, sentence, scene=sentence, persist=True, sandbox=self.test_mode)
            await self.ui({"type": "reward", "label": f"★ Panel {pnum} Inked into “{proj.get('title','Book')}”!"})
            await self.ui({"type": "item", "item": projects.project_ui_payload(proj)})
            await self.ui({"type": "goal", "text": self.ctrl.goal_badge()})
            self.spawn(self._draw_project_panel(proj, pnum, sentence))
            self.log.add("auto_draw_book_panel", project=proj["id"], panel=pnum, sentence=sentence)
            return f" (Book Panel {pnum} is already saved and rendering on screen automatically—do NOT call draw or comic_panel again.)"

        if self.comic:
            idx = next((i for i, p in enumerate(self.comic["panels"]) if not p.get("image") and p.get("status") != "drawing"), None)
            if idx is None:
                self.comic["panels"].append({"caption": "", "dialogue": [], "scene": "", "image": None, "status": "empty"})
                idx = len(self.comic["panels"]) - 1
            p = self.comic["panels"][idx]
            c_txt, c_bubs = projects.extract_dialogue(sentence)
            p["caption"] = c_txt
            p["dialogue"] = c_bubs
            p["scene"] = sentence
            p["status"] = "drawing"
            await self.push_comic()
            self.spawn(self._draw_panel(idx))
            self.log.add("auto_draw_panel", panel=idx + 1, sentence=sentence)
            return f" (Panel {idx + 1} is already rendering on screen automatically—do NOT call comic_panel or draw again for this sentence.)"

        iid = new_id("draw")
        d_cap, d_bubs = projects.extract_dialogue(sentence)
        item = {"id": iid, "kind": "image", "caption": d_cap, "dialogue": d_bubs, "scene": sentence, "status": "drawing"}
        self.drawn_items[iid] = item
        await self.ui({"type": "item", "item": item})
        self.spawn(self._draw(item, sentence, media.DEFAULT_STYLE_KEY))
        self.log.add("auto_draw", id=iid, sentence=sentence)
        return " (The illustration for this sentence is already rendering on screen automatically—do NOT call draw again for this sentence.)"

    async def _maybe_prompt_art_check(self, target: str) -> None:
        if self.ctrl.phase == "AWAITING_ART_CHECK" and self.ctrl.pending_art_target == target:
            ui_chk, _, _ = self.ctrl.prompt_after_art_rendered(target)
            await self.apply_controller_ui(ui_chk)

    async def _run_redraw_art(self, rd: dict[str, Any] | None) -> str:
        if not rd or not self.ctrl.project:
            return ""
        if rd.get("kind") == "spine":
            self.spawn(self._draw_spine_beat(self.ctrl.project, rd["beat"], rd["scene"]))
            return " (Redrawing the Story Spine scene now—do NOT call draw.)"
        if rd.get("kind") == "panel":
            self.spawn(self._draw_project_panel(self.ctrl.project, int(rd["panel"]), rd["scene"]))
            return " (Redrawing the Comic Panel now—do NOT call draw.)"
        return ""

    async def _draw_project_panel(self, proj: dict[str, Any], panel_number: int, sentence: str) -> None:
        target = f"panel:{panel_number}"
        refs = []
        for mid in projects.recent_reference_media_ids(proj, limit=2, target=target):
            try:
                refs.append(media.media_path(mid).read_bytes())
            except OSError:
                pass
        continuity = projects.chronological_scene_context(proj, target)
        try:
            mid, _ = await asyncio.to_thread(
                media.generate_image,
                sentence,
                proj.get("style_key") or proj.get("style") or media.DEFAULT_STYLE_KEY,
                "4:3",
                refs,
                continuity,
            )
            projects.update_panel_media(proj, panel_number, mid, "done", sandbox=self.test_mode)
            self.log.add("book_panel_drawn", project=proj["id"], panel=panel_number, id=mid)
            await self.ui({"type": "item", "item": projects.project_ui_payload(proj)})
            self.silent_context.append(f'[Book Panel {panel_number} rendered on screen for: "{sentence[:140]}"]')
        except Exception as e:
            projects.update_panel_media(proj, panel_number, None, "failed", sandbox=self.test_mode)
            await self.ui({"type": "item", "item": projects.project_ui_payload(proj)})
            self.log.add("error", where="draw_project_panel", error=str(e))
        await self._maybe_prompt_art_check(target)

    async def _draw_spine_beat(self, proj: dict[str, Any], beat: str, sentence: str) -> None:
        """Immediately renders Cover / Story Spine artwork with strictly chronological setting context (never leaking future Finale locations!)."""
        target = f"spine:{beat}"
        refs = []
        for mid in projects.recent_reference_media_ids(proj, limit=2, target=target):
            try:
                refs.append(media.media_path(mid).read_bytes())
            except OSError:
                pass
        continuity = projects.chronological_scene_context(proj, target)
        try:
            mid, _ = await asyncio.to_thread(
                media.generate_image,
                sentence,
                proj.get("style_key") or proj.get("style") or media.DEFAULT_STYLE_KEY,
                "4:3",
                refs,
                continuity,
            )
            projects.update_spine_media(proj, beat, mid, "done", sandbox=self.test_mode)
            self.log.add("spine_art_drawn", project=proj["id"], beat=beat, id=mid)
            await self.ui({"type": "item", "item": projects.project_ui_payload(proj)})
        except Exception as e:
            projects.update_spine_media(proj, beat, None, "failed", sandbox=self.test_mode)
            await self.ui({"type": "item", "item": projects.project_ui_payload(proj)})
            self.log.add("error", where="draw_spine_beat", error=str(e))
        await self._maybe_prompt_art_check(target)

    async def _draw_codex_sketch(self, proj: dict[str, Any], prompt_txt: str) -> None:
        """Renders an immediate blueprint field sketch as soon as the Codex Reading Inference Check locks in!"""
        try:
            mid, _ = await asyncio.to_thread(
                media.generate_image,
                prompt_txt,
                "clean blueprint technical field sketch on dark parchment, crisp ink lines",
                "4:3",
            )
            projects.update_codex_sketch(proj, mid, "done", sandbox=self.test_mode)
            await self.ui({"type": "item", "item": projects.project_ui_payload(proj)})
        except Exception as e:
            projects.update_codex_sketch(proj, None, "failed", sandbox=self.test_mode)
            await self.ui({"type": "item", "item": projects.project_ui_payload(proj)})
            self.log.add("error", where="draw_codex_sketch", error=str(e))

    async def from_kid(self, payload: str, directive: str, image: bytes | None = None, spoken_fallback: str = "") -> None:
        prefix = ""
        if not self.first_input_sent:
            self.first_input_sent = True
            prefix = self.opening() + "\n"
        notes = ""
        if self.silent_context:
            notes = "\n" + "\n".join(self.silent_context[-3:])
            self.silent_context.clear()
        self.kid_turn_id += 1
        self.spoke_since_kid = False
        fb = spoken_fallback or ((self.ctrl.last_coach or {}).get("kid_words") or "")
        full = (
            f"{prefix}{payload}{notes}\n"
            f"[TURN PLAN — Warm reactions to his story ('Oh no, poor guy!', 'Super stinky!') are great, but NEVER use babyish metaphors for writing rules ('little dot', 'big like a superhero'—just say 'capital' and 'period' directly), and NEVER suggest plot ideas. Follow strictly in 1-2 short sentences: {directive}]"
        )
        await self._send_content(full, image, spoken_fallback=fb)

    async def notify(self, text: str, image: bytes | None = None) -> None:
        """Used only for major async completions (e.g. a live HTML5 game finished building)."""
        if self.tutor_busy:
            self.pending.append((text, image))
        else:
            await self._send_content(text, image)

    async def flush_pending(self) -> None:
        if not self.pending:
            return
        items, self.pending = self.pending, []
        text = "\n".join(t for t, _ in items)
        image = next((img for _, img in reversed(items) if img), None)
        await self._send_content(text, image)

    async def trigger_protective_bug(self, alert: dict[str, Any]) -> None:
        """Calmly freezes the child's session behind a believable 'App Bug' screen so a parent checks `/parent`."""
        self.log.add("protective_bug_stop", category=alert.get("category"), reason=alert.get("reason"))
        await self.ui({"type": "tutor_mic", "action": "off"})
        await self.ui({"type": "protective_bug", "code": alert.get("code") or "ERR-G42"})
        self.closed = True
        for t in list(self.bg):
            if t is not asyncio.current_task():
                t.cancel()
        if self.live:
            try:
                await self.live.close()
            except Exception:
                pass

    async def _watch_turn_bg(self, kid_text: str, tutor_text: str = "") -> None:
        try:
            ctx = self.recent_exchange(6)
            res = await asyncio.to_thread(
                guardian.watch_exchange,
                self.id,
                self.rec,
                kid_text,
                tutor_text,
                ctx,
                self.test_mode,
            )
            if not self.test_mode:
                LIVE.setdefault(self.id, {})["guardian"] = res
            if res.get("level") == "nervous_stop":
                await self.trigger_protective_bug(res)
        except Exception as e:
            self.log.add("error", where="guardian_watch", error=str(e))

    def _flush_kid(self) -> None:
        spoken = _clean_transcript(self.kid_raw_buf).strip()
        if spoken:
            self.log.add("kid_said", text=spoken)
            inst = guardian.instant_screen(self.id, spoken, sandbox=self.test_mode)
            if inst:
                self.spawn(self.trigger_protective_bug(inst))
                self.kid_raw_buf = ""
                self.kid_buf = ""
                return
            self.kid_events += 1
            self.kid_turn_id += 1
            self.spoke_since_kid = False
            plan = self.ctrl.classify_and_advance(spoken, "spoken", chk=None, opening_ideas=self.opening_ideas)
            self.log.add("ctrl_plan", how="spoken", input_class=plan["kind"], phase=self.ctrl.phase, rung=self.ctrl.rung)
            self.spawn(self.apply_controller_ui(plan["ui"]))
            self.spawn(self._watch_turn_bg(spoken, plan.get("spoken_fallback", "")))
        self.kid_raw_buf = ""
        self.kid_buf = ""

    def _flush_tutor(self) -> bool:
        cleaned = _clean_transcript(self.tutor_raw_buf).strip()
        self.tutor_raw_buf = ""
        self.tutor_buf = ""
        if cleaned:
            self.log.add("tutor_said", text=cleaned)
            # Watch the AI's own spoken output as well!
            self.spawn(self._watch_turn_bg(self.ctrl.last_kid_text, cleaned))
            return True
        return False

    def _log_coach(self) -> None:
        d = self.ctrl.last_coach
        if not d:
            return
        self.log.add(
            "coach",
            accept=d.get("accept"),
            focus=d.get("focus"),
            focus_word=d.get("focus_word"),
            spell_rung=d.get("spell_rung"),
            scaffold=d.get("scaffold"),
            next_scaffold=d.get("next_scaffold"),
            today_state=d.get("today_state"),
            kid_words=d.get("kid_words"),
            rationale=d.get("rationale"),
            guardrail=d.get("guardrail"),
            deferred=d.get("deferred"),
            latency_s=d.get("latency_s"),
        )
        if not self.test_mode:
            LIVE.setdefault(self.id, {})["coach"] = {
                "today_state": d.get("today_state"),
                "last": {k: d.get(k) for k in ("accept", "focus", "rationale", "guardrail")},
                "pushed": self.ctrl.coach_session.get("pushed", 0),
                "deferred": self.ctrl.coach_session.get("deferred", 0),
            }

    def page_text(self) -> str:
        return "\n".join(s["text"] for s in self.page)

    # ---------- Live config ----------

    def live_config(self) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=build_system_prompt(self.rec, list_activities()),
            tools=_tool_declarations(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.rec.get("voice") or "Umbriel")
                )
            ),
            session_resumption=types.SessionResumptionConfig(handle=self.resume_handle),
            context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()),
        )

    # ---------- main loop ----------

    async def run(self) -> None:
        existing_lock = guardian.get_bug_lock(sandbox=self.test_mode)
        if existing_lock:
            await self.trigger_protective_bug(existing_lock)
            return
        key = api_key()
        if not key:
            await self.ui({"type": "error", "message": "No Gemini API key yet. Add it on the parent page."})
            return
        client = genai_client(live=True)
        model_candidates = list(dict.fromkeys(LIVE_FALLBACK_MODELS))
        model_idx = 0
        active_live_model = model_candidates[0]
        self.log.add("session_start", learner=self.name, model=active_live_model, voice=self.rec.get("voice"), test_mode=self.test_mode)
        reader = asyncio.create_task(self.read_browser())
        self.spawn(self.observe_loop())
        if not self.test_mode:
            LIVE[self.id] = {"updated": now_iso(), "minutes": 0, "tracker": {}, "critic": {}, "stats": {}, "mechanic": ""}
        attempts = 0
        try:
            while not self.closed and attempts < 6:
                active_live_model = model_candidates[min(model_idx, len(model_candidates) - 1)]
                try:
                    async with client.aio.live.connect(model=active_live_model, config=self.live_config()) as live:
                        self.live = live
                        attempts = 0
                        self.ready.set()
                        await self.ui({"type": "ready", "session_id": self.id, "model": active_live_model})
                        reconnect = await self.read_live()
                        self.ready.clear()
                        self.live = None
                        if not reconnect:
                            break
                except Exception as e:
                    self.ready.clear()
                    self.live = None
                    err_s = str(e)
                    self.log.add("error", where="live", model=active_live_model, error=err_s)
                    blackboard.QUOTA.note_error("live_connect", err_s)
                    if any(k in err_s.lower() for k in ("404", "not found", "not supported", "429", "quota", "resource_exhausted", "1011")) and model_idx + 1 < len(model_candidates):
                        model_idx += 1
                        continue
                    attempts += 1
                    if self.closed:
                        break
                    short_err = err_s.splitlines()[0][:140]
                    if attempts >= 2:
                        await self.ui({"type": "error", "message": f"Gemini connection issue ({short_err}). Retrying…"})
                    else:
                        await self.ui({"type": "status", "message": "Reconnecting to Gemini…"})
                    await asyncio.sleep(min(2 * attempts, 6))
        finally:
            reader.cancel()
            for t in list(self.bg):
                t.cancel()
            self._flush_kid()
            self._flush_tutor()
            self.ctrl._save_current_if_needed()
            self.log.add("writing_stats", stats=self.stats.as_dict())
            self.log.add("session_end", minutes=round((time.time() - self.started) / 60, 1), page=self.page_text())
            if not self.test_mode:
                if self.id in LIVE:
                    LIVE[self.id]["ended"] = True
                rec = load_learner()
                if self.rec.get("spelling_deck"):
                    rec["spelling_deck"] = self.rec["spelling_deck"]
                rc = curriculum_tracker.ensure_report_card(rec)
                evs = read_session(self.id, test_mode=False)
                wchecks = [e for e in evs if e.get("kind") == "writing_check"]
                had_spine = bool(self.ctrl.project and (self.ctrl.project.get("spine") or {}).get("beginning"))
                curriculum_tracker.update_from_session_deterministic(
                    rc,
                    wchecks,
                    self.stats.as_dict(),
                    had_spine=had_spine,
                    had_revision=self.ctrl.had_revision,
                    had_inference=self.ctrl.had_inference,
                    had_synthesis=self.ctrl.had_synthesis,
                    words_studied=len(self.ctrl.studied_words_today),
                )
                rec.setdefault("sessions", []).append(
                    {
                        "id": self.id,
                        "date": now_iso(),
                        "minutes": round((time.time() - self.started) / 60, 1),
                        "project_id": self.ctrl.project["id"] if self.ctrl.project else None,
                        "reviewed": False,
                    }
                )
                save_learner(rec)

    async def read_browser(self) -> None:
        try:
            while True:
                msg = await self.ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    if self.live:
                        try:
                            async with self.send_lock:
                                await self.live.send_realtime_input(
                                    audio=types.Blob(data=msg["bytes"], mime_type="audio/pcm;rate=16000")
                                )
                        except Exception:
                            pass
                    continue
                if msg.get("text"):
                    try:
                        await self.handle_browser(json.loads(msg["text"]))
                    except Exception:
                        self.log.add("error", where="browser_msg", error=traceback.format_exc()[-600:])
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self.closed = True
            if self.live:
                try:
                    await self.live.close()
                except Exception:
                    pass

    async def handle_browser(self, m: dict[str, Any]) -> None:
        kind = m.get("type")

        if kind == "text":
            text = (m.get("text") or "").strip()
            if not text:
                return
            inst = guardian.instant_screen(self.id, text, sandbox=self.test_mode)
            if inst:
                self.log.add("kid_typed", text=text)
                await self.trigger_protective_bug(inst)
                return
            secs = round((m.get("ms") or 0) / 1000, 1)
            bs = m.get("backspaces", 0)
            target = self.input_target
            self.input_target = None
            self.kid_events += 1

            self.log.add("kid_typed", text=text, seconds=secs, backspaces=bs, target=target)
            self.ctrl.turn_signals = {"secs": secs, "backspaces": bs, "how": "typed"}
            try:
                plan = await asyncio.wait_for(
                    asyncio.to_thread(self.ctrl.classify_and_advance, text, "typed", None, self.opening_ideas),
                    timeout=4.5,
                )
            except asyncio.TimeoutError:
                chk_fb = blackboard.local_check_writing(text)
                plan = await asyncio.to_thread(self.ctrl.classify_and_advance, text, "typed", chk_fb, self.opening_ideas)

            chk_used = ((self.ctrl.coach_session.get("last_request") or {}).get("chk")) or blackboard.local_check_writing(text)
            check_note = self._record_check_stats(text, "typed", secs, chk_used)
            self.log.add("ctrl_plan", how="typed", input_class=plan["kind"], phase=self.ctrl.phase, rung=self.ctrl.rung)
            self._log_coach()
            await self.apply_controller_ui(plan["ui"], epoch=plan.get("epoch"))
            render_note = ""
            if plan.get("redraw_art"):
                render_note = await self._run_redraw_art(plan["redraw_art"])
            elif plan.get("spine_draw") and self.ctrl.project:
                sd = plan["spine_draw"]
                self.spawn(self._draw_spine_beat(self.ctrl.project, sd["beat"], sd["text"]))
                render_note = " (Story Spine / Cover illustration is already rendering on the right—do NOT call draw.)"
            elif plan.get("codex_sketch") and self.ctrl.project:
                self.spawn(self._draw_codex_sketch(self.ctrl.project, plan["codex_sketch"]))
                render_note = " (Specimen Blueprint Sketch is already rendering on the right—do NOT call draw.)"
            elif plan["kind"] == "COMPLETE_SENTENCE":
                final_txt = plan.get("full_paragraph") or plan.get("repaired_text") or text
                await self.apply_target(target, final_txt, "typed")
                render_note = await self.auto_render_sentence(final_txt)
            self.spawn(self._watch_turn_bg(text, plan.get("spoken_fallback", "")))
            await self.from_kid(
                f'[{self.name} typed ({secs}s, {bs} backspaces): "{text}"]{check_note}',
                plan["directive"] + render_note,
                spoken_fallback=plan.get("spoken_fallback", ""),
            )

        elif kind == "pen":
            png = base64.b64decode((m.get("png_b64") or "").split(",", 1)[-1])
            target = self.input_target
            self.input_target = None
            self.kid_events += 1
            mid = new_id("pen")
            media.media_path(mid).write_bytes(media._to_jpeg(png, 900))
            skip_lchk = self.ctrl.handwriting_fix_tries > 0
            try:
                res = await asyncio.to_thread(media.read_handwriting, png, m.get("prompt") or "", skip_lchk)
            except Exception as e:
                res = {"text": "", "legible": False, "letter_issue": None, "error": str(e)}
            text = (res.get("text") or "").strip()
            letter_issue = res.get("letter_issue") if isinstance(res.get("letter_issue"), dict) else None
            self.log.add("kid_wrote", text=text, legible=res.get("legible"), letter_issue=letter_issue, image=mid, target=target)
            inst_pen = guardian.instant_screen(self.id, text, sandbox=self.test_mode)
            if inst_pen:
                await self.trigger_protective_bug(inst_pen)
                return
            await self.ui({"type": "kid_pen", "text": text, "image": f"/media/{mid}.jpg"})
            chk, check_note = await self.check(text, "handwritten") if (text and not letter_issue) else ({}, "")
            self.ctrl.turn_signals = {"how": "handwritten"}
            plan = await asyncio.to_thread(
                self.ctrl.classify_and_advance, text or "?", "handwritten", chk, self.opening_ideas, letter_issue
            )
            self.log.add("ctrl_plan", how="pen", input_class=plan["kind"], phase=self.ctrl.phase, rung=self.ctrl.rung)
            self._log_coach()
            await self.apply_controller_ui(plan["ui"], epoch=plan.get("epoch"))
            render_note = ""
            if plan.get("redraw_art"):
                render_note = await self._run_redraw_art(plan["redraw_art"])
            elif plan.get("spine_draw") and self.ctrl.project:
                sd = plan["spine_draw"]
                self.spawn(self._draw_spine_beat(self.ctrl.project, sd["beat"], sd["text"]))
                render_note = " (Story Spine / Cover illustration is already rendering on the right—do NOT call draw.)"
            elif plan.get("codex_sketch") and self.ctrl.project:
                self.spawn(self._draw_codex_sketch(self.ctrl.project, plan["codex_sketch"]))
                render_note = " (Specimen Blueprint Sketch is already rendering on the right—do NOT call draw.)"
            elif text and plan["kind"] == "COMPLETE_SENTENCE":
                final_txt = plan.get("full_paragraph") or plan.get("repaired_text") or text
                await self.apply_target(target, final_txt, "handwritten")
                render_note = await self.auto_render_sentence(final_txt)
            if text:
                self.spawn(self._watch_turn_bg(text, plan.get("spoken_fallback", "")))
            await self.from_kid(
                f'[{self.name} handwrote: "{text}" (legible: {res.get("legible")}).]{check_note}',
                plan["directive"] + render_note,
                png,
                spoken_fallback=plan.get("spoken_fallback", ""),
            )

        elif kind == "set_style":
            skey = str(m.get("style_key") or "").strip()
            if self.ctrl.project and projects.set_project_style(self.ctrl.project, skey, sandbox=self.test_mode):
                sp = self.ctrl.project.get("spine") or {}
                if sp.get("beginning") and projects.total_panels(self.ctrl.project) == 0:
                    sp["beginning_status"] = "drawing"
                    await self.ui({"type": "item", "item": projects.project_ui_payload(self.ctrl.project)})
                    self.spawn(self._draw_spine_beat(self.ctrl.project, "beginning", sp["beginning"]))
                else:
                    await self.ui({"type": "item", "item": projects.project_ui_payload(self.ctrl.project)})
            if self.comic and skey in media.STYLE_BY_KEY:
                self.comic["style"] = media.resolve_style_prompt(skey)

        elif kind == "open_project":
            pid = str(m.get("id") or "").strip()
            proj = projects.load_project(pid)
            if not proj:
                return
            self.kid_events += 1
            ui_acts, directive = await asyncio.to_thread(self.ctrl.resume_loaded_project, proj)
            await self.apply_controller_ui(ui_acts)
            await self.from_kid(f'[{self.name} switched to saved book "{proj.get("title")}" ({projects.total_panels(proj)} panels)]', directive)

        elif kind == "new_project":
            pkind = str(m.get("kind") or "epic_graphic_novel").strip()
            ptitle = str(m.get("title") or "").strip()
            self.kid_events += 1
            self.log.add("kid_tapped", value=f"new_project:{pkind}", prompt=ptitle)
            ui_acts, directive = await asyncio.to_thread(self.ctrl.create_or_switch_project, pkind, ptitle)
            await self.apply_controller_ui(ui_acts)
            await self.from_kid(f'[{self.name} saved previous work and started a brand-new {pkind} project{f" titled {ptitle!r}" if ptitle else ""}]', directive)

        elif kind == "rename_project":
            pid = str(m.get("id") or "").strip()
            ptitle = str(m.get("title") or "").strip()
            if self.ctrl.project and self.ctrl.project.get("id") == pid and ptitle:
                self.ctrl.project["title"] = ptitle[:80]
                self.ctrl.project["custom_titled"] = True
                projects.save_project(self.ctrl.project, sandbox=self.test_mode)
                await self.ui({"type": "item", "item": projects.project_ui_payload(self.ctrl.project)})
            else:
                projects.rename_project(pid, ptitle)

        elif kind == "open_activity_saved":
            aid = str(m.get("id") or "").strip()
            act = load_activity(aid)
            if not act:
                return
            self.ctrl._save_current_if_needed()
            self.ctrl.project = None
            self.activity = dict(act)
            await self.ui({"type": "item", "item": {"id": "activity", "kind": "activity", "title": act.get("title", "Game"), "html": act["html"]}})
            await self.from_kid(
                f'[{self.name} reopened saved mini-game "{act.get("title")}"]',
                "Invite typing the first complete sentence inside the reopened game in 1 short sentence.",
            )

        elif kind == "art_feedback":
            if not self.ctrl.project:
                return
            art_target = str(m.get("target") or "").strip()
            if not art_target:
                return
            self.kid_events += 1
            if m.get("remove"):
                removed = projects.remove_art_beat(self.ctrl.project, art_target, sandbox=self.test_mode)
                await self.ui({"type": "item", "item": projects.project_ui_payload(self.ctrl.project)})
                if removed:
                    await self.from_kid(
                        f'[{self.name} removed beat {art_target}: "{removed[:80]}"]',
                        "Confirm in 1 short sentence that you removed that beat cleanly and ask what happens instead.",
                        spoken_fallback="Got it—I removed that part cleanly! What happens next instead?",
                    )
                return
            if m.get("ok"):
                projects.mark_art_verified(self.ctrl.project, art_target, sandbox=self.test_mode)
                if self.ctrl.phase == "AWAITING_ART_CHECK" and self.ctrl.pending_art_target == art_target:
                    plan = self.ctrl._continue_after_art_approved([])
                    await self.apply_controller_ui(plan["ui"], epoch=self.ctrl.blackboard.bump_epoch())
                    await self.from_kid(f'[{self.name} approved picture {art_target}]', plan["directive"])
                else:
                    await self.ui({"type": "item", "item": projects.project_ui_payload(self.ctrl.project)})
                return
            plan = self.ctrl.start_fix_art_prompt(art_target)
            await self.apply_controller_ui(plan["ui"], epoch=plan.get("epoch"))
            await self.from_kid(
                f'[{self.name} asked to fix picture {art_target}]',
                plan["directive"],
                spoken_fallback=plan.get("spoken_fallback", ""),
            )

        elif kind == "request_dialogue_mic":
            target_m = str(m.get("target") or "").strip()
            if not target_m:
                return
            self.ctrl.active_mic_request = {"purpose": f"dialogue:{target_m}", "sentence": ""}
            await self.ui(
                {
                    "type": "tutor_mic",
                    "action": "on",
                    "purpose": f"dialogue:{target_m}",
                    "target_word": "",
                    "sentence": "",
                    "prompt": "Say out loud what the speech bubble should say!",
                }
            )

        elif kind == "comic_lettering":
            target_l = str(m.get("target") or "").strip()
            action_l = str(m.get("action") or "").strip()
            if not target_l or action_l not in ("add_bubble", "edit_bubble", "delete_bubble", "move_bubble", "set_caption"):
                return
            raw_check_txt = " ".join(str(m.get(k) or "") for k in ("speaker", "text", "caption")).strip()
            if raw_check_txt:
                inst_l = guardian.instant_screen(self.id, raw_check_txt, sandbox=self.test_mode)
                if inst_l:
                    self.log.add("kid_typed", text=raw_check_txt, target=target_l)
                    await self.trigger_protective_bug(inst_l)
                    return

            if action_l in ("add_bubble", "edit_bubble", "set_caption") and not m.get("force"):
                mode_l = "caption" if action_l == "set_caption" else "bubble"
                field_txt = str(m.get("caption") if mode_l == "caption" else m.get("text") or "").strip()
                bkind_l = str(m.get("kind") or "speech").strip().lower()
                tries_key = f"{target_l}:{mode_l}"
                tries_n = self.lettering_tries.get(tries_key, 0)
                if mode_l == "bubble" or field_txt:
                    vchk = await asyncio.to_thread(self.ctrl.validate_comic_lettering, field_txt, mode_l, bkind_l, tries_n)
                    if not vchk.get("ok"):
                        self.lettering_tries[tries_key] = tries_n + 1
                        await self.ui({"type": "comic_lettering_fix", "target": target_l, "mode": mode_l, "fix": vchk})
                        return
                self.lettering_tries[tries_key] = 0

            updated_ok = False
            if (target_l.startswith("spine:") or target_l.startswith("panel:")) and self.ctrl.project:
                updated_ok = projects.apply_comic_lettering(self.ctrl.project, target_l, action_l, m, sandbox=self.test_mode)
                if updated_ok:
                    await self.ui({"type": "item", "item": projects.project_ui_payload(self.ctrl.project)})
            elif target_l.startswith("strip:") and self.comic:
                try:
                    s_idx = int(target_l.split(":", 1)[1])
                except ValueError:
                    s_idx = -1
                if 0 <= s_idx < len(self.comic.get("panels") or []):
                    updated_ok = projects.mutate_lettering_holder(self.comic["panels"][s_idx], action_l, m)
                    if updated_ok:
                        await self.push_comic()
            elif target_l.startswith("draw:"):
                d_id = target_l.split(":", 1)[1]
                d_item = self.drawn_items.get(d_id)
                if d_item:
                    updated_ok = projects.mutate_lettering_holder(d_item, action_l, m)
                    if updated_ok:
                        await self.ui({"type": "item", "item": d_item})

            if updated_ok and action_l != "move_bubble":
                self.log.add("comic_lettering", target=target_l, action=action_l)
                if raw_check_txt and action_l in ("add_bubble", "edit_bubble", "set_caption"):
                    self.spawn(self._watch_turn_bg(raw_check_txt, ""))
                await self.ui({"type": "comic_lettering_saved", "target": target_l, "action": action_l})

        elif kind == "tap":
            val = str(m.get("value") or "").strip()
            if not val:
                return
            self.kid_events += 1
            self.log.add("kid_tapped", value=val, prompt=m.get("prompt"))
            plan = await asyncio.to_thread(
                self.ctrl.classify_and_advance, val, "tap", None, self.opening_ideas
            )
            self.log.add("ctrl_plan", how="tap", input_class=plan["kind"], phase=self.ctrl.phase, rung=self.ctrl.rung)
            await self.apply_controller_ui(plan["ui"], epoch=plan.get("epoch"))
            render_note = ""
            if plan.get("redraw_art"):
                render_note = await self._run_redraw_art(plan["redraw_art"])
            elif plan.get("spine_draw") and self.ctrl.project:
                sd = plan["spine_draw"]
                self.spawn(self._draw_spine_beat(self.ctrl.project, sd["beat"], sd["text"]))
                render_note = " (Story Spine / Cover illustration is already rendering on the right—do NOT call draw.)"
            elif plan.get("codex_sketch") and self.ctrl.project:
                self.spawn(self._draw_codex_sketch(self.ctrl.project, plan["codex_sketch"]))
                render_note = " (Specimen Blueprint Sketch is already rendering on the right—do NOT call draw.)"
            elif plan["kind"] == "COMPLETE_SENTENCE":
                final_txt = plan.get("full_paragraph") or plan.get("repaired_text") or val
                await self.apply_target(self.input_target, final_txt, "typed")
                render_note = await self.auto_render_sentence(final_txt)
            await self.from_kid(
                f'[{self.name} tapped choice: "{val}"]',
                plan["directive"] + render_note,
                spoken_fallback=plan.get("spoken_fallback", ""),
            )

        elif kind == "activity_event":
            data = m.get("data")
            self.log.add("activity_event", data=data)
            if self.activity is not None and isinstance(data, dict) and data.get("kind") == "ready" and data.get("summary"):
                self.activity["summary"] = str(data["summary"])[:300]
                save_activity({"id": self.activity["id"], "summary": self.activity["summary"]}, sandbox=self.test_mode)
            if isinstance(data, dict) and data.get("typed"):
                sub = str(data["typed"]).strip()
                if sub:
                    chk, check_note = await self.check(sub, "typed", 0.0)
                    plan = await asyncio.to_thread(
                        self.ctrl.classify_and_advance, sub, "typed", chk, self.opening_ideas
                    )
                    await self.ui({"type": "goal", "text": self.ctrl.goal_badge()})
                    await self.notify(
                        f'[In game "{self.activity.get("title","") if self.activity else "Game"}", {self.name} submitted: "{sub}"]{check_note}\n'
                        f'[TURN PLAN: {plan["directive"]}]'
                    )
                    return
            important = isinstance(data, dict) and data.get("kind") in ("done", "finished", "quit")
            now = time.time()
            if important and now - self.last_activity_event > 4:
                self.last_activity_event = now
                await self.notify(f"[Activity finished: {json.dumps(data, ensure_ascii=False)[:400]}]")

        elif kind == "activity_error":
            self.log.add("activity_error", error=m.get("data"))
            await self.notify(f"[The game on screen hit a bug: {str(m.get('data'))[:200]}. Consider change_activity to fix it.]")

        elif kind == "app_note":
            await self.notify(f"[{m.get('text', '')}]")

        elif kind == "voice_clip":
            await self.ui({"type": "tutor_mic", "action": "off"})
            b64 = (m.get("wav_b64") or "").split(",", 1)[-1]
            if not b64:
                return
            wav_bytes = base64.b64decode(b64)
            purpose = str(m.get("purpose") or "word").strip()
            tword = str(m.get("target_word") or "").strip()
            sctx = str(m.get("sentence") or self.ctrl.spine_summary() or "").strip()
            try:
                res = await asyncio.wait_for(
                    asyncio.to_thread(media.transcribe_voice_clip, wav_bytes, purpose, tword, sctx),
                    timeout=5.5,
                )
            except Exception as e:
                self.log.add("error", where="voice_clip", error=str(e))
                res = {"transcript": "", "intended_word": ""}
            transcript = (res.get("transcript") or "").strip()
            intended = (res.get("intended_word") or "").strip()
            if not transcript and not intended:
                await self.ui({"type": "status", "message": "Didn't hear anything clearly—you can type it in the box below (or tap 'Say the word out loud' to try again)."})
                return
            shown = intended if (purpose == "word" and intended and not transcript) else (transcript or intended)
            inst_vc = guardian.instant_screen(self.id, f"{transcript} {intended}".strip(), sandbox=self.test_mode)
            if inst_vc:
                self.log.add("kid_said", text=shown, purpose=purpose)
                await self.trigger_protective_bug(inst_vc)
                return
            self.kid_events += 1
            self.turn += 1
            self.log.add("kid_said", text=shown, intended_word=intended, purpose=purpose)
            await self.ui({"type": "kid_caption", "turn": self.turn, "text": f"🎤 {shown}"})
            plan = await asyncio.to_thread(self.ctrl.handle_voice_clip_result, transcript, intended, purpose)
            self.log.add("ctrl_plan", how="voice_clip", input_class=plan["kind"], phase=self.ctrl.phase, rung=self.ctrl.rung)
            await self.apply_controller_ui(plan["ui"], epoch=plan.get("epoch"))
            render_note = ""
            if plan.get("redraw_art"):
                render_note = await self._run_redraw_art(plan["redraw_art"])
            self.spawn(self._watch_turn_bg(shown, plan.get("spoken_fallback", "")))
            await self.from_kid(
                f'[{self.name} spoke into the green mic ({purpose}): "{shown}"' + (f' -> intended word "{intended}"' if intended else "") + "]",
                plan["directive"] + render_note,
                spoken_fallback=plan.get("spoken_fallback", ""),
            )

        elif kind == "mic_paused":
            if self.live:
                try:
                    async with self.send_lock:
                        await self.live.send_realtime_input(audio_stream_end=True)
                except Exception:
                    pass

        elif kind == "mic_started":
            if not self.first_input_sent:
                self.first_input_sent = True
                self.silent_context.append(self.opening())

        elif kind == "end":
            self.closed = True

    # ---------- writing check + observers ----------

    def _record_check_stats(self, text: str, how: str, seconds: float, chk: dict[str, Any]) -> str:
        words = set(re.findall(r"[a-z']+", text.lower()))
        prev = self.last_flawed_words
        first_try = not (prev and words and len(words & prev) / max(1, len(prev)) >= 0.5)
        self.stats.add(text, chk, how, seconds, first_try=first_try)
        has_issue = (
            any(
                s.get("issue") not in ("none", "not_a_sentence_attempt", None)
                or s.get("capital_ok") is False
                or s.get("end_ok") is False
                for s in (chk.get("sentences") or [])
            )
            or bool(chk.get("misspellings"))
            or bool(chk.get("grammar_fixes"))
        )
        self.last_flawed_words = words if has_issue else set()
        self.log.add("writing_check", text=text, how=how, first_try=first_try, check=chk)
        if not self.test_mode:
            LIVE.setdefault(self.id, {})["stats"] = self.stats.as_dict()
        summary = thinking.summarize_check(chk)
        self.last_check_note = summary
        return f" [check: {summary}]" if summary else ""

    async def check(self, text: str, how: str, seconds: float = 0.0) -> tuple[dict[str, Any], str]:
        """Precise syntactic & orthographic check of what he wrote."""
        try:
            chk = await asyncio.wait_for(asyncio.to_thread(thinking.check_writing, text), timeout=3.8)
        except Exception:
            chk = blackboard.local_check_writing(text)
        return chk, self._record_check_stats(text, how, seconds, chk)

    def mechanic_desc(self) -> str:
        bits = [f"Goal: {self.ctrl.goal_badge()} | Rung: {self.ctrl.rung} | Phase: {self.ctrl.phase}"]
        if self.ctrl.project:
            pr = self.ctrl.project
            bits.append(
                f"Book Project '{pr.get('title')}' ({pr.get('kind')}, stage={pr.get('stage')}, {projects.total_panels(pr)} panels):\n"
                f"{self.ctrl.spine_summary()}"
            )
        if self.current_card:
            bits.append(f"Active card on screen ('{self.current_card.get('title')}'):\n{self.current_card.get('text','')[:400]}")
        if self.ctrl.phase == "WORD_STUDY" and self.ctrl.word_target:
            bits.append(f"Word study card on screen: {self.ctrl.word_target.get('word')} ({self.ctrl.word_target.get('parts')})")
        if self.activity:
            bits.append(f"Game on screen: {self.activity.get('title')} — {self.activity.get('description','')[:400]}")
        if self.comic:
            filled = sum(1 for p in self.comic["panels"] if p.get("image"))
            caps = [p.get("caption") for p in self.comic["panels"] if p.get("caption")]
            bits.append(f"Comic '{self.comic.get('title')}': {filled}/{len(self.comic['panels'])} panels drawn; captions: {caps}")
        if self.page:
            bits.append(f"Writing page: {self.page_text()[:400]}")
        return "\n".join(bits)

    def recent_window(self, seconds: float = 240) -> str:
        from .review import _transcript

        events = read_session(self.id, test_mode=self.test_mode)
        if not events:
            return ""
        cutoff = events[-1].get("t", 0) - seconds
        recent = [e for e in events if e.get("t", 0) >= cutoff and e.get("kind") not in ("tracker", "critic")]
        return _transcript(recent, self.name)

    async def observe_loop(self) -> None:
        await asyncio.sleep(20)
        while not self.closed:
            try:
                if self.kid_events > self.observed_at_events:
                    self.observed_at_events = self.kid_events
                    await self.observe_once()
            except Exception as e:
                self.log.add("error", where="observe", error=str(e))
            await asyncio.sleep(25)

    async def observe_once(self) -> None:
        if not blackboard.QUOTA.allow_background():
            return
        window = self.recent_window()
        if not window:
            return
        stats = self.stats.as_dict()
        tracker, critic = await asyncio.gather(
            asyncio.to_thread(observers.track, window, stats, self.tracker_state),
            asyncio.to_thread(observers.critique, window, self.mechanic_desc(), stats, self.tracker_state),
        )
        if tracker:
            self.tracker_state = tracker
        if critic:
            self.critic_state = critic
        self.log.add("tracker", state=self.tracker_state)
        self.log.add("critic", state=self.critic_state)
        if not self.test_mode:
            LIVE[self.id] = {
                **LIVE.get(self.id, {}),
                "updated": now_iso(),
                "minutes": round((time.time() - self.started) / 60, 1),
                "tracker": self.tracker_state,
                "critic": self.critic_state,
                "stats": stats,
                "mechanic": self.mechanic_desc(),
            }
        verdict = self.critic_state.get("verdict", "on_track")
        if verdict != "on_track" and self.critic_state.get("advice"):
            self.silent_context.append(f"[Critic advice: {self.critic_state['advice']}]")

    async def _invent(self, situation: str, focus: str) -> None:
        try:
            out = await asyncio.to_thread(thinking.invent, situation, focus, self.rec, self.tried[-8:])
            ideas = out.get("ideas", [])[:3]
            self.opening_ideas = ideas or self.opening_ideas
            self.log.add("ideas", situation=situation, focus=focus, ideas=ideas)
            if not self.test_mode:
                LIVE.setdefault(self.id, {})["ideas"] = ideas
            if ideas:
                names = ", ".join(f"{i.get('name')} ({i.get('pitch')})" for i in ideas)
                self.silent_context.append(f"[Fresh vetted mechanics ready if switching: {names}]")
        finally:
            self.inventing = False

    async def apply_target(self, target: str | None, text: str, how: str) -> None:
        if not target:
            return
        if target == "page":
            self.page.append({"text": text, "author": "kid"})
            await self.ui({"type": "item", "item": {"id": "page", "kind": "page", "segments": self.page}})
        elif target.startswith("comic:") and self.comic:
            try:
                idx = int(target.split(":", 1)[1]) - 1
                if 0 <= idx < len(self.comic["panels"]):
                    self.comic["panels"][idx]["caption"] = text
                    await self.push_comic()
            except ValueError:
                pass

    async def read_live(self) -> bool:
        go_away = False
        while not self.closed:
            try:
                async for msg in self.live.receive():
                    if self.closed:
                        return False
                    if msg.session_resumption_update and msg.session_resumption_update.new_handle:
                        self.resume_handle = msg.session_resumption_update.new_handle
                    if msg.go_away is not None:
                        go_away = True
                    if msg.tool_call:
                        self._flush_kid()
                        await self.handle_tool_calls(msg.tool_call.function_calls or [])
                    sc = msg.server_content
                    if not sc:
                        continue
                    if sc.input_transcription and sc.input_transcription.text:
                        self.kid_raw_buf += sc.input_transcription.text
                        self.kid_buf = _clean_transcript(self.kid_raw_buf)
                        if self.kid_buf.strip():
                            await self.ui({"type": "kid_caption", "turn": self.turn, "text": self.kid_buf.strip()})
                    if sc.model_turn:
                        if not self.tutor_busy:
                            self.tutor_busy = True
                            self._flush_kid()
                            self.turn += 1
                        for p in sc.model_turn.parts or []:
                            if p.inline_data and p.inline_data.data:
                                await self.ui_audio(p.inline_data.data)
                    if sc.output_transcription and sc.output_transcription.text:
                        self.tutor_raw_buf += sc.output_transcription.text
                        cleaned_full = _clean_transcript(self.tutor_raw_buf)
                        if cleaned_full.strip():
                            if not self.tutor_busy:
                                self.tutor_busy = True
                                self._flush_kid()
                                self.turn += 1
                            self.tutor_buf = cleaned_full
                            if len(self.tutor_buf.strip()) > 8:
                                self.spoke_since_kid = True
                            await self.ui({"type": "tutor_caption", "turn": self.turn, "text": self.tutor_buf.strip()})
                    if sc.interrupted:
                        self._flush_tutor()
                        self.tutor_busy = False
                        await self.ui({"type": "interrupted"})
                    if sc.turn_complete:
                        self._flush_kid()
                        had_tutor_speech = self._flush_tutor()
                        self.tutor_busy = False
                        await self.ui({"type": "turn_complete", "kid_turn": self.kid_turn_id})
                        await self.flush_pending()
                        if had_tutor_speech:
                            self.spawn(self.audit_tutor_turn())
            except Exception as e:
                if self.closed:
                    return False
                self.log.add("error", where="receive", error=str(e))
                return True
            if go_away:
                return True
        return False

    # ---------- tools ----------

    async def handle_tool_calls(self, calls: list[Any]) -> None:
        responses = []
        already_spoke = self.spoke_since_kid
        for fc in calls:
            args = dict(fc.args or {})
            gate_block = self.ctrl.gate_tool(fc.name, args)
            if gate_block is not None:
                if already_spoke and gate_block.get("ok"):
                    gate_block = {**gate_block, "stop_speaking": "You ALREADY spoke to the student this turn. End your turn silently now without repeating yourself."}
                self.log.add("tool_gated", name=fc.name, args=args, gate=gate_block)
                responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=gate_block))
                continue
            self.log.add("tool", name=fc.name, args=args)
            try:
                result = await self.run_tool(fc.name, args)
                if already_spoke and isinstance(result, dict):
                    result = {**result, "note_on_speech": "If you ALREADY spoke the next sentence prompt aloud before this tool call, do NOT repeat it; otherwise state it once briefly."}
            except Exception as e:
                result = {"error": str(e)}
                self.log.add("error", where=f"tool:{fc.name}", error=traceback.format_exc()[-800:])
            responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
        if self.live:
            async with self.send_lock:
                await self.live.send_tool_response(function_responses=responses)

    async def push_comic(self) -> None:
        if not self.comic:
            return
        await self.ui({"type": "item", "item": {"id": self.comic["id"], "kind": "comic", **{k: v for k, v in self.comic.items() if k != "id"}}})

    async def run_tool(self, name: str, a: dict[str, Any]) -> dict[str, Any]:
        if name == "invent_ideas":
            if self.inventing:
                return {"status": "Already inventing; ideas will be available shortly."}
            self.inventing = True
            self.spawn(self._invent(a.get("situation", ""), a.get("skill_focus", "")))
            return {"status": "Inventing in the background. Proceed with the current concrete sentence task meanwhile."}

        if name == "draw":
            iid = new_id("draw")
            raw_cap = a.get("caption") or (self.ctrl.active_story[-1] if self.ctrl.active_story else "")
            d_cap, d_bubs = projects.extract_dialogue(raw_cap)
            item = {"id": iid, "kind": "image", "caption": d_cap, "dialogue": d_bubs, "scene": a.get("scene", ""), "status": "drawing"}
            self.drawn_items[iid] = item
            await self.ui({"type": "item", "item": item})
            self.spawn(self._draw(item, a.get("scene", ""), a.get("style", "")))
            return {"status": "Rendering scene on screen (~10s). Continue directly to the next sentence prompt without waiting."}

        if name == "comic_new":
            try:
                n = max(2, min(6, int(str(a.get("panels", "3")).strip())))
            except ValueError:
                n = 3
            self.comic = {
                "id": new_id("comic"),
                "title": a.get("title", "Untitled Comic"),
                "style": a.get("style") or media.DEFAULT_STYLE_KEY,
                "characters": a.get("characters", ""),
                "panels": [{"caption": "", "dialogue": [], "scene": "", "image": None, "status": "empty"} for _ in range(n)],
            }
            self.tried.append(f"comic: {a.get('title', '')}")
            await self.ui({"type": "goal", "text": self.ctrl.goal_badge()})
            await self.push_comic()
            return {"ok": True, "panels": n}

        if name == "comic_panel":
            if not self.comic:
                # Auto-initialize a 3-panel comic if the model called comic_panel first
                self.comic = {
                    "id": new_id("comic"),
                    "title": "Story Strip",
                    "style": media.DEFAULT_STYLE_KEY,
                    "characters": "",
                    "panels": [{"caption": "", "dialogue": [], "scene": "", "image": None, "status": "empty"} for _ in range(max(3, self.ctrl.goal_target))],
                }
                self.ctrl.goal_label = "Panels"
            try:
                idx = int(str(a.get("panel", "1")).strip()) - 1
            except ValueError:
                return {"error": "panel must be a number"}
            if not 0 <= idx < len(self.comic["panels"]):
                idx = min(max(0, self.ctrl.goal_done - 1), len(self.comic["panels"]) - 1)
            p = self.comic["panels"][idx]
            cap = a.get("caption") or (self.ctrl.active_story[-1] if self.ctrl.active_story else "")
            if cap:
                c_txt, c_bubs = projects.extract_dialogue(cap)
                p["caption"] = c_txt
                p["dialogue"] = c_bubs
            if a.get("scene"):
                p["scene"] = a["scene"]
                p["status"] = "drawing"
                self.spawn(self._draw_panel(idx))
            await self.push_comic()
            return {"status": f"Rendering panel {idx + 1} (~10s). Continue directly to the next step."}

        if name == "show_card":
            await self.ui({"type": "item", "item": {"id": "forge", "kind": "card", "title": a.get("title", ""), "text": a.get("text", "")}})
            return {"ok": True}

        if name == "show_choices":
            opts = [o.strip() for o in (a.get("options") or "").split("|") if o.strip()]
            await self.ui({"type": "item", "item": {"id": new_id("choice"), "kind": "choices", "prompt": a.get("prompt", ""), "options": opts}})
            return {"ok": True}

        if name == "ask_input":
            mode = (a.get("mode") or "type").lower()
            self.input_target = a.get("target") or None
            await self.ui({"type": "input", "mode": mode, "prompt": a.get("prompt", "")})
            return {"status": f"Prompt displayed ({mode})."}

        if name == "show_word":
            parts = [p.strip() for p in (a.get("parts") or "").replace("|", "+").split("+") if p.strip()]
            await self.ui({"type": "item", "item": {"id": "word", "kind": "word", "word": a.get("word", ""), "parts": parts, "note": a.get("note", "")}})
            return {"ok": True, "note": "Word card shown; it automatically covers itself when he starts typing or opens the pen."}

        if name == "hide_word":
            await self.ui({"type": "cover_word"})
            return {"ok": True}

        if name == "write_on_page":
            self.page.append({"text": a.get("text", ""), "author": a.get("author") or "kid"})
            await self.ui({"type": "item", "item": {"id": "page", "kind": "page", "segments": self.page}})
            return {"ok": True, "page": self.page_text()}

        if name == "rewrite_page":
            self.page = [{"text": a.get("text", ""), "author": "kid"}]
            await self.ui({"type": "item", "item": {"id": "page", "kind": "page", "segments": self.page}})
            return {"ok": True}

        if name == "save_piece":
            if not self.page and self.ctrl.active_story and not self.comic:
                self.page = [{"text": s, "author": "kid"} for s in self.ctrl.active_story]
            pid = new_id("sbox_piece" if self.test_mode else "piece")
            piece = {
                "id": pid,
                "title": a.get("title") or "Untitled",
                "audience": a.get("audience") or (self.rec.get("parent_title") or "Dad"),
                "author": self.name,
                "segments": self.page,
                "comic": self.comic,
                "date": now_iso(),
                "session": self.id,
            }
            save_piece(piece, sandbox=self.test_mode)
            self.log.add("piece_saved", id=pid, title=piece["title"], audience=piece["audience"])
            await self.ui({"type": "item", "item": {"id": pid, "kind": "saved", "title": piece["title"], "url": f"/piece/{pid}"}})
            return {"ok": True, "url": f"/piece/{pid}"}

        if name == "build_activity":
            self.tried.append(a.get("title") or "game")
            return await self.start_build(a.get("title") or "Game", a.get("description", ""), a.get("why", ""))

        if name == "change_activity":
            if not self.activity:
                return {"error": "No game on screen. Use build_activity."}
            return await self.start_build(self.activity["title"], self.activity.get("description", ""), "", change=a.get("request", ""))

        if name == "open_activity":
            act = load_activity(a.get("id", ""))
            if not act:
                return {"error": "No activity with that id."}
            self.activity = dict(act)
            await self.ui({"type": "item", "item": {"id": "activity", "kind": "activity", "title": act.get("title", ""), "html": act["html"]}})
            return {"ok": True, "summary": act.get("summary", "")}

        if name == "close_activity":
            self.activity = None
            await self.ui({"type": "remove", "id": "activity"})
            return {"ok": True}

        if name == "message_activity":
            try:
                data = json.loads(a.get("data_json") or "{}")
            except json.JSONDecodeError:
                data = {"text": a.get("data_json")}
            await self.ui({"type": "to_activity", "data": data})
            return {"ok": True}

        if name == "turn_on_mic":
            purpose = str(a.get("purpose") or "story").strip().lower()
            if purpose not in ("word", "picture", "story"):
                purpose = "story"
            tword = str(a.get("target_word") or "").strip()
            prompt_lbl = str(a.get("prompt") or ("Say that word out loud" if purpose == "word" else "Tell me out loud")).strip()
            self.ctrl.active_mic_request = {
                "purpose": purpose,
                "wrote": tword,
                "meant_guess": "",
                "sentence": self.ctrl.pending_spell_sentence or "",
                "extra_ms": [],
            }
            await self.ui({
                "type": "tutor_mic",
                "action": "on",
                "purpose": purpose,
                "target_word": tword,
                "sentence": self.ctrl.pending_spell_sentence or "",
                "prompt": prompt_lbl,
            })
            return {"ok": True, "status": "Green center microphone will activate automatically as soon as you finish speaking."}

        if name == "note":
            self.log.add("note", category=a.get("category", "other"), detail=a.get("detail", ""))
            return {"ok": True}

        return {"error": f"unknown tool {name}"}

    # ---------- background work ----------

    async def _draw(self, item: dict[str, Any], scene: str, style: str) -> None:
        t0 = time.time()
        try:
            mid, _ = await asyncio.to_thread(media.generate_image, scene, style)
            item.update(status="done", src=f"/media/{mid}.jpg")
            await self.ui({"type": "item", "item": item})
            self.log.add("drawn", id=mid, scene=scene, seconds=round(time.time() - t0, 1))
            # Never fire turn_complete=True here—it would interrupt the child mid-typing!
            self.silent_context.append(f'[Picture rendered on screen for: "{scene[:140]}"]')
        except Exception as e:
            item.update(status="failed")
            await self.ui({"type": "item", "item": item})
            self.log.add("error", where="draw", error=str(e))

    async def _draw_panel(self, idx: int) -> None:
        comic = self.comic
        if not comic:
            return
        p = comic["panels"][idx]
        refs = []
        for q in comic["panels"]:
            if q is not p and q.get("image"):
                try:
                    refs.append(media.media_path(q["image"]).read_bytes())
                except OSError:
                    pass
        try:
            mid, _ = await asyncio.to_thread(
                media.generate_image, p["scene"], comic["style"], "4:3", refs[-2:], comic.get("characters", "")
            )
            p.update(image=mid, status="done", src=f"/media/{mid}.jpg")
            self.log.add("panel_drawn", panel=idx + 1, scene=p["scene"], caption=p.get("caption"))
            await self.push_comic()
            self.silent_context.append(f'[Panel {idx + 1} rendered on screen for: "{p["scene"][:140]}"]')
        except Exception as e:
            p["status"] = "failed"
            await self.push_comic()
            self.log.add("error", where="draw_panel", error=str(e))

    async def start_build(self, title: str, description: str, why: str, change: str | None = None) -> dict[str, Any]:
        if self.build_task and not self.build_task.done():
            return {"status": "Already building something; wait for it."}
        await self.ui({"type": "building", "title": title})
        self.build_task = asyncio.create_task(self._build(title, description, why, change))
        return {"status": "Building live HTML5 game (~30s). Keep him working on the current sentence meanwhile."}

    async def _build(self, title: str, description: str, why: str, change: str | None) -> None:
        t0 = time.time()
        prev_html = self.activity.get("html") if (change and self.activity) else None
        try:
            if not change:
                try:
                    vet = await asyncio.wait_for(asyncio.to_thread(observers.vet_spec, title, description), timeout=25)
                except Exception:
                    vet = {}
                self.log.add("critic_vet", title=title, vet=vet)
                if vet and not vet.get("approve", True) and vet.get("revised_description"):
                    description = vet["revised_description"]
            html = None
            async for kind, val in builder.stream_build(title, description, self.rec, prev_html, change):
                if kind == "progress":
                    await self.ui({"type": "build_progress", "chars": val})
                else:
                    html = val
            assert html
            aid = self.activity["id"] if (change and self.activity) else new_id("sbox_act" if self.test_mode else "act")
            meta = {
                "id": aid,
                "title": title,
                "description": description if not change else f"{description}\nChange: {change}",
                "why": why,
                "created": now_iso(),
                "session": self.id,
            }
            self.activity = {**meta, "html": html}
            save_activity({**meta, "html": html}, sandbox=self.test_mode)
            secs = round(time.time() - t0)
            self.log.add("activity_built", id=aid, title=title, seconds=secs, change=change, why=why)
            await self.ui({"type": "build_done"})
            await self.ui({"type": "item", "item": {"id": "activity", "kind": "activity", "title": title, "html": html}})
            await self.notify(
                f"[The live game '{title}' is now on screen ({secs}s). Invite him in ONE short sentence to type his first complete sentence inside the game.]"
            )
        except Exception as e:
            self.log.add("error", where="build", error=str(e))
            await self.ui({"type": "build_done"})
            self.silent_context.append(f"[Building '{title}' failed ({str(e)[:120]}); stay with comic/cards.]")
