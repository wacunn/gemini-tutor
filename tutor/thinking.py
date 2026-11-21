"""Thinking tools behind the live tutor.

- check_writing(): fast, high-precision syntactic & orthographic analysis (clauses, fragments,
  run-ons, capitals, end punctuation, and real orthographic/morphological misspellings) using
  gemini-3.5-flash plus deterministic verification.
- analyze_word_study(): prepares a Cover-Copy-Compare morphological/orthographic breakdown
  (Ontario B2.1–B2.3) from a word the child actually misspelled.
- invent(): uses gemini-3.1-pro-preview + critic screening to invent intrinsically integrated
  activities (Habgood & Ainsworth 2011; Saddler & Graham 2005; Graham et al. 2012) tailored to
  the learner's record.
"""

from __future__ import annotations

import json
import re
from typing import Any

from google import genai
from google.genai import types

from .config import FALLBACK_MODEL, FAST_MODEL, HYDROGEN_MODEL, genai_client

CHECK_MODEL = FAST_MODEL  # sub-second synchronous syntax/spelling check on hot path
INVENT_MODEL = HYDROGEN_MODEL  # gemini-4-hydrogen for inventing tailored mechanics


def _client() -> genai.Client:
    return genai_client()


def _json(text: str) -> Any:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"[\[{][\s\S]*[\]}]", t)
        return json.loads(m.group(0)) if m else {}


CHECK_SYSTEM = """You are a precise syntactic, grammatical, and orthographic analyzer for Grade 3–4 student writing (Ontario B3.1, B3.2, B3.3, B2.1–B2.3).
Analyze the student's exact text literally.

For each sentence-like unit:
- complete: true ONLY if it has BOTH an explicit subject (who/what, unless a clear imperative command in a command-terminal game) AND a finite verb forming a complete thought. Mark bare verb phrases ("runs away", "eating the village") as missing_subject, and bare noun/participial phrases ("a giant diamond cow", "a cow eating grass", "in the nether") as missing_verb / incomplete_thought.
- issue: one of:
  - "none": has subject + finite verb + complete thought (track capitalization, punctuation, spelling, and verb-ending/grammar fixes separately in capital_ok, end_ok, misspellings, and grammar_fixes!).
  - "missing_subject": has a finite verb/predicate ("eats the village", "fell into lava") but no subject.
  - "missing_verb": names a who/what ("a giant cow made of diamond blocks", "the iron golem with lasers") with no finite verb.
  - "incomplete_thought": prepositional phrase ("in the nether fortress") or dependent clause standing alone ("when the lever clicks", "because the creeper exploded") with no main clause.
  - "run_on": two or more independent clauses fused without proper punctuation/conjunction, comma splice, or 3+ clauses strung together with repeated "and" / "and then".
  - "not_a_sentence_attempt": ONLY for single-word bare nouns/interjections ("cow", "hi", "idk", "stuff", "no"). Any 2+ word phrase MUST be classified by its syntactic gap ("missing_verb", "missing_subject", or "incomplete_thought").
- capital_ok: starts with an uppercase letter.
- end_ok: ends with . ! or ? (optionally followed by closing quotation mark).

For misspellings (B2.1–B2.3):
- List ONLY genuine orthographic/phonological/morphological spelling errors (e.g. {"wrote":"traped","meant":"trapped"}, {"wrote":"smelee","meant":"smelly"}, {"wrote":"wantd","meant":"wanted"}, {"wrote":"noon","meant":"no one"} when context clearly means 'no one').
- Do NOT list capitalization differences ("minecraft" vs "Minecraft") or standard game/music proper nouns (creeper, wither, redstone, nether, enderman, Megadeth, Metallica).

For grammar_fixes (Ontario B3.2 — verb tense & subject-verb agreement, irregular verbs, missing required articles):
- Flag clear word-level grammatical inflections or agreement errors where a verb ending or determiner is missing or mismatched:
  * Missing 3rd-person singular -s/-es or past -ed verb ending: e.g. "Because the cat is smelly, Bob barf." -> {"wrote":"barf","options":["barfs","barfed"],"rule":"With 'Bob', add -s ('barfs') or -ed ('barfed') to the verb."}
  * Subject-verb agreement mismatch: e.g. "The cats is loud." -> {"wrote":"is","options":["are","were"],"rule":"Use 'are' or 'were' with plural 'cats'."}; "They was mad." -> {"wrote":"was","options":["were"],"rule":"Use 'were' with 'they'."}
  * Over-regularized irregular past tense: e.g. "runned" -> ["ran"], "catched" -> ["caught"], "eated" -> ["ate"], "goed" -> ["went"].
  * Missing required article/determiner before a singular countable noun when clearly ungrammatical: e.g. "When people saw cat was cool" -> {"wrote":"cat","options":["the cat","his cat"],"rule":"Add 'the' or 'his' before 'cat'."}
- Do NOT flag valid kid voice, contractions, or sentences that are already grammatical in either present or past tense ("Bob barfs." and "Bob barfed." are both completely fine—empty grammar_fixes!).
- Do NOT duplicate the same word in both misspellings and grammar_fixes (put spelling errors in misspellings, inflection/agreement errors in grammar_fixes).

Return strict JSON:
{"sentences":[{"text":"...","complete":true,"issue":"none","capital_ok":true,"end_ok":true,"clause_type":"simple|compound|complex|fragment|run_on"}],
 "misspellings":[{"wrote":"...","meant":"..."}],
 "grammar_fixes":[{"wrote":"...","options":["..."],"rule":"..."}]}"""


