"""Skill Arcade v2.1 — Critic-Hardened Ontario Grade 3–4 Curriculum Games for Gemini Tutor.

6 bespoke interactive games with deep non-repeating banks (174 handcrafted items),
real spoken narration, Lenovo Yoga stylus support, Gemini grammar & semantic checking,
Leitner spaced-repetition sync, and strict anti-gaming integrity:
  1. Sentence Surgery       — 30 cases (10 run-ons, 10 fragments, 10 mechanics & dialogue)
  2. Word Forge             — 42 morphology words + spoken context sentences + Yoga pen OCR + Leitner SRS
  3. Homophone & Verb Ast.  — 36 orbital waves + live on-canvas Dreadnought Boss sentence wave
  4. Sentence Stretch Lab   — 20 compound/complex bridge & vivid verb labs
  5. Neon Turbo Typing      — 30 pure-ASCII sentences + rotating Leitner deck sentence injection
  6. Mystery Clue Detective — 16 inference, literary craft & POV dossiers (balanced clue indices 0..3)
"""

from __future__ import annotations

import base64
import copy
import datetime
import json
import random
import re
import time
from typing import Any

from google.genai import types

from . import arcade, curriculum_tracker, media, spelling_srs, thinking
from .config import FAST_MODEL, api_key, genai_client
from .projects import list_projects
from .record import load_learner, now_iso, save_learner

_SANDBOX_SKILL_STATE: dict[str, Any] = {}

# --------------------------------------------------------------------------- Game Catalog

GAME_CATALOG: list[dict[str, Any]] = [
    {
        "id": "sentence_surgery",
        "title": "Sentence Surgery",
        "subtitle": "Slash run-ons with a laser scalpel, repair fragment circuits & stamp dialogue punctuation",
        "icon": "⚔️",
        "accent": "#38bdf8",
        "glow": "rgba(56, 189, 248, 0.35)",
        "est_minutes": "3–4 min",
        "controls": "Stylus slash · Tap · Voice",
        "skills": ["B3.1_simple", "B3.1_boundaries", "B3.3_mechanics", "B3.3_dialogue", "D2.5_6_revision"],
        "skill_badges": ["Gr.3 B3.1 Sentences", "Gr.3 B3.3 Punctuation", "Dialogue"],
    },
    {
        "id": "word_forge",
        "title": "Word Forge",
        "subtitle": "Hammer Prefix + Base + Suffix runes into an enchanted blade, then spell from memory (type or Yoga pen!)",
        "icon": "🔥",
        "accent": "#f97316",
        "glow": "rgba(249, 115, 22, 0.35)",
        "est_minutes": "3–4 min",
        "controls": "Runes · Voice · Type / Pen",
        "skills": ["B2.1_2_orthography", "B2.3_morphology"],
        "skill_badges": ["Gr.3–4 B2.3 Morphology", "Leitner Spelling Deck"],
    },
    {
        "id": "homophone_asteroids",
        "title": "Homophone & Verb Asteroids",
        "subtitle": "60fps orbital defense! Blast cratered word asteroids, then shatter the live Dreadnought Boss with a real sentence",
        "icon": "☄️",
        "accent": "#a855f7",
        "glow": "rgba(168, 85, 247, 0.38)",
        "est_minutes": "3 min",
        "controls": "Tap · Keys 1-3 · Boss Beam",
        "skills": ["B3.2_grammar", "B2.4_vocabulary"],
        "skill_badges": ["Gr.3–4 B3.2 Grammar", "Homophones & Verbs"],
    },
    {
        "id": "sentence_stretch",
        "title": "Sentence Stretch Lab",
        "subtitle": "Power up the plasma reactor by fusing choppy sentences with causal bridges and vivid action verbs",
        "icon": "⚡",
        "accent": "#10b981",
        "glow": "rgba(16, 185, 129, 0.35)",
        "est_minutes": "3–4 min",
        "controls": "Bridges · Vivid Verbs · Voice",
        "skills": ["B3.1_compound", "B3.1_complex", "B2.4_vocabulary"],
        "skill_badges": ["Gr.3–4 B3.1 Compound/Complex", "Vivid Verbs"],
    },
    {
        "id": "typing_arena",
        "title": "Neon Turbo Typing",
        "subtitle": "60fps Toronto synthwave highway! Overtake rival racers with accuracy-gated Turbo Boost & finger guide",
        "icon": "🏎️",
        "accent": "#22d3ee",
        "glow": "rgba(34, 211, 238, 0.38)",
        "est_minutes": "2–3 min",
        "controls": "Keyboard · Rivals · Fingers",
        "skills": ["D2.2_keyboarding", "B3.3_mechanics"],
        "skill_badges": ["Gr.4 D2.2 Keyboarding", "Accuracy & Speed"],
    },
    {
        "id": "clue_detective",
        "title": "Mystery Clue Detective",
        "subtitle": "Drag glowing highlighter ink over the proof sentence, crack the case & slam CASE CLOSED with a causal verdict",
        "icon": "🔎",
        "accent": "#facc15",
        "glow": "rgba(250, 204, 21, 0.35)",
        "est_minutes": "4 min",
        "controls": "Stylus Highlight · Verdict",
        "skills": ["C2.3_inference", "C1.2_3_craft", "C1.5_pov"],
        "skill_badges": ["Gr.3–4 C2.3 Inference", "Literary Craft & POV"],
    },
]

GAME_BY_ID = {g["id"]: g for g in GAME_CATALOG}


# --------------------------------------------------------------------------- Helpers for Text & Morphology Hygiene

def _ascii_normalize(text: str) -> str:
    """Converts smart typography to clean standard keyboard ASCII so Typing Arena can never hard-lock."""
    s = (text or "").strip()
    repls = {
        "\u2014": ", ",  # em-dash -> comma + space
        "\u2013": "-",   # en-dash -> hyphen
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u00a0": " ",
    }
    for k, v in repls.items():
        s = s.replace(k, v)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_pure_typeable_ascii(text: str) -> bool:
    return bool(text) and all(32 <= ord(ch) <= 126 for ch in text)


def _blank_word_in_sentence(sentence: str, word: str) -> str:
    if not sentence or not word:
        return sentence or ""
    return re.sub(rf"\b{re.escape(word)}\b", "_____", sentence, flags=re.I)


def _safe_memory_hint(rule: str, unit: str, *, direct_memory: bool = False) -> str:
    """Returns a non-spoiling orthographic rule hint for Cover-Copy-Compare Memory Forge."""
    if direct_memory:
        return "Spell this tricky deck word cleanly from memory — listen carefully to every sound!"
    hints = {
        "double": "Rule reminder: 1-1-1 short vowel + single end consonant — double the final consonant before a vowel suffix!",
        "drop_e": "Rule reminder: Drop the silent final 'e' on the base word before adding a vowel suffix!",
        "y_to_i": "Rule reminder: Consonant + 'y' at the end of the base changes 'y' to 'i' before adding this suffix!",
        "keep": "Rule reminder: Keep every letter of the prefix, base, and suffix cleanly intact!",
    }
    return hints.get(rule, f"Focus on {unit} and spell carefully from memory!")


def _verify_forge_rule(prefix: str, base: str, suffix: str, rule: str, word: str) -> bool:
    """Mathematically verifies that prefix + base + suffix under `rule` produces `word`."""
    p = (prefix or "").strip().lower()
    b = (base or "").strip().lower()
    s = (suffix or "").strip().lower()
    w = (word or "").strip().lower()
    if not b or not w or not w.isalpha():
        return False
    if rule == "keep":
        return (p + b + s) == w
    if rule == "double":
        return len(b) >= 2 and (p + b + b[-1] + s) == w
    if rule == "drop_e":
        return b.endswith("e") and (p + b[:-1] + s) == w
    if rule == "y_to_i":
        return b.endswith("y") and (p + b[:-1] + "i" + s) == w
    return False


# --------------------------------------------------------------------------- Deep Curated Ontario Gr. 3-4 Banks (174 Items)

