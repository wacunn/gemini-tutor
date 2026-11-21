"""Shared Working-Memory Blackboard + Fast Small-Model Talker Reflex + Background Specialists.

Architecture:
1. FAST FRONT-LINE TALKER (`fast_reflex_turn`, `gemini-3.1-flash-lite`, ~0.8s, 1 single API call,
   hard 3.2s ceiling + 0ms pure-Python fallback):
   - Reads the Blackboard's `policy` in 0ms (never waits on deliberative agents).
   - Evaluates the child's sentence, decides accept vs. ONE gentle fix per the Blackboard policy,
     and returns BOTH the spoken reaction AND the next story prompt/starters in one shot.
2. SHARED WORKING-MEMORY BLACKBOARD (`WorkingMemoryBlackboard`):
   - Holds `turn_epoch` (cancels stale UI updates so old turns never overwrite new typing),
     `policy` (today's energy, ask_mode, priority_skills, spell_rung, use_starters),
     `next_beat_cache` (pre-fetched story prompts), and `QUOTA` (Free-Tier 429 circuit breaker).
3. BACKGROUND SPECIALISTS (`background_coach_update`):
   - Run asynchronously AFTER the Talker has already replied to the child.
   - Update `learner.json` hypotheses/skill beliefs and write the updated `policy` onto the
     Blackboard for turn t+1. Automatically pause LLM calls if Free-Tier 429 pressure is detected.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from google.genai import types

from . import coach, thinking
from .config import COACH_MODEL, LITE_MODEL, genai_client
from .record import save_learner


class APIQuotaTracker:
    """Process-wide circuit breaker for Free-Tier API keys (429 / paid-only image endpoints)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.last_429_at: float = 0.0
        self.image_paid_blocked_until: float = 0.0
        self.free_tier_suspected: bool = False
        self.notice: str = ""

    def is_quota_err(self, err: Any) -> bool:
        s = str(err or "").lower()
        return any(k in s for k in ("429", "resource_exhausted", "quota", "rate limit", "too many requests"))

    def note_error(self, where: str, err: Any) -> None:
        s = str(err or "")
        low = s.lower()
        with self._lock:
            if self.is_quota_err(s):
                self.last_429_at = time.time()
                if "limit: 0" in low or "free_tier" in low or "billing" in low:
                    self.free_tier_suspected = True
                if not self.notice:
                    self.notice = (
                        "Free-Tier Gemini API rate limit detected. Background observers are paused to save quota "
                        "for your child's live turns."
                    )
            if where == "image" and (self.is_quota_err(s) or "403" in low or "404" in low or "not supported" in low):
                # Paid image model unavailable on this key -> switch to instant Notebook Ink Doodle for 10 min
                self.image_paid_blocked_until = time.time() + 600
                self.free_tier_suspected = True
                self.notice = (
                    "Your API key appears to be on the Google AI Studio Free Tier (paid image models returned a quota "
                    "limit). Using fast Notebook Ink Doodle illustrations so every panel still draws right away!"
                )

    def allow_background(self) -> bool:
        with self._lock:
            return (time.time() - self.last_429_at) > 75.0

    def allow_paid_image(self) -> bool:
        with self._lock:
            return time.time() >= self.image_paid_blocked_until

    def status_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "free_tier_suspected": self.free_tier_suspected,
                "rate_limited_recently": (time.time() - self.last_429_at) <= 75.0,
                "paid_image_active": time.time() >= self.image_paid_blocked_until,
                "notice": self.notice,
            }


QUOTA = APIQuotaTracker()