def _post_verify_check(raw_text: str, out: dict[str, Any]) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        return {"sentences": [], "misspellings": []}

    words = re.findall(r"[A-Za-z']+", text)
    sents = out.get("sentences") if isinstance(out.get("sentences"), list) else []

    if not sents:
        first_alpha = next((ch for ch in text if ch.isalpha()), "")
        cap_ok = bool(first_alpha and first_alpha.isupper())
        end_ok = bool(re.search(r'[.!?]["\')\]]*$', text))
        issue = "not_a_sentence_attempt" if len(words) <= 1 else "incomplete_thought"
        sents = [{"text": text, "complete": False, "issue": issue, "capital_ok": cap_ok, "end_ok": end_ok, "clause_type": "fragment"}]

    verified_sents = []
    for s in sents:
        if not isinstance(s, dict):
            continue
        st = str(s.get("text") or text).strip()
        s_words = re.findall(r"[A-Za-z']+", st)
        first_alpha = next((ch for ch in st if ch.isalpha()), "")
        cap_ok = bool(first_alpha and first_alpha.isupper())
        end_ok = bool(re.search(r'[.!?]["\')\]]*$', st))

        issue = str(s.get("issue") or "none")
        complete = bool(s.get("complete"))

        # Deterministic run-on catch for breathless "and then ... and then" chains
        low = " " + st.lower() + " "
        if low.count(" and then ") >= 2 or (low.count(" and ") >= 3 and len(s_words) >= 14 and not re.search(r"[.!?;]", st[:-1])):
            issue = "run_on"
            complete = False

        # Never let 2+ content-word phrases hide as "not_a_sentence_attempt"
        if issue == "not_a_sentence_attempt" and len(s_words) >= 2 and st.lower() not in {"i dont know", "i don't know", "no thanks", "not really"}:
            issue = "incomplete_thought"
            complete = False

        if issue != "none":
            complete = False
        elif not complete:
            issue = "incomplete_thought"

        verified_sents.append(
            {
                "text": st,
                "complete": complete,
                "issue": issue,
                "capital_ok": cap_ok,
                "end_ok": end_ok,
                "clause_type": s.get("clause_type") or ("run_on" if issue == "run_on" else ("simple" if complete else "fragment")),
            }
        )

    # Deterministic syntactic & craft features across the full submission (for Mastery Tier & Genre enforcement)
    has_connector = bool(
        re.search(
            r"\b(because|when|whenever|if|unless|although|though|even though|while|before|after|until|since|whereas|therefore|however|but|so|finally|eventually|in the end|then|next|afterward)\b",
            text,
            re.I,
        )
    )
    has_dialogue = bool('"' in text or re.match(r"^[A-Z][A-Za-z0-9 _-]{0,16}:\s+\S+", text))
    # Dialogue punctuation check (Ontario B3.3): if quotes used, check capital at start of quote & punctuation inside closing quote
    dialogue_punct_ok = True
    if '"' in text:
        quotes = re.findall(r'"([^"]*)"', text)
        if not quotes or text.count('"') % 2 != 0:
            dialogue_punct_ok = False
        else:
            for q in quotes:
                q_strip = q.strip()
                first_q = next((ch for ch in q_strip if ch.isalpha()), "")
                if not q_strip or (first_q and not first_q.isupper()) or not re.search(r"[,.!?]$", q_strip):
                    dialogue_punct_ok = False
    has_opener = bool(
        re.match(
            r"^(In|Inside|Beneath|Under|Above|Behind|Across|Beyond|Near|During|Before|After|When|While|Seconds|Deep|High|Suddenly|Finally|Although|Unlike)\b[^.!?]{4,45},",
            text,
        )
    )
    weak_found = sorted(
        {m.group(0).lower() for m in re.finditer(r"\b(went|got|did|stuff|things|very big|very bad|nice)\b", text, re.I)}
    )

    # Filter capitalization-only or identical "misspellings"
    clean_ms = []
    seen = set()
    ms_words = set()
    for m in out.get("misspellings") or []:
        if not isinstance(m, dict):
            continue
        wrote = str(m.get("wrote") or "").strip(".,!?;:\"'()[] ")
        meant = str(m.get("meant") or "").strip(".,!?;:\"'()[] ")
        if not wrote or not meant:
            continue
        if wrote.lower() == meant.lower():
            continue
        key = (wrote.lower(), meant.lower())
        if key in seen:
            continue
        seen.add(key)
        ms_words.add(wrote.lower())
        clean_ms.append({"wrote": wrote, "meant": meant})

    clean_gf = []
    seen_gf = set()
    for g in out.get("grammar_fixes") or []:
        if not isinstance(g, dict):
            continue
        wrote = str(g.get("wrote") or "").strip(".,!?;:\"'()[] ")
        raw_opts = g.get("options") if isinstance(g.get("options"), list) else ([g.get("meant")] if g.get("meant") else [])
        opts = [str(o).strip(".,!?;:\"'()[] ") for o in raw_opts if str(o or "").strip(".,!?;:\"'()[] ")]
        opts = [o for o in opts if o.lower() != wrote.lower()]
        if not wrote or not opts:
            continue
        if wrote.lower() in ms_words or wrote.lower() in seen_gf:
            continue
        seen_gf.add(wrote.lower())
        rule = str(g.get("rule") or f"Change '{wrote}' to {' or '.join(repr(o) for o in opts[:2])}.").strip()
        clean_gf.append({"wrote": wrote, "options": opts[:3], "rule": rule})

    return {
        "sentences": verified_sents,
        "misspellings": clean_ms,
        "grammar_fixes": clean_gf,
        "features": {
            "sentence_count": len(verified_sents),
            "has_connector": has_connector,
            "has_dialogue": has_dialogue,
            "dialogue_punct_ok": dialogue_punct_ok,
            "has_opener": has_opener,
            "weak_words": weak_found,
        },
    }