SENTENCE_SURGERY_BANK: list[dict[str, Any]] = [
    # ---- 10 Run-On Cases (Stylus Laser Slash) ----
    {"id": "ss_r01", "mode": "runon", "tier": 1, "skill": "B3.1_boundaries",
     "prompt": "SLASH right between the two mashed-together sentences!",
     "words": ["The", "creeper", "hissed", "it", "blew", "up", "the", "stone", "bridge."], "split_after": 2,
     "fixed": "The creeper hissed. It blew up the stone bridge.",
     "explain": "Two complete actions ('The creeper hissed' + 'It blew up...') need a period and a new capital!"},
    {"id": "ss_r02", "mode": "runon", "tier": 1, "skill": "B3.1_boundaries",
     "prompt": "SLASH between the two separate sentences!",
     "words": ["Maya", "grabbed", "her", "jetpack", "she", "launched", "off", "the", "CN", "Tower."], "split_after": 3,
     "fixed": "Maya grabbed her jetpack. She launched off the CN Tower.",
     "explain": "Split right after 'jetpack' so both complete thoughts stand cleanly on their own."},
    {"id": "ss_r03", "mode": "runon", "tier": 1, "skill": "B3.1_boundaries",
     "prompt": "SLASH this run-on in half cleanly!",
     "words": ["Our", "minecart", "jumped", "the", "broken", "rail", "we", "landed", "in", "deep", "water."], "split_after": 5,
     "fixed": "Our minecart jumped the broken rail. We landed in deep water.",
     "explain": "'Our minecart jumped the broken rail' is complete — start 'We landed...' as sentence two."},
    {"id": "ss_r04", "mode": "runon", "tier": 1, "skill": "B3.1_boundaries",
     "prompt": "Find the hidden seam and SLASH this run-on!",
     "words": ["The", "wolf", "barked", "at", "the", "skeleton", "Leo", "raised", "his", "iron", "shield."], "split_after": 5,
     "fixed": "The wolf barked at the skeleton. Leo raised his iron shield.",
     "explain": "Sentence one finishes after 'skeleton'; 'Leo raised...' begins the second sentence."},
    {"id": "ss_r05", "mode": "runon", "tier": 2, "skill": "B3.1_boundaries",
     "prompt": "SLASH where sentence one ends and sentence two starts!",
     "words": ["The", "rogue", "robot", "charged", "down", "Yonge", "Street", "citizens", "ducked", "behind", "a", "streetcar."], "split_after": 6,
     "fixed": "The rogue robot charged down Yonge Street. Citizens ducked behind a streetcar.",
     "explain": "Place a period after 'Street' and capitalize 'Citizens'."},
    {"id": "ss_r06", "mode": "runon", "tier": 2, "skill": "B3.1_boundaries",
     "prompt": "SLASH the run-on cleanly!",
     "words": ["A", "giant", "squid", "inked", "the", "submarine", "window", "the", "radar", "alarm", "started", "beeping."], "split_after": 6,
     "fixed": "A giant squid inked the submarine window. The radar alarm started beeping.",
     "explain": "Two independent clauses mashed together become a run-on — end after 'window'."},
    {"id": "ss_r07", "mode": "runon", "tier": 2, "skill": "B3.1_boundaries",
     "prompt": "Separate these two fused comic actions with one SLASH!",
     "words": ["Lightning", "struck", "the", "copper", "roof", "sparks", "showered", "across", "the", "courtyard."], "split_after": 4,
     "fixed": "Lightning struck the copper roof. Sparks showered across the courtyard.",
     "explain": "'Lightning struck the copper roof' finishes thought one; 'Sparks showered...' is thought two."},
    {"id": "ss_r08", "mode": "runon", "tier": 2, "skill": "B3.1_boundaries",
     "prompt": "SLASH cleanly between the two complete thoughts!",
     "words": ["The", "skateboard", "clipped", "a", "loose", "brick", "Kai", "tucked", "into", "a", "smooth", "roll."], "split_after": 5,
     "fixed": "The skateboard clipped a loose brick. Kai tucked into a smooth roll.",
     "explain": "Break cleanly after 'brick' so Kai's roll starts a crisp new sentence."},
    {"id": "ss_r09", "mode": "runon", "tier": 3, "skill": "B3.1_boundaries",
     "prompt": "Find the hidden sentence boundary and SLASH it!",
     "words": ["After", "midnight", "the", "Redstone", "door", "jammed", "nobody", "could", "escape", "the", "vault."], "split_after": 5,
     "fixed": "After midnight, the Redstone door jammed. Nobody could escape the vault.",
     "explain": "'After midnight' belongs to sentence one; sentence two begins at 'Nobody'."},
    {"id": "ss_r10", "mode": "runon", "tier": 3, "skill": "B3.1_boundaries",
     "prompt": "Careful! SLASH right between the two complete clauses!",
     "words": ["Beneath", "the", "frozen", "lake", "a", "hatch", "opened", "three", "glowing", "drones", "rose", "out."], "split_after": 6,
     "fixed": "Beneath the frozen lake, a hatch opened. Three glowing drones rose out.",
     "explain": "Keep the opener with 'a hatch opened', then start 'Three glowing drones...' cleanly."},

    # ---- 10 Fragment Repair Cases ----
    {"id": "ss_f01", "mode": "fragment", "tier": 1, "skill": "B3.1_simple",
     "prompt": "This fragment is missing a main action (verb)! Pick the repair that makes a complete sentence:",
     "broken": "The silver dragon on top of the obsidian tower.", "missing": "verb",
     "choices": [
         {"text": "The silver dragon on top of the obsidian tower breathed blue fire.", "ok": True},
         {"text": "On top of the very tall obsidian tower.", "ok": False, "why": "Still just a place — nobody is doing anything!"},
         {"text": "The silver dragon with giant glowing wings.", "ok": False, "why": "Adds detail, but still has no action verb."},
     ],
     "explain": "A complete sentence needs WHO/WHAT ('The silver dragon') + DOES WHAT ('breathed blue fire')."},
    {"id": "ss_f02", "mode": "fragment", "tier": 1, "skill": "B3.1_simple",
     "prompt": "Who did this action? Repair the missing subject!",
     "broken": "Sprinted past the laser grid before it shut.", "missing": "subject",
     "choices": [
         {"text": "Very quickly past the laser grid before it shut.", "ok": False, "why": "Still doesn't tell us WHO sprinted!"},
         {"text": "Captain Maple sprinted past the laser grid before it shut.", "ok": True},
         {"text": "Sprinting past the buzzing red laser grid.", "ok": False, "why": "An '-ing' phrase with no subject is still a fragment."},
     ],
     "explain": "Adding 'Captain Maple' supplies the explicit subject who performed the action."},
    {"id": "ss_f03", "mode": "fragment", "tier": 1, "skill": "B3.1_simple",
     "prompt": "Repair this broken fragment so something actually happens!",
     "broken": "Three armoured creepers hiding near the oak farmhouse.", "missing": "verb",
     "choices": [
         {"text": "Three armoured creepers crouched silently near the oak farmhouse.", "ok": True},
         {"text": "Near the quiet oak farmhouse at midnight.", "ok": False, "why": "Just a place and time — no subject or verb!"},
         {"text": "Three green armoured creepers with glowing eyes.", "ok": False, "why": "Describes the creepers, but still no main action verb!"},
     ],
     "explain": "Changing 'hiding' to the finite verb 'crouched' completes the circuit!"},
    {"id": "ss_f04", "mode": "fragment", "tier": 1, "skill": "B3.1_simple",
     "prompt": "This sentence lost its subject! Pick the complete fix:",
     "broken": "Tossed a water bucket down the cliff just in time.", "missing": "subject",
     "choices": [
         {"text": "Down the steep mossy cliff just in time.", "ok": False, "why": "Still missing WHO tossed the bucket!"},
         {"text": "Alex tossed a water bucket down the cliff just in time.", "ok": True},
         {"text": "Tossing a shiny iron water bucket fast.", "ok": False, "why": "No subject and no finite verb!"},
     ],
     "explain": "Adding 'Alex' gives the action a clear subject."},
    {"id": "ss_f05", "mode": "fragment", "tier": 2, "skill": "B3.1_simple",
     "prompt": "This 'Because...' clause was left hanging! Complete the thought:",
     "broken": "Because the diamond pickaxe broke right next to the lava.", "missing": "main_clause",
     "choices": [
         {"text": "Because the diamond pickaxe broke right next to the lava, Alex built a cobblestone bridge.", "ok": True},
         {"text": "Because the glowing hot lava bubbled underground.", "ok": False, "why": "Still starts with 'Because' and never tells what happened as a result!"},
         {"text": "Right next to the deep glowing lava pit.", "ok": False, "why": "That's just a location phrase, not a complete thought."},
     ],
     "explain": "A clause starting with 'Because' needs a main clause showing the result!"},
    {"id": "ss_f06", "mode": "fragment", "tier": 2, "skill": "B3.1_simple",
     "prompt": "Complete this hanging 'When...' fragment!",
     "broken": "When the alien disguise flickered in the stadium lights.", "missing": "main_clause",
     "choices": [
         {"text": "Inside the bright Rogers Centre stadium lights.", "ok": False, "why": "No subject and no action verb!"},
         {"text": "When the alien disguise flickered in the stadium lights, the crowd gasped.", "ok": True},
         {"text": "Flickering brightly under the huge stadium lights.", "ok": False, "why": "Still missing who did what."},
     ],
     "explain": "Pairing the 'When...' opener with 'the crowd gasped' completes the sentence!"},
    {"id": "ss_f07", "mode": "fragment", "tier": 2, "skill": "B3.1_simple",
     "prompt": "Finish this dangling 'Before...' fragment!",
     "broken": "Before the submarine hatch sealed against the ocean pressure.", "missing": "main_clause",
     "choices": [
         {"text": "Before the submarine hatch sealed against the ocean pressure, the diver pulled the sample crate inside.", "ok": True},
         {"text": "Against the freezing deep ocean pressure.", "ok": False, "why": "Only a prepositional phrase — nobody acts!"},
         {"text": "Before sealing the heavy steel hatch tight.", "ok": False, "why": "Leaves the reader hanging: what happened before?"},
     ],
     "explain": "An opener starting with 'Before' needs a main clause telling what happened!"},
    {"id": "ss_f08", "mode": "fragment", "tier": 2, "skill": "B3.1_simple",
     "prompt": "Fix this broken '-ing' fragment!",
     "broken": "Dodging laser beams across the rooftops of downtown Toronto.", "missing": "subject + verb",
     "choices": [
         {"text": "Across the neon rooftops of downtown Toronto.", "ok": False, "why": "Just a location phrase!"},
         {"text": "Zara dodged laser beams across the rooftops of downtown Toronto.", "ok": True},
         {"text": "Fast red laser beams flashing across the rooftops.", "ok": False, "why": "Still missing a main finite verb!"},
     ],
     "explain": "'Zara dodged...' supplies a clear subject and a past-tense main verb."},
    {"id": "ss_f09", "mode": "fragment", "tier": 3, "skill": "B3.1_simple",
     "prompt": "Repair this hanging 'Although...' fragment!",
     "broken": "Although the blizzard buried every road to the observatory.", "missing": "main_clause",
     "choices": [
         {"text": "Although the blizzard buried every road to the observatory, the scientists kept the telescope running.", "ok": True},
         {"text": "Although the thick snow drifted ten feet high.", "ok": False, "why": "Still a dependent 'Although' clause with no main result!"},
         {"text": "Every icy road leading to the mountain observatory.", "ok": False, "why": "Noun phrase only — no verb!"},
     ],
     "explain": "'Although' sets up a contrast, so it MUST be paired with the surprising main clause!"},
    {"id": "ss_f10", "mode": "fragment", "tier": 3, "skill": "B3.1_simple",
     "prompt": "Complete this hanging 'If...' condition!",
     "broken": "If the Redstone repeater flips one tick too late.", "missing": "main_clause",
     "choices": [
         {"text": "One single Redstone tick too late.", "ok": False, "why": "No subject, no verb!"},
         {"text": "If the Redstone repeater flips one tick too late, the secret piston door locks shut.", "ok": True},
         {"text": "Flipping the glowing Redstone repeater lever.", "ok": False, "why": "Still missing who/what happens!"},
     ],
     "explain": "An 'If...' condition must connect to a consequence clause to form a complete sentence."},

    # ---- 10 Mechanics & Dialogue Surgery Cases ----
    {"id": "ss_m01", "mode": "mechanics", "tier": 1, "skill": "B3.3_mechanics",
     "prompt": "Tap EVERY buggy word to fix capitals, apostrophes & end punctuation!",
     "tokens": [
         {"raw": "dylan", "fix": "Dylan", "bug": True, "hint": "Capitalize the start & proper name!"},
         {"raw": "didnt", "fix": "didn't", "bug": True, "hint": "Contraction 'did not' needs an apostrophe!"},
         {"raw": "drop", "fix": "drop", "bug": False},
         {"raw": "his", "fix": "his", "bug": False},
         {"raw": "shield", "fix": "shield.", "bug": True, "hint": "Add ending punctuation!"},
     ],
     "explain": "Sentence-start capital ('Dylan'), contraction apostrophe ('didn't'), and end period."},
    {"id": "ss_m02", "mode": "mechanics", "tier": 1, "skill": "B3.3_mechanics",
     "prompt": "Fix the 3 punctuation & capital bugs in this Toronto adventure!",
     "tokens": [
         {"raw": "we", "fix": "We", "bug": True, "hint": "Start every sentence with a capital letter."},
         {"raw": "cant", "fix": "can't", "bug": True, "hint": "'can not' contracts to can't!"},
         {"raw": "let", "fix": "let", "bug": False},
         {"raw": "the", "fix": "the", "bug": False},
         {"raw": "robots", "fix": "robots", "bug": False},
         {"raw": "escape", "fix": "escape!", "bug": True, "hint": "Add an exclamation mark or period at the end!"},
     ],
     "explain": "Fixed start capital ('We'), contraction ('can't'), and end mark ('escape!')."},
    {"id": "ss_m03", "mode": "mechanics", "tier": 1, "skill": "B3.3_mechanics",
     "prompt": "Stamp the 3 missing capitals and punctuation marks!",
     "tokens": [
         {"raw": "did", "fix": "Did", "bug": True, "hint": "Capitalize the first word!"},
         {"raw": "sam", "fix": "Sam", "bug": True, "hint": "Always capitalize names!"},
         {"raw": "craft", "fix": "craft", "bug": False},
         {"raw": "a", "fix": "a", "bug": False},
         {"raw": "compass", "fix": "compass?", "bug": True, "hint": "Questions end with a question mark (?)!"},
     ],
     "explain": "Capitalized start ('Did'), name ('Sam'), and ended the question with '?'."},
    {"id": "ss_m04", "mode": "mechanics", "tier": 2, "skill": "B3.3_mechanics",
     "prompt": "Fix the possessive apostrophe, city name & end mark!",
     "tokens": [
         {"raw": "the", "fix": "The", "bug": True, "hint": "Capitalize the first word!"},
         {"raw": "robots", "fix": "robot's", "bug": True, "hint": "The visor belongs to one robot: robot's!"},
         {"raw": "visor", "fix": "visor", "bug": False},
         {"raw": "glowed", "fix": "glowed", "bug": False},
         {"raw": "over", "fix": "over", "bug": False},
         {"raw": "toronto", "fix": "Toronto.", "bug": True, "hint": "Capitalize city name 'Toronto' and add a period!"},
     ],
     "explain": "Possessive singular takes 's ('robot's'), and city names like 'Toronto' are capitalized."},
    {"id": "ss_m05", "mode": "mechanics", "tier": 2, "skill": "B3.3_mechanics",
     "prompt": "Fix the 4 capital, contraction & end-mark bugs!",
     "tokens": [
         {"raw": "they", "fix": "They", "bug": True, "hint": "Capitalize the start!"},
         {"raw": "wouldnt", "fix": "wouldn't", "bug": True, "hint": "'would not' needs an apostrophe: wouldn't!"},
         {"raw": "enter", "fix": "enter", "bug": False},
         {"raw": "the", "fix": "the", "bug": False},
         {"raw": "nether", "fix": "Nether", "bug": True, "hint": "Capitalize the proper place name 'Nether'!"},
         {"raw": "without", "fix": "without", "bug": False},
         {"raw": "armour", "fix": "armour.", "bug": True, "hint": "Close the sentence with a period!"},
     ],
     "explain": "Start capital ('They'), contraction ('wouldn't'), proper place name ('Nether'), and end period."},
    {"id": "ss_m06", "mode": "mechanics", "tier": 2, "skill": "B3.3_dialogue",
     "prompt": "DIALOGUE SURGERY: Fix the 3 bugs in this spoken line!",
     "tokens": [
         {"raw": "Watch", "fix": "\"Watch", "bug": True, "hint": "Open quotation marks before the spoken words!"},
         {"raw": "out", "fix": "out", "bug": False},
         {"raw": "for", "fix": "for", "bug": False},
         {"raw": "lava", "fix": "lava!\"", "bug": True, "hint": "Close the exclamation & quotation marks!"},
         {"raw": "shouted", "fix": "shouted", "bug": False},
         {"raw": "kai", "fix": "Kai.", "bug": True, "hint": "Capitalize the speaker's name and add a period!"},
     ],
     "explain": "Put quotation marks around exact spoken words (\"Watch out for lava!\") and capitalize names."},
    {"id": "ss_m07", "mode": "mechanics", "tier": 2, "skill": "B3.3_dialogue",
     "prompt": "DIALOGUE SURGERY: Stamp the missing quotation marks, comma & capitals!",
     "tokens": [
         {"raw": "the", "fix": "\"The", "bug": True, "hint": "Open quotes AND capitalize the first spoken word!"},
         {"raw": "portal", "fix": "portal", "bug": False},
         {"raw": "is", "fix": "is", "bug": False},
         {"raw": "closing", "fix": "closing,\"", "bug": True, "hint": "Comma + closing quote before 'warned'!"},
         {"raw": "warned", "fix": "warned", "bug": False},
         {"raw": "nova", "fix": "Nova.", "bug": True, "hint": "Capitalize Nova and end with a period!"},
     ],
     "explain": "Use a comma inside the closing quote before a dialogue tag like 'warned Nova.'"},
    {"id": "ss_m08", "mode": "mechanics", "tier": 2, "skill": "B3.3_dialogue",
     "prompt": "DIALOGUE SURGERY: Fix this excited question!",
     "tokens": [
         {"raw": "where", "fix": "\"Where", "bug": True, "hint": "Open quotes and capitalize 'Where'!"},
         {"raw": "did", "fix": "did", "bug": False},
         {"raw": "the", "fix": "the", "bug": False},
         {"raw": "drone", "fix": "drone", "bug": False},
         {"raw": "go", "fix": "go?\"", "bug": True, "hint": "Put ? inside the closing quotation marks!"},
         {"raw": "asked", "fix": "asked", "bug": False},
         {"raw": "maya", "fix": "Maya.", "bug": True, "hint": "Capitalize Maya and add a period!"},
     ],
     "explain": "Question marks stay INSIDE the closing quotation marks: \"Where did the drone go?\" asked Maya."},
    {"id": "ss_m09", "mode": "mechanics", "tier": 3, "skill": "B3.3_dialogue",
     "prompt": "DIALOGUE SURGERY: Speaker comes FIRST — fix the comma, quotes & end mark!",
     "tokens": [
         {"raw": "Leo", "fix": "Leo", "bug": False},
         {"raw": "whispered", "fix": "whispered,", "bug": True, "hint": "Put a comma right after 'whispered' before the quote!"},
         {"raw": "dont", "fix": "\"Don't", "bug": True, "hint": "Open quotes, capitalize 'Don't', and add the apostrophe!"},
         {"raw": "wake", "fix": "wake", "bug": False},
         {"raw": "the", "fix": "the", "bug": False},
         {"raw": "warden", "fix": "Warden!\"", "bug": True, "hint": "Capitalize Warden, add '!' and close quotes!"},
     ],
     "explain": "When the speaker tag comes first, put a comma after it: Leo whispered, \"Don't wake the Warden!\""},
    {"id": "ss_m10", "mode": "mechanics", "tier": 3, "skill": "B3.3_mechanics",
     "prompt": "Fix the commas in a list, start capital & end period!",
     "tokens": [
         {"raw": "pack", "fix": "Pack", "bug": True, "hint": "Capitalize the first word!"},
         {"raw": "torches", "fix": "torches,", "bug": True, "hint": "Separate items in a list with commas!"},
         {"raw": "cobblestone", "fix": "cobblestone,", "bug": True, "hint": "Add a comma before 'and'!"},
         {"raw": "and", "fix": "and", "bug": False},
         {"raw": "apples", "fix": "apples.", "bug": True, "hint": "End with a period!"},
     ],
     "explain": "Use commas to separate three or more items in a series: torches, cobblestone, and apples."},
]