# High-frequency Grade 3 misspellings for the 0ms offline/429 reflex fallback
COMMON_TYPOS: dict[str, str] = {
    "becuase": "because",
    "becuz": "because",
    "becuse": "because",
    "cuz": "because",
    "freind": "friend",
    "frend": "friend",
    "wantd": "wanted",
    "wit": "with",
    "smelee": "smelly",
    "smeleey": "smelly",
    "smely": "smelly",
    "smeled": "smelled",
    "smeld": "smelled",
    "fase": "face",
    "fasse": "face",
    "fases": "faces",
    "uoos": "whose",
    "hoos": "whose",
    "whos": "whose",
    "fkying": "flying",
    "fky": "fly",
    "fliyng": "flying",
    "flyin": "flying",
    "spaship": "spaceship",
    "spacship": "spaceship",
    "spaceshipe": "spaceship",
    "perminantly": "permanently",
    "alens": "aliens",
    "aleins": "aliens",
    "alienz": "aliens",
    "stinkee": "stinky",
    "stinkey": "stinky",
    "wut": "what",
    "wuz": "was",
    "sed": "said",
    "traped": "trapped",
    "stoped": "stopped",
    "droped": "dropped",
    "grabed": "grabbed",
    "grabbd": "grabbed",
    "floted": "floated",
    "tryed": "tried",
    "trys": "tries",
    "tryes": "tries",
    "peple": "people",
    "poeple": "people",
    "wuld": "would",
    "shuld": "should",
    "culd": "could",
    "cudnt": "couldn't",
    "dont": "don't",
    "cant": "can't",
    "didnt": "didn't",
    "wasnt": "wasn't",
    "wentd": "went",
    "runned": "ran",
    "ranned": "ran",
    "eated": "ate",
    "catched": "caught",
    "monstur": "monster",
    "burito": "burrito",
    "tortiya": "tortilla",
    "accidently": "accidentally",
    "finelly": "finally",
    "finaly": "finally",
}