def check_writing(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    if not t:
        return {"sentences": [], "misspellings": [], "grammar_fixes": []}
    client = _client()
    for model in (CHECK_MODEL, FALLBACK_MODEL):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=f"Student writing:\n{t}",
                config=types.GenerateContentConfig(
                    system_instruction=CHECK_SYSTEM,
                    temperature=0.0,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            out = _json(resp.text)
            if isinstance(out, dict):
                return _post_verify_check(t, out)
        except Exception:
            continue
    return _post_verify_check(t, {})


def summarize_check(chk: dict[str, Any]) -> str:
    """One compact, exact summary line for the controller and tutor."""
    if not chk:
        return ""
    bits = []
    for s in chk.get("sentences", []) or []:
        issue = s.get("issue", "none")
        flags = []
        if issue not in ("none", "not_a_sentence_attempt"):
            flags.append(issue.replace("_", " "))
        elif issue == "not_a_sentence_attempt":
            flags.append("1-word / non-sentence")
        else:
            flags.append(f"complete ({s.get('clause_type', 'simple')})")
        if issue != "not_a_sentence_attempt":
            if s.get("capital_ok") is False:
                flags.append("missing start capital")
            if s.get("end_ok") is False:
                flags.append("missing end punctuation (.!?)")
        bits.append(f'"{s.get("text","")[:80]}": ' + ", ".join(flags))
    ms = chk.get("misspellings") or []
    if ms:
        bits.append("misspelled: " + ", ".join(f'{m.get("wrote")}->{m.get("meant")}' for m in ms))
    gf = chk.get("grammar_fixes") or []
    if gf:
        bits.append("grammar: " + ", ".join(f'{g.get("wrote")}->{"/".join(g.get("options") or [])}' for g in gf))
    return "; ".join(bits)


WORD_STUDY_SYSTEM = """You are an Ontario Grade 3–4 structured-literacy spelling specialist (B2.1–B2.3: phonics, orthographic position rules, and morphology: bases, prefixes, suffixes).
Given one word the child misspelled (wrote vs meant), break the CORRECT target word into 2–4 meaningful morphemes (prefer base + prefix/suffix if morphologically complex, e.g. "trap + p + ed", "make -> mak + ing", "un + break + able") OR clear orthographic chunks (e.g. "w + itch", "be + cause", "kn + ight").
Write ONE short, plain, 100% linguistically accurate sentence explaining the pattern or rule (never invent fake etymology, never use baby talk).
Return JSON: {"word":"...","parts":"part1 + part2","note":"One short accurate sentence."}"""


def analyze_word_study(wrote: str, meant: str) -> dict[str, str]:
    client = _client()
    for model in (CHECK_MODEL, FALLBACK_MODEL):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=f"Child wrote: {wrote!r}\nIntended word: {meant!r}",
                config=types.GenerateContentConfig(
                    system_instruction=WORD_STUDY_SYSTEM,
                    temperature=0.1,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            out = _json(resp.text)
            if isinstance(out, dict) and out.get("parts"):
                return {
                    "word": str(out.get("word") or meant).strip(),
                    "wrote": wrote,
                    "parts": str(out["parts"]).strip(),
                    "note": str(out.get("note") or f"Notice the spelling in '{meant}' compared with '{wrote}'.").strip(),
                }
        except Exception:
            continue
    return {"word": meant, "wrote": wrote, "parts": meant, "note": f"Look closely at the letters in '{meant}'."}


INVENT_SYSTEM = """You are the activity designer behind a 1:1 AI writing & spelling tutor for one specific Grade 3 child.
You combine empirical writing science (SRSD, Graham et al. 2012; Saddler & Graham 2005 sentence combining; Habgood & Ainsworth 2011 intrinsic integration) with sharp, age-respectful game design.

THE NON-NEGOTIABLE DESIGN LAWS:
1. INTRINSIC INTEGRATION: Every mechanic must make constructing, combining, expanding, or debugging FULL SENTENCES (Who/What + Does What + Capital & .!?) the literal control input that makes the world move.
   - Never design an activity that can be played with 1-word answers, conversational wh- questions, or multiple-choice sentence picking.
   - Good mechanics:
     a) 3-Panel Literal Comic: panels ONLY render once given a complete sentence, and redraw dramatically better when expanded with 'when', 'because', or 'but'.
     b) Sentence-Combining / Trap or Mod Compiler: displays 2 short raw kernels on screen that the child combines with 'when', 'because', 'but', or 'so' (or writes as a complete rule) to execute a visual outcome.
     c) Live Interactive HTML5 Mini-Game (via build_activity): a custom dark-themed terminal/forge/contraption game where typing complete sentences or repairing broken fragments/run-ons triggers immediate simulated physics/events.
2. ZERO BLANK-PAGE PARALYSIS: Always include concrete raw material on screen in `first_move` (e.g., 2 short kernels to combine, a concrete visual starting state, or a broken fragment to debug) so a kid with ADHD never stares at an empty box wondering what to write.
3. RESPECTFUL, PLAIN TONE (ANTI-BABY & ANTI-"FELLOW KIDS"):
   - Never use 1st-grade animal/zoo/bedtime themes ("what does a bear eat", "magical forest fairy").
   - Never use insults ("idiot", "stupid") or cringe slang ("yo", "epic vibes", "rock on", forcing band names into math/grammar drills).
   - Across your 3 ideas, span DIFFERENT formats (e.g., 1 comic/visual builder, 1 compiler/sentence-combiner, 1 interactive mini-game) and let at least one stay open to HIS own absurd premise rather than hard-forcing a stereotype on all three.
4. AI TRANSPARENCY & PARENT BOUNDARY:
   - Gemini is an AI tutor made by Google—never a friend, buddy, or human persona.
   - Parent sits nearby as audience for finished pieces ONLY; never assign the parent roleplay or drawing chores.

Skill targets (Ontario Language Curriculum 2023):
{targets}

Return strict JSON:
{"ideas":[
  {"name":"Short plain title",
   "pitch":"One plain, matter-of-fact sentence offering this build",
   "mechanic":"Detailed step-by-step mechanic (4-6 sentences) explaining what goes on screen, what full sentence the child constructs each turn, how fragments/run-ons fail in-world, and how sentences progress from simple to compound/complex (but/so/when/because).",
   "why_skill_is_required":"Why one-word answers or fragments physically cannot advance this mechanic.",
   "skills":["B3.1 ..."],
   "tools":["comic_new / show_card / draw / build_activity"],
   "first_move":"Exact first on-screen card/comic setup + exact 1-sentence writing prompt (never a wh- chat question)."}
]}"""


def invent(situation: str, skills: str, rec: dict[str, Any], tried: list[str]) -> dict[str, Any]:
    """Invent 3 mechanics, then have the education critic screen them before the tutor sees them."""
    from .observers import targets_text, vet_ideas

    client = _client()
    system = INVENT_SYSTEM.replace("{targets}", targets_text())
    model_info = rec.get("model", {})
    prompt = json.dumps(
        {
            "child": {"name": rec.get("name"), "grade": rec.get("grade")},
            "parent_notes": [n["note"] for n in rec.get("parent_notes", [])],
            "focus_now": skills,
            "what_we_know": {
                k: model_info.get(k)
                for k in ("summary", "interests", "what_engages", "what_shuts_down", "writing", "typing")
            },
            "situation_right_now": situation,
            "already_tried_recently": tried,
        },
        ensure_ascii=False,
        indent=2,
    )
    for model in (INVENT_MODEL, FALLBACK_MODEL):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system, temperature=0.75, response_mime_type="application/json"
                ),
            )
            out = _json(resp.text)
            if isinstance(out, dict) and out.get("ideas"):
                out["_model"] = model
                try:
                    out["ideas"] = vet_ideas(out["ideas"])
                except Exception:
                    pass
                return out
        except Exception:
            continue
    return {"ideas": []}