WORD_FORGE_CURRICULUM_BANK: list[dict[str, Any]] = [
    # ---- 1-1-1 Consonant Doubling (10 words) ----
    {"id": "wf_01", "word": "trapped", "prefix": "", "base": "trap", "suffix": "ed", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "context_sentence": "The skeleton was trapped behind an iron gate.",
     "note": "1-1-1 rule: 1 syllable, 1 short vowel (a), 1 end consonant (p) -> double 'p' before -ed!"},
    {"id": "wf_02", "word": "stopped", "prefix": "", "base": "stop", "suffix": "ed", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "context_sentence": "The streetcar stopped right outside Union Station.",
     "note": "Short vowel 'o' + single 'p' -> double the 'p' before adding vowel suffix -ed."},
    {"id": "wf_03", "word": "running", "prefix": "", "base": "run", "suffix": "ing", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "context_sentence": "The generator is running at full power now.",
     "note": "Short 'u' + single 'n' -> double 'n' before -ing."},
    {"id": "wf_04", "word": "grabbing", "prefix": "", "base": "grab", "suffix": "ing", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "context_sentence": "He escaped after grabbing the glowing diamond.",
     "note": "Short 'a' + single 'b' -> double 'b' before -ing so the vowel stays short!"},
    {"id": "wf_05", "word": "unstoppable", "prefix": "un", "base": "stop", "suffix": "able", "rule": "double", "unit": "B2.3 Prefix + Doubling",
     "context_sentence": "With enchanted armour, the hero felt unstoppable.",
     "note": "Prefix 'un-' + 'stop' (double the 'p'!) + '-able'."},
    {"id": "wf_06", "word": "slipped", "prefix": "", "base": "slip", "suffix": "ed", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "context_sentence": "Her boots slipped across the wet cavern stone.",
     "note": "Short 'i' + single 'p' -> double 'p' before -ed so the vowel stays short."},
    {"id": "wf_07", "word": "dropped", "prefix": "", "base": "drop", "suffix": "ed", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "context_sentence": "The drone dropped a supply crate onto the roof.",
     "note": "1-1-1 doubling: short 'o' + single 'p' -> double 'p' before -ed!"},
    {"id": "wf_08", "word": "spinning", "prefix": "", "base": "spin", "suffix": "ing", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "context_sentence": "The radar dish kept spinning through the blizzard.",
     "note": "Short 'i' + single 'n' -> double 'n' before -ing."},
    {"id": "wf_09", "word": "planner", "prefix": "", "base": "plan", "suffix": "er", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "context_sentence": "Maya was the sharpest mission planner on the team.",
     "note": "Double the 'n' in 'plan' before '-er' so the short vowel stays sharp!"},
    {"id": "wf_10", "word": "swimmer", "prefix": "", "base": "swim", "suffix": "er", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "context_sentence": "A fast swimmer can cross the underwater tunnel easily.",
     "note": "Short 'i' + single 'm' -> double 'm' before '-er'."},

    # ---- Drop Silent-e Before Vowel Suffix (10 words) ----
    {"id": "wf_11", "word": "exploding", "prefix": "", "base": "explode", "suffix": "ing", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "context_sentence": "We sprinted away from the exploding TNT block.",
     "note": "Drop the silent 'e' on the base before adding vowel suffix '-ing'."},
    {"id": "wf_12", "word": "survivor", "prefix": "", "base": "survive", "suffix": "or", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "context_sentence": "Only one explorer was a survivor of the ice storm.",
     "note": "Drop silent 'e' on the base before adding agent suffix '-or'."},
    {"id": "wf_13", "word": "chasing", "prefix": "", "base": "chase", "suffix": "ing", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "context_sentence": "Three cyber-hounds were chasing the hoverbike.",
     "note": "Drop silent 'e' on the base before adding '-ing'."},
    {"id": "wf_14", "word": "gliding", "prefix": "", "base": "glide", "suffix": "ing", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "context_sentence": "The hawk was gliding high over Lake Ontario.",
     "note": "Drop silent 'e' on the base before adding '-ing'."},
    {"id": "wf_15", "word": "invader", "prefix": "", "base": "invade", "suffix": "er", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "context_sentence": "Our bio-scanner spotted an alien invader in disguise.",
     "note": "Drop silent 'e' on the base before adding '-er'."},
    {"id": "wf_16", "word": "upgrading", "prefix": "up", "base": "grade", "suffix": "ing", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "context_sentence": "She spent an hour upgrading her Netherite sword.",
     "note": "Prefix + base (drop the silent 'e'!) + '-ing'."},
    {"id": "wf_17", "word": "misplaced", "prefix": "mis", "base": "place", "suffix": "ed", "rule": "drop_e", "unit": "B2.3 Prefix + Drop-e",
     "context_sentence": "Leo misplaced his map right before entering the cave.",
     "note": "Prefix 'mis-' (wrongly) + base (drop silent 'e'!) + '-ed'."},
    {"id": "wf_18", "word": "escaping", "prefix": "", "base": "escape", "suffix": "ing", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "context_sentence": "The rogue android is escaping down the tunnel!",
     "note": "Drop silent 'e' on the base before adding vowel suffix '-ing'."},
    {"id": "wf_19", "word": "bravest", "prefix": "", "base": "brave", "suffix": "est", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "context_sentence": "The bravest knight stepped onto the obsidian bridge.",
     "note": "Drop silent 'e' on the base before adding '-est' (no double 'e'!)."},
    {"id": "wf_20", "word": "creating", "prefix": "", "base": "create", "suffix": "ing", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "context_sentence": "He is creating a brand-new 100-page comic book.",
     "note": "Drop silent 'e' on the base before '-ing'."},

    # ---- Change y to i (10 words) ----
    {"id": "wf_21", "word": "heaviest", "prefix": "", "base": "heavy", "suffix": "est", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "context_sentence": "An anvil is the heaviest block in the workshop.",
     "note": "Consonant + y at the end -> change 'y' to 'i' before adding '-est'."},
    {"id": "wf_22", "word": "supplies", "prefix": "", "base": "supply", "suffix": "es", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "context_sentence": "We packed extra torches and food supplies.",
     "note": "Consonant + y -> change 'y' to 'i' and add '-es'."},
    {"id": "wf_23", "word": "carried", "prefix": "", "base": "carry", "suffix": "ed", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "context_sentence": "The iron golem carried the broken cart back to town.",
     "note": "Consonant + y -> change 'y' to 'i' before '-ed'."},
    {"id": "wf_24", "word": "enemies", "prefix": "", "base": "enemy", "suffix": "es", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "context_sentence": "Three robotic enemies blocked the stadium exit.",
     "note": "Consonant + y -> change 'y' to 'i' and add '-es'."},
    {"id": "wf_25", "word": "happily", "prefix": "", "base": "happy", "suffix": "ly", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "context_sentence": "The rescued puppy barked happily at the crowd.",
     "note": "Consonant + y -> change 'y' to 'i' before adding '-ly'."},
    {"id": "wf_26", "word": "emptied", "prefix": "", "base": "empty", "suffix": "ed", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "context_sentence": "Someone emptied the diamond chest before sunrise.",
     "note": "Consonant + y -> change 'y' to 'i' before '-ed'."},
    {"id": "wf_27", "word": "noisier", "prefix": "", "base": "noisy", "suffix": "er", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "context_sentence": "The second rocket engine was even noisier than the first.",
     "note": "Consonant + y -> change 'y' to 'i' before '-er'."},
    {"id": "wf_28", "word": "replied", "prefix": "", "base": "reply", "suffix": "ed", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "context_sentence": "Mission control replied with the secret launch code.",
     "note": "Consonant + y -> change 'y' to 'i' before '-ed'."},
    {"id": "wf_29", "word": "hurried", "prefix": "", "base": "hurry", "suffix": "ed", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "context_sentence": "They hurried inside before the thunderstorm arrived.",
     "note": "Consonant + y -> change 'y' to 'i' before '-ed'."},
    {"id": "wf_30", "word": "mysteries", "prefix": "", "base": "mystery", "suffix": "es", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "context_sentence": "Detective Nova solved three impossible mysteries this week.",
     "note": "Consonant + y -> change 'y' to 'i' and add '-es'."},

    # ---- Keep Base / Prefixes / Bound Roots / Positional -tch (12 words) ----
    {"id": "wf_31", "word": "unbreakable", "prefix": "un", "base": "break", "suffix": "able", "rule": "keep", "unit": "B2.3 Prefix + Suffix",
     "context_sentence": "The obsidian fortress walls were unbreakable.",
     "note": "Three clean morphemes — prefix + base + suffix all stay unchanged!"},
    {"id": "wf_32", "word": "disappear", "prefix": "dis", "base": "appear", "suffix": "", "rule": "keep", "unit": "B2.3 Prefixes",
     "context_sentence": "Endermen can disappear in a flash of purple sparks.",
     "note": "Prefix 'dis-' (away) attaches cleanly — just one 's' and double 'p'!"},
    {"id": "wf_33", "word": "rebuilding", "prefix": "re", "base": "build", "suffix": "ing", "rule": "keep", "unit": "B2.3 Prefix + Suffix",
     "context_sentence": "The villagers started rebuilding the tower after the blast.",
     "note": "Prefix 're-' (again) + base + '-ing' — keep every base letter intact!"},
    {"id": "wf_34", "word": "fearless", "prefix": "", "base": "fear", "suffix": "less", "rule": "keep", "unit": "B2.3 Suffixes",
     "context_sentence": "That fearless pilot flew straight through the canyon.",
     "note": "Base + consonant suffix '-less' (without) — zero spelling change needed."},
    {"id": "wf_35", "word": "destruction", "prefix": "de", "base": "struct", "suffix": "ion", "rule": "keep", "unit": "Gr.4 B2.1 Bound Roots",
     "context_sentence": "The giant laser nearly caused total destruction.",
     "note": "Latin root meaning 'build' + reverse prefix + noun suffix '-ion'."},
    {"id": "wf_36", "word": "erupted", "prefix": "e", "base": "rupt", "suffix": "ed", "rule": "keep", "unit": "Gr.4 B2.1 Bound Roots",
     "context_sentence": "A hidden volcano erupted behind the ice island.",
     "note": "Latin root meaning 'burst' + 'e-' (out) + past suffix '-ed'."},
    {"id": "wf_37", "word": "switched", "prefix": "", "base": "switch", "suffix": "ed", "rule": "keep", "unit": "B2.2 Positional -tch",
     "context_sentence": "Kai switched the lever and opened the vault.",
     "note": "Right after a short vowel ('i'), /ch/ is spelled '-tch' — keep base clean!"},
    {"id": "wf_38", "word": "portable", "prefix": "", "base": "port", "suffix": "able", "rule": "keep", "unit": "Gr.4 B2.1 Bound Roots",
     "context_sentence": "A portable solar charger kept the drone flying.",
     "note": "Latin root meaning 'carry' + '-able' (can be carried) — keep base clean!"},
    {"id": "wf_39", "word": "unlocked", "prefix": "un", "base": "lock", "suffix": "ed", "rule": "keep", "unit": "B2.2 Positional -ck",
     "context_sentence": "She unlocked the secret basement with a golden key.",
     "note": "Prefix 'un-' + '-ck' base + '-ed' — base stays clean!"},
    {"id": "wf_40", "word": "inspection", "prefix": "in", "base": "spect", "suffix": "ion", "rule": "keep", "unit": "Gr.4 B2.1 Bound Roots",
     "context_sentence": "Every bridge passes a careful safety inspection.",
     "note": "Latin root meaning 'look' + 'in-' + '-ion' — keep all morphemes intact!"},
    {"id": "wf_41", "word": "distraction", "prefix": "dis", "base": "tract", "suffix": "ion", "rule": "keep", "unit": "Gr.4 B2.1 Bound Roots",
     "context_sentence": "Tossing a snowball created the perfect distraction.",
     "note": "Latin root meaning 'pull' + 'dis-' + '-ion' — keep all morphemes intact!"},
    {"id": "wf_42", "word": "recharged", "prefix": "re", "base": "charge", "suffix": "ed", "rule": "drop_e", "unit": "B2.3 Prefix + Drop-e",
     "context_sentence": "Our orbital plasma turret recharged in three seconds.",
     "note": "Prefix 're-' (again) + base (drop silent 'e'!) + '-ed'."},
]


HOMOPHONE_ASTEROIDS_BANK: list[dict[str, Any]] = [
    # ---- Homophones (22 waves) ----
    {"id": "ha_01", "tier": 1, "skill": "B2.4_vocabulary", "sentence": "The knights dropped ___ shields when the dragon roared.",
     "options": ["their", "there", "they're"], "answer": "their", "explain": "'their' = belongs to them (their shields)!"},
    {"id": "ha_02", "tier": 1, "skill": "B2.4_vocabulary", "sentence": "Watch out, ___ is a hidden pressure plate by the door!",
     "options": ["there", "their", "they're"], "answer": "there", "explain": "'there' points to a place (has 'here' inside it!)."},
    {"id": "ha_03", "tier": 1, "skill": "B2.4_vocabulary", "sentence": "Hurry up, ___ already building the Nether portal!",
     "options": ["they're", "their", "there"], "answer": "they're", "explain": "'they're' = 'they are' ('they are already building')."},
    {"id": "ha_04", "tier": 1, "skill": "B2.4_vocabulary", "sentence": "My backpack was ___ heavy to carry up the cliff.",
     "options": ["too", "to", "two"], "answer": "too", "explain": "'too' means 'excessively' or 'also' (extra 'o' = extra much!)."},
    {"id": "ha_05", "tier": 1, "skill": "B2.4_vocabulary", "sentence": "We crafted ___ iron swords before entering the cave.",
     "options": ["two", "too", "to"], "answer": "two", "explain": "'two' is the number 2."},
    {"id": "ha_06", "tier": 1, "skill": "B2.4_vocabulary", "sentence": "Sprint ___ the beacon before the storm wall closes!",
     "options": ["to", "too", "two"], "answer": "to", "explain": "'to' shows direction or movement toward something."},
    {"id": "ha_07", "tier": 1, "skill": "B2.4_vocabulary", "sentence": "Grab ___ flashlight before the power grid cuts out!",
     "options": ["your", "you're", "yore"], "answer": "your", "explain": "'your' shows ownership (your flashlight)."},
    {"id": "ha_08", "tier": 1, "skill": "B2.4_vocabulary", "sentence": "Wait, ___ the only pilot who knows the secret code!",
     "options": ["you're", "your", "yore"], "answer": "you're", "explain": "'you're' = 'you are' ('you are the only pilot')."},
    {"id": "ha_09", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "The rover spun ___ wheels in the Martian sand.",
     "options": ["its", "it's", "its'"], "answer": "its", "explain": "Possessive 'its' has NO apostrophe (just like 'his' and 'her')!"},
    {"id": "ha_10", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "Check the radar, ___ tracking three incoming drones!",
     "options": ["it's", "its", "is"], "answer": "it's", "explain": "'it's' = 'it is' ('it is tracking')."},
    {"id": "ha_11", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "Do you ___ where the hidden Redstone switch is?",
     "options": ["know", "no", "now"], "answer": "know", "explain": "'know' (with silent k, like 'knowledge') means to understand."},
    {"id": "ha_12", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "We could ___ the wolf howling across the snow biome.",
     "options": ["hear", "here", "hare"], "answer": "hear", "explain": "'hear' has the word 'ear' right inside it!"},
    {"id": "ha_13", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "Set the crafting table right ___ beside the torch.",
     "options": ["here", "hear", "hare"], "answer": "here", "explain": "'here' names a place (right in this spot)."},
    {"id": "ha_14", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "She ___ a flaming arrow straight into the target block.",
     "options": ["threw", "through", "thorough"], "answer": "threw", "explain": "'threw' is the past tense of 'throw'."},
    {"id": "ha_15", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "The tunnel led straight ___ the hollow mountain.",
     "options": ["through", "threw", "true"], "answer": "through", "explain": "'through' means passing from one side to the other."},
    {"id": "ha_16", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "The storm knocked out power across the ___ city.",
     "options": ["whole", "hole", "hold"], "answer": "whole", "explain": "'whole' (with 'w') means complete/entire; 'hole' is an opening."},
    {"id": "ha_17", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "A creeper blast left a huge ___ in our courtyard.",
     "options": ["hole", "whole", "hold"], "answer": "hole", "explain": "'hole' (no 'w') is an empty pit or opening."},
    {"id": "ha_18", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "Always ___ your helmet before testing the hoverboard!",
     "options": ["wear", "where", "were"], "answer": "wear", "explain": "'wear' means to have clothing or gear on your body."},
    {"id": "ha_19", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "Pull the emergency ___ before the minecart hits the wall!",
     "options": ["brake", "break", "brick"], "answer": "brake", "explain": "'brake' slows down a vehicle; 'break' means smash/snap."},
    {"id": "ha_20", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "You need an iron pickaxe to ___ diamond ore cleanly.",
     "options": ["break", "brake", "brook"], "answer": "break", "explain": "'break' means shatter or crack apart."},
    {"id": "ha_21", "tier": 3, "skill": "B2.4_vocabulary", "sentence": "Check the ___ forecast before launching the high-altitude balloon.",
     "options": ["weather", "whether", "wether"], "answer": "weather", "explain": "'weather' is rain, wind, and sun; 'whether' introduces a choice."},
    {"id": "ha_22", "tier": 3, "skill": "B2.4_vocabulary", "sentence": "Only one ___ of the glowing cipher map was still missing.",
     "options": ["piece", "peace", "peaks"], "answer": "piece", "explain": "'piece' (has 'pie' in it!) means a part of something."},

    # ---- Irregular Past Tense & Subject-Verb Agreement (14 waves) ----
    {"id": "ha_23", "tier": 1, "skill": "B3.2_grammar", "sentence": "Yesterday, Leo ___ a rare golden axolotl in the cave.",
     "options": ["caught", "catched", "catch"], "answer": "caught", "explain": "'catch' is irregular in past tense: 'caught' (like 'taught')."},
    {"id": "ha_24", "tier": 1, "skill": "B3.2_grammar", "sentence": "Our goalkeeper ___ across the net and blocked the shot!",
     "options": ["flew", "flied", "flowed"], "answer": "flew", "explain": "Past tense of 'fly' is 'flew' (not 'flied')."},
    {"id": "ha_25", "tier": 1, "skill": "B3.2_grammar", "sentence": "She ___ extra torches so nobody would get lost underground.",
     "options": ["brought", "brang", "bringed"], "answer": "brought", "explain": "Past tense of 'bring' is 'brought'."},
    {"id": "ha_26", "tier": 1, "skill": "B3.2_grammar", "sentence": "The coach ___ us how to aim a wrist shot accurately.",
     "options": ["taught", "teached", "tought"], "answer": "taught", "explain": "Past tense of 'teach' is 'taught'."},
    {"id": "ha_27", "tier": 2, "skill": "B3.2_grammar", "sentence": "The two robotic guards ___ watching the main gate.",
     "options": ["were", "was", "is"], "answer": "were", "explain": "Plural subject ('two robotic guards') takes 'were'."},
    {"id": "ha_28", "tier": 2, "skill": "B3.2_grammar", "sentence": "Each explorer ___ a glowing compass before sunset.",
     "options": ["carries", "carry", "carrying"], "answer": "carries", "explain": "'Each explorer' is singular, so the verb takes '-ies' ('carries')."},
    {"id": "ha_29", "tier": 2, "skill": "B3.2_grammar", "sentence": "Dylan ___ an awesome comic cover using the Lenovo pen.",
     "options": ["drew", "drawed", "drawn"], "answer": "drew", "explain": "Simple past tense of 'draw' is 'drew'."},
    {"id": "ha_30", "tier": 2, "skill": "B3.2_grammar", "sentence": "The giant bamboo tower ___ six blocks taller overnight!",
     "options": ["grew", "growed", "grown"], "answer": "grew", "explain": "Past tense of 'grow' is 'grew'."},
    {"id": "ha_31", "tier": 2, "skill": "B3.2_grammar", "sentence": "Maya ___ across the icy cavern pool to reach the chest.",
     "options": ["swam", "swimmed", "swum"], "answer": "swam", "explain": "Simple past tense of 'swim' is 'swam'."},
    {"id": "ha_32", "tier": 2, "skill": "B3.2_grammar", "sentence": "The whole squad ___ loud cheers when the boss shattered!",
     "options": ["shouted", "shouting", "shout"], "answer": "shouted", "explain": "Completed past action uses '-ed' ('shouted')."},
    {"id": "ha_33", "tier": 3, "skill": "B3.2_grammar", "sentence": "Before the bridge collapsed, the squad had already ___ across.",
     "options": ["driven", "drove", "drived"], "answer": "driven", "explain": "With 'had', use the past participle 'driven' ('had driven')."},
    {"id": "ha_34", "tier": 3, "skill": "B3.2_grammar", "sentence": "Someone had ___ the iron lock before the alarm triggered.",
     "options": ["broken", "broke", "breaked"], "answer": "broken", "explain": "With 'had', use the past participle 'broken' ('had broken')."},
    {"id": "ha_35", "tier": 3, "skill": "B3.2_grammar", "sentence": "Neither of the drones ___ enough battery to reach the roof.",
     "options": ["has", "have", "having"], "answer": "has", "explain": "'Neither' is singular, so it pairs with 'has'!"},
    {"id": "ha_36", "tier": 3, "skill": "B3.2_grammar", "sentence": "She had already ___ three chapters before dinner started.",
     "options": ["written", "wrote", "writed"], "answer": "written", "explain": "With 'had', use the past participle 'written' ('had written')."},
]