class WorkingMemoryBlackboard:
    """Shared working-memory workspace read in 0ms by the Fast Talker and updated asynchronously by background specialists."""

    def __init__(self, rec: dict[str, Any]) -> None:
        self._lock = threading.RLock()
        self.turn_epoch: int = 0
        cm = coach.ensure_model(rec)
        last_day = (cm.get("day_states") or [{}])[-1] if cm.get("day_states") else {}
        self.policy: dict[str, Any] = {
            "energy": last_day.get("energy") or "medium",
            "willingness": last_day.get("willingness") or "medium",
            "ask_mode": "ask_one",  # "ask_one" | "accept_flow"
            "priority_skills": ["complete_sentence", "spelling", "verb_ending", "end_mark", "capital"],
            "spell_rung": 3,
            "scaffold": "none",
            "use_starters": False,
            "suggest_pen": False,
        }
        self.next_beat_cache: dict[str, dict[str, Any]] = {}
        self.recent_bg_notes: list[str] = []

    def bump_epoch(self) -> int:
        with self._lock:
            self.turn_epoch += 1
            return self.turn_epoch

    def current_epoch(self) -> int:
        with self._lock:
            return self.turn_epoch

    def get_policy(self) -> dict[str, Any]:
        with self._lock:
            return dict(self.policy)

    def update_policy(self, updates: dict[str, Any], note: str = "") -> None:
        with self._lock:
            for k, v in updates.items():
                if v is not None:
                    self.policy[k] = v
            if note:
                self.recent_bg_notes = (self.recent_bg_notes + [note])[-10:]

    def put_next_beat(self, key: str, beat: dict[str, Any]) -> None:
        with self._lock:
            self.next_beat_cache[key] = dict(beat)

    def pop_next_beat(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            return self.next_beat_cache.pop(key, None)


REFLEX_SYSTEM = """You are the fast front-line comic collaborator & writing reflex for {name} (Grade {grade}, ADHD).
You read the Shared Working-Memory Blackboard policy set by the background coach, check what {name} just wrote, and respond in ONE shot so there is zero lag.

1. WRITING CHECK (`check`):
   - Analyze literally: `complete` (true only if explicit subject + finite verb + complete thought), `issue` ("none"|"missing_subject"|"missing_verb"|"incomplete_thought"|"run_on"|"not_a_sentence_attempt"), `capital_ok`, `end_ok`.
   - `misspellings`: genuine spelling mistakes INCLUDING phonetic spellings of sight/function words in context (`{{"wrote":"fase","meant":"face"}}`, `{{"wrote":"uoos","meant":"whose"}}` in "Dylan uoos Cat", `{{"wrote":"noon","meant":"no one"}}`). Ignore proper nouns/Minecraft/band names.
   - `grammar_fixes`: missing verb endings or agreement (`"Bob barf"` -> `{{"wrote":"barf","options":["barfs","barfed"],"rule":"Add -s or -ed"}}`).

2. ACCEPT vs ONE QUICK FIX (`accept`):
   - Hard ceiling: consecutive fixes so far = {consecutive} (max {max_fixes}; if at max, MUST set `accept: true`).
   - Blackboard policy right now: energy={energy}, ask_mode={ask_mode}, top priority={top_skill}, target spell_rung={spell_rung}.
   - If the sentence is clean -> `accept: true`.
   - If it is a fragment (`missing_subject`/`missing_verb`/`incomplete_thought`) or breathless `run_on` -> ask to finish/split it (`accept: false`, `focus: "complete_sentence"` or `"run_on"`), unless at max_fixes.
   - For spelling errors, verb endings, or missing period/capital:
     * If `ask_mode == "accept_flow"` -> set `accept: true` and list skipped items in `deferred`.
     * If `ask_mode == "ask_one"` -> pick AT MOST ONE single thing (`focus`: `"spelling"`|`"verb_ending"`|`"end_mark"`|`"capital"`), set `accept: false`, and use `spell_rung` ({spell_rung}):
       - rung 1: ask if he can spot the spelling slip himself (do NOT name the word)
       - rung 2: tell him how many words look off (do NOT name them)
       - rung 3: name `focus_word` so it highlights in his box
       - rung 4: give 2-3 `spell_options` including the right spelling
       - rung 5: full word-parts card

3. KID-FACING SPEECH & NEXT BEAT (`story_reaction`, `kid_words`, `next_spoken`, `next_input`, `book_title`):
   - `story_reaction`: 1 short, warm, playful 3-8 word reaction to HIS STORY ("Oh no, poor guy!", "That's a super stinky situation!", "Cat farts right on his face?!"). Keep it strictly about his story—zero grammar talk in `story_reaction`!
   - NEVER use babyish metaphors for writing/punctuation rules ("little dot", "big and tall like a superhero", "crash the printer"). Just use normal direct words: "Add a period at the end.", "Capitalize the first letter.", "Check the spelling of 'fase'."
   - ZERO PLOT SUGGESTING: NEVER invent story ideas, potions, rockets, or "Does X or Y happen?" choices! Ask short, OPEN questions ("How does the whole story end?", "What happens next?") using ONLY what {name} already wrote.
   - `starters`: leave `[]` empty unless he wrote "idk".
   - `book_title`: 2-4 words using ONLY words/concepts ALREADY in his sentence (never invent future plot words like "Blast" or "Revenge"!).

Return STRICT JSON:
{{"check":{{"sentences":[{{"text":"...","complete":true,"issue":"none","capital_ok":true,"end_ok":true,"clause_type":"simple|compound|complex|fragment|run_on"}}],"misspellings":[],"grammar_fixes":[]}},
 "accept":true,
 "focus":"none|complete_sentence|run_on|capital|end_mark|spelling|verb_ending",
 "focus_word":"",
 "focus_correct":"",
 "spell_rung":{spell_rung},
 "spell_options":[],
 "scaffold":"none|story_question|starter_chips|partial_frame",
 "chips":[],
 "prefill":"",
 "story_reaction":"short 3-8 word warm reaction to his story idea",
 "kid_words":"plain direct fix request when accept=false",
 "input_prompt":"short bar cue when accept=false",
 "deferred":[],
 "book_title":"Punchy Comic Title",
 "next_spoken":"specific next-beat story question when accept=true",
 "next_input":"short next-beat bar prompt when accept=true",
 "starters":["When Bob…","Because the…"],
 "rationale":"1 short sentence for parent log"}}"""


def local_check_writing(text: str) -> dict[str, Any]:
    """0ms deterministic syntax & common-typo check when the network/API is rate-limited."""
    t = (text or "").strip()
    if not t:
        return {"sentences": [], "misspellings": [], "grammar_fixes": [], "features": {}}
    words = re.findall(r"[A-Za-z']+", t)
    first_alpha = next((ch for ch in t if ch.isalpha()), "")
    cap_ok = bool(first_alpha and first_alpha.isupper())
    end_ok = bool(re.search(r'[.!?]["\')\]]*$', t))
    low = t.lower()

    # Fragment / run-on heuristics
    has_finite_verb = bool(
        re.search(
            r"\b(is|are|was|were|am|has|have|had|can|could|will|would|did|does|do|got|went|came|saw|made|said|yelled|ran|fell|ate|barfed|barfs|smells|smelled|jumped|scares|scared|tried|tries|opened|marched|climbs|climbed|traps|trapped|exploded|shoots|shot|chased|grabbed|flushed|melted|tripped|slid|screamed|yells|laughs|laughed|sneezed|dropped|escaped|wiggled|roared|grabs|starts|loves|hates|wants|wanted|plays|played)\b|\b[a-z]{3,}(?:ed|ing|es)\b",
            low,
        )
    )
    lone_subord = bool(
        re.match(r"^(because|when|whenever|if|although|while|before|after|since)\b", low)
        and "," not in t
        and len(words) <= 8
    )
    if len(words) <= 1:
        issue = "not_a_sentence_attempt"
    elif " and then " in low and low.count(" and then ") >= 2:
        issue = "run_on"
    elif lone_subord:
        issue = "incomplete_thought"
    elif len(words) < 3 or not has_finite_verb:
        issue = "missing_verb"
    else:
        issue = "none"

    ms = []
    for w in words:
        wl = w.lower()
        if wl in COMMON_TYPOS:
            ms.append({"wrote": w, "meant": COMMON_TYPOS[wl]})

    raw_out = {
        "sentences": [
            {
                "text": t,
                "complete": issue == "none",
                "issue": issue,
                "capital_ok": cap_ok,
                "end_ok": end_ok,
                "clause_type": "fragment" if issue != "none" else "simple",
            }
        ],
        "misspellings": ms,
        "grammar_fixes": [],
    }
    return thinking._post_verify_check(t, raw_out)


def local_reflex_fallback(
    raw: str,
    chk: dict[str, Any],
    policy: dict[str, Any],
    session: dict[str, Any],
    next_goal: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """0ms turn decision when Free-Tier 429 or network timeout hits—keeps the session moving smoothly."""
    sents = chk.get("sentences") or []
    ms = chk.get("misspellings") or []
    gf = chk.get("grammar_fixes") or []
    consecutive = session.get("consecutive_fixes", 0)
    has_frag = any(s.get("issue") not in ("none", "run_on") for s in sents) or not sents
    has_runon = any(s.get("issue") == "run_on" for s in sents)
    no_end = any(s.get("end_ok") is False for s in sents)

    decision: dict[str, Any] = {
        "accept": True,
        "focus": "none",
        "focus_word": "",
        "focus_correct": "",
        "spell_rung": policy.get("spell_rung", 3),
        "spell_options": [],
        "scaffold": "none",
        "chips": [],
        "prefill": raw,
        "kid_words": "Got it.",
        "input_prompt": next_goal[:90],
        "deferred": [],
        "next_scaffold": "none",
        "today_state": {"energy": policy.get("energy", "medium"), "willingness": policy.get("willingness", "medium"), "note": "instant local reflex"},
        "rationale": "Instant local reflex kept turn under 1s while API was busy/rate-limited.",
        "guardrail": "local_reflex",
        "latency_s": 0.0,
    }

    if consecutive < coach.MAX_CONSECUTIVE_FIXES:
        if has_frag:
            decision.update(
                accept=False,
                focus="complete_sentence",
                scaffold="partial_frame",
                prefill=raw.rstrip(".!? ") + " ",
                kid_words="That's part of a sentence—finish what happens so it's a complete thought.",
                input_prompt="Finish the sentence in the box and hit Enter",
            )
        elif has_runon:
            decision.update(
                accept=False,
                focus="run_on",
                kid_words="Split 'and then' into two sentences with a period and a capital letter.",
                input_prompt="Split 'and then' into two sentences with a period",
            )
        elif policy.get("ask_mode") == "ask_one" and ms:
            m0 = ms[0]
            decision.update(
                accept=False,
                focus="spelling",
                focus_word=m0["wrote"],
                focus_correct=m0["meant"],
                spell_rung=3,
                kid_words=f"Check the spelling of '{m0['wrote']}' in your box and hit Enter.",
                input_prompt=f"Fix '{m0['wrote']}' in your sentence and hit Enter",
            )
        elif policy.get("ask_mode") == "ask_one" and gf:
            g0 = gf[0]
            opts = g0.get("options") or [""]
            decision.update(
                accept=False,
                focus="verb_ending",
                focus_word=g0["wrote"],
                focus_correct=opts[0],
                kid_words=f"Change '{g0['wrote']}' to '{opts[0]}' in your box and hit Enter.",
                input_prompt=f"Change '{g0['wrote']}' to '{opts[0]}' and hit Enter",
            )
        elif policy.get("ask_mode") == "ask_one" and no_end:
            decision.update(
                accept=False,
                focus="end_mark",
                kid_words="Add a period (or ! or ?) at the end of your sentence.",
                input_prompt="Add a period, !, or ? at the end and hit Enter",
            )

    beat = {
        "spoken_prompt": next_goal,
        "input_prompt": next_goal[:95],
        "starters": [],
        "kernel_1": "",
        "kernel_2": "",
        "connectors": "when | because | but",
    }
    return decision, beat


def fast_reflex_turn(
    rec: dict[str, Any],
    bb: WorkingMemoryBlackboard,
    session: dict[str, Any],
    raw: str,
    how: str,
    story_context: str,
    next_goal: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Runs ONE fast `gemini-3.1-flash-lite` call (~0.8s, 3.2s hard cap) returning (chk, decision, next_beat).
    Falls back in 0ms to `local_reflex_fallback` if rate-limited or slow."""
    t0 = time.time()
    policy = bb.get_policy()
    name = rec.get("name") or "the student"
    grade = rec.get("grade", 3)
    consecutive = session.get("consecutive_fixes", 0)
    top_skill = (policy.get("priority_skills") or ["complete_sentence"])[0]

    if consecutive >= coach.MAX_CONSECUTIVE_FIXES:
        effective_ask_mode = "accept_flow"
    elif policy.get("ask_mode") == "accept_flow" and (consecutive >= 1 or policy.get("energy") == "low"):
        effective_ask_mode = "accept_flow"
    else:
        effective_ask_mode = "ask_one"

    sys_prompt = REFLEX_SYSTEM.format(
        name=name,
        grade=grade,
        consecutive=consecutive,
        max_fixes=coach.MAX_CONSECUTIVE_FIXES,
        energy=policy.get("energy", "medium"),
        ask_mode=effective_ask_mode,
        top_skill=top_skill,
        spell_rung=policy.get("spell_rung", 3),
        next_goal=next_goal,
    )
    user_prompt = (
        f"STORY CONTEXT SO FAR:\n{story_context or '(starting now)'}\n\n"
        f"NEXT BEAT GOAL IF ACCEPTED:\n{next_goal}\n\n"
        f"STUDENT WROTE ({how}):\n{raw}"
    )

    try:
        client = genai_client(timeout_ms=3200)
        resp = client.models.generate_content(
            model=LITE_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=sys_prompt,
                temperature=0.25,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", (resp.text or "").strip())
        out = json.loads(txt)
        if not isinstance(out, dict):
            raise ValueError("non-dict reflex output")

        chk = thinking._post_verify_check(raw, out.get("check") if isinstance(out.get("check"), dict) else {})
        # Merge local common-typo safety net if LLM missed an unmistakable typo (e.g. 'fkying' -> 'flying', 'fasse' -> 'face')
        known_ms = {m["wrote"].lower() for m in (chk.get("misspellings") or [])}
        injected_typo: dict[str, str] | None = None
        for w in re.findall(r"[A-Za-z']+", raw):
            wl = w.lower()
            if wl in COMMON_TYPOS and wl not in known_ms:
                item_ms = {"wrote": w, "meant": COMMON_TYPOS[wl]}
                chk.setdefault("misspellings", []).append(item_ms)
                known_ms.add(wl)
                if injected_typo is None:
                    injected_typo = item_ms

        all_ms = chk.get("misspellings") or []
        if all_ms and out.get("accept", True) and effective_ask_mode == "ask_one" and consecutive < coach.MAX_CONSECUTIVE_FIXES:
            pick_ms = injected_typo or sorted(all_ms, key=lambda x: len(x.get("meant", "")), reverse=True)[0]
            out["accept"] = False
            out["focus"] = "spelling"
            out["focus_word"] = pick_ms["wrote"]
            out["focus_correct"] = pick_ms["meant"]
            out["spell_rung"] = max(3, int(policy.get("spell_rung", 3)))
            out["kid_words"] = f"Check the spelling of '{pick_ms['wrote']}' in your box and hit Enter."
            out["input_prompt"] = f"Fix '{pick_ms['wrote']}' in your sentence and hit Enter"

        out["next_scaffold"] = "none"
        out["today_state"] = {
            "energy": policy.get("energy", "medium"),
            "willingness": policy.get("willingness", "medium"),
            "note": "blackboard reflex",
        }
        decision = coach.validate(out, raw, chk, session)
        # Combine warm story reaction ("Oh no, poor guy!") with plain, non-cringe writing mechanics ("Capitalize the first letter.")!
        story_rx = str(out.get("story_reaction") or "").strip()
        if re.search(r"\b(capital|period|dot|superhero|spell|fix|mistake|letter|sentence|printer)\b", story_rx, re.I):
            story_rx = ""
        rx_prefix = (story_rx + " ") if story_rx else ""
        decision["story_reaction"] = story_rx
        foc = decision.get("focus")
        if not decision.get("accept"):
            if foc == "capital":
                decision["kid_words"] = f"{rx_prefix}Capitalize the first letter at the start of your sentence."
                decision["input_prompt"] = "Capitalize the first letter at the start and hit Enter"
            elif foc == "end_mark":
                decision["kid_words"] = f"{rx_prefix}Add a period (or ! or ?) at the end of your sentence."
                decision["input_prompt"] = "Add a period, !, or ? at the end and hit Enter"
            elif foc == "spelling" and decision.get("focus_word"):
                decision["kid_words"] = f"{rx_prefix}Check the spelling of '{decision['focus_word']}' (highlighted in your box) and hit Enter."
                decision["input_prompt"] = f"Fix '{decision['focus_word']}' in your sentence and hit Enter"
            elif foc == "verb_ending" and decision.get("focus_word"):
                opt0 = decision.get("focus_correct") or ""
                decision["kid_words"] = f"{rx_prefix}Change '{decision['focus_word']}' to '{opt0}' in your box and hit Enter."
                decision["input_prompt"] = f"Change '{decision['focus_word']}' to '{opt0}' and hit Enter"
            elif foc == "complete_sentence":
                decision["kid_words"] = f"{rx_prefix}Finish what happens so that's a complete sentence."
                decision["input_prompt"] = "Finish the sentence in the box and hit Enter"
            elif foc == "run_on":
                decision["kid_words"] = f"{rx_prefix}Split 'and then' into two sentences with a period and a capital letter."
                decision["input_prompt"] = "Split 'and then' into two sentences with a period"
        else:
            decision["kid_words"] = story_rx

        decision["latency_s"] = round(time.time() - t0, 2)

        next_spoken = str(out.get("next_spoken") or next_goal).strip()
        next_input = str(out.get("next_input") or next_spoken[:90]).strip()
        beat = {
            "spoken_prompt": next_spoken,
            "input_prompt": next_input,
            "starters": [],
            "book_title": str(out.get("book_title") or "").strip()[:56],
            "kernel_1": "",
            "kernel_2": "",
            "connectors": "when | because | but",
        }
        return chk, decision, beat
    except Exception as e:
        QUOTA.note_error("reflex", e)
        chk = local_check_writing(raw)
        decision, beat = local_reflex_fallback(raw, chk, policy, session, next_goal)
        decision["latency_s"] = round(time.time() - t0, 2)
        return chk, decision, beat


BG_POLICY_SYSTEM = """You are the background Pedagogical Scientist & Coach updating the Shared Working-Memory Blackboard for {name} (Grade {grade}, ADHD).
The front-line Talker has ALREADY responded to {name} so nobody is waiting on you.
Review the latest turn, measured behaviour facts, and skill history, then set the Blackboard policy for the NEXT turn (`t+1`):
- `energy` / `willingness`: "high"|"medium"|"low" (match MEASURED EFFORT SIGNAL unless there's a clear reason).
- `ask_mode`: "ask_one" (nudge 1 high-value issue if the next sentence has one) OR "accept_flow" (let minor slips go next turn to build momentum—e.g. right after he fixed something, when tired, or when starting a cool streak).
- `priority_skills`: ordered list of top 3 skills to care about next.
- `spell_rung`: 1..5 (1-2 on high-energy streaks to test self-catching; 3-4 on medium/low energy).
- `use_starters`: true if he still benefits from 'because'/'when' starter chips; false once he uses linking words on his own reliably on good days.
- `suggest_pen`: true occasionally on high/medium energy days to practice lined handwriting.
- `hypothesis_updates`: update H1..H7 when this turn gave clear evidence for or against.
- `what_works_add`: optional short observation.
Return STRICT JSON:
{{"energy":"high|medium|low","willingness":"high|medium|low","note":"short",
 "ask_mode":"ask_one|accept_flow",
 "priority_skills":["complete_sentence","spelling","verb_ending"],
 "spell_rung":3,
 "use_starters":true,
 "suggest_pen":false,
 "hypothesis_updates":[],
 "what_works_add":""}}"""


def background_coach_update(
    rec: dict[str, Any],
    bb: WorkingMemoryBlackboard,
    session_snapshot: dict[str, Any],
    raw: str,
    how: str,
    chk: dict[str, Any],
    signals: dict[str, Any],
    decision: dict[str, Any],
    test_mode: bool = False,
) -> None:
    """Runs asynchronously in a background worker AFTER the child already got their response.
    Updates `learner.json` and writes the next-turn `policy` onto the Blackboard."""
    model = coach.ensure_model(rec)
    beh = coach.behaviour_facts(session_snapshot, raw, signals)

    # 1. Always compute fast local heuristic policy update first (0 API calls, works under 429!)
    m_eff = re.search(r"MEASURED EFFORT SIGNAL:\s*([\d.]+)/10\s*=>\s*(high|medium|low)", beh)
    eff_label = m_eff.group(2) if m_eff else "medium"
    just_asked = not bool(decision.get("accept", True))
    ss = model.get("skill_stats") or {}
    conn_hist = (ss.get("connector") or [])[-8:]
    uses_conn_unprompted = len(conn_hist) >= 5 and (sum(conn_hist) / len(conn_hist)) >= 0.6

    heuristic_policy = {
        "energy": eff_label,
        "willingness": eff_label,
        # Right after asking a fix (or when energy is low), alternate with flow so it never feels like a gauntlet!
        "ask_mode": "accept_flow" if (just_asked or eff_label == "low") else "ask_one",
        "spell_rung": 1 if (eff_label == "high" and model.get("self_catches", 0) >= 1) else (4 if eff_label == "low" else 3),
        "use_starters": (not uses_conn_unprompted) or eff_label == "low",
    }
    bb.update_policy(heuristic_policy)
    decision_for_log = {
        **decision,
        "today_state": {"energy": eff_label, "willingness": eff_label, "note": decision.get("today_state", {}).get("note", "")},
    }
    coach.apply_learning(model, decision_for_log, raw)

    # 2. Only run deliberative LLM scientist update if API quota is completely healthy!
    if QUOTA.allow_background():
        try:
            client = genai_client(timeout_ms=5000)
            prompt = (
                f"SKILLS:\n{coach._skills_summary(model)}\n\n"
                f"HYPOTHESES:\n{coach._hyp_summary(model)}\n\n"
                f"BEHAVIOUR FACTS:\n{beh}\n\n"
                f"LATEST TURN ({how}): {raw!r}\n"
                f"TALKER DECISION JUST TAKEN: accept={decision.get('accept')}, focus={decision.get('focus')}\n"
                f"OUTCOME OF PREVIOUS ASK: {json.dumps(signals.get('outcome') or {})}"
            )
            resp = client.models.generate_content(
                model=COACH_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=BG_POLICY_SYSTEM.format(name=rec.get("name") or "the student", grade=rec.get("grade", 3)),
                    temperature=0.3,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", (resp.text or "").strip())
            out = json.loads(txt)
            if isinstance(out, dict):
                bb.update_policy(
                    {
                        "energy": out.get("energy") if out.get("energy") in ("high", "medium", "low") else eff_label,
                        "willingness": out.get("willingness") if out.get("willingness") in ("high", "medium", "low") else eff_label,
                        "ask_mode": out.get("ask_mode") if out.get("ask_mode") in ("ask_one", "accept_flow") else heuristic_policy["ask_mode"],
                        "priority_skills": [s for s in (out.get("priority_skills") or []) if isinstance(s, str)][:4] or None,
                        "spell_rung": max(1, min(5, int(out.get("spell_rung") or heuristic_policy["spell_rung"]))),
                        "use_starters": bool(out.get("use_starters", heuristic_policy["use_starters"])),
                        "suggest_pen": bool(out.get("suggest_pen", False)),
                    },
                    note=str(out.get("note") or ""),
                )
                coach.apply_learning(
                    model,
                    {
                        "accept": decision.get("accept"),
                        "focus": decision.get("focus"),
                        "scaffold": decision.get("scaffold"),
                        "spell_rung": decision.get("spell_rung"),
                        "kid_words": decision.get("kid_words"),
                        "rationale": f"[Blackboard Coach -> next={out.get('ask_mode')}, rung={out.get('spell_rung')}] {out.get('note', '')}",
                        "guardrail": "bg_blackboard",
                        "today_state": {"energy": out.get("energy", eff_label), "willingness": out.get("willingness", eff_label), "note": out.get("note", "")},
                        "hypothesis_updates": out.get("hypothesis_updates") or [],
                        "what_works_add": out.get("what_works_add") or "",
                        "deferred": [],
                    },
                    raw,
                )
                # Keep decisions list tidy (don't double-count the same turn in accept/push stats)
                if len(model.get("decisions") or []) >= 2 and model["decisions"][-1].get("guardrail") == "bg_blackboard":
                    bg_entry = model["decisions"].pop()
                    model["decisions"][-1]["rationale"] = bg_entry["rationale"]
        except Exception as e:
            QUOTA.note_error("bg_coach", e)

    if not test_mode:
        save_learner(rec)