SENTENCE_STRETCH_BANK: list[dict[str, Any]] = [
    {"id": "st_01", "tier": 1, "skill": "B3.1_compound",
     "clause_a": "The creeper hissed behind the wall.", "clause_b": "Alex jumped into the river.", "weak_verb": "jumped",
     "verb_upgrades": [{"word": "dove", "power": 2, "ok": True}, {"word": "vaulted", "power": 2, "ok": True}, {"word": "walked", "power": 0, "ok": False}],
     "bridges": [{"word": "so", "kind": "compound", "ok": True, "why": "'so' shows the exact cause-and-effect result!"},
                 {"word": "but", "kind": "compound", "ok": False, "why": "'but' shows contrast — jumping into the river was the RESULT!"},
                 {"word": "or", "kind": "compound", "ok": False, "why": "'or' offers a choice instead of showing a result."}]},
    {"id": "st_02", "tier": 1, "skill": "B3.1_compound",
     "clause_a": "Our drone's battery was almost dead.", "clause_b": "It still made the rooftop landing.", "weak_verb": "made",
     "verb_upgrades": [{"word": "nailed", "power": 2, "ok": True}, {"word": "pulled off", "power": 2, "ok": True}, {"word": "did", "power": 0, "ok": False}],
     "bridges": [{"word": "but", "kind": "compound", "ok": True, "why": "'but' connects two surprising, contrasting ideas!"},
                 {"word": "so", "kind": "compound", "ok": False, "why": "A dead battery wouldn't CAUSE a safe landing — use contrast!"},
                 {"word": "because", "kind": "complex", "ok": False, "why": "The landing didn't cause the dead battery!"}]},
    {"id": "st_03", "tier": 1, "skill": "B3.1_compound",
     "clause_a": "The storm knocked out the streetlights.", "clause_b": "Our robot team turned on its floodlights.", "weak_verb": "turned on",
     "verb_upgrades": [{"word": "activated", "power": 2, "ok": True}, {"word": "ignited", "power": 2, "ok": True}, {"word": "used", "power": 0, "ok": False}],
     "bridges": [{"word": "so", "kind": "compound", "ok": True, "why": "'so' links the blackout directly to what they did next!"},
                 {"word": "but", "kind": "compound", "ok": False, "why": "Turning on floodlights makes total sense in a blackout — not contrast!"},
                 {"word": "although", "kind": "complex", "ok": False, "why": "Use a result connector, not contrast!"}]},
    {"id": "st_04", "tier": 1, "skill": "B3.1_compound",
     "clause_a": "The cave looked totally empty.", "clause_b": "A spider came down from the ceiling.", "weak_verb": "came",
     "verb_upgrades": [{"word": "dropped", "power": 2, "ok": True}, {"word": "lunged", "power": 2, "ok": True}, {"word": "went", "power": 0, "ok": False}],
     "bridges": [{"word": "but", "kind": "compound", "ok": True, "why": "'but' highlights the surprise twist!"},
                 {"word": "so", "kind": "compound", "ok": False, "why": "Looking empty didn't CAUSE the spider to drop!"},
                 {"word": "because", "kind": "complex", "ok": False, "why": "Show the surprise twist with a contrast bridge!"}]},
    {"id": "st_05", "tier": 2, "skill": "B3.1_complex",
     "clause_a": "The whole stadium went dark.", "clause_b": "A rogue android cut the main cable.", "weak_verb": "cut",
     "verb_upgrades": [{"word": "severed", "power": 2, "ok": True}, {"word": "sliced", "power": 2, "ok": True}, {"word": "touched", "power": 0, "ok": False}],
     "bridges": [{"word": "because", "kind": "complex", "ok": True, "why": "'because' explains the exact reason the stadium went dark!"},
                 {"word": "but", "kind": "compound", "ok": False, "why": "Cutting the cable explains WHY it went dark — use cause!"},
                 {"word": "until", "kind": "complex", "ok": False, "why": "'until' reverses the timing!"}]},
    {"id": "st_06", "tier": 2, "skill": "B3.1_complex",
     "clause_a": "Nova grabbed the golden key.", "clause_b": "The stone trapdoor snapped shut.", "weak_verb": "grabbed",
     "verb_upgrades": [{"word": "snatched", "power": 2, "ok": True}, {"word": "yanked", "power": 2, "ok": True}, {"word": "got", "power": 0, "ok": False}],
     "bridges": [{"word": "before", "kind": "complex", "ok": True, "why": "'before' builds real suspense by showing exact timing!"},
                 {"word": "because", "kind": "complex", "ok": False, "why": "The trapdoor closing wasn't the reason — show the timing!"},
                 {"word": "although", "kind": "complex", "ok": False, "why": "She grabbed it JUST IN TIME!"}]},
    {"id": "st_07", "tier": 2, "skill": "B3.1_complex",
     "clause_a": "The iron golem guarded the village gate.", "clause_b": "The builders fixed the broken wall.", "weak_verb": "fixed",
     "verb_upgrades": [{"word": "reinforced", "power": 2, "ok": True}, {"word": "rebuilt", "power": 2, "ok": True}, {"word": "did", "power": 0, "ok": False}],
     "bridges": [{"word": "while", "kind": "complex", "ok": True, "why": "'while' shows two heroic actions happening at the exact same time!"},
                 {"word": "so", "kind": "compound", "ok": False, "why": "Guarding didn't cause the repair — both happened at once!"},
                 {"word": "unless", "kind": "complex", "ok": False, "why": "'unless' changes the whole meaning."}]},
    {"id": "st_08", "tier": 2, "skill": "B3.1_complex",
     "clause_a": "The crowd cheered loudly.", "clause_b": "The goalie stopped the breakaway shot.", "weak_verb": "stopped",
     "verb_upgrades": [{"word": "snagged", "power": 2, "ok": True}, {"word": "deflected", "power": 2, "ok": True}, {"word": "got", "power": 0, "ok": False}],
     "bridges": [{"word": "when", "kind": "complex", "ok": True, "why": "'when' connects the exact moment of the save to the cheer!"},
                 {"word": "but", "kind": "compound", "ok": False, "why": "Cheering matches a huge save — no contrast!"},
                 {"word": "unless", "kind": "complex", "ok": False, "why": "That flips the meaning!"}]},
    {"id": "st_09", "tier": 2, "skill": "B3.1_complex",
     "clause_a": "The volcano rumbled beneath our camp.", "clause_b": "We moved our gear to higher ground.", "weak_verb": "moved",
     "verb_upgrades": [{"word": "hauled", "power": 2, "ok": True}, {"word": "rushed", "power": 2, "ok": True}, {"word": "put", "power": 0, "ok": False}],
     "bridges": [{"word": "so", "kind": "compound", "ok": True, "why": "'so' shows the direct smart reaction to the rumble!"},
                 {"word": "but", "kind": "compound", "ok": False, "why": "Moving to high ground matches the danger — not a contrast!"},
                 {"word": "or", "kind": "compound", "ok": False, "why": "'or' turns it into an either/or choice."}]},
    {"id": "st_10", "tier": 2, "skill": "B3.1_complex",
     "clause_a": "The secret vault will stay locked.", "clause_b": "You match all three emerald runes.", "weak_verb": "match",
     "verb_upgrades": [{"word": "align", "power": 2, "ok": True}, {"word": "synchronize", "power": 2, "ok": True}, {"word": "get", "power": 0, "ok": False}],
     "bridges": [{"word": "until", "kind": "complex", "ok": True, "why": "'until' sets the exact condition that unlocks the vault!"},
                 {"word": "so", "kind": "compound", "ok": False, "why": "Staying locked doesn't cause you to align runes!"},
                 {"word": "and", "kind": "compound", "ok": False, "why": "'until' shows the true timing rule!"}]},
    {"id": "st_11", "tier": 2, "skill": "B3.1_complex",
     "clause_a": "The Mars rover paused on the ridge.", "clause_b": "Its cameras looked at the red canyon.", "weak_verb": "looked at",
     "verb_upgrades": [{"word": "scanned", "power": 2, "ok": True}, {"word": "surveyed", "power": 2, "ok": True}, {"word": "saw", "power": 0, "ok": False}],
     "bridges": [{"word": "while", "kind": "complex", "ok": True, "why": "'while' shows pausing and scanning happening together!"},
                 {"word": "but", "kind": "compound", "ok": False, "why": "Pausing helps cameras scan — they aren't opposites!"},
                 {"word": "unless", "kind": "complex", "ok": False, "why": "'unless' changes the logic completely."}]},
    {"id": "st_12", "tier": 2, "skill": "B3.1_complex",
     "clause_a": "The streetcar bell rang twice.", "clause_b": "A stray raccoon ran across the tracks.", "weak_verb": "ran",
     "verb_upgrades": [{"word": "darted", "power": 2, "ok": True}, {"word": "scampered", "power": 2, "ok": True}, {"word": "went", "power": 0, "ok": False}],
     "bridges": [{"word": "because", "kind": "complex", "ok": True, "why": "'because' explains WHY the driver rang the warning bell!"},
                 {"word": "although", "kind": "complex", "ok": False, "why": "The raccoon was the REASON, not a contrast!"},
                 {"word": "or", "kind": "compound", "ok": False, "why": "Connect cause and effect, not a choice."}]},
    {"id": "st_13", "tier": 2, "skill": "B3.1_complex",
     "clause_a": "Our submarine hull creaked loudly.", "clause_b": "We went deeper into the Mariana Trench.", "weak_verb": "went",
     "verb_upgrades": [{"word": "plunged", "power": 2, "ok": True}, {"word": "descended", "power": 2, "ok": True}, {"word": "got", "power": 0, "ok": False}],
     "bridges": [{"word": "as", "kind": "complex", "ok": True, "why": "'as' links the creaking directly to descending deeper!"},
                 {"word": "but", "kind": "compound", "ok": False, "why": "Deeper pressure causes creaking — not a contrast!"},
                 {"word": "or", "kind": "compound", "ok": False, "why": "Both happened at the same time!"}]},
    {"id": "st_14", "tier": 2, "skill": "B3.1_complex",
     "clause_a": "The laser turret overheated.", "clause_b": "It fired six plasma blasts in a row.", "weak_verb": "fired",
     "verb_upgrades": [{"word": "unleashed", "power": 2, "ok": True}, {"word": "blasted", "power": 2, "ok": True}, {"word": "did", "power": 0, "ok": False}],
     "bridges": [{"word": "after", "kind": "complex", "ok": True, "why": "'after' puts the six blasts first and the overheating second!"},
                 {"word": "before", "kind": "complex", "ok": False, "why": "It overheated AFTER firing six blasts, not before!"},
                 {"word": "unless", "kind": "complex", "ok": False, "why": "Use a time connector showing what happened first."}]},
    {"id": "st_15", "tier": 3, "skill": "B3.1_complex", "front_connector": True,
     "clause_a": "The snowstorm buried the runway.", "clause_b": "The rescue jet took off safely.", "weak_verb": "took off",
     "verb_upgrades": [{"word": "rocketed", "power": 2, "ok": True}, {"word": "soared", "power": 2, "ok": True}, {"word": "went up", "power": 0, "ok": False}],
     "bridges": [{"word": "although", "kind": "complex", "ok": True, "why": "'Although' at the front creates a crisp Grade 4 complex contrast sentence!"},
                 {"word": "because", "kind": "complex", "ok": False, "why": "A buried runway doesn't HELP a jet take off — this is a contrast!"},
                 {"word": "so", "kind": "compound", "ok": False, "why": "Try a subordinating contrast connector at the front!"}]},
    {"id": "st_16", "tier": 3, "skill": "B3.1_complex", "front_connector": True,
     "clause_a": "The shield drops to zero.", "clause_b": "The escape pods will launch automatically.", "weak_verb": "launch",
     "verb_upgrades": [{"word": "eject", "power": 2, "ok": True}, {"word": "catapult", "power": 2, "ok": True}, {"word": "go", "power": 0, "ok": False}],
     "bridges": [{"word": "if", "kind": "complex", "ok": True, "why": "'If' at the front sets up a crisp conditional rule!"},
                 {"word": "although", "kind": "complex", "ok": False, "why": "Launching pods matches zero shields — use a condition word!"},
                 {"word": "but", "kind": "compound", "ok": False, "why": "Don't start a conditional sentence with 'but'!"}]},
    {"id": "st_17", "tier": 3, "skill": "B3.1_complex", "front_connector": True,
     "clause_a": "The sun dipped behind the skyline.", "clause_b": "The CN Tower lights came on in neon blue.", "weak_verb": "came on",
     "verb_upgrades": [{"word": "blazed", "power": 2, "ok": True}, {"word": "flared", "power": 2, "ok": True}, {"word": "went on", "power": 0, "ok": False}],
     "bridges": [{"word": "when", "kind": "complex", "ok": True, "why": "'When' at the front builds a smooth Grade 4 temporal opener!"},
                 {"word": "unless", "kind": "complex", "ok": False, "why": "Sunset is the exact time lights turn on!"},
                 {"word": "although", "kind": "complex", "ok": False, "why": "Lights turning on at sunset isn't a surprise contrast."}]},
    {"id": "st_18", "tier": 3, "skill": "B3.1_complex",
     "clause_a": "The bridge won't hold the heavy mech.", "clause_b": "We add steel support beams tonight.", "weak_verb": "add",
     "verb_upgrades": [{"word": "weld", "power": 2, "ok": True}, {"word": "bolt", "power": 2, "ok": True}, {"word": "put", "power": 0, "ok": False}],
     "bridges": [{"word": "unless", "kind": "complex", "ok": True, "why": "'unless' expresses 'except if' like a pro!"},
                 {"word": "because", "kind": "complex", "ok": False, "why": "Adding steel beams wouldn't make the bridge WEAKER!"},
                 {"word": "while", "kind": "complex", "ok": False, "why": "Show the exact 'except if' condition!"}]},
    {"id": "st_19", "tier": 3, "skill": "B3.1_complex", "front_connector": True,
     "clause_a": "The ancient portal hummed louder.", "clause_b": "Kai tightened his grip on the emerald blade.", "weak_verb": "tightened",
     "verb_upgrades": [{"word": "clenched", "power": 2, "ok": True}, {"word": "locked", "power": 2, "ok": True}, {"word": "held", "power": 0, "ok": False}],
     "bridges": [{"word": "as", "kind": "complex", "ok": True, "why": "'As' puts both tense moments in lockstep!"},
                 {"word": "unless", "kind": "complex", "ok": False, "why": "Show two actions rising together!"},
                 {"word": "or", "kind": "compound", "ok": False, "why": "Use a subordinating time connector!"}]},
    {"id": "st_20", "tier": 3, "skill": "B3.1_complex",
     "clause_a": "The dragon swooped past the cliffs.", "clause_b": "Its wings made a booming shockwave.", "weak_verb": "made",
     "verb_upgrades": [{"word": "unleashed", "power": 2, "ok": True}, {"word": "triggered", "power": 2, "ok": True}, {"word": "did", "power": 0, "ok": False}],
     "bridges": [{"word": "while", "kind": "complex", "ok": True, "why": "'while' blends the swoop and shockwave seamlessly!"},
                 {"word": "unless", "kind": "complex", "ok": False, "why": "Both actions happened simultaneously!"},
                 {"word": "but", "kind": "compound", "ok": False, "why": "No contrast here — show simultaneous action!"}]},
]


TYPING_ARENA_BANK: list[dict[str, Any]] = [
    {"id": "ty_01", "tier": 1, "tag": "Minecraft", "text": "Always carry a water bucket when you mine near deep lava."},
    {"id": "ty_02", "tier": 1, "tag": "Toronto", "text": "The CN Tower rises 553 meters above downtown Toronto."},
    {"id": "ty_03", "tier": 1, "tag": "Science", "text": "Octopuses have three hearts and blue blood inside their bodies."},
    {"id": "ty_04", "tier": 1, "tag": "Minecraft", "text": "Redstone dust carries power from a lever to an iron door."},
    {"id": "ty_05", "tier": 1, "tag": "Sports", "text": "Our goalie dove across the crease and snagged the puck."},
    {"id": "ty_06", "tier": 1, "tag": "Space", "text": "Saturn has icy rings wider than the distance to the Moon."},
    {"id": "ty_07", "tier": 1, "tag": "Toronto", "text": "Red streetcars glide down King Street past busy shops."},
    {"id": "ty_08", "tier": 1, "tag": "Animals", "text": "Peregrine falcons dive faster than a speeding race car."},
    {"id": "ty_09", "tier": 1, "tag": "Minecraft", "text": "Crouching with Shift keeps your boots safe on high ledges."},
    {"id": "ty_10", "tier": 1, "tag": "Invention", "text": "Solar panels turn bright sunlight into quiet electric power."},
    {"id": "ty_11", "tier": 2, "tag": "Action", "text": "Captain Maple vaulted over the streetcar and blocked the laser."},
    {"id": "ty_12", "tier": 2, "tag": "Minecraft", "text": "Enchanting an unbreakable diamond pickaxe saves time in caves."},
    {"id": "ty_13", "tier": 2, "tag": "Space", "text": "Mars rovers beam sharp photos across millions of kilometers."},
    {"id": "ty_14", "tier": 2, "tag": "Invention", "text": "Engineers test every bridge cable before opening it to traffic."},
    {"id": "ty_15", "tier": 2, "tag": "Ocean", "text": "Giant squids hunt silently in the pitch-black ocean trenches."},
    {"id": "ty_16", "tier": 2, "tag": "Minecraft", "text": "Place torches on the right wall so you always find the exit."},
    {"id": "ty_17", "tier": 2, "tag": "Science", "text": "Lightning bolts heat the surrounding air hotter than the Sun."},
    {"id": "ty_18", "tier": 2, "tag": "Comics", "text": "A sharp plot twist keeps every reader flipping to the next page."},
    {"id": "ty_19", "tier": 2, "tag": "Robotics", "text": "Sensors help rescue drones dodge branches inside dense forests."},
    {"id": "ty_20", "tier": 2, "tag": "Toronto", "text": "Ferries cross Toronto Harbour toward the quiet island beaches."},
    {"id": "ty_21", "tier": 2, "tag": "Homophones", "text": "They brought their compasses before walking through the tunnel."},
    {"id": "ty_22", "tier": 2, "tag": "Morphology", "text": "The fearless survivor stopped grabbing heavy supplies near lava."},
    {"id": "ty_23", "tier": 3, "tag": "Dialogue", "text": "\"Watch the radar!\" shouted Nova, because three drones appeared."},
    {"id": "ty_24", "tier": 3, "tag": "Morphology", "text": "Although the heavy supply cart slipped, the team kept rebuilding."},
    {"id": "ty_25", "tier": 3, "tag": "Dialogue", "text": "Kai whispered, \"Don't wake the Warden until we seal the gate!\""},
    {"id": "ty_26", "tier": 3, "tag": "Science", "text": "Volcanoes erupted underground, creating brand-new rocky islands."},
    {"id": "ty_27", "tier": 3, "tag": "Action", "text": "Before the trapdoor snapped shut, Maya snatched the golden key."},
    {"id": "ty_28", "tier": 3, "tag": "Homophones", "text": "Wait, you're sure it's spinning its wheels because of the ice?"},
    {"id": "ty_29", "tier": 3, "tag": "Space", "text": "Astronauts exercise two hours daily while orbiting above Earth."},
    {"id": "ty_30", "tier": 3, "tag": "Comics", "text": "Because every panel connects causally, the whole story feels epic!"},
]


# 16 Mystery & Literary Craft Cases: clue_index strictly balanced (4x idx 0, 4x idx 1, 4x idx 2, 4x idx 3)
# and ZERO answer spoilers in Step 1 prompts!
CLUE_DETECTIVE_BANK: list[dict[str, Any]] = [
    # ---- clue_index = 0 (4 cases) ----
    {"id": "cd_01", "tier": 1, "skill": "C2.3_inference", "case_title": "Case #104: The Missing Diamond Pickaxe",
     "question": "Who actually took the diamond pickaxe from the storage chest?",
     "sentences": [
         "At 4:15 PM, Sam walked out of the oak base with fresh wood splinters on his muddy boots and a glowing purple glint inside his satchel.",
         "At 4:00 PM, Leo had locked his enchanted diamond pickaxe inside the base.",
         "Maya spent the whole afternoon fishing by the frozen river with zero tools.",
         "Later, the village iron golem patrolled the wheat field without entering any houses.",
     ], "clue_index": 0,
     "choices": [{"label": "Sam", "ok": True},
                 {"label": "Maya", "ok": False, "why": "Maya was out at the frozen river with zero tools."},
                 {"label": "The Iron Golem", "ok": False, "why": "The golem never entered any houses."}],
     "verdict_starter": "I know Sam took the pickaxe because", "required_word": "because",
     "explain": "Oak splinters + a glowing purple enchanted glint in Sam's satchel prove Sam was the culprit!"},
    {"id": "cd_05", "tier": 2, "skill": "C1.2_3_craft", "case_title": "Case #312: Launchpad Craft Scan",
     "question": "Highlight the sentence that uses vivid figurative language to describe the rocket!",
     "sentences": [
         "As the countdown hit zero, the rocket became a blazing spear slicing through the night sky.",
         "The heavy steel boosters rumbled loudly across the concrete launchpad.",
         "Engineers checked their glowing tablets one final time before ignition.",
         "Everyone inside mission control cheered when it cleared the clouds.",
     ], "clue_index": 0,
     "choices": [{"label": "Metaphor ('became a blazing spear')", "ok": True},
                 {"label": "Simile (uses 'like' or 'as')", "ok": False, "why": "It says the rocket BECAME a blazing spear — no 'like' or 'as'!"},
                 {"label": "Onomatopoeia (sound word)", "ok": False, "why": "Calling a rocket a 'blazing spear' is a direct metaphor, not a sound word!"}],
     "verdict_starter": "That sentence is a metaphor because", "required_word": "because",
     "explain": "A metaphor says one thing IS (or became) another thing directly without 'like' or 'as'."},
    {"id": "cd_10", "tier": 2, "skill": "C2.3_inference", "case_title": "Case #455: The Disguised Body Snatcher",
     "question": "How did Captain Maple spot the disguised alien in the parade crowd?",
     "sentences": [
         "When sunlight hit the tall stranger's face, violet slit pupils flashed behind his glasses and purple spores pulsed along his collar.",
         "Hundreds of Torontonians lined Front Street watching the colourful parade floats.",
         "He wore a regular dark blue parka and clapped along near the corner.",
         "Beside him, a street vendor handed out hot pretzels.",
     ], "clue_index": 0,
     "choices": [{"label": "Violet slit pupils & glowing purple spores", "ok": True},
                 {"label": "He wore a blue parka", "ok": False, "why": "Lots of real Torontonians wear blue parkas!"},
                 {"label": "He stood near a pretzel vendor", "ok": False, "why": "Standing near pretzels isn't alien evidence!"}],
     "verdict_starter": "I know he was an alien because", "required_word": "because",
     "explain": "Violet slit pupils and pulsing purple spores directly expose the disguise!"},
    {"id": "cd_14", "tier": 3, "skill": "C1.2_3_craft", "case_title": "Case #560: Championship Chess Craft",
     "question": "Highlight the sentence that uses bold figurative imagery to transform the chess match!",
     "sentences": [
         "To Leo, the chessboard was a silent battlefield where every wooden pawn guarded a fortress.",
         "The chess clock ticked steadily inside the quiet school library.",
         "Eight finalists leaned forward over their black-and-white boards.",
         "After forty tense minutes, he finally announced checkmate.",
     ], "clue_index": 0,
     "choices": [{"label": "Metaphor ('chessboard was a silent battlefield')", "ok": True},
                 {"label": "Simile ('like' or 'as')", "ok": False, "why": "It says the board WAS a battlefield — direct metaphor!"},
                 {"label": "Onomatopoeia", "ok": False, "why": "This is a direct imaginative comparison, not a sound word."}],
     "verdict_starter": "That sentence is a metaphor because", "required_word": "because",
     "explain": "Calling the chessboard 'a silent battlefield' without 'like' or 'as' is a sharp metaphor!"},

    # ---- clue_index = 1 (4 cases) ----
    {"id": "cd_03", "tier": 1, "skill": "C2.3_inference", "case_title": "Case #215: The Vanished Pizza Slice",
     "question": "Who secretly ate the final pepperoni slice in the clubhouse?",
     "sentences": [
         "Dylan left one hot pepperoni slice on a paper plate beside the comic desk.",
         "When Dylan returned, his golden retriever Max was hiding under the table licking bright orange tomato sauce off his whiskers.",
         "His sister Zoe stayed outside shooting hoops in the driveway for twenty minutes.",
         "The kitchen window was shut tight with the latch locked.",
     ], "clue_index": 1,
     "choices": [{"label": "Max the dog", "ok": True},
                 {"label": "Zoe", "ok": False, "why": "Zoe was outside shooting hoops the whole time."},
                 {"label": "A bird through the window", "ok": False, "why": "The window was shut tight and locked."}],
     "verdict_starter": "I know Max ate the pizza because", "required_word": "because",
     "explain": "Hiding under the table with orange tomato sauce on his whiskers gives Max away!"},
    {"id": "cd_07", "tier": 2, "skill": "C1.2_3_craft", "case_title": "Case #418: Harbourfront Storm Craft",
     "question": "Highlight the sentence that uses explosive comic literary craft!",
     "sentences": [
         "The heavy storm clouds gathered quietly over the harbourfront.",
         "Suddenly, CRACK, BOOM, SIZZLE, lightning split the old wooden pier in half!",
         "Nearby seagulls lifted off the water and circled above the lighthouse.",
         "Within five minutes, rescue boats steered carefully toward the dock.",
     ], "clue_index": 1,
     "choices": [{"label": "Onomatopoeia ('CRACK, BOOM, SIZZLE')", "ok": True},
                 {"label": "Simile (uses 'like' or 'as')", "ok": False, "why": "There is no 'like' or 'as' comparison — those are comic sound words!"},
                 {"label": "Personification", "ok": False, "why": "CRACK, BOOM, and SIZZLE directly mimic real sounds!"}],
     "verdict_starter": "That sentence uses onomatopoeia because", "required_word": "because",
     "explain": "Words like CRACK, BOOM, and SIZZLE imitate the exact sounds they name!"},
    {"id": "cd_08", "tier": 2, "skill": "C1.2_3_craft", "case_title": "Case #430: Midnight Train Depot Craft",
     "question": "Highlight the sentence that brings a non-living force of nature to life!",
     "sentences": [
         "Thick winter frost coated every window of the old train depot.",
         "The angry blizzard clawed at the steel shutters and screamed down the empty tracks.",
         "Inside the waiting room, two conductors checked their pocket watches.",
         "The midnight express finally pulled up ten minutes behind schedule.",
     ], "clue_index": 1,
     "choices": [{"label": "Personification ('blizzard clawed and screamed')", "ok": True},
                 {"label": "Simile ('like' or 'as')", "ok": False, "why": "No 'like' or 'as' — it makes the storm act like an angry living creature!"},
                 {"label": "Literal weather report", "ok": False, "why": "Real snowstorms don't literally have claws or scream!"}],
     "verdict_starter": "That sentence uses personification because", "required_word": "because",
     "explain": "Giving a blizzard human/creature actions ('clawed' and 'screamed') is personification!"},
    {"id": "cd_12", "tier": 3, "skill": "C1.5_pov", "case_title": "Case #531: Narrator Lens Check",
     "question": "Highlight the sentence whose narrator pronouns reveal the story's Point of View!",
     "sentences": [
         "Thunder boomed above the harbour as rain drummed on the tin roof.",
         "Although Nova hid her nerves behind a cool grin, she secretly wondered whether her jetpack wings would unfold in time.",
         "Inside the workshop, gears clicked inside a glowing bronze compass.",
         "Outside, the countdown siren echoed across the empty pier.",
     ], "clue_index": 1,
     "choices": [{"label": "Third-person ('Nova', 'her', 'she')", "ok": True},
                 {"label": "First-person ('I', 'my')", "ok": False, "why": "Notice it calls her 'Nova' and 'she', not 'I'!"},
                 {"label": "Second-person ('you')", "ok": False, "why": "It narrates about 'she', not 'you'."}],
     "verdict_starter": "I know it is third-person because", "required_word": "because",
     "explain": "Using 'she/her' and the character's name ('Nova') marks third-person narration."},

    # ---- clue_index = 2 (4 cases) ----
    {"id": "cd_02", "tier": 1, "skill": "C2.3_inference", "case_title": "Case #208: The Midnight CN Tower Glitch",
     "question": "What caused the neon beacon on the roof to flicker off?",
     "sentences": [
         "Every night, the tall beacon guides helicopters safely over Toronto's harbour.",
         "Last Tuesday, the sky was crystal clear with no wind and no thunder.",
         "At midnight, the backup lights blinked red right as a raccoon squeezed out of the chewed-open fuse box holding shiny copper wire.",
         "Security guards checked the lobby doors and found every lock still bolted.",
     ], "clue_index": 2,
     "choices": [{"label": "A raccoon chewed the fuse box wire", "ok": True},
                 {"label": "A huge thunderstorm hit Toronto", "ok": False, "why": "Line 2 says the sky was crystal clear with no thunder."},
                 {"label": "Someone unlocked the lobby door", "ok": False, "why": "Every lobby lock was still bolted."}],
     "verdict_starter": "I know a raccoon caused the glitch because", "required_word": "because",
     "explain": "The chewed-open fuse box + copper wire in the raccoon's paws is direct text evidence!"},
    {"id": "cd_06", "tier": 2, "skill": "C1.2_3_craft", "case_title": "Case #405: Breakaway Ice Rink Craft",
     "question": "Highlight the sentence that compares the skater's speed using vivid figurative language!",
     "sentences": [
         "A cold northern gust swept across the hockey rink at dusk.",
         "Kai laced up his skates and tapped his stick on the ice.",
         "He burst down the right wing as fast as a peregrine falcon diving for prey.",
         "The puck rattled the back of the net before the goalie could blink.",
     ], "clue_index": 2,
     "choices": [{"label": "Simile ('as fast as a peregrine falcon')", "ok": True},
                 {"label": "Metaphor (no 'like' or 'as')", "ok": False, "why": "Notice the comparison word 'as...as' — that makes it a simile!"},
                 {"label": "Onomatopoeia (sound word)", "ok": False, "why": "It compares Kai's speed to a diving falcon using 'as...as'!"}],
     "verdict_starter": "That sentence is a simile because", "required_word": "because",
     "explain": "'as fast as a peregrine falcon' compares Kai's speed using 'as...as' — classic simile!"},
    {"id": "cd_09", "tier": 2, "skill": "C2.3_inference", "case_title": "Case #442: The Muddy Rover Tracks",
     "question": "How do the astronauts know the Martian canyon once held liquid water?",
     "sentences": [
         "At dawn, the solar rover rolled off its landing ramp onto dry orange dust.",
         "Its drill sampled three crumbly boulders near the crater rim.",
         "Close-up photos revealed smooth, rounded pebbles stacked in wavy riverbed ripples that only flowing water can carve.",
         "Overhead, two tiny moons drifted across the pink Martian sky.",
     ], "clue_index": 2,
     "choices": [{"label": "Smooth rounded pebbles & riverbed ripples", "ok": True},
                 {"label": "The sky looked pink at dawn", "ok": False, "why": "Dust makes the Martian sky pink — not water!"},
                 {"label": "Mars has two small moons", "ok": False, "why": "Moons don't prove liquid water once flowed there."}],
     "verdict_starter": "I know water once flowed there because", "required_word": "because",
     "explain": "Rounded pebbles and wavy riverbed ripples are geological proof of ancient flowing water!"},
    {"id": "cd_11", "tier": 3, "skill": "C1.5_pov", "case_title": "Case #519: Cavern Explorer POV",
     "question": "Highlight the sentence whose narrator pronouns reveal this story's Point of View!",
     "sentences": [
         "The ancient stone gate groaned open into a cavern lit by glowing moss.",
         "Blue crystals hummed along the ceiling in the chilly draft.",
         "My boots slipped on the wet rock, and I barely caught the ledge before falling.",
         "Far below, an underground river rushed toward the dark chasm.",
     ], "clue_index": 2,
     "choices": [{"label": "First-person ('My' and 'I')", "ok": True},
                 {"label": "Third-person ('he / she / they')", "ok": False, "why": "Look closely at the narrator pronouns in line 3: 'My' and 'I'!"},
                 {"label": "Second-person ('you')", "ok": False, "why": "The narrator tells their own experience using 'I'."}],
     "verdict_starter": "I know it is first-person because", "required_word": "because",
     "explain": "First-person narration uses 'I', 'me', and 'my' so we see through the narrator's eyes."},

    # ---- clue_index = 3 (4 cases) ----
    {"id": "cd_04", "tier": 1, "skill": "C2.3_inference", "case_title": "Case #229: The Frozen Redstone Door",
     "question": "Why did the automatic fortress door refuse to open?",
     "sentences": [
         "Normally, stepping on the stone pressure plate slides both iron pistons apart.",
         "All morning, explorers walked freely in and out of the main courtyard.",
         "The iron pistons themselves looked brand new with zero scratches.",
         "When Kai checked behind the wall, a splash of river water had washed away three blocks of Redstone dust connecting the plate.",
     ], "clue_index": 3,
     "choices": [{"label": "Water washed away the Redstone trail", "ok": True},
                 {"label": "The iron pistons were rusted shut", "ok": False, "why": "Line 3 says the pistons looked brand new."},
                 {"label": "The pressure plate vanished", "ok": False, "why": "The Redstone dust trail behind the wall was washed away!"}],
     "verdict_starter": "I know the door broke because", "required_word": "because",
     "explain": "Washed-away Redstone dust breaks the signal from the plate to the pistons!"},
    {"id": "cd_13", "tier": 3, "skill": "C2.3_inference", "case_title": "Case #548: The Sabotaged Hover-Racer",
     "question": "Why did Racer #7 lose speed right after entering Turn 3?",
     "sentences": [
         "Racer #7 blasted off the starting line in first place with full neon thrusters.",
         "Her battery meter still read 95% full as she approached the neon tunnel.",
         "The race announcer gasped as two rival cars shot ahead down the straightaway.",
         "Slow-motion replay caught a heavy magnetic clamp snapping onto her rear fin as she brushed past Pit Wall B.",
     ], "clue_index": 3,
     "choices": [{"label": "A magnetic clamp dragged on her rear fin", "ok": True},
                 {"label": "Her battery ran completely dry", "ok": False, "why": "Line 2 explicitly says her battery was 95% full!"},
                 {"label": "She started in last place", "ok": False, "why": "Line 1 says she blasted off in first place!"}],
     "verdict_starter": "I know Racer #7 slowed down because", "required_word": "because",
     "explain": "The slow-motion replay proves a heavy magnetic clamp latched onto her rear fin!"},
    {"id": "cd_15", "tier": 3, "skill": "C2.3_inference", "case_title": "Case #574: The Secret Cave Exit",
     "question": "How did Maya figure out which dark tunnel led back to fresh outside air?",
     "sentences": [
         "Deep under the mountain, the mine shaft split into three identical dark tunnels.",
         "Tunnels A and B smelled dusty and stale, with spiderwebs hanging completely still.",
         "Her compass spun wildly because of thick iron ore in the cavern walls.",
         "When Maya held her torch near Tunnel C, the flame bent sideways in a cool breeze carrying the crisp scent of pine needles.",
     ], "clue_index": 3,
     "choices": [{"label": "Tunnel C had a cool breeze & pine scent", "ok": True},
                 {"label": "Her compass pointed straight down Tunnel C", "ok": False, "why": "Line 3 says her compass was spinning wildly!"},
                 {"label": "Tunnel A had moving spiderwebs", "ok": False, "why": "Line 2 says the webs in A and B hung completely still."}],
     "verdict_starter": "I know Tunnel C led outside because", "required_word": "because",
     "explain": "A cool breeze bending the flame plus the outdoor scent of pine needles proves Tunnel C opens outside!"},
    {"id": "cd_16", "tier": 3, "skill": "C1.2_3_craft", "case_title": "Case #589: Harbour Fog Imagery",
     "question": "Highlight the sentence that paints a vivid figurative comparison of the skyscraper!",
     "sentences": [
         "Morning fog drifted slowly off Lake Ontario into downtown Toronto.",
         "Commuters stepped off the GO Train carrying warm mugs of coffee.",
         "By noon, warm sunlight had cleared the low harbour fog away.",
         "High above the clouds, the glass spire gleamed like a silver needle stitched into the sky.",
     ], "clue_index": 3,
     "choices": [{"label": "Simile ('gleamed like a silver needle')", "ok": True},
                 {"label": "Metaphor (no 'like' or 'as')", "ok": False, "why": "Notice the word 'like' — comparing with 'like' or 'as' makes it a simile!"},
                 {"label": "Onomatopoeia", "ok": False, "why": "It creates a visual comparison using 'like', not a sound effect."}],
     "verdict_starter": "That sentence is a simile because", "required_word": "because",
     "explain": "'gleamed like a silver needle' uses 'like' to compare the tower spire to a needle!"},
]


# --------------------------------------------------------------------------- State & Persistence Helpers

def _default_skill_arcade() -> dict[str, Any]:
    return {
        "total_runs": 0,
        "total_correct": 0,
        "total_attempts": 0,
        "streak_days": 0,
        "last_played_date": "",
        "seen_ids": {},
        "games": {},
        "recent_runs": [],
    }


def ensure_skill_arcade(rec: dict[str, Any]) -> dict[str, Any]:
    sa = rec.get("skill_arcade")
    if not isinstance(sa, dict):
        sa = _default_skill_arcade()
        rec["skill_arcade"] = sa
    sa.setdefault("total_runs", 0)
    sa.setdefault("total_correct", 0)
    sa.setdefault("total_attempts", 0)
    sa.setdefault("streak_days", 0)
    sa.setdefault("last_played_date", "")
    sa.setdefault("seen_ids", {})
    sa.setdefault("games", {})
    sa.setdefault("recent_runs", [])
    return sa


def _active_rec(sandbox: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    if sandbox:
        if "rec" not in _SANDBOX_SKILL_STATE:
            _SANDBOX_SKILL_STATE["rec"] = copy.deepcopy(load_learner())
        rec = _SANDBOX_SKILL_STATE["rec"]
        return rec, ensure_skill_arcade(rec)
    rec = load_learner()
    return rec, ensure_skill_arcade(rec)


def _save_rec(rec: dict[str, Any], sandbox: bool = False) -> None:
    if sandbox:
        _SANDBOX_SKILL_STATE["rec"] = rec
    else:
        save_learner(rec)


def _pick_fresh(pool: list[dict[str, Any]], seen: list[str], count: int) -> tuple[list[dict[str, Any]], list[str]]:
    seen_set = set(seen or [])
    fresh = [copy.deepcopy(x) for x in pool if x.get("id") not in seen_set]
    stale = [copy.deepcopy(x) for x in pool if x.get("id") in seen_set]
    random.shuffle(fresh)
    random.shuffle(stale)
    picked = fresh[:count]
    new_seen = list(seen or [])
    if len(picked) < count:
        need = count - len(picked)
        picked.extend(stale[:need])
        new_seen = [x.get("id", "") for x in picked if x.get("id")]
    else:
        new_seen.extend(x.get("id", "") for x in picked if x.get("id"))
        new_seen = new_seen[-len(pool):]
    return picked, new_seen


def _skill_need_score(rc: dict[str, Any], deck_due: int, game: dict[str, Any]) -> tuple[float, str]:
    sk = (rc or {}).get("skills") or {}
    lowest = 5
    lowest_name = ""
    exp_map = {e["id"]: e["name"] for e in curriculum_tracker.ONTARIO_EXPECTATIONS}
    for sid in game["skills"]:
        lvl = int((sk.get(sid) or {}).get("level") or 0)
        if lvl < lowest:
            lowest = lvl
            lowest_name = exp_map.get(sid, sid)

    score = (5 - lowest) * 10.0
    reason = f"Boosts {lowest_name}" if lowest_name else "Curriculum Practice"
    if game["id"] == "word_forge" and deck_due > 0:
        score += 18.0 + min(deck_due, 6) * 2.0
        reason = f"{deck_due} spelling card{'s' if deck_due != 1 else ''} ready for review!"
    elif lowest == 0:
        reason = f"Unassessed skill: {lowest_name}"
    elif lowest <= 2:
        reason = f"Level {lowest} target: {lowest_name}"
    else:
        reason = f"Keep sharp: {lowest_name}"
    return score, reason


def get_arcade_hub_state(*, sandbox: bool = False) -> dict[str, Any]:
    rec, sa = _active_rec(sandbox=sandbox)
    rc = curriculum_tracker.ensure_report_card(rec)
    deck = spelling_srs.deck_summary(rec)
    due_now = int(deck.get("due_now") or 0)
    games_stats = sa.get("games") or {}

    bank_sizes = {
        "sentence_surgery": len(SENTENCE_SURGERY_BANK),
        "word_forge": len(WORD_FORGE_CURRICULUM_BANK),
        "homophone_asteroids": len(HOMOPHONE_ASTEROIDS_BANK),
        "sentence_stretch": len(SENTENCE_STRETCH_BANK),
        "typing_arena": len(TYPING_ARENA_BANK),
        "clue_detective": len(CLUE_DETECTIVE_BANK),
    }

    enriched = []
    scored = []
    for g in GAME_CATALOG:
        gid = g["id"]
        gs = games_stats.get(gid) or {}
        need, reason = _skill_need_score(rc, due_now, g)
        scored.append((need, gid))
        enriched.append({
            **g,
            "bank_size": bank_sizes.get(gid, 0),
            "runs": int(gs.get("runs") or 0),
            "best_score": int(gs.get("best_score") or 0),
            "best_accuracy": int(gs.get("best_accuracy") or 0),
            "best_wpm": int(gs.get("best_wpm") or 0),
            "mastery_stars": min(3, int(gs.get("mastery_stars") or 0)),
            "reason": reason,
            "recommended": False,
        })

    scored.sort(key=lambda x: -x[0])
    top_ids = {gid for _, gid in scored[:2]}
    for item in enriched:
        if item["id"] in top_ids:
            item["recommended"] = True

    arc_status = arcade.client_status(rec, sandbox=sandbox)
    return {
        "child_name": rec.get("name") or "Player",
        "grade": int(rec.get("grade") or 3),
        "mastery_tier": int(rc.get("mastery_tier") or 1),
        "spelling_due": due_now,
        "spelling_mastered": int(deck.get("mastered") or 0),
        "ai_available": bool(api_key()),
        "total_runs": int(sa.get("total_runs") or 0),
        "streak_days": int(sa.get("streak_days") or 0),
        "games": enriched,
        "arcade": arc_status,
        "sandbox": sandbox,
    }


def parent_summary(rec: dict[str, Any]) -> dict[str, Any]:
    sa = ensure_skill_arcade(rec)
    games_out = []
    for g in GAME_CATALOG:
        gs = (sa.get("games") or {}).get(g["id"]) or {}
        games_out.append({
            "id": g["id"],
            "title": g["title"],
            "icon": g["icon"],
            "runs": int(gs.get("runs") or 0),
            "best_score": int(gs.get("best_score") or 0),
            "best_accuracy": int(gs.get("best_accuracy") or 0),
            "best_wpm": int(gs.get("best_wpm") or 0),
            "mastery_stars": int(gs.get("mastery_stars") or 0),
            "last_played": gs.get("last_played") or "",
        })
    return {
        "total_runs": int(sa.get("total_runs") or 0),
        "total_correct": int(sa.get("total_correct") or 0),
        "total_attempts": int(sa.get("total_attempts") or 0),
        "avg_accuracy": round(100.0 * sa["total_correct"] / max(1, sa["total_attempts"])) if sa["total_attempts"] else 0,
        "streak_days": int(sa.get("streak_days") or 0),
        "games": games_out,
        "recent_runs": list(reversed((sa.get("recent_runs") or [])[-12:])),
    }


# --------------------------------------------------------------------------- Adaptive Pack Generation

_VALID_FORGE_PREFIXES = frozenset({
    "un", "dis", "re", "mis", "pre", "sub", "de", "in", "im", "up", "e",
    "over", "under", "non", "out", "super", "inter", "trans",
})
_VALID_FORGE_SUFFIXES = frozenset({
    "ed", "ing", "er", "or", "est", "s", "es", "ly", "ful", "less", "ness",
    "ment", "able", "ible", "ion", "tion", "sion", "ous", "al", "y", "en",
    "ish", "ist", "ive",
})


def _parse_parts_to_forge_item(card: dict[str, Any]) -> dict[str, Any] | None:
    """Safely maps a Leitner deck card to a verified Word Forge item (never producing corrupted stems)."""
    word = (card.get("word") or "").strip().lower()
    if not word or not word.isalpha() or len(word) < 4:
        return None
    # 1. Exact match in curated ontology bank
    for item in WORD_FORGE_CURRICULUM_BANK:
        if item["word"].lower() == word:
            return {**item, "from_deck": True, "box": int(card.get("box") or 1)}

    # 2. Clean structured parsing of `parts` with strict mathematical + morpheme allowlist verification
    parts_raw = (card.get("parts") or "").strip()
    note = (card.get("note") or "").strip() or f"Spell '{word}' carefully piece by piece!"
    unit = card.get("unit") or "From your spelling deck"
    ctx_sent = f"Spell the word {word} cleanly in your next writing mission."

    clean_p = parts_raw.replace("−", "-").replace("→", "->")
    # Remove parenthetical annotations like `(y->i)` or `(dge)` before extracting morpheme tokens!
    no_parens = re.sub(r"\([^)]*\)", "", clean_p)
    # Remove trailing `- e` notation (`explode - e + ing` -> `explode + ing`)
    no_minus_e = re.sub(r"-\s*e\b", "", no_parens, flags=re.I)

    if "+" in no_minus_e:
        segs = [re.sub(r"[^a-z]", "", s.lower()) for s in no_minus_e.split("+")]
        segs = [s for s in segs if s]
        # Candidate `(prefix, base, suffix)` layouts
        candidates: list[tuple[str, str, str]] = []
        if len(segs) == 3 and len(segs[1]) == 1 and segs[0].endswith(segs[1]):
            candidates.append(("", segs[0], segs[2]))
        elif len(segs) == 3:
            candidates.append((segs[0], segs[1], segs[2]))
        elif len(segs) == 2:
            if segs[0] in _VALID_FORGE_PREFIXES:
                candidates.append((segs[0], segs[1], ""))
            candidates.append(("", segs[0], segs[1]))
        for p, b, s in candidates:
            if len(b) < 3:
                continue
            if p and p not in _VALID_FORGE_PREFIXES:
                continue
            if s and s not in _VALID_FORGE_SUFFIXES:
                continue
            if not p and not s:
                continue
            for rl in ("double", "drop_e", "y_to_i", "keep"):
                if _verify_forge_rule(p, b, s, rl, word):
                    return {
                        "id": f"deck_{word}", "word": word, "prefix": p, "base": b, "suffix": s, "rule": rl,
                        "unit": unit, "note": note, "context_sentence": ctx_sent,
                        "from_deck": True, "box": int(card.get("box") or 1),
                    }

    # 3. Direct-memory card for irregular/non-affix misspellings (skips fake morpheme splitting!)
    return {
        "id": f"deck_{word}", "word": word, "prefix": "", "base": word, "suffix": "", "rule": "keep",
        "direct_memory": True, "unit": unit, "note": note, "context_sentence": ctx_sent,
        "from_deck": True, "box": int(card.get("box") or 1),
    }


def _enrich_forge_items(items: list[dict[str, Any]]) -> None:
    """Attaches safe distractor tiles, blanked context sentences, and non-spoiling memory hints."""
    all_prefixes = ["un", "dis", "re", "mis", "de", "up", "pre", "in"]
    all_suffixes = ["ed", "ing", "er", "or", "es", "est", "ly", "able", "less", "ion"]
    for it in items:
        it["blanked_sentence"] = _blank_word_in_sentence(it.get("context_sentence") or "", it["word"])
        it["memory_hint"] = _safe_memory_hint(
            it.get("rule", "keep"),
            it.get("unit", "Morphology"),
            direct_memory=bool(it.get("direct_memory")),
        )
        tiles = []
        if not it.get("direct_memory"):
            if it.get("prefix"):
                tiles.append({"text": it["prefix"] + "-", "part": "prefix", "value": it["prefix"], "correct": True})
                dist_p = random.choice([p for p in all_prefixes if p != it["prefix"]])
                tiles.append({"text": dist_p + "-", "part": "prefix", "value": dist_p, "correct": False})
            tiles.append({"text": it["base"], "part": "base", "value": it["base"], "correct": True})
            if it.get("suffix"):
                tiles.append({"text": "-" + it["suffix"], "part": "suffix", "value": it["suffix"], "correct": True})
                dist_s = random.choice([s for s in all_suffixes if s != it["suffix"]])
                tiles.append({"text": "-" + dist_s, "part": "suffix", "value": dist_s, "correct": False})
            random.shuffle(tiles)
        it["tiles"] = tiles


def _build_word_forge_pack(rec: dict[str, Any], sa: dict[str, Any], count: int = 6) -> list[dict[str, Any]]:
    deck = spelling_srs.ensure_deck(rec)
    cards = list((deck.get("cards") or {}).values())
    now = time.time()
    cards.sort(key=lambda c: (0 if (c.get("next_due") or 0) <= now else 1, c.get("box", 1), -(c.get("lapses", 0))))

    chosen: list[dict[str, Any]] = []
    seen_words: set[str] = set()
    for c in cards:
        if len(chosen) >= min(3, count):
            break
        if c.get("box", 1) >= 5 and (c.get("next_due") or 0) > now:
            continue
        item = _parse_parts_to_forge_item(c)
        if item and item["word"] not in seen_words:
            seen_words.add(item["word"])
            chosen.append(item)

    pool = [dict(x, from_deck=False, box=1) for x in WORD_FORGE_CURRICULUM_BANK if x["word"] not in seen_words]
    prev_seen = sa.setdefault("seen_ids", {}).get("word_forge", [])
    fresh_pool, new_seen = _pick_fresh(pool, prev_seen, max(0, count - len(chosen)))
    sa["seen_ids"]["word_forge"] = new_seen
    chosen.extend(fresh_pool)
    _enrich_forge_items(chosen)
    return chosen[:count]


def _student_theme_snippet(rec: dict[str, Any]) -> str:
    interests = (rec.get("model") or {}).get("interests") or []
    proj_titles = [p.get("title", "") for p in list_projects()[:4] if p.get("title")]
    bits = []
    if interests:
        bits.append("Interests: " + ", ".join(str(x) for x in interests[:5]))
    if proj_titles:
        bits.append("Saved books: " + ", ".join(proj_titles))
    if not bits:
        bits.append("Interests: Minecraft (Bedrock & Java), Toronto superheroes, robots, comic adventures, cool inventions")
    return "; ".join(bits)


def _try_ai_pack(game_id: str, rec: dict[str, Any]) -> list[dict[str, Any]] | None:
    if not api_key():
        return None
    theme = _student_theme_snippet(rec)
    grade = int(rec.get("grade") or 3)
    schemas = {
        "sentence_surgery": (
            'Return JSON array of 6 items (2 runon, 2 fragment, 2 mechanics): '
            'Runon: {"mode":"runon","tier":2,"skill":"B3.1_boundaries","prompt":"SLASH between the two sentences!","words":["The","hero","leaped","she","caught","the","drone."],"split_after":2,"fixed":"The hero leaped. She caught the drone.","explain":"Short rule."}. '
            'Fragment: {"mode":"fragment","tier":2,"skill":"B3.1_simple","prompt":"Repair this fragment!","broken":"...","missing":"verb","choices":[{"text":"Complete sentence.","ok":true},{"text":"Fragment 1.","ok":false,"why":"Why."},{"text":"Fragment 2.","ok":false,"why":"Why."}],"explain":"Short rule."}. '
            'Mechanics: {"mode":"mechanics","tier":2,"skill":"B3.3_dialogue","prompt":"Fix the 3 bugs!","tokens":[{"raw":"watch","fix":"\\"Watch","bug":true,"hint":"Open quotes & capital!"},{"raw":"out","fix":"out","bug":false},{"raw":"now","fix":"now!\\"","bug":true,"hint":"Close quotes!"},{"raw":"yelled","fix":"yelled","bug":false},{"raw":"leo","fix":"Leo.","bug":true,"hint":"Capitalize name & period!"}],"explain":"Short rule."}.'
        ),
        "word_forge": (
            'Return JSON array of 6 real English words (Grades 3-4 morphology): '
            '[{"word":"unstoppable","prefix":"un","base":"stop","suffix":"able","rule":"double","unit":"B2.3 Morphology",'
            '"context_sentence":"With enchanted armour, the hero felt unstoppable.","note":"Short clear spelling rule without printing the full fused word."}]. '
            'rule MUST mathematically match prefix+base+suffix -> word and be one of: "keep", "double", "drop_e", "y_to_i".'
        ),
        "homophone_asteroids": (
            'Return JSON array of 7 items: [{"tier":2,"skill":"B2.4_vocabulary","sentence":"Sentence with ___ blank.",'
            '"options":["correct","wrong1","wrong2"],"answer":"correct","explain":"Short clear rule."}]. '
            "Never repeat the answer word elsewhere in the same sentence. Use pure ASCII punctuation only."
        ),
        "typing_arena": (
            'Return JSON array of 5 items: [{"tier":2,"tag":"ThemeTag","text":"One clean crisp complete sentence 8-13 words long."}]. '
            "STRICT: Use ONLY standard keyboard ASCII characters (no em-dashes, no curly quotes)."
        ),
        "sentence_stretch": (
            'Return JSON array of 5 items: [{"tier":2,"skill":"B3.1_complex","clause_a":"Short sentence 1.","clause_b":"Short sentence 2.",'
            '"weak_verb":"word appearing verbatim in clause_a or clause_b","verb_upgrades":[{"word":"vivid1","power":2,"ok":true},'
            '{"word":"vivid2","power":2,"ok":true},{"word":"bland","power":0,"ok":false}],'
            '"bridges":[{"word":"because","kind":"complex","ok":true,"why":"Why it fits."},{"word":"wrong1","kind":"compound","ok":false,"why":"Why not."},'
            '{"word":"wrong2","kind":"complex","ok":false,"why":"Why not."}]}]. '
            "weak_verb MUST appear verbatim in clause_a or clause_b and every vivid verb upgrade MUST fit grammatically."
        ),
        "clue_detective": (
            'Return JSON array of 3 mini-mysteries: [{"tier":2,"skill":"C2.3_inference","case_title":"Case #...: Title",'
            '"question":"Deduction question without spoiling the answer?","sentences":["S1.","S2.","S3.","S4."],"clue_index":1,'
            '"choices":[{"label":"Right Answer","ok":true},{"label":"Wrong 1","ok":false,"why":"Why wrong."},{"label":"Wrong 2","ok":false,"why":"Why wrong."}],'
            '"verdict_starter":"I know ... because","required_word":"because","explain":"Why clue proves it."}]. '
            "Vary clue_index across 0, 1, 2, 3!"
        ),
    }
    schema_hint = schemas.get(game_id)
    if not schema_hint:
        return None
    prompt = (
        f"Create a fun, respectful, zero-babyish Ontario Grade {grade}–{grade+1} ELA game pack themed around: {theme}.\n"
        f"{schema_hint}\n"
        "Return ONLY valid raw JSON (no markdown fences, no commentary)."
    )
    try:
        client = genai_client(timeout_ms=9000)
        resp = client.models.generate_content(
            model=FAST_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.65,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        raw = (resp.text or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) < 3:
            return None

        if game_id == "sentence_surgery":
            valid = []
            for idx_x, x in enumerate(data):
                if not isinstance(x, dict):
                    continue
                m = x.get("mode")
                if m == "runon" and isinstance(x.get("words"), list) and isinstance(x.get("split_after"), int) and 0 <= x["split_after"] < len(x["words"]) - 1:
                    x.setdefault("id", f"ai_ss_r{idx_x}")
                    x.setdefault("skill", "B3.1_boundaries")
                    x.setdefault("prompt", "SLASH right between the two mashed-together sentences!")
                    x.setdefault("explain", "Two complete sentences need a period and a capital letter between them!")
                    valid.append(x)
                elif m == "fragment" and x.get("broken") and sum(1 for c in (x.get("choices") or []) if c.get("ok")) == 1:
                    x.setdefault("id", f"ai_ss_f{idx_x}")
                    x.setdefault("skill", "B3.1_simple")
                    x.setdefault("prompt", "Repair this incomplete fragment so it has Who/What + Does What!")
                    x.setdefault("explain", "A complete sentence needs both a subject and a main action verb!")
                    valid.append(x)
                elif m == "mechanics" and isinstance(x.get("tokens"), list) and sum(1 for t in x["tokens"] if t.get("bug")) >= 2:
                    x.setdefault("id", f"ai_ss_m{idx_x}")
                    x.setdefault("skill", "B3.3_mechanics")
                    x.setdefault("prompt", "Tap EVERY buggy word to fix capitals, apostrophes & end punctuation!")
                    x.setdefault("explain", "Check sentence-start capitals, proper nouns, apostrophes, and end punctuation!")
                    valid.append(x)
            return valid[:6] if len(valid) >= 4 else None
        if game_id == "word_forge":
            valid = []
            for x in data:
                if not isinstance(x, dict):
                    continue
                w = str(x.get("word") or "").strip().lower()
                p = str(x.get("prefix") or "").strip().lower()
                b = str(x.get("base") or "").strip().lower()
                s = str(x.get("suffix") or "").strip().lower()
                rl = str(x.get("rule") or "").strip().lower()
                if rl in ("keep", "double", "drop_e", "y_to_i") and _verify_forge_rule(p, b, s, rl, w):
                    x["word"], x["prefix"], x["base"], x["suffix"], x["rule"] = w, p, b, s, rl
                    x["from_deck"] = False
                    x["box"] = 1
                    ctx = str(x.get("context_sentence") or "").strip()
                    if w not in ctx.lower():
                        ctx = f"Listen carefully and forge the word {w}."
                    x["context_sentence"] = ctx
                    valid.append(x)
            if len(valid) >= 4:
                _enrich_forge_items(valid)
                return valid[:6]
            return None
        if game_id == "homophone_asteroids":
            valid = []
            for idx_x, x in enumerate(data):
                if not isinstance(x, dict):
                    continue
                sent = _ascii_normalize(str(x.get("sentence") or ""))
                ans = str(x.get("answer") or "").strip()
                opts = x.get("options") or []
                if "___" in sent and ans in opts and len(opts) == 3 and not re.search(rf"\b{re.escape(ans)}\b", sent, re.I):
                    x["sentence"] = sent
                    x.setdefault("id", f"ai_ha_{idx_x}")
                    x.setdefault("skill", "B3.2_grammar")
                    x.setdefault("explain", f"'{ans}' fits the sentence meaning and grammar cleanly!")
                    valid.append(x)
            return valid[:7] if len(valid) >= 4 else None
        if game_id == "typing_arena":
            valid = []
            for idx_x, x in enumerate(data):
                if not isinstance(x, dict):
                    continue
                t = _ascii_normalize(str(x.get("text") or ""))
                if 28 <= len(t) <= 95 and _is_pure_typeable_ascii(t):
                    x["text"] = t
                    x.setdefault("id", f"ai_ty_{idx_x}")
                    x.setdefault("tag", "World Pack")
                    valid.append(x)
            return valid[:5] if len(valid) >= 3 else None
        if game_id == "sentence_stretch":
            valid = []
            for idx_x, x in enumerate(data):
                if not isinstance(x, dict):
                    continue
                wv = str(x.get("weak_verb") or "")
                comb = f"{x.get('clause_a','')} {x.get('clause_b','')}"
                bridges = x.get("bridges") or []
                verbs = x.get("verb_upgrades") or []
                if wv and re.search(rf"\b{re.escape(wv)}\b", comb, re.I) \
                   and sum(1 for b in bridges if b.get("ok")) == 1 \
                   and all(isinstance(b, dict) and b.get("word") for b in bridges) \
                   and sum(1 for v in verbs if v.get("ok")) >= 1:
                    x.setdefault("id", f"ai_st_{idx_x}")
                    x.setdefault("skill", "B3.1_complex")
                    for b in bridges:
                        b.setdefault("kind", "complex")
                        b.setdefault("why", "Check the cause, timing, or contrast!")
                    valid.append(x)
            return valid[:5] if len(valid) >= 3 else None
        if game_id == "clue_detective":
            valid = []
            for idx_x, x in enumerate(data):
                if (
                    isinstance(x, dict)
                    and isinstance(x.get("sentences"), list) and len(x["sentences"]) == 4
                    and isinstance(x.get("clue_index"), int) and 0 <= x["clue_index"] <= 3
                    and sum(1 for c in (x.get("choices") or []) if c.get("ok")) == 1
                ):
                    x.setdefault("id", f"ai_cd_{idx_x}")
                    x.setdefault("skill", "C2.3_inference")
                    x.setdefault("case_title", f"Case #{idx_x + 1}: Field Investigation")
                    x.setdefault("verdict_starter", "I proved this case because")
                    x.setdefault("required_word", "because")
                    x.setdefault("explain", "The highlighted proof sentence gives direct evidence!")
                    valid.append(x)
            return valid[:3] if len(valid) >= 2 else None
    except Exception:
        return None
    return None


def _shuffle_pack_choices(game_id: str, items: list[dict[str, Any]]) -> None:
    """Shuffles choices/options/bridges/verbs unconditionally for BOTH AI packs and curated packs!"""
    for it in items:
        if game_id == "sentence_surgery" and it.get("mode") == "fragment" and isinstance(it.get("choices"), list):
            random.shuffle(it["choices"])
        elif game_id == "homophone_asteroids" and isinstance(it.get("options"), list):
            random.shuffle(it["options"])
        elif game_id == "sentence_stretch":
            if isinstance(it.get("bridges"), list):
                random.shuffle(it["bridges"])
            if isinstance(it.get("verb_upgrades"), list):
                random.shuffle(it["verb_upgrades"])
        elif game_id == "clue_detective" and isinstance(it.get("choices"), list):
            random.shuffle(it["choices"])


def generate_game_pack(
    game_id: str,
    *,
    use_ai: bool = False,
    sandbox: bool = False,
) -> dict[str, Any]:
    if game_id not in GAME_BY_ID:
        raise ValueError(f"Unknown skill game: {game_id}")
    rec, sa = _active_rec(sandbox=sandbox)
    rc = curriculum_tracker.ensure_report_card(rec)
    meta = GAME_BY_ID[game_id]
    ai_generated = False
    seen_map = sa.setdefault("seen_ids", {})

    items: list[dict[str, Any]] = []
    if use_ai:
        ai_items = _try_ai_pack(game_id, rec)
        if ai_items:
            items = ai_items
            ai_generated = True

    if not items:
        if game_id == "sentence_surgery":
            # Separate seen_ids per mode so no mode truncates another mode's rotation!
            r_pick, seen_map["ss_runon"] = _pick_fresh(
                [x for x in SENTENCE_SURGERY_BANK if x["mode"] == "runon"], seen_map.get("ss_runon", []), 2
            )
            f_pick, seen_map["ss_fragment"] = _pick_fresh(
                [x for x in SENTENCE_SURGERY_BANK if x["mode"] == "fragment"], seen_map.get("ss_fragment", []), 2
            )
            m_pick, seen_map["ss_mechanics"] = _pick_fresh(
                [x for x in SENTENCE_SURGERY_BANK if x["mode"] == "mechanics"], seen_map.get("ss_mechanics", []), 2
            )
            items = r_pick + f_pick + m_pick
            random.shuffle(items)
        elif game_id == "word_forge":
            items = _build_word_forge_pack(rec, sa, count=6)
        elif game_id == "homophone_asteroids":
            items, seen_map["homophone_asteroids"] = _pick_fresh(HOMOPHONE_ASTEROIDS_BANK, seen_map.get("homophone_asteroids", []), 7)
        elif game_id == "sentence_stretch":
            items, seen_map["sentence_stretch"] = _pick_fresh(SENTENCE_STRETCH_BANK, seen_map.get("sentence_stretch", []), 5)
        elif game_id == "typing_arena":
            items, seen_map["typing_arena"] = _pick_fresh(TYPING_ARENA_BANK, seen_map.get("typing_arena", []), 5)
            deck = spelling_srs.ensure_deck(rec)
            due_words = [c["word"] for c in (deck.get("cards") or {}).values() if c.get("box", 1) < 5]
            if len(due_words) >= 2:
                pair = random.sample(due_words, 2)
                inj = _ascii_normalize(f"Watch how cleanly I spell {pair[0]} and {pair[1]} today!")
                if _is_pure_typeable_ascii(inj):
                    items[0] = {"id": f"deck_ty_{pair[0]}_{pair[1]}", "tier": 2, "tag": "Your Spelling Deck", "text": inj}
        elif game_id == "clue_detective":
            items, seen_map["clue_detective"] = _pick_fresh(CLUE_DETECTIVE_BANK, seen_map.get("clue_detective", []), 3)

        _save_rec(rec, sandbox=sandbox)

    # Unconditional shuffling for BOTH AI packs and curated packs!
    _shuffle_pack_choices(game_id, items)

    return {
        "game": meta,
        "ai_generated": ai_generated,
        "mastery_tier": int(rc.get("mastery_tier") or 1),
        "items": items,
    }


# --------------------------------------------------------------------------- Hardened Sentence & Stylus Verification

# Strict explicit finite/auxiliary/action verb matcher — includes subject+verb contractions
# (`you're`, `they're`, `it's`, `I'm`, etc.) and common irregulars (`became`, `led`, `bit`, etc.)
# while NEVER matching arbitrary plural nouns like "cats", "dogs", or "shields"!
_REAL_VERB_RE = re.compile(
    r"\b("
    r"is|are|was|were|am|be|been|being|has|have|had|do|does|did|can|cannot|could|will|would|shall|should|may|might|must|"
    r"isn't|aren't|wasn't|weren't|hasn't|haven't|hadn't|don't|doesn't|didn't|can't|couldn't|won't|wouldn't|shouldn't|mustn't|"
    r"i'm|you're|we're|they're|he's|she's|it's|that's|there's|here's|who's|what's|"
    r"i've|you've|we've|they've|i'll|you'll|he'll|she'll|we'll|they'll|i'd|you'd|he'd|she'd|we'd|they'd|"
    r"become|becomes|became|lead|leads|led|let|lets|bite|bites|bit|bitten|carve|carves|split|splits|burst|bursts|"
    r"talk|talks|mimic|mimics|seem|seems|appear|appears|disappear|disappears|stay|stays|remain|remains|happen|happens|"
    r"belong|belongs|contain|contains|mention|mentions|reveal|reveals|notice|notices|spot|spots|detect|detects|"
    r"go|goes|went|gone|get|gets|got|make|makes|made|take|takes|took|taken|see|sees|saw|seen|come|comes|came|"
    r"run|runs|ran|fly|flies|flew|flown|catch|catches|caught|bring|brings|brought|teach|teaches|taught|"
    r"throw|throws|threw|thrown|draw|draws|drew|drawn|grow|grows|grew|grown|swim|swims|swam|swum|"
    r"write|writes|wrote|written|drive|drives|drove|driven|ride|rides|rode|ridden|wake|wakes|woke|woken|"
    r"break|breaks|broke|broken|brake|brakes|braked|tear|tears|tore|torn|shoot|shoots|shot|fight|fights|fought|"
    r"find|finds|found|give|gives|gave|given|say|says|said|tell|tells|told|keep|keeps|kept|leave|leaves|left|"
    r"build|builds|built|eat|eats|ate|eaten|drink|drinks|drank|drunk|steal|steals|stole|stolen|hide|hides|hid|hidden|"
    r"wear|wears|wore|worn|know|knows|knew|known|think|thinks|thought|hear|hears|heard|feel|feels|felt|fall|falls|fell|fallen|"
    r"hold|holds|held|stand|stands|stood|sit|sits|sat|sleep|sleeps|slept|win|wins|won|lose|loses|lost|"
    r"speak|speaks|spoke|spoken|choose|chooses|chose|chosen|blow|blows|blew|blown|cut|cuts|hit|hits|put|puts|"
    r"buy|buys|bought|pay|pays|paid|send|sends|sent|spend|spends|spent|sell|sells|sold|dig|digs|dug|"
    r"ring|rings|rang|rung|sing|sings|sang|sung|sink|sinks|sank|sunk|burn|burns|burnt|shine|shines|shone|"
    r"freeze|freezes|froze|frozen|melt|melts|shake|shakes|shook|shaken|slide|slides|slid|stick|sticks|stuck|"
    r"strike|strikes|struck|swing|swings|swung|creep|creeps|crept|sneak|sneaks|snuck|leap|leaps|leapt|"
    r"set|sets|shut|shuts|read|reads|show|shows|prove|proves|use|uses|compare|compares|act|acts|imitate|imitates|"
    r"sound|sounds|call|calls|mean|means|meant|point|points|describe|describes|refer|refers|explain|explains|"
    r"look|looks|walk|walks|jump|jumps|sprint|sprints|dodge|dodges|block|blocks|carry|carries|follow|follows|chase|chases|"
    r"grab|grabs|drop|drops|stop|stops|open|opens|close|closes|lock|locks|unlock|unlocks|escape|escapes|save|saves|rescue|rescues|"
    r"create|creates|destroy|destroys|protect|protects|defend|defends|attack|attacks|launch|launches|land|lands|crash|crashes|"
    r"explode|explodes|enter|enters|arrive|arrives|return|returns|wait|waits|reach|reaches|change|changes|switch|switches|"
    r"blast|blasts|shatter|shatters|glow|glows|solve|solves|chew|chews|wash|washes|spark|sparks|flash|flashes|"
    r"zoom|zooms|soar|soars|rocket|rockets|vault|vaults|dive|dives|dove|snatch|snatches|forge|forges|craft|crafts|"
    r"play|plays|like|likes|love|loves|want|wants|need|needs|try|tries|help|helps|work|works|start|starts|"
    r"live|lives|move|moves|turn|turns|watch|watches|check|checks|test|tests|pull|pulls|push|pushes|bend|bends|bent|"
    r"whisper|whispers|shout|shouts|yell|yells|scream|screams|laugh|laughs|cheer|cheers|roar|roars|bark|barks|howl|howls|hiss|hisses|"
    r"rumble|rumbles|drip|drips|pour|pours|spill|spills|float|floats|sail|sails|skate|skates|slip|slips|bounce|bounces|roll|rolls|"
    r"smell|smells|lick|licks|hang|hangs|hung|spin|spins|spun|snap|snaps|drag|drags|pulse|pulses|climb|climbs|"
    r"[a-z]{3,}ed|[a-z]{3,}ing"
    r")\b",
    re.I,
)


def verify_production_sentence(
    text: str,
    *,
    required_word: str = "",
    require_because: bool = False,
    context_prompt: str = "",
    use_ai_check: bool = True,
) -> dict[str, Any]:
    """Critic-hardened Homework-Standard verifier (deterministic + Gemini check_writing + semantic check)."""
    raw = (text or "").strip()
    words = re.findall(r"[A-Za-z']+", raw)
    issues: list[str] = []

    if len(words) < 4:
        issues.append("Write a full sentence (at least 4 words).")
    if raw and not raw[0].isupper():
        issues.append("Start with a capital letter!")
    if raw and raw[-1] not in ".!?":
        issues.append("Add ending punctuation (. ! or ?)!")
    if required_word:
        req = required_word.strip().lower()
        if req and not re.search(rf"\b{re.escape(req)}\b", raw.lower()):
            issues.append(f"Use the target word '{required_word}' inside your sentence!")
    if require_because or (required_word or "").strip().lower() in ("because", "since"):
        m_bec = re.search(r"\b(because|since)\b", raw, re.I)
        if not m_bec:
            issues.append("Use 'because' to prove WHY your evidence solves the case!")
        else:
            after = raw[m_bec.end():].strip()
            after_words = re.findall(r"[A-Za-z']+", after)
            if len(after_words) < 3:
                issues.append("Finish explaining your proof AFTER 'because' (at least 3 words)!")
            elif not _REAL_VERB_RE.search(after):
                issues.append("Add a verb in your proof after 'because' (e.g. '...because his boots had oak splinters.')!")
    else:
        m_any_bec = re.search(r"\b(because|since)\b", raw, re.I)
        if m_any_bec and len(re.findall(r"[A-Za-z']+", raw[m_any_bec.end():])) < 2:
            issues.append("Finish your reason after 'because'!")

    # Reject dangling dependent fragments at sentence start
    if re.match(r"^(because|when|while|although|if|before|after)\b", raw.lower()) and "," not in raw and len(words) < 7:
        issues.append("Finish the whole thought after your opener!")

    # Reject repeated-word spam
    unique_alpha = {w.lower() for w in words}
    if len(words) >= 4 and len(unique_alpha) <= 2:
        issues.append("Write a real sentence instead of repeating the same words!")

    # Strict verb presence guard (rejects "The cat their blue dog." AND "Cats dogs their shields.")
    if len(words) >= 4 and not _REAL_VERB_RE.search(raw):
        issues.append("Add a real action verb so somebody is doing something!")

    if issues:
        return {"ok": False, "issues": issues, "feedback": issues[0], "word_count": len(words), "checked_by": "deterministic"}

    # Full Gemini grammar, spelling, completeness & semantic relevance verification
    checked_by = "deterministic"
    if use_ai_check and api_key():
        try:
            chk = thinking.check_writing(raw)
            checked_by = "gemini_check_writing"
            sents = chk.get("sentences") or []
            # Require ALL sentences to be complete (blocks "I know Sam stole it. Because boots.")
            if sents and not all(s.get("complete") for s in sents):
                return {
                    "ok": False,
                    "issues": ["Make sure every sentence is complete (no trailing fragments)!"],
                    "feedback": "Almost! One part is an incomplete fragment — make sure every sentence has Who/What + Does What.",
                    "word_count": len(words),
                    "checked_by": checked_by,
                }
            ms = chk.get("misspellings") or []
            if ms:
                m0 = ms[0]
                return {
                    "ok": False,
                    "issues": [f"Check spelling of '{m0['wrote']}'"],
                    "feedback": f"Almost a direct hit! Double-check the spelling of “{m0['wrote']}” (starts with {m0['meant'][:2]}…).",
                    "word_count": len(words),
                    "checked_by": checked_by,
                }
            gf = chk.get("grammar_fixes") or []
            if gf:
                g0 = gf[0]
                return {
                    "ok": False,
                    "issues": [g0.get("rule") or "Check grammar!"],
                    "feedback": f"Quick grammar fix: {g0.get('rule') or 'Check your word choice.'}",
                    "word_count": len(words),
                    "checked_by": checked_by,
                }
            # Fast semantic sanity check when verifying homophone meaning or detective evidence
            if required_word or context_prompt:
                sem_ok, sem_tip = _semantic_sentence_check(raw, required_word=required_word, context_prompt=context_prompt)
                if not sem_ok:
                    return {"ok": False, "issues": [sem_tip], "feedback": sem_tip, "word_count": len(words), "checked_by": "gemini_semantic"}
        except Exception:
            pass

    return {
        "ok": True,
        "issues": [],
        "feedback": "Clean Homework-Standard sentence — Direct hit!",
        "word_count": len(words),
        "checked_by": checked_by,
    }


def _semantic_sentence_check(raw: str, *, required_word: str = "", context_prompt: str = "") -> tuple[bool, str]:
    """Quick Gemini semantic relevance & homophone-usage check (thinking_budget=0 for sub-second speed!)."""
    sem_prompt = (
        f"Grade 3-4 student sentence: \"{raw}\"\n"
        + (f"Target word that MUST be used with its CORRECT meaning/part of speech: '{required_word}'\n" if required_word else "")
        + (f"Evidence/case context the explanation MUST actually match (reject silly/unrelated excuses): {context_prompt}\n" if context_prompt else "")
        + 'Reply ONLY raw JSON: {"ok": true|false, "tip": "short encouraging 1-line fix if false"}'
    )
    c = genai_client(timeout_ms=3500)
    sr = c.models.generate_content(
        model=FAST_MODEL,
        contents=sem_prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    sraw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (sr.text or "").strip())
    sdat = json.loads(sraw)
    if isinstance(sdat, dict) and sdat.get("ok") is False:
        tip = str(sdat.get("tip") or "Double-check that your sentence uses the word/evidence accurately!")
        return False, tip
    return True, ""


def read_forge_handwriting(image_b64: str, expected_word: str = "") -> dict[str, Any]:
    if not api_key():
        return {"ok": False, "text": "", "error": "Handwriting pen recognition requires your Gemini API key. Switch to Type It anytime!"}
    raw = (image_b64 or "").strip()
    if "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        png_bytes = base64.b64decode(raw)
    except Exception:
        return {"ok": False, "text": "", "error": "Could not decode handwriting image."}
    ctx = "Single English spelling word written in Word Forge (transcribe exact letters written, preserving any misspellings)."
    try:
        res = media.read_handwriting(png_bytes, context=ctx, skip_letter_check=True)
    except Exception:
        return {"ok": False, "text": "", "error": "Couldn't reach handwriting vision right now — try again or switch to Type It!"}
    txt = re.sub(r"[^A-Za-z'-]", "", (res.get("text") or "").strip()).lower()
    if not res.get("legible") or not txt:
        return {"ok": False, "text": "", "error": "Couldn't quite read those letters — try writing a little larger on the grass line!"}
    return {"ok": True, "text": txt, "expected_match": bool(expected_word and txt == expected_word.strip().lower())}


# --------------------------------------------------------------------------- Completion, Mastery & Arcade Credit

def record_game_completion(payload: dict[str, Any], *, sandbox: bool = False) -> dict[str, Any]:
    game_id = str(payload.get("game_id") or "")
    if game_id not in GAME_BY_ID:
        raise ValueError(f"Unknown skill game: {game_id}")
    meta = GAME_BY_ID[game_id]

    correct = max(0, int(payload.get("correct") or 0))
    total = max(1, int(payload.get("total") or 1))
    accuracy = max(0, min(100, int(round(100.0 * correct / total))))
    score = max(0, int(payload.get("score") or 0))
    raw_active = max(0.0, float(payload.get("active_seconds") or 0.0))
    # Anti-AFK server-side cap: max 40s per item (capped at 180s per round)
    max_for_items = 180.0 if game_id == "typing_arena" else min(180.0, max(35.0, total * 40.0))
    active_seconds = min(max_for_items, raw_active)

    wpm = max(0, int(payload.get("wpm") or 0))
    cpm = max(0, int(payload.get("cpm") or 0))
    production_passed = bool(payload.get("production_passed", False))
    production_sentence = str(payload.get("production_sentence") or "").strip()[:180]
    # Only honor `production_passed` for games with genuine typed/handwritten retrieval or sentence composition
    if game_id in ("sentence_surgery", "sentence_stretch"):
        production_passed = False
    word_results = payload.get("word_results") or []
    skill_hits = payload.get("skill_hits") or {}

    rec, sa = _active_rec(sandbox=sandbox)
    rc = curriculum_tracker.ensure_report_card(rec)
    ts_iso = now_iso()
    today = ts_iso[:10]

    # True consecutive-day streak logic using local calendar day (avoids UTC midnight rollover in evening!)
    sa["total_runs"] = int(sa.get("total_runs") or 0) + 1
    sa["total_correct"] = int(sa.get("total_correct") or 0) + correct
    sa["total_attempts"] = int(sa.get("total_attempts") or 0) + total
    local_today = datetime.date.today()
    local_today_str = local_today.isoformat()
    prev_day = str(sa.get("last_played_date") or "")
    if prev_day != local_today_str:
        try:
            d_prev = datetime.date.fromisoformat(prev_day) if prev_day else None
            if d_prev and (local_today - d_prev).days == 1:
                sa["streak_days"] = int(sa.get("streak_days") or 0) + 1
            else:
                sa["streak_days"] = 1
        except ValueError:
            sa["streak_days"] = 1
        sa["last_played_date"] = local_today_str

    stars = 3 if (accuracy >= 90 and (production_passed or game_id in ("sentence_surgery", "sentence_stretch", "typing_arena"))) else (2 if accuracy >= 75 else (1 if accuracy >= 65 else 0))
    gs = sa.setdefault("games", {}).setdefault(game_id, {
        "runs": 0, "best_score": 0, "best_accuracy": 0, "best_wpm": 0, "mastery_stars": 0, "last_played": "",
    })
    gs["runs"] = int(gs.get("runs") or 0) + 1
    gs["best_score"] = max(int(gs.get("best_score") or 0), score)
    gs["best_accuracy"] = max(int(gs.get("best_accuracy") or 0), accuracy)
    gs["best_wpm"] = max(int(gs.get("best_wpm") or 0), wpm)
    gs["mastery_stars"] = max(int(gs.get("mastery_stars") or 0), stars)
    gs["last_played"] = ts_iso

    # Sync Word Forge retrieval into Leitner Spaced-Repetition Deck (preserving AI card metadata!)
    srs_updates: list[dict[str, Any]] = []
    if word_results:
        deck = spelling_srs.ensure_deck(rec)
        for wr in word_results:
            w = str(wr.get("word") or "").strip().lower()
            if not w:
                continue
            first_try = bool(wr.get("first_try", False))
            wrote = str(wr.get("wrote") or "").strip()
            if w not in deck["cards"]:
                meta_w = next((x for x in WORD_FORGE_CURRICULUM_BANK if x["word"].lower() == w), None)
                parts_str = str(wr.get("parts") or "").strip()
                if not parts_str and meta_w:
                    parts_str = " + ".join(p for p in [meta_w.get("prefix"), meta_w.get("base"), meta_w.get("suffix")] if p)
                deck["cards"][w] = {
                    "word": w,
                    "wrote": wrote if not first_try else "",
                    "parts": parts_str or w,
                    "note": str(wr.get("note") or (meta_w or {}).get("note") or ""),
                    "unit": str(wr.get("unit") or (meta_w or {}).get("unit") or "Word Forge"),
                    "source": "word_forge",
                    "box": 1,
                    "next_due": time.time(),
                    "successes": 0,
                    "lapses": 0,
                }
            updated_card = spelling_srs.record_retrieval_result(rec, w, correct_first_try=first_try)
            if updated_card:
                srs_updates.append({"word": w, "box": updated_card.get("box", 1), "first_try": first_try})

    # Strict anti-inflation Ontario Report Card updates: REQUIRE accuracy >= 65% to boost ANY level!
    sk = rc["skills"]
    skills_boosted: list[str] = []

    def _bump_skill(sid: str, est_level: int, evidence_txt: str) -> None:
        if sid not in sk or est_level <= 0 or accuracy < 65:
            return
        entry = sk[sid]
        old = int(entry.get("level") or 0)
        entry["attempts"] = int(entry.get("attempts") or 0) + 1
        if est_level > old:
            entry["level"] = est_level
            entry["trend"] = "rising"
            skills_boosted.append(sid)
        elif old == 0:
            entry["level"] = est_level
            entry["trend"] = "new"
            skills_boosted.append(sid)
        elif est_level == old:
            entry["trend"] = "steady"
        entry["evidence"] = evidence_txt[:190]
        entry["updated"] = today
        hist = entry.setdefault("history", [])
        hist.append({"date": today, "session": f"skill_{game_id}", "level": entry["level"]})
        entry["history"] = hist[-20:]

    if accuracy >= 65:
        if game_id == "typing_arena" and cpm >= 25:
            k_est = 4 if (cpm >= 140 and accuracy >= 92) else (3 if (cpm >= 95 and accuracy >= 90) else (2 if (cpm >= 55 and accuracy >= 85) else 1))
            _bump_skill("D2.2_keyboarding", k_est, f"Neon Turbo Typing: {wpm} WPM ({cpm} cpm) at {accuracy}% accuracy")
            if accuracy >= 92:
                _bump_skill("B3.3_mechanics", 2 if accuracy < 96 else 3, f"Typed clean capitals & punctuation at {accuracy}% accuracy")
        elif game_id == "word_forge":
            est = 3 if (accuracy >= 85 and total >= 5) else 2
            words_ok = [u["word"] for u in srs_updates if u["first_try"]][:4]
            ev = f"Word Forge: {correct}/{total} forged from memory ({', '.join(words_ok) or 'practice'})"
            _bump_skill("B2.3_morphology", est, ev)
            if accuracy >= 80:
                _bump_skill("B2.1_2_orthography", est, ev)
        else:
            base_est = 3 if (accuracy >= 85 and (production_passed or game_id in ("sentence_surgery", "sentence_stretch"))) else 2
            ev_tail = f" · “{production_sentence}”" if production_sentence else ""
            if skill_hits:
                for sid, stats_s in skill_hits.items():
                    sc = int(stats_s.get("correct") or 0)
                    st = max(1, int(stats_s.get("total") or 1))
                    s_acc = 100.0 * sc / st
                    if s_acc >= 65:
                        s_est = min(base_est, 3 if s_acc >= 85 else 2)
                        _bump_skill(sid, s_est, f"{meta['title']}: {sc}/{st} ({round(s_acc)}%){ev_tail}")
            else:
                for sid in meta["skills"][:2]:
                    _bump_skill(sid, base_est, f"{meta['title']}: {correct}/{total} ({accuracy}%){ev_tail}")

    rc["mastery_tier"] = curriculum_tracker.compute_mastery_tier(rc)
    rc["updated"] = ts_iso

    sa.setdefault("recent_runs", []).append({
        "date": ts_iso,
        "game_id": game_id,
        "title": meta["title"],
        "score": score,
        "correct": correct,
        "total": total,
        "accuracy": accuracy,
        "wpm": wpm,
        "stars": stars,
        "production_sentence": production_sentence,
        "skills_boosted": skills_boosted,
    })
    sa["recent_runs"] = sa["recent_runs"][-30:]
    _save_rec(rec, sandbox=sandbox)

    arcade_reward = arcade.record_skill_game_credit(
        active_seconds=active_seconds,
        accuracy=accuracy,
        items_completed=correct,
        production_passed=production_passed,
        game_title=meta["title"],
        sandbox=sandbox,
    )

    return {
        "ok": True,
        "game_id": game_id,
        "stars": stars,
        "accuracy": accuracy,
        "score": score,
        "srs_updates": srs_updates,
        "skills_boosted": skills_boosted,
        "mastery_tier": rc["mastery_tier"],
        "arcade_reward": arcade_reward,
        "arcade": arcade.client_status(sandbox=sandbox),
    }
