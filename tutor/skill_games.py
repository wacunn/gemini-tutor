"""Starblade Arcade v2.2 — Stealth-School & Closed-Loop ZPD Adaptive Arenas for Gemini Tutor.

6 bespoke 60fps 2x-DPR OLED Canvas2D + Lenovo Yoga stylus games ("school without school smell"):
zero curriculum jargon on player screens, 16-microskill spaced-repetition & ZPD tier adaptation,
closed-loop Studio writing trouble-spot ingestion, and full Ontario Grade 3–4 reporting on /parent:
  1. Cyber Blade            — 30 stream splits, circuit repairs & security/comms seals
  2. Obsidian Forge         — 42 rune blades + spoken context + Yoga pen OCR + Vault SRS
  3. Starshield Turret      — 36 orbital waves + live on-canvas Dreadnought Boss wave
  4. Reactor Overdrive      — 20 twin-core bridge & power-word fusion runs
  5. Neon Drift: Toronto    — 30 pure-ASCII highway laps + adaptive rival cruisers
  6. Shadow Detective       — 16 balanced 4×4×4×4 noir dossiers + highlighter + final verdict
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
        "title": "Cyber Blade",
        "parent_title": "Cyber Blade (Sentence Surgery · B3.1/B3.3)",
        "subtitle": "Slice jammed streams & lock broken circuits.",
        "icon": "⚔️",
        "accent": "#38bdf8",
        "glow": "rgba(56, 189, 248, 0.35)",
        "est_minutes": "3 min",
        "controls": "Stylus · Tap · Voice",
        "skills": ["B3.1_simple", "B3.1_boundaries", "B3.3_mechanics", "B3.3_dialogue", "D2.5_6_revision"],
    },
    {
        "id": "word_forge",
        "title": "Obsidian Forge",
        "parent_title": "Obsidian Forge (Morphology & Spelling · B2.1–B2.3)",
        "subtitle": "Hammer rune blades & strike words into steel.",
        "icon": "🔥",
        "accent": "#f97316",
        "glow": "rgba(249, 115, 22, 0.35)",
        "est_minutes": "3 min",
        "controls": "Runes · Voice · Pen/Keys",
        "skills": ["B2.1_2_orthography", "B2.3_morphology"],
    },
    {
        "id": "homophone_asteroids",
        "title": "Starshield Turret",
        "parent_title": "Starshield Turret (Homophones & Verbs · B3.2/B2.4)",
        "subtitle": "Blast twin decoy meteors & vaporize the Dreadnought.",
        "icon": "☄️",
        "accent": "#a855f7",
        "glow": "rgba(168, 85, 247, 0.38)",
        "est_minutes": "3 min",
        "controls": "Tap · Keys 1–3 · Boss Beam",
        "skills": ["B3.2_grammar", "B2.4_vocabulary"],
    },
    {
        "id": "sentence_stretch",
        "title": "Reactor Overdrive",
        "parent_title": "Reactor Overdrive (Compound/Complex & Verbs · B3.1/B2.4)",
        "subtitle": "Link twin power cores to hit 100% Overdrive.",
        "icon": "⚡",
        "accent": "#10b981",
        "glow": "rgba(16, 185, 129, 0.35)",
        "est_minutes": "3 min",
        "controls": "Bridges · Power Words",
        "skills": ["B3.1_compound", "B3.1_complex", "B2.4_vocabulary"],
    },
    {
        "id": "typing_arena",
        "title": "Neon Drift: Toronto",
        "parent_title": "Neon Drift: Toronto (Keyboarding Fluency · D2.2)",
        "subtitle": "Outrun 3 rival cruisers down the midnight highway.",
        "icon": "🏎️",
        "accent": "#22d3ee",
        "glow": "rgba(34, 211, 238, 0.38)",
        "est_minutes": "2–3 min",
        "controls": "Keyboard · Live Rivals",
        "skills": ["D2.2_keyboarding", "B3.3_mechanics"],
    },
    {
        "id": "clue_detective",
        "title": "Shadow Detective",
        "parent_title": "Shadow Detective (Inference, Craft & POV · C2.3/C1)",
        "subtitle": "Spotlight the hidden clue & slam CASE CLOSED.",
        "icon": "🔎",
        "accent": "#facc15",
        "glow": "rgba(250, 204, 21, 0.35)",
        "est_minutes": "4 min",
        "controls": "Stylus Highlight · Verdict",
        "skills": ["C2.3_inference", "C1.2_3_craft", "C1.5_pov"],
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
    """Returns a non-spoiling smithing hint for Memory Forge (zero school/worksheet jargon!)."""
    if direct_memory:
        return "Forge hint: Tricky vault word — listen closely to every sound and strike it from memory!"
    hints = {
        "double": "Forge hint: Short sound + single end letter — double that last letter before locking on the ending!",
        "drop_e": "Forge hint: Drop the silent final 'e' on the base before locking on this ending!",
        "y_to_i": "Forge hint: Flip the final 'y' to 'i' before locking on this ending!",
        "keep": "Forge hint: Lock every part together cleanly — zero letters dropped or doubled!",
    }
    return hints.get(rule, f"Focus on {unit} and strike every letter cleanly from memory!")


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
     "prompt": "SLASH this jammed stream in half cleanly!",
     "words": ["Our", "minecart", "jumped", "the", "broken", "rail", "we", "landed", "in", "deep", "water."], "split_after": 5,
     "fixed": "Our minecart jumped the broken rail. We landed in deep water.",
     "explain": "'Our minecart jumped the broken rail' is complete — start 'We landed...' as sentence two."},
    {"id": "ss_r04", "mode": "runon", "tier": 1, "skill": "B3.1_boundaries",
     "prompt": "Find the hidden seam and SLASH these fused actions!",
     "words": ["The", "wolf", "barked", "at", "the", "skeleton", "Leo", "raised", "his", "iron", "shield."], "split_after": 5,
     "fixed": "The wolf barked at the skeleton. Leo raised his iron shield.",
     "explain": "Sentence one finishes after 'skeleton'; 'Leo raised...' begins the second sentence."},
    {"id": "ss_r05", "mode": "runon", "tier": 2, "skill": "B3.1_boundaries",
     "prompt": "SLASH where sentence one ends and sentence two starts!",
     "words": ["The", "rogue", "robot", "charged", "down", "Yonge", "Street", "citizens", "ducked", "behind", "a", "streetcar."], "split_after": 6,
     "fixed": "The rogue robot charged down Yonge Street. Citizens ducked behind a streetcar.",
     "explain": "Place a period after 'Street' and capitalize 'Citizens'."},
    {"id": "ss_r06", "mode": "runon", "tier": 2, "skill": "B3.1_boundaries",
     "prompt": "SLASH this jammed stream cleanly!",
     "words": ["A", "giant", "squid", "inked", "the", "submarine", "window", "the", "radar", "alarm", "started", "beeping."], "split_after": 6,
     "fixed": "A giant squid inked the submarine window. The radar alarm started beeping.",
     "explain": "Two full actions jammed together — end the first sentence right after 'window'."},
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
     "prompt": "Find the hidden boundary and SLASH it!",
     "words": ["After", "midnight,", "the", "Redstone", "door", "jammed", "nobody", "could", "escape", "the", "vault."], "split_after": 5,
     "fixed": "After midnight, the Redstone door jammed. Nobody could escape the vault.",
     "explain": "'After midnight,' belongs to sentence one; sentence two begins at 'Nobody'."},
    {"id": "ss_r10", "mode": "runon", "tier": 3, "skill": "B3.1_boundaries",
     "prompt": "Careful! SLASH right between the two complete thoughts!",
     "words": ["Beneath", "the", "frozen", "lake,", "a", "hatch", "opened", "three", "glowing", "drones", "rose", "out."], "split_after": 6,
     "fixed": "Beneath the frozen lake, a hatch opened. Three glowing drones rose out.",
     "explain": "Keep the opener with 'a hatch opened', then start 'Three glowing drones...' cleanly."},

    # ---- 10 Broken-Circuit Repair Cases ----
    {"id": "ss_f01", "mode": "fragment", "tier": 1, "skill": "B3.1_simple",
     "prompt": "Missing an action! Pick the repair that powers a full sentence:",
     "broken": "The silver dragon on top of the obsidian tower.", "missing": "action",
     "choices": [
         {"text": "The silver dragon on top of the obsidian tower breathed blue fire.", "ok": True},
         {"text": "On top of the very tall obsidian tower.", "ok": False, "why": "Still just a place — nobody is doing anything!"},
         {"text": "The silver dragon with giant glowing wings.", "ok": False, "why": "Adds detail, but still has no real action!"},
     ],
     "explain": "Every sentence needs WHO/WHAT ('The silver dragon') + DOES WHAT ('breathed blue fire')."},
    {"id": "ss_f02", "mode": "fragment", "tier": 1, "skill": "B3.1_simple",
     "prompt": "Who did this action? Lock in the missing hero!",
     "broken": "Sprinted past the laser grid before it shut.", "missing": "who",
     "choices": [
         {"text": "Very quickly past the laser grid before it shut.", "ok": False, "why": "Still doesn't tell us WHO sprinted!"},
         {"text": "Captain Maple sprinted past the laser grid before it shut.", "ok": True},
         {"text": "Sprinting past the buzzing red laser grid.", "ok": False, "why": "An '-ing' phrase with nobody in charge is still incomplete."},
     ],
     "explain": "Adding 'Captain Maple' tells us who actually sprinted!"},
    {"id": "ss_f03", "mode": "fragment", "tier": 1, "skill": "B3.1_simple",
     "prompt": "Repair this broken line so something actually happens!",
     "broken": "Three armoured creepers hiding near the oak farmhouse.", "missing": "action",
     "choices": [
         {"text": "Three armoured creepers crouched silently near the oak farmhouse.", "ok": True},
         {"text": "Near the quiet oak farmhouse at midnight.", "ok": False, "why": "Just a place and time — nobody acts!"},
         {"text": "Three green armoured creepers with glowing eyes.", "ok": False, "why": "Describes the creepers, but still no real action!"},
     ],
     "explain": "Swapping 'hiding' for the strong action 'crouched' completes the circuit!"},
    {"id": "ss_f04", "mode": "fragment", "tier": 1, "skill": "B3.1_simple",
     "prompt": "Who threw the bucket? Pick the complete fix:",
     "broken": "Tossed a water bucket down the cliff just in time.", "missing": "who",
     "choices": [
         {"text": "Down the steep mossy cliff just in time.", "ok": False, "why": "Still missing WHO tossed the bucket!"},
         {"text": "Alex tossed a water bucket down the cliff just in time.", "ok": True},
         {"text": "Tossing a shiny iron water bucket fast.", "ok": False, "why": "Still missing who did it!"},
     ],
     "explain": "Adding 'Alex' gives the action a clear hero."},
    {"id": "ss_f05", "mode": "fragment", "tier": 2, "skill": "B3.1_simple",
     "prompt": "This 'Because...' opener was left hanging! Finish what happened:",
     "broken": "Because the diamond pickaxe broke right next to the lava.", "missing": "result",
     "choices": [
         {"text": "Because the diamond pickaxe broke right next to the lava, Alex built a cobblestone bridge.", "ok": True},
         {"text": "Because the glowing hot lava bubbled underground.", "ok": False, "why": "Still starts with 'Because' and never tells what happened next!"},
         {"text": "Right next to the deep glowing lava pit.", "ok": False, "why": "Just a location — not a complete thought."},
     ],
     "explain": "Starting with 'Because...' sets up a reason, so you have to finish with what happened!"},
    {"id": "ss_f06", "mode": "fragment", "tier": 2, "skill": "B3.1_simple",
     "prompt": "Finish this hanging 'When...' opener!",
     "broken": "When the alien disguise flickered in the stadium lights.", "missing": "result",
     "choices": [
         {"text": "Inside the bright Rogers Centre stadium lights.", "ok": False, "why": "Nobody is doing anything here!"},
         {"text": "When the alien disguise flickered in the stadium lights, the crowd gasped.", "ok": True},
         {"text": "Flickering brightly under the huge stadium lights.", "ok": False, "why": "Still missing who did what."},
     ],
     "explain": "Pairing the 'When...' opener with 'the crowd gasped' finishes the thought!"},
    {"id": "ss_f07", "mode": "fragment", "tier": 2, "skill": "B3.1_simple",
     "prompt": "Finish this dangling 'Before...' opener!",
     "broken": "Before the submarine hatch sealed against the ocean pressure.", "missing": "result",
     "choices": [
         {"text": "Before the submarine hatch sealed against the ocean pressure, the diver pulled the sample crate inside.", "ok": True},
         {"text": "Against the freezing deep ocean pressure.", "ok": False, "why": "Only tells where — nobody acts!"},
         {"text": "Before sealing the heavy steel hatch tight.", "ok": False, "why": "Leaves us hanging: what happened before?"},
     ],
     "explain": "An opener starting with 'Before...' needs the main action that happened in time!"},
    {"id": "ss_f08", "mode": "fragment", "tier": 2, "skill": "B3.1_simple",
     "prompt": "Power up this incomplete '-ing' line!",
     "broken": "Dodging laser beams across the rooftops of downtown Toronto.", "missing": "who + action",
     "choices": [
         {"text": "Across the neon rooftops of downtown Toronto.", "ok": False, "why": "Just a place on the map!"},
         {"text": "Zara dodged laser beams across the rooftops of downtown Toronto.", "ok": True},
         {"text": "Fast red laser beams flashing across the rooftops.", "ok": False, "why": "Still missing a real action word!"},
     ],
     "explain": "'Zara dodged...' locks in both the hero and the action."},
    {"id": "ss_f09", "mode": "fragment", "tier": 3, "skill": "B3.1_simple",
     "prompt": "Finish this hanging 'Although...' twist!",
     "broken": "Although the blizzard buried every road to the observatory.", "missing": "result",
     "choices": [
         {"text": "Although the blizzard buried every road to the observatory, the scientists kept the telescope running.", "ok": True},
         {"text": "Although the thick snow drifted ten feet high.", "ok": False, "why": "Still leaves 'Although...' hanging with no result!"},
         {"text": "Every icy road leading to the mountain observatory.", "ok": False, "why": "Nobody does anything here!"},
     ],
     "explain": "'Although...' sets up an obstacle, so finish it with the surprising action that still happened!"},
    {"id": "ss_f10", "mode": "fragment", "tier": 3, "skill": "B3.1_simple",
     "prompt": "Finish this hanging 'If...' trigger!",
     "broken": "If the Redstone repeater flips one tick too late.", "missing": "result",
     "choices": [
         {"text": "One single Redstone tick too late.", "ok": False, "why": "Missing who or what acts!"},
         {"text": "If the Redstone repeater flips one tick too late, the secret piston door locks shut.", "ok": True},
         {"text": "Flipping the glowing Redstone repeater lever.", "ok": False, "why": "Still missing what happens next!"},
     ],
     "explain": "An 'If...' trigger needs the result ('the secret piston door locks shut') to complete the circuit!"},

    # ---- 10 Security & Comms Seal Cases ----
    {"id": "ss_m01", "mode": "mechanics", "tier": 1, "skill": "B3.3_mechanics",
     "prompt": "Tap EVERY glitched word to seal capitals, apostrophes & end marks!",
     "tokens": [
         {"raw": "dylan", "fix": "Dylan", "bug": True, "hint": "Capitalize the start & name!"},
         {"raw": "didnt", "fix": "didn't", "bug": True, "hint": "'did + not' needs an apostrophe: didn't!"},
         {"raw": "drop", "fix": "drop", "bug": False},
         {"raw": "his", "fix": "his", "bug": False},
         {"raw": "shield", "fix": "shield.", "bug": True, "hint": "Close the line with a period!"},
     ],
     "explain": "Start capital ('Dylan'), apostrophe in 'didn't', and end period."},
    {"id": "ss_m02", "mode": "mechanics", "tier": 1, "skill": "B3.3_mechanics",
     "prompt": "Seal the 3 capital, apostrophe & end-mark glitches in this Toronto run!",
     "tokens": [
         {"raw": "we", "fix": "We", "bug": True, "hint": "Start every line with a capital letter."},
         {"raw": "cant", "fix": "can't", "bug": True, "hint": "'can + not' needs an apostrophe: can't!"},
         {"raw": "let", "fix": "let", "bug": False},
         {"raw": "the", "fix": "the", "bug": False},
         {"raw": "robots", "fix": "robots", "bug": False},
         {"raw": "escape", "fix": "escape!", "bug": True, "hint": "Lock an exclamation mark or period at the end!"},
     ],
     "explain": "Locked start capital ('We'), apostrophe ('can't'), and end mark ('escape!')."},
    {"id": "ss_m03", "mode": "mechanics", "tier": 1, "skill": "B3.3_mechanics",
     "prompt": "Stamp the 3 missing capitals and end marks!",
     "tokens": [
         {"raw": "did", "fix": "Did", "bug": True, "hint": "Capitalize the first word!"},
         {"raw": "sam", "fix": "Sam", "bug": True, "hint": "Always capitalize names!"},
         {"raw": "craft", "fix": "craft", "bug": False},
         {"raw": "a", "fix": "a", "bug": False},
         {"raw": "compass", "fix": "compass?", "bug": True, "hint": "Questions end with a question mark (?)!"},
     ],
     "explain": "Capitalized start ('Did'), name ('Sam'), and ended the question with '?'."},
    {"id": "ss_m04", "mode": "mechanics", "tier": 2, "skill": "B3.3_mechanics",
     "prompt": "Seal the 's ownership mark, city name & end period!",
     "tokens": [
         {"raw": "the", "fix": "The", "bug": True, "hint": "Capitalize the first word!"},
         {"raw": "robots", "fix": "robot's", "bug": True, "hint": "The visor belongs to one robot: robot's!"},
         {"raw": "visor", "fix": "visor", "bug": False},
         {"raw": "glowed", "fix": "glowed", "bug": False},
         {"raw": "over", "fix": "over", "bug": False},
         {"raw": "toronto", "fix": "Toronto.", "bug": True, "hint": "Capitalize 'Toronto' and add a period!"},
     ],
     "explain": "Belonging to one robot uses 's ('robot's'), and city names like 'Toronto' get a capital."},
    {"id": "ss_m05", "mode": "mechanics", "tier": 2, "skill": "B3.3_mechanics",
     "prompt": "Seal all 4 capital, apostrophe & end-mark glitches!",
     "tokens": [
         {"raw": "they", "fix": "They", "bug": True, "hint": "Capitalize the start!"},
         {"raw": "wouldnt", "fix": "wouldn't", "bug": True, "hint": "'would + not' needs an apostrophe: wouldn't!"},
         {"raw": "enter", "fix": "enter", "bug": False},
         {"raw": "the", "fix": "the", "bug": False},
         {"raw": "nether", "fix": "Nether", "bug": True, "hint": "Capitalize the world name 'Nether'!"},
         {"raw": "without", "fix": "without", "bug": False},
         {"raw": "armour", "fix": "armour.", "bug": True, "hint": "Close the line with a period!"},
     ],
     "explain": "Start capital ('They'), apostrophe ('wouldn't'), world name ('Nether'), and end period."},
    {"id": "ss_m06", "mode": "mechanics", "tier": 2, "skill": "B3.3_dialogue",
     "prompt": "COMMS LOCK: Seal the 3 quote & name glitches in this shout!",
     "tokens": [
         {"raw": "Watch", "fix": "\"Watch", "bug": True, "hint": "Open quote marks right before the spoken words!"},
         {"raw": "out", "fix": "out", "bug": False},
         {"raw": "for", "fix": "for", "bug": False},
         {"raw": "lava", "fix": "lava!\"", "bug": True, "hint": "Lock in ! and closing quote marks!"},
         {"raw": "shouted", "fix": "shouted", "bug": False},
         {"raw": "kai", "fix": "Kai.", "bug": True, "hint": "Capitalize Kai and add a period!"},
     ],
     "explain": "Wrap spoken words in quote marks (\"Watch out for lava!\") and capitalize names."},
    {"id": "ss_m07", "mode": "mechanics", "tier": 2, "skill": "B3.3_dialogue",
     "prompt": "COMMS LOCK: Stamp the missing quote marks, comma & capitals!",
     "tokens": [
         {"raw": "the", "fix": "\"The", "bug": True, "hint": "Open quotes AND capitalize the first spoken word!"},
         {"raw": "portal", "fix": "portal", "bug": False},
         {"raw": "is", "fix": "is", "bug": False},
         {"raw": "closing", "fix": "closing,\"", "bug": True, "hint": "Comma + closing quote right before 'warned'!"},
         {"raw": "warned", "fix": "warned", "bug": False},
         {"raw": "nova", "fix": "Nova.", "bug": True, "hint": "Capitalize Nova and end with a period!"},
     ],
     "explain": "Tuck a comma inside the closing quote right before 'warned Nova.'"},
    {"id": "ss_m08", "mode": "mechanics", "tier": 2, "skill": "B3.3_dialogue",
     "prompt": "COMMS LOCK: Seal the quotes & question mark on this radio call!",
     "tokens": [
         {"raw": "where", "fix": "\"Where", "bug": True, "hint": "Open quotes and capitalize 'Where'!"},
         {"raw": "did", "fix": "did", "bug": False},
         {"raw": "the", "fix": "the", "bug": False},
         {"raw": "drone", "fix": "drone", "bug": False},
         {"raw": "go", "fix": "go?\"", "bug": True, "hint": "Keep ? INSIDE the closing quote marks!"},
         {"raw": "asked", "fix": "asked", "bug": False},
         {"raw": "maya", "fix": "Maya.", "bug": True, "hint": "Capitalize Maya and add a period!"},
     ],
     "explain": "Keep '?' tucked inside the closing quotes: \"Where did the drone go?\" asked Maya."},
    {"id": "ss_m09", "mode": "mechanics", "tier": 3, "skill": "B3.3_dialogue",
     "prompt": "COMMS LOCK: Speaker comes FIRST — seal the comma, quotes & end mark!",
     "tokens": [
         {"raw": "Leo", "fix": "Leo", "bug": False},
         {"raw": "whispered", "fix": "whispered,", "bug": True, "hint": "Put a comma right after 'whispered' before the quote!"},
         {"raw": "dont", "fix": "\"Don't", "bug": True, "hint": "Open quotes, capitalize 'Don't', and add the apostrophe!"},
         {"raw": "wake", "fix": "wake", "bug": False},
         {"raw": "the", "fix": "the", "bug": False},
         {"raw": "warden", "fix": "Warden!\"", "bug": True, "hint": "Capitalize Warden, add '!' and close quotes!"},
     ],
     "explain": "When who spoke comes first, drop a comma right before the opening quote: Leo whispered, \"Don't wake the Warden!\""},
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
    # ---- 1-1-1 Twin-Iron Forge (10 words) ----
    {"id": "wf_01", "tier": 1, "word": "trapped", "prefix": "", "base": "trap", "suffix": "ed", "rule": "double", "unit": "Twin-Iron Forge",
     "context_sentence": "The skeleton was trapped behind an iron gate.",
     "note": "Short 'a' + single 'p' -> double 'p' before '-ed'!"},
    {"id": "wf_02", "tier": 1, "word": "stopped", "prefix": "", "base": "stop", "suffix": "ed", "rule": "double", "unit": "Twin-Iron Forge",
     "context_sentence": "The streetcar stopped right outside Union Station.",
     "note": "Short vowel 'o' + single 'p' -> double the 'p' before adding -ed."},
    {"id": "wf_03", "tier": 1, "word": "running", "prefix": "", "base": "run", "suffix": "ing", "rule": "double", "unit": "Twin-Iron Forge",
     "context_sentence": "The generator is running at full power now.",
     "note": "Short 'u' + single 'n' -> double 'n' before -ing."},
    {"id": "wf_04", "tier": 2, "word": "grabbing", "prefix": "", "base": "grab", "suffix": "ing", "rule": "double", "unit": "Twin-Iron Forge",
     "context_sentence": "He escaped after grabbing the glowing diamond.",
     "note": "Short 'a' + single 'b' -> double 'b' before -ing so the vowel stays short!"},
    {"id": "wf_05", "tier": 3, "word": "unstoppable", "prefix": "un", "base": "stop", "suffix": "able", "rule": "double", "unit": "Master Rune Forge",
     "context_sentence": "With enchanted armour, the hero felt unstoppable.",
     "note": "'un-' + 'stop' (double the 'p'!) + '-able'."},
    {"id": "wf_06", "tier": 1, "word": "slipped", "prefix": "", "base": "slip", "suffix": "ed", "rule": "double", "unit": "Twin-Iron Forge",
     "context_sentence": "Her boots slipped across the wet cavern stone.",
     "note": "Short 'i' + single 'p' -> double 'p' before -ed so the vowel stays short."},
    {"id": "wf_07", "tier": 1, "word": "dropped", "prefix": "", "base": "drop", "suffix": "ed", "rule": "double", "unit": "Twin-Iron Forge",
     "context_sentence": "The drone dropped a supply crate onto the roof.",
     "note": "Short 'o' + single 'p' -> double 'p' before '-ed'!"},
    {"id": "wf_08", "tier": 2, "word": "spinning", "prefix": "", "base": "spin", "suffix": "ing", "rule": "double", "unit": "Twin-Iron Forge",
     "context_sentence": "The radar dish kept spinning through the blizzard.",
     "note": "Short 'i' + single 'n' -> double 'n' before -ing."},
    {"id": "wf_09", "tier": 2, "word": "planner", "prefix": "", "base": "plan", "suffix": "er", "rule": "double", "unit": "Twin-Iron Forge",
     "context_sentence": "Maya was the sharpest mission planner on the team.",
     "note": "Double the 'n' in 'plan' before '-er' so the short vowel stays sharp!"},
    {"id": "wf_10", "tier": 2, "word": "swimmer", "prefix": "", "base": "swim", "suffix": "er", "rule": "double", "unit": "Twin-Iron Forge",
     "context_sentence": "A fast swimmer can cross the underwater tunnel easily.",
     "note": "Short 'i' + single 'm' -> double 'm' before '-er'."},

    # ---- Silent-E Forge (10 words) ----
    {"id": "wf_11", "tier": 2, "word": "exploding", "prefix": "", "base": "explode", "suffix": "ing", "rule": "drop_e", "unit": "Silent-E Forge",
     "context_sentence": "We sprinted away from the exploding TNT block.",
     "note": "Drop the silent 'e' on the base before adding '-ing'."},
    {"id": "wf_12", "tier": 2, "word": "survivor", "prefix": "", "base": "survive", "suffix": "or", "rule": "drop_e", "unit": "Silent-E Forge",
     "context_sentence": "Only one explorer was a survivor of the ice storm.",
     "note": "Drop silent 'e' on the base before adding '-or'."},
    {"id": "wf_13", "tier": 1, "word": "chasing", "prefix": "", "base": "chase", "suffix": "ing", "rule": "drop_e", "unit": "Silent-E Forge",
     "context_sentence": "Three cyber-hounds were chasing the hoverbike.",
     "note": "Drop silent 'e' on the base before adding '-ing'."},
    {"id": "wf_14", "tier": 1, "word": "gliding", "prefix": "", "base": "glide", "suffix": "ing", "rule": "drop_e", "unit": "Silent-E Forge",
     "context_sentence": "The hawk was gliding high over the deep harbour.",
     "note": "Drop silent 'e' on the base before adding '-ing'."},
    {"id": "wf_15", "tier": 2, "word": "invader", "prefix": "", "base": "invade", "suffix": "er", "rule": "drop_e", "unit": "Silent-E Forge",
     "context_sentence": "Our bio-scanner spotted an alien invader in disguise.",
     "note": "Drop silent 'e' on the base before adding '-er'."},
    {"id": "wf_16", "tier": 3, "word": "upgrading", "prefix": "up", "base": "grade", "suffix": "ing", "rule": "drop_e", "unit": "Master Rune Forge",
     "context_sentence": "She spent an hour upgrading her Netherite sword.",
     "note": "'up-' + base (drop the silent 'e'!) + '-ing'."},
    {"id": "wf_17", "tier": 3, "word": "misplaced", "prefix": "mis", "base": "place", "suffix": "ed", "rule": "drop_e", "unit": "Master Rune Forge",
     "context_sentence": "Leo misplaced his map right before entering the cave.",
     "note": "'mis-' (wrongly) + base (drop silent 'e'!) + '-ed'."},
    {"id": "wf_18", "tier": 2, "word": "escaping", "prefix": "", "base": "escape", "suffix": "ing", "rule": "drop_e", "unit": "Silent-E Forge",
     "context_sentence": "The rogue android is escaping down the tunnel!",
     "note": "Drop silent 'e' on the base before adding '-ing'."},
    {"id": "wf_19", "tier": 1, "word": "bravest", "prefix": "", "base": "brave", "suffix": "est", "rule": "drop_e", "unit": "Silent-E Forge",
     "context_sentence": "The bravest knight stepped onto the obsidian bridge.",
     "note": "Drop silent 'e' on the base before adding '-est' (no double 'e'!)."},
    {"id": "wf_20", "tier": 2, "word": "creating", "prefix": "", "base": "create", "suffix": "ing", "rule": "drop_e", "unit": "Silent-E Forge",
     "context_sentence": "He is creating a brand-new 100-page comic book.",
     "note": "Drop silent 'e' on the base before '-ing'."},

    # ---- Y-Shift Forge (10 words) ----
    {"id": "wf_21", "tier": 2, "word": "heaviest", "prefix": "", "base": "heavy", "suffix": "est", "rule": "y_to_i", "unit": "Y-Shift Forge",
     "context_sentence": "An anvil is the heaviest block in the workshop.",
     "note": "Consonant + y at the end -> change 'y' to 'i' before adding '-est'."},
    {"id": "wf_22", "tier": 2, "word": "supplies", "prefix": "", "base": "supply", "suffix": "es", "rule": "y_to_i", "unit": "Y-Shift Forge",
     "context_sentence": "We packed extra torches and food supplies.",
     "note": "Consonant + y -> change 'y' to 'i' and add '-es'."},
    {"id": "wf_23", "tier": 1, "word": "carried", "prefix": "", "base": "carry", "suffix": "ed", "rule": "y_to_i", "unit": "Y-Shift Forge",
     "context_sentence": "The iron golem carried the broken cart back to town.",
     "note": "Consonant + y -> change 'y' to 'i' before '-ed'."},
    {"id": "wf_24", "tier": 2, "word": "enemies", "prefix": "", "base": "enemy", "suffix": "es", "rule": "y_to_i", "unit": "Y-Shift Forge",
     "context_sentence": "Three robotic enemies blocked the stadium exit.",
     "note": "Consonant + y -> change 'y' to 'i' and add '-es'."},
    {"id": "wf_25", "tier": 1, "word": "happily", "prefix": "", "base": "happy", "suffix": "ly", "rule": "y_to_i", "unit": "Y-Shift Forge",
     "context_sentence": "The rescued puppy barked happily at the crowd.",
     "note": "Consonant + y -> change 'y' to 'i' before adding '-ly'."},
    {"id": "wf_26", "tier": 2, "word": "emptied", "prefix": "", "base": "empty", "suffix": "ed", "rule": "y_to_i", "unit": "Y-Shift Forge",
     "context_sentence": "Someone emptied the diamond chest before sunrise.",
     "note": "Consonant + y -> change 'y' to 'i' before '-ed'."},
    {"id": "wf_27", "tier": 2, "word": "noisier", "prefix": "", "base": "noisy", "suffix": "er", "rule": "y_to_i", "unit": "Y-Shift Forge",
     "context_sentence": "The second rocket engine was even noisier than the first.",
     "note": "Consonant + y -> change 'y' to 'i' before '-er'."},
    {"id": "wf_28", "tier": 2, "word": "replied", "prefix": "", "base": "reply", "suffix": "ed", "rule": "y_to_i", "unit": "Y-Shift Forge",
     "context_sentence": "Mission control replied with the secret launch code.",
     "note": "Consonant + y -> change 'y' to 'i' before '-ed'."},
    {"id": "wf_29", "tier": 1, "word": "hurried", "prefix": "", "base": "hurry", "suffix": "ed", "rule": "y_to_i", "unit": "Y-Shift Forge",
     "context_sentence": "They hurried inside before the thunderstorm arrived.",
     "note": "Consonant + y -> change 'y' to 'i' before '-ed'."},
    {"id": "wf_30", "tier": 3, "word": "mysteries", "prefix": "", "base": "mystery", "suffix": "es", "rule": "y_to_i", "unit": "Y-Shift Forge",
     "context_sentence": "Detective Nova solved three impossible mysteries this week.",
     "note": "Consonant + y -> change 'y' to 'i' and add '-es'."},

    # ---- Rune Lock & Ancient Root Forge (12 words) ----
    {"id": "wf_31", "tier": 2, "word": "unbreakable", "prefix": "un", "base": "break", "suffix": "able", "rule": "keep", "unit": "Rune Lock Forge",
     "context_sentence": "The obsidian fortress walls were unbreakable.",
     "note": "Three clean parts — 'un-' + 'break' + '-able' all stay unchanged!"},
    {"id": "wf_32", "tier": 2, "word": "disappear", "prefix": "dis", "base": "appear", "suffix": "", "rule": "keep", "unit": "Rune Lock Forge",
     "context_sentence": "Endermen can disappear in a flash of purple sparks.",
     "note": "'dis-' (away) locks straight onto 'appear' — one 's' and double 'p'!"},
    {"id": "wf_33", "tier": 2, "word": "rebuilding", "prefix": "re", "base": "build", "suffix": "ing", "rule": "keep", "unit": "Rune Lock Forge",
     "context_sentence": "The villagers started rebuilding the tower after the blast.",
     "note": "'re-' (again) + 'build' + '-ing' — keep every base letter intact!"},
    {"id": "wf_34", "tier": 1, "word": "fearless", "prefix": "", "base": "fear", "suffix": "less", "rule": "keep", "unit": "Rune Lock Forge",
     "context_sentence": "That fearless pilot flew straight through the canyon.",
     "note": "'fear' + '-less' (without) — zero spelling change needed."},
    {"id": "wf_35", "tier": 3, "word": "destruction", "prefix": "de", "base": "struct", "suffix": "ion", "rule": "keep", "unit": "Ancient Root Forge",
     "context_sentence": "The giant laser nearly caused total destruction.",
     "note": "Root 'struct' (build) + 'de-' + '-ion'."},
    {"id": "wf_36", "tier": 3, "word": "erupted", "prefix": "e", "base": "rupt", "suffix": "ed", "rule": "keep", "unit": "Ancient Root Forge",
     "context_sentence": "A hidden volcano erupted behind the ice island.",
     "note": "Root 'rupt' (burst) + 'e-' (out) + '-ed'."},
    {"id": "wf_37", "tier": 1, "word": "switched", "prefix": "", "base": "switch", "suffix": "ed", "rule": "keep", "unit": "Rune Lock Forge",
     "context_sentence": "Kai switched the lever and opened the vault.",
     "note": "Right after short 'i', /ch/ uses '-tch' — keep base clean!"},
    {"id": "wf_38", "tier": 3, "word": "portable", "prefix": "", "base": "port", "suffix": "able", "rule": "keep", "unit": "Ancient Root Forge",
     "context_sentence": "A portable solar charger kept the drone flying.",
     "note": "Root 'port' (carry) + '-able' (can be carried) — keep base clean!"},
    {"id": "wf_39", "tier": 1, "word": "unlocked", "prefix": "un", "base": "lock", "suffix": "ed", "rule": "keep", "unit": "Rune Lock Forge",
     "context_sentence": "She unlocked the secret basement with a golden key.",
     "note": "'un-' + 'lock' + '-ed' — base stays clean!"},
    {"id": "wf_40", "tier": 3, "word": "inspection", "prefix": "in", "base": "spect", "suffix": "ion", "rule": "keep", "unit": "Ancient Root Forge",
     "context_sentence": "Every bridge passes a careful safety inspection.",
     "note": "Root 'spect' (look) + 'in-' + '-ion' — keep every part intact!"},
    {"id": "wf_41", "tier": 3, "word": "distraction", "prefix": "dis", "base": "tract", "suffix": "ion", "rule": "keep", "unit": "Ancient Root Forge",
     "context_sentence": "Tossing a snowball created the perfect distraction.",
     "note": "Root 'tract' (pull) + 'dis-' (away) + '-ion' — keep every part intact!"},
    {"id": "wf_42", "tier": 3, "word": "recharged", "prefix": "re", "base": "charge", "suffix": "ed", "rule": "drop_e", "unit": "Master Rune Forge",
     "context_sentence": "Our orbital plasma turret recharged in three seconds.",
     "note": "'re-' (again) + base (drop silent 'e'!) + '-ed'."},
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
     "options": ["its", "it's", "its'"], "answer": "its", "explain": "'its' = belongs to it (NO apostrophe, just like 'his' and 'her')!"},
    {"id": "ha_10", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "Check the radar, ___ tracking three incoming drones!",
     "options": ["it's", "its", "is"], "answer": "it's", "explain": "'it's' = 'it is' ('it is tracking')."},
    {"id": "ha_11", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "Do you ___ where the hidden Redstone switch is?",
     "options": ["know", "no", "now"], "answer": "know", "explain": "'know' (with silent k, like 'knowledge') means to understand."},
    {"id": "ha_12", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "We could ___ the wolf howling across the snow biome.",
     "options": ["hear", "here", "hare"], "answer": "hear", "explain": "'hear' has the word 'ear' right inside it!"},
    {"id": "ha_13", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "Set the crafting table right ___ beside the torch.",
     "options": ["here", "hear", "hare"], "answer": "here", "explain": "'here' names a place (right in this spot)."},
    {"id": "ha_14", "tier": 2, "skill": "B2.4_vocabulary", "sentence": "She ___ a flaming arrow straight into the target block.",
     "options": ["threw", "through", "thorough"], "answer": "threw", "explain": "'threw' is the action of throwing ('She threw an arrow')!"},
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

    # ---- Action Thrusters & Squad Agreement (14 waves) ----
    {"id": "ha_23", "tier": 1, "skill": "B3.2_grammar", "sentence": "Yesterday, Leo ___ a rare golden axolotl in the cave.",
     "options": ["caught", "catched", "catch"], "answer": "caught", "explain": "Yesterday + 'catch' becomes 'caught' (rhymes with 'taught')!"},
    {"id": "ha_24", "tier": 1, "skill": "B3.2_grammar", "sentence": "Our goalkeeper ___ across the net and blocked the shot!",
     "options": ["flew", "flied", "flowed"], "answer": "flew", "explain": "'fly' flips to 'flew' (never 'flied')!"},
    {"id": "ha_25", "tier": 1, "skill": "B3.2_grammar", "sentence": "She ___ extra torches so nobody would get lost underground.",
     "options": ["brought", "brang", "bringed"], "answer": "brought", "explain": "'bring' flips to 'brought' (rhymes with 'caught')!"},
    {"id": "ha_26", "tier": 1, "skill": "B3.2_grammar", "sentence": "The coach ___ us how to aim a wrist shot accurately.",
     "options": ["taught", "teached", "tought"], "answer": "taught", "explain": "'teach' flips to 'taught'!"},
    {"id": "ha_27", "tier": 2, "skill": "B3.2_grammar", "sentence": "The two robotic guards ___ watching the main gate.",
     "options": ["were", "was", "is"], "answer": "were", "explain": "Two guards = 'were' ('was' is only for one)!"},
    {"id": "ha_28", "tier": 2, "skill": "B3.2_grammar", "sentence": "Each explorer ___ a glowing compass before sunset.",
     "options": ["carries", "carry", "carrying"], "answer": "carries", "explain": "'Each explorer' means one by one -> 'carries' (y flips to -ies)!"},
    {"id": "ha_29", "tier": 2, "skill": "B3.2_grammar", "sentence": "Dylan ___ an awesome comic cover using the Lenovo pen.",
     "options": ["drew", "drawed", "drawn"], "answer": "drew", "explain": "'draw' flips to 'drew' ('Dylan drew a cover')!"},
    {"id": "ha_30", "tier": 2, "skill": "B3.2_grammar", "sentence": "The giant bamboo tower ___ six blocks taller overnight!",
     "options": ["grew", "growed", "grown"], "answer": "grew", "explain": "'grow' flips to 'grew' (just like 'know' -> 'knew')!"},
    {"id": "ha_31", "tier": 2, "skill": "B3.2_grammar", "sentence": "Maya ___ across the icy cavern pool to reach the chest.",
     "options": ["swam", "swimmed", "swum"], "answer": "swam", "explain": "'swim' flips to 'swam' ('Maya swam across')!"},
    {"id": "ha_32", "tier": 2, "skill": "B3.2_grammar", "sentence": "The whole squad ___ loud cheers when the boss shattered!",
     "options": ["shouted", "shouting", "shout"], "answer": "shouted", "explain": "It already happened, so lock in '-ed' ('shouted')!"},
    {"id": "ha_33", "tier": 3, "skill": "B3.2_grammar", "sentence": "Before the bridge collapsed, the squad had already ___ across.",
     "options": ["driven", "drove", "drived"], "answer": "driven", "explain": "Right after 'had', lock in 'driven' ('had driven')!"},
    {"id": "ha_34", "tier": 3, "skill": "B3.2_grammar", "sentence": "Someone had ___ the iron lock before the alarm triggered.",
     "options": ["broken", "broke", "breaked"], "answer": "broken", "explain": "Right after 'had', lock in 'broken' ('had broken')!"},
    {"id": "ha_35", "tier": 3, "skill": "B3.2_grammar", "sentence": "Neither of the drones ___ enough battery to reach the roof.",
     "options": ["has", "have", "having"], "answer": "has", "explain": "'Neither' means not even one — so pair it with 'has'!"},
    {"id": "ha_36", "tier": 3, "skill": "B3.2_grammar", "sentence": "She had already ___ three chapters before dinner started.",
     "options": ["written", "wrote", "writed"], "answer": "written", "explain": "Right after 'had', lock in 'written' ('had written')!"},
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
     "bridges": [{"word": "although", "kind": "complex", "ok": True, "why": "'Although' at the front sets up an awesome obstacle-vs-win twist!"},
                 {"word": "because", "kind": "complex", "ok": False, "why": "A buried runway doesn't HELP a jet take off — this is a surprise contrast!"},
                 {"word": "so", "kind": "compound", "ok": False, "why": "Pick a twist word that works right at the start!"}]},
    {"id": "st_16", "tier": 3, "skill": "B3.1_complex", "front_connector": True,
     "clause_a": "The shield drops to zero.", "clause_b": "The escape pods will launch automatically.", "weak_verb": "launch",
     "verb_upgrades": [{"word": "eject", "power": 2, "ok": True}, {"word": "catapult", "power": 2, "ok": True}, {"word": "go", "power": 0, "ok": False}],
     "bridges": [{"word": "if", "kind": "complex", "ok": True, "why": "'If' at the front sets up a sharp trigger rule!"},
                 {"word": "although", "kind": "complex", "ok": False, "why": "Launching pods matches zero shields — use a trigger word!"},
                 {"word": "but", "kind": "compound", "ok": False, "why": "Pick a trigger word that starts the whole sentence!"}]},
    {"id": "st_17", "tier": 3, "skill": "B3.1_complex", "front_connector": True,
     "clause_a": "The sun dipped behind the skyline.", "clause_b": "The CN Tower lights came on in neon blue.", "weak_verb": "came on",
     "verb_upgrades": [{"word": "blazed", "power": 2, "ok": True}, {"word": "flared", "power": 2, "ok": True}, {"word": "went on", "power": 0, "ok": False}],
     "bridges": [{"word": "when", "kind": "complex", "ok": True, "why": "'When' at the front locks the exact timing into place!"},
                 {"word": "unless", "kind": "complex", "ok": False, "why": "Sunset is the exact moment the lights turn on!"},
                 {"word": "although", "kind": "complex", "ok": False, "why": "Lights turning on at sunset isn't a surprise contrast."}]},
    {"id": "st_18", "tier": 3, "skill": "B3.1_complex",
     "clause_a": "The bridge won't hold the heavy mech.", "clause_b": "We add steel support beams tonight.", "weak_verb": "add",
     "verb_upgrades": [{"word": "weld", "power": 2, "ok": True}, {"word": "bolt", "power": 2, "ok": True}, {"word": "put", "power": 0, "ok": False}],
     "bridges": [{"word": "unless", "kind": "complex", "ok": True, "why": "'unless' expresses 'except if' like a pro!"},
                 {"word": "because", "kind": "complex", "ok": False, "why": "Adding steel beams wouldn't make the bridge WEAKER!"},
                 {"word": "while", "kind": "complex", "ok": False, "why": "Show the exact 'except if' rule!"}]},
    {"id": "st_19", "tier": 3, "skill": "B3.1_complex", "front_connector": True,
     "clause_a": "The ancient portal hummed louder.", "clause_b": "Kai tightened his grip on the emerald blade.", "weak_verb": "tightened",
     "verb_upgrades": [{"word": "clenched", "power": 2, "ok": True}, {"word": "locked", "power": 2, "ok": True}, {"word": "held", "power": 0, "ok": False}],
     "bridges": [{"word": "as", "kind": "complex", "ok": True, "why": "'As' puts both tense moments in lockstep!"},
                 {"word": "unless", "kind": "complex", "ok": False, "why": "Show two actions rising together!"},
                 {"word": "or", "kind": "compound", "ok": False, "why": "Pick a timing word that links both moments!"}]},
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
    {"id": "ty_21", "tier": 2, "tag": "Cavern Run", "text": "They brought their compasses before walking through the tunnel."},
    {"id": "ty_22", "tier": 2, "tag": "Lava Base", "text": "The fearless survivor stopped grabbing heavy supplies near lava."},
    {"id": "ty_23", "tier": 3, "tag": "Comms Link", "text": "\"Watch the radar!\" shouted Nova, because three drones appeared."},
    {"id": "ty_24", "tier": 3, "tag": "Supply Convoy", "text": "Although the heavy supply cart slipped, the team kept rebuilding."},
    {"id": "ty_25", "tier": 3, "tag": "Stealth Ops", "text": "Kai whispered, \"Don't wake the Warden until we seal the gate!\""},
    {"id": "ty_26", "tier": 3, "tag": "Deep Core", "text": "Volcanoes erupted underground, creating brand-new rocky islands."},
    {"id": "ty_27", "tier": 3, "tag": "Vault Heist", "text": "Before the trapdoor snapped shut, Maya snatched the golden key."},
    {"id": "ty_28", "tier": 3, "tag": "Ice Drift", "text": "Wait, you're sure it's spinning its wheels because of the ice?"},
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
    {"id": "cd_05", "tier": 2, "skill": "C1.2_3_craft", "case_title": "Case #312: Launchpad Signal Scan",
     "question": "Highlight the line that turns the rocket into a bold, fiery image!",
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
    {"id": "cd_14", "tier": 3, "skill": "C1.2_3_craft", "case_title": "Case #560: Championship Chess Scan",
     "question": "Highlight the line that turns the quiet chess match into an epic battle!",
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
    {"id": "cd_07", "tier": 2, "skill": "C1.2_3_craft", "case_title": "Case #418: Harbourfront Storm Scan",
     "question": "Highlight the line where the storm explodes with comic-book sound effects!",
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
    {"id": "cd_08", "tier": 2, "skill": "C1.2_3_craft", "case_title": "Case #430: Midnight Train Depot Scan",
     "question": "Highlight the line that makes the winter storm act like an angry creature!",
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
    {"id": "cd_12", "tier": 3, "skill": "C1.5_pov", "case_title": "Case #531: Witness Camera Check",
     "question": "Highlight the line that proves whether Nova tells this story herself or an outside narrator tells it!",
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
    {"id": "cd_06", "tier": 2, "skill": "C1.2_3_craft", "case_title": "Case #405: Breakaway Ice Rink Scan",
     "question": "Highlight the line that compares Kai's speed on the ice to a wild predator!",
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
    {"id": "cd_11", "tier": 3, "skill": "C1.5_pov", "case_title": "Case #519: Cavern Witness Log",
     "question": "Highlight the line that proves WHO is telling this underground adventure!",
     "sentences": [
         "The ancient stone gate groaned open into a cavern lit by glowing moss.",
         "Blue crystals hummed along the ceiling in the chilly draft.",
         "My boots slipped on the wet rock, and I barely caught the ledge before falling.",
         "Far below, an underground river rushed toward the dark chasm.",
     ], "clue_index": 2,
     "choices": [{"label": "First-person ('My' and 'I')", "ok": True},
                 {"label": "Third-person ('he / she / they')", "ok": False, "why": "Look closely at line 3: 'My' and 'I'!"},
                 {"label": "Second-person ('you')", "ok": False, "why": "The explorer tells their own story using 'I'."}],
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
    {"id": "cd_16", "tier": 3, "skill": "C1.2_3_craft", "case_title": "Case #589: Harbour Fog Scan",
     "question": "Highlight the line that compares the skyscraper to something sharp and bright!",
     "sentences": [
         "Morning fog drifted slowly off the deep blue harbour into downtown Toronto.",
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


# --------------------------------------------------------------------------- Closed-Loop Adaptive ZPD & Micro-Skill Engine

MICRO_SKILL_CATALOG: dict[str, dict[str, str]] = {
    # Cyber Blade (sentence_surgery)
    "ss_runon": {"game": "sentence_surgery", "ontario": "B3.1_boundaries", "parent_label": "Run-On Boundary Splits", "kid_tag": "Stream Splits"},
    "ss_frag_core": {"game": "sentence_surgery", "ontario": "B3.1_simple", "parent_label": "Subject/Verb Fragments", "kid_tag": "Core Circuits"},
    "ss_frag_opener": {"game": "sentence_surgery", "ontario": "B3.1_simple", "parent_label": "Hanging Opener Fragments (Because/Although)", "kid_tag": "Trigger Circuits"},
    "ss_mech_caps": {"game": "sentence_surgery", "ontario": "B3.3_mechanics", "parent_label": "Capitals, Contractions & End Marks", "kid_tag": "Security Seals"},
    "ss_mech_dialogue": {"game": "sentence_surgery", "ontario": "B3.3_dialogue", "parent_label": "Dialogue Quotes & Commas", "kid_tag": "Comms Quotes"},
    # Obsidian Forge (word_forge)
    "wf_double": {"game": "word_forge", "ontario": "B2.3_morphology", "parent_label": "1-1-1 Consonant Doubling", "kid_tag": "Twin-Iron Strike"},
    "wf_drop_e": {"game": "word_forge", "ontario": "B2.3_morphology", "parent_label": "Drop Silent -e", "kid_tag": "Silent-E Forge"},
    "wf_y_to_i": {"game": "word_forge", "ontario": "B2.3_morphology", "parent_label": "Change y to i", "kid_tag": "Y-Shift Forge"},
    "wf_keep_roots": {"game": "word_forge", "ontario": "B2.1_2_orthography", "parent_label": "Prefixes, Roots & Positional Spelling", "kid_tag": "Rune Locks"},
    # Starshield Turret (homophone_asteroids)
    "ha_homophone": {"game": "homophone_asteroids", "ontario": "B2.4_vocabulary", "parent_label": "Confusable Homophones (their/there/they're, its/it's)", "kid_tag": "Twin Decoys"},
    "ha_verb": {"game": "homophone_asteroids", "ontario": "B3.2_grammar", "parent_label": "Irregular Past Verbs & Agreement", "kid_tag": "Warp Thrusters"},
    # Reactor Overdrive (sentence_stretch)
    "st_compound": {"game": "sentence_stretch", "ontario": "B3.1_compound", "parent_label": "Compound Bridges (so / but / and)", "kid_tag": "Twin Bridges"},
    "st_complex": {"game": "sentence_stretch", "ontario": "B3.1_complex", "parent_label": "Complex Causal/Time Bridges (because / although / while)", "kid_tag": "Overdrive Links"},
    # Neon Drift: Toronto (typing_arena)
    "ty_caps_punct": {"game": "typing_arena", "ontario": "B3.3_mechanics", "parent_label": "Shift Capitals, Apostrophes & Dialogue Keys", "kid_tag": "Precision Corners"},
    "ty_fluency": {"game": "typing_arena", "ontario": "D2.2_keyboarding", "parent_label": "Touch-Typing Speed & Rhythm", "kid_tag": "Straightaway Boost"},
    # Shadow Detective (clue_detective)
    "cd_inference": {"game": "clue_detective", "ontario": "C2.3_inference", "parent_label": "Causal Text Inference & Proof", "kid_tag": "Culprit Clues"},
    "cd_craft": {"game": "clue_detective", "ontario": "C1.2_3_craft", "parent_label": "Simile, Metaphor & Imagery Craft", "kid_tag": "Secret Signals"},
    "cd_pov": {"game": "clue_detective", "ontario": "C1.5_pov", "parent_label": "1st vs 3rd Person Perspective", "kid_tag": "Witness Angles"},
}

GAME_MICRO_SKILLS: dict[str, list[str]] = {}
for _ms_id, _ms_meta in MICRO_SKILL_CATALOG.items():
    GAME_MICRO_SKILLS.setdefault(_ms_meta["game"], []).append(_ms_id)

RANK_TITLES = {
    1: "Cadet",
    2: "Star Ranger",
    3: "Cyber Ace",
    4: "Vanguard Legend",
}

_FORGE_UNIT_BY_RULE = {
    "double": "Twin-Iron Forge",
    "drop_e": "Silent-E Forge",
    "y_to_i": "Y-Shift Forge",
    "keep": "Rune Lock Forge",
}

_HOMOPHONE_FAMILY_WORDS = frozenset({
    "their", "there", "they're", "your", "you're", "its", "it's", "to", "too", "two",
    "hear", "here", "threw", "through", "whole", "hole", "wear", "where", "were",
    "brake", "break", "weather", "whether", "piece", "peace", "know", "no", "knew", "new",
})

_ASTEROID_VALID_WORDS = frozenset(
    {str(o).strip().lower() for it in HOMOPHONE_ASTEROIDS_BANK for o in it["options"]}
    | set(_HOMOPHONE_FAMILY_WORDS)
)


def _sanitize_forge_unit(unit: str, rule: str) -> str:
    u = (unit or "").strip()
    if not u or re.search(r"\b(b2\.|b3\.|gr\.|grade|morphology|orthography|curriculum|deck|spelling)\b", u, re.I):
        return _FORGE_UNIT_BY_RULE.get(rule, "Rune Lock Forge")
    return u


def _item_subskill(game_id: str, it: dict[str, Any]) -> str:
    if it.get("subskill") in MICRO_SKILL_CATALOG:
        return str(it["subskill"])
    if game_id == "sentence_surgery":
        m = it.get("mode")
        if m == "runon":
            return "ss_runon"
        if m == "fragment":
            brk = str(it.get("broken") or "")
            if re.match(r"^(because|when|before|after|although|if|while|unless)\b", brk.strip(), re.I):
                return "ss_frag_opener"
            return "ss_frag_core"
        if it.get("skill") == "B3.3_dialogue" or any('"' in str(t.get("fix", "")) for t in (it.get("tokens") or [])):
            return "ss_mech_dialogue"
        return "ss_mech_caps"
    if game_id == "word_forge":
        rl = it.get("rule")
        if rl == "double":
            return "wf_double"
        if rl == "drop_e":
            return "wf_drop_e"
        if rl == "y_to_i":
            return "wf_y_to_i"
        return "wf_keep_roots"
    if game_id == "homophone_asteroids":
        return "ha_homophone" if it.get("skill") == "B2.4_vocabulary" else "ha_verb"
    if game_id == "sentence_stretch":
        return "st_compound" if it.get("skill") == "B3.1_compound" else "st_complex"
    if game_id == "typing_arena":
        txt = str(it.get("text") or "")
        return "ty_caps_punct" if any(ch in txt for ch in ("'", '"', "?", "!")) else "ty_fluency"
    if game_id == "clue_detective":
        sk = it.get("skill")
        if sk == "C1.2_3_craft":
            return "cd_craft"
        if sk == "C1.5_pov":
            return "cd_pov"
        return "cd_inference"
    return "ss_runon"


def _default_skill_arcade() -> dict[str, Any]:
    return {
        "total_runs": 0,
        "total_correct": 0,
        "total_attempts": 0,
        "streak_days": 0,
        "last_played_date": "",
        "seen_ids": {},
        "games": {},
        "micro_skills": {},
        "trouble_words": {},
        "key_errors": {},
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
    sa.setdefault("micro_skills", {})
    sa.setdefault("trouble_words", {})
    sa.setdefault("key_errors", {})
    sa.setdefault("recent_runs", [])
    return sa


def _ensure_micro_entry(sa: dict[str, Any], sub_id: str) -> dict[str, Any]:
    ms = sa.setdefault("micro_skills", {}).setdefault(sub_id, {
        "ema_acc": 0.72,
        "attempts": 0,
        "streak": 0,
        "box": 1,
        "next_due": 0.0,
        "studio_flags": 0,
    })
    ms.setdefault("ema_acc", 0.72)
    ms.setdefault("attempts", 0)
    ms.setdefault("streak", 0)
    ms.setdefault("box", 1)
    ms.setdefault("next_due", 0.0)
    ms.setdefault("studio_flags", 0)
    return ms


def _game_zpd(rec: dict[str, Any], sa: dict[str, Any], game_id: str) -> float:
    gs = (sa.get("games") or {}).get(game_id) or {}
    if "zpd" in gs:
        return max(1.0, min(3.0, float(gs["zpd"])))
    default_zpd = 1.75 if int(rec.get("grade") or 3) >= 4 else 1.25
    return default_zpd


def ingest_studio_session_signals(rec: dict[str, Any], wchecks: list[dict[str, Any]]) -> dict[str, int]:
    """Closed-loop bridge: silently translates real Studio writing slips into Stealth Arcade priorities!"""
    sa = ensure_skill_arcade(rec)
    flagged: dict[str, int] = {}

    def _flag(sub_id: str, inc: int = 1) -> None:
        entry = _ensure_micro_entry(sa, sub_id)
        entry["studio_flags"] = min(6, int(entry.get("studio_flags") or 0) + inc)
        entry["next_due"] = 0.0
        flagged[sub_id] = flagged.get(sub_id, 0) + inc

    ke = sa.setdefault("key_errors", {})
    tw = sa.setdefault("trouble_words", {})

    for ev in (wchecks or []):
        chk = (ev or {}).get("check") or {}
        sents = chk.get("sentences") or []
        feats = chk.get("features") or {}
        for s in sents:
            iss = s.get("issue")
            if iss == "run_on":
                _flag("ss_runon")
                _flag("st_compound")
            elif iss in ("missing_subject", "missing_verb", "incomplete_thought"):
                txt_s = str(s.get("text") or "").strip()
                if re.match(r"^(because|when|while|although|if|before|after)\b", txt_s, re.I):
                    _flag("ss_frag_opener")
                    _flag("st_complex")
                else:
                    _flag("ss_frag_core")
            if s.get("capital_ok") is False:
                _flag("ss_mech_caps")
                ke["SHIFT"] = min(25, int(ke.get("SHIFT") or 0) + 1)
            if s.get("end_ok") is False:
                _flag("ss_mech_caps")
                ke["."] = min(25, int(ke.get(".") or 0) + 1)
        if feats.get("has_dialogue") and feats.get("dialogue_punct_ok") is False:
            _flag("ss_mech_dialogue", 2)
            ke['"'] = min(25, int(ke.get('"') or 0) + 2)
        for gf in (chk.get("grammar_fixes") or []):
            wrote = str(gf.get("wrote") or "").strip().lower()
            opts = [str(o).strip().lower() for o in (gf.get("options") or []) if str(o).strip()]
            target = opts[0] if opts else wrote
            # Only queue clean single-word tokens that actually belong to Starshield Turret's confusable/verb bank!
            for cand_w in (target, wrote):
                if cand_w and " " not in cand_w and cand_w in _ASTEROID_VALID_WORDS:
                    tw[cand_w] = min(6, int(tw.get(cand_w) or 0) + 2)
                    break
            if wrote in _HOMOPHONE_FAMILY_WORDS or target in _HOMOPHONE_FAMILY_WORDS:
                _flag("ha_homophone", 2)
            else:
                _flag("ha_verb", 2)
    return flagged


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


def _subskill_need_weight(sa: dict[str, Any], rc: dict[str, Any], sub_id: str, now_ts: float) -> float:
    meta = MICRO_SKILL_CATALOG.get(sub_id) or {}
    ont_id = meta.get("ontario", "")
    ont_lvl = int((((rc or {}).get("skills") or {}).get(ont_id) or {}).get("level") or 0)
    ms = (sa.get("micro_skills") or {}).get(sub_id) or {}
    attempts = int(ms.get("attempts") or 0)
    ema = float(ms.get("ema_acc", 0.72))
    flags = int(ms.get("studio_flags") or 0)
    due = float(ms.get("next_due") or 0.0) <= now_ts

    # Higher weight = child needs this micro-skill more right now
    w = (4 - min(4, ont_lvl)) * 0.45
    if attempts == 0:
        w += 0.65
    else:
        w += max(0.0, 0.92 - ema) * 2.4
    if due and attempts > 0:
        w += 0.55
    if flags > 0:
        w += 1.25 + min(3, flags) * 0.45
    return w


def _adaptive_pick_fresh(
    game_id: str,
    pool: list[dict[str, Any]],
    seen: list[str],
    count: int,
    *,
    rec: dict[str, Any],
    sa: dict[str, Any],
    rc: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], dict[str, list[dict[str, Any]]]]:
    """Selects `count` unseen items weighted by ZPD tier, micro-skill deficits, and Studio trouble spots,
    plus returns an unseen `reserve_by_tier` map for live mid-round ZPD escalation/scaffolding!
    """
    now_ts = time.time()
    zpd = _game_zpd(rec, sa, game_id)
    target_tier = max(1.0, min(3.0, zpd))
    trouble_words = sa.get("trouble_words") or {}
    key_errors = sa.get("key_errors") or {}

    seen_set = set(seen or [])
    fresh = [copy.deepcopy(x) for x in pool if x.get("id") not in seen_set]
    stale = [copy.deepcopy(x) for x in pool if x.get("id") in seen_set]

    def _score_item(it: dict[str, Any]) -> float:
        sub = _item_subskill(game_id, it)
        it["subskill"] = sub
        tier = float(it.get("tier") or 2)
        # ZPD bell curve: strongly prefer items near current ZPD tier
        tier_fit = max(0.0, 1.35 - abs(tier - target_tier) * 0.75)
        sub_need = _subskill_need_weight(sa, rc, sub, now_ts)
        bonus = 0.0
        if game_id == "homophone_asteroids":
            ans = str(it.get("answer") or "").lower()
            opts = [str(o).lower() for o in (it.get("options") or [])]
            if ans in trouble_words or any(o in trouble_words for o in opts):
                bonus += 2.6
        elif game_id == "typing_arena" and key_errors:
            txt = str(it.get("text") or "")
            if key_errors.get("'") and "'" in txt:
                bonus += 1.2
            if key_errors.get('"') and '"' in txt:
                bonus += 1.4
            if key_errors.get("?") and "?" in txt:
                bonus += 1.1
            if key_errors.get("SHIFT") and sum(1 for c in txt if c.isupper()) >= 2:
                bonus += 0.9
            for ch_k, cnt_k in key_errors.items():
                if len(ch_k) == 1 and cnt_k >= 2 and ch_k.lower() in txt.lower():
                    bonus += min(1.0, cnt_k * 0.15)
        return tier_fit * 1.4 + sub_need + bonus + random.uniform(0.0, 0.28)

    for x in fresh:
        x["_score"] = _score_item(x)
    for x in stale:
        x["_score"] = _score_item(x)

    fresh.sort(key=lambda x: -x["_score"])
    stale.sort(key=lambda x: -x["_score"])

    # ~70% top-need ZPD edge + ~30% fresh confidence-variety items so rounds stay brisk & fun!
    picked: list[dict[str, Any]] = []
    new_seen = list(seen or [])

    if count <= 0:
        leftover_fresh = list(fresh) if fresh else list(stale)
    elif len(fresh) >= count:
        focus_n = max(1, min(count, int(round(count * 0.7))))
        top_slice = fresh[:focus_n]
        rem_slice = fresh[focus_n:]
        random.shuffle(rem_slice)
        picked = top_slice + rem_slice[: max(0, count - focus_n)]
        picked_ids = {x["id"] for x in picked}
        leftover_fresh = [x for x in fresh if x["id"] not in picked_ids]
        new_seen.extend(x["id"] for x in picked if x.get("id"))
        new_seen = new_seen[-len(pool):]
    else:
        picked = list(fresh)
        need = max(0, count - len(picked))
        picked.extend(stale[:need])
        picked_ids = {x["id"] for x in picked}
        leftover_fresh = [x for x in stale[need:] if x["id"] not in picked_ids]
        new_seen = [x["id"] for x in picked if x.get("id")]

    # Lightly interleave picked items so identical modes don't clump back-to-back, while keeping #1 strong
    if len(picked) > 2:
        tail = picked[1:]
        random.shuffle(tail)
        picked = [picked[0]] + tail

    reserves: dict[str, list[dict[str, Any]]] = {"1": [], "2": [], "3": []}
    for rx in leftover_fresh:
        t_key = str(max(1, min(3, int(rx.get("tier") or 2))))
        if len(reserves[t_key]) < 3:
            clean_rx = {k: v for k, v in rx.items() if k != "_score"}
            reserves[t_key].append(clean_rx)

    clean_picked = [{k: v for k, v in px.items() if k != "_score"} for px in picked]
    return clean_picked, new_seen, reserves


def _game_need_and_stealth_pill(
    rec: dict[str, Any], sa: dict[str, Any], rc: dict[str, Any], deck_due: int, game: dict[str, Any]
) -> tuple[float, str, list[str]]:
    """Computes adaptive priority AND a 100% school-smell-free arcade status pill (plus parent diagnostics)."""
    gid = game["id"]
    gs = (sa.get("games") or {}).get(gid) or {}
    now_ts = time.time()
    zpd = _game_zpd(rec, sa, gid)
    zpd_tier = int(round(zpd))

    sub_ids = GAME_MICRO_SKILLS.get(gid, [])
    scored_subs = sorted(
        [( _subskill_need_weight(sa, rc, sid, now_ts), sid) for sid in sub_ids],
        key=lambda t: -t[0],
    )
    top_need_w, top_sub = scored_subs[0] if scored_subs else (1.0, "")
    studio_flags = sum(int(((sa.get("micro_skills") or {}).get(sid) or {}).get("studio_flags") or 0) for sid in sub_ids)
    parent_targets = [
        MICRO_SKILL_CATALOG[sid]["parent_label"]
        for w, sid in scored_subs[:2]
        if w >= 1.2
    ]

    score = top_need_w * 10.0 + studio_flags * 8.0
    if gid == "word_forge" and deck_due > 0:
        score += 18.0 + min(deck_due, 6) * 2.5
        pill = f"🔥 {deck_due} Rune{'s' if deck_due != 1 else ''} Ready in Forge"
    elif studio_flags > 0 and top_sub:
        pill = f"⚡ Power-Up Mission · {MICRO_SKILL_CATALOG[top_sub]['kid_tag']}"
    elif int(gs.get("runs") or 0) == 0:
        pill = f"🚀 Sector {zpd_tier} · {MICRO_SKILL_CATALOG[top_sub]['kid_tag'] if top_sub else 'Ready'}"
    elif gid == "typing_arena" and int(gs.get("best_wpm") or 0) > 0:
        pill = f"🏁 Beat Rival Pace · {int(gs['best_wpm']) + 2} WPM"
    else:
        pill = f"⚡ Sector {zpd_tier} · {MICRO_SKILL_CATALOG[top_sub]['kid_tag'] if top_sub else 'Overclock Ready'}"

    return score, pill, parent_targets


def _has_custom_worlds(rec: dict[str, Any]) -> bool:
    interests = (rec.get("model") or {}).get("interests") or []
    projs = [p for p in list_projects()[:4] if p.get("title")]
    return bool(interests or projs)


def get_arcade_hub_state(*, sandbox: bool = False) -> dict[str, Any]:
    rec, sa = _active_rec(sandbox=sandbox)
    rc = curriculum_tracker.ensure_report_card(rec)
    deck = spelling_srs.deck_summary(rec)
    due_now = int(deck.get("due_now") or 0)
    games_stats = sa.get("games") or {}
    tier_num = max(1, min(4, int(rc.get("mastery_tier") or 1)))

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
        need, status_pill, _ = _game_need_and_stealth_pill(rec, sa, rc, due_now, g)
        scored.append((need, gid))
        # Kid-safe game object: ZERO Ontario codes or parent_title leaked to player DOM!
        kid_g = {k: v for k, v in g.items() if k not in ("parent_title", "skills")}
        enriched.append({
            **kid_g,
            "bank_size": bank_sizes.get(gid, 0),
            "runs": int(gs.get("runs") or 0),
            "best_score": int(gs.get("best_score") or 0),
            "best_accuracy": int(gs.get("best_accuracy") or 0),
            "best_wpm": int(gs.get("best_wpm") or 0),
            "mastery_stars": min(3, int(gs.get("mastery_stars") or 0)),
            "zpd_tier": int(round(_game_zpd(rec, sa, gid))),
            "status_pill": status_pill,
            "recommended": False,
        })

    scored.sort(key=lambda x: -x[0])
    top_ids = {gid for _, gid in scored[:2]}
    for item in enriched:
        if item["id"] in top_ids:
            item["recommended"] = True

    ai_ok = bool(api_key())
    arc_status = arcade.client_status(rec, sandbox=sandbox)
    return {
        "child_name": rec.get("name") or "Pilot",
        "rank_level": tier_num,
        "rank_title": RANK_TITLES.get(tier_num, "Cadet"),
        "runes_ready": due_now,
        "runes_forged": int(deck.get("mastered") or 0),
        "ai_available": ai_ok,
        "auto_worlds_ready": ai_ok and _has_custom_worlds(rec),
        "total_runs": int(sa.get("total_runs") or 0),
        "streak_days": int(sa.get("streak_days") or 0),
        "games": enriched,
        "arcade": arc_status,
        "sandbox": sandbox,
    }


def parent_summary(rec: dict[str, Any]) -> dict[str, Any]:
    sa = ensure_skill_arcade(rec)
    rc = curriculum_tracker.ensure_report_card(rec)
    deck = spelling_srs.deck_summary(rec)
    due_now = int(deck.get("due_now") or 0)
    games_out = []
    active_studio_flags: list[str] = []
    for sub_id, ms in (sa.get("micro_skills") or {}).items():
        if int(ms.get("studio_flags") or 0) > 0 and sub_id in MICRO_SKILL_CATALOG:
            active_studio_flags.append(MICRO_SKILL_CATALOG[sub_id]["parent_label"])

    for g in GAME_CATALOG:
        gid = g["id"]
        gs = (sa.get("games") or {}).get(gid) or {}
        _, _, parent_targets = _game_need_and_stealth_pill(rec, sa, rc, due_now, g)
        games_out.append({
            "id": gid,
            "title": g.get("parent_title") or g["title"],
            "kid_title": g["title"],
            "icon": g["icon"],
            "runs": int(gs.get("runs") or 0),
            "best_score": int(gs.get("best_score") or 0),
            "best_accuracy": int(gs.get("best_accuracy") or 0),
            "best_wpm": int(gs.get("best_wpm") or 0),
            "mastery_stars": int(gs.get("mastery_stars") or 0),
            "zpd": round(_game_zpd(rec, sa, gid), 2),
            "stealth_targets": parent_targets,
            "last_played": gs.get("last_played") or "",
        })
    return {
        "total_runs": int(sa.get("total_runs") or 0),
        "total_correct": int(sa.get("total_correct") or 0),
        "total_attempts": int(sa.get("total_attempts") or 0),
        "avg_accuracy": round(100.0 * sa["total_correct"] / max(1, sa["total_attempts"])) if sa["total_attempts"] else 0,
        "streak_days": int(sa.get("streak_days") or 0),
        "studio_flags": active_studio_flags,
        "trouble_words": list((sa.get("trouble_words") or {}).keys())[:10],
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
    """Safely maps a spelling vault card to a verified Obsidian Forge item (never producing corrupted stems)."""
    word = (card.get("word") or "").strip().lower()
    if not word or not word.isalpha() or len(word) < 4:
        return None
    for item in WORD_FORGE_CURRICULUM_BANK:
        if item["word"].lower() == word:
            return {**item, "from_deck": True, "box": int(card.get("box") or 1)}

    parts_raw = (card.get("parts") or "").strip()
    note = (card.get("note") or "").strip() or f"Strike '{word}' cleanly piece by piece!"
    ctx_sent = f"Use the word {word} cleanly in your next adventure."

    clean_p = parts_raw.replace("−", "-").replace("→", "->")
    no_parens = re.sub(r"\([^)]*\)", "", clean_p)
    no_minus_e = re.sub(r"-\s*e\b", "", no_parens, flags=re.I)

    if "+" in no_minus_e:
        segs = [re.sub(r"[^a-z]", "", s.lower()) for s in no_minus_e.split("+")]
        segs = [s for s in segs if s]
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
                        "id": f"deck_{word}", "tier": 2, "word": word, "prefix": p, "base": b, "suffix": s, "rule": rl,
                        "unit": _sanitize_forge_unit(card.get("unit") or "", rl), "note": note, "context_sentence": ctx_sent,
                        "from_deck": True, "box": int(card.get("box") or 1),
                    }

    return {
        "id": f"deck_{word}", "tier": 2, "word": word, "prefix": "", "base": word, "suffix": "", "rule": "keep",
        "direct_memory": True, "unit": "Memory Vault Forge", "note": note, "context_sentence": ctx_sent,
        "from_deck": True, "box": int(card.get("box") or 1),
    }


def _enrich_forge_items(items: list[dict[str, Any]]) -> None:
    """Attaches safe distractor tiles, blanked context sentences, subskills, and non-spoiling memory hints."""
    all_prefixes = ["un", "dis", "re", "mis", "de", "up", "pre", "in"]
    all_suffixes = ["ed", "ing", "er", "or", "es", "est", "ly", "able", "less", "ion"]
    for it in items:
        rl = it.get("rule", "keep")
        it["unit"] = _sanitize_forge_unit(it.get("unit") or "", rl)
        it["subskill"] = _item_subskill("word_forge", it)
        it["blanked_sentence"] = _blank_word_in_sentence(it.get("context_sentence") or "", it["word"])
        it["memory_hint"] = _safe_memory_hint(
            rl,
            it["unit"],
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


def _build_word_forge_pack(
    rec: dict[str, Any], sa: dict[str, Any], rc: dict[str, Any], count: int = 6
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
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
    fresh_pool, new_seen, reserves = _adaptive_pick_fresh(
        "word_forge", pool, prev_seen, max(0, count - len(chosen)), rec=rec, sa=sa, rc=rc
    )
    sa["seen_ids"]["word_forge"] = new_seen
    chosen.extend(fresh_pool)
    _enrich_forge_items(chosen)
    for r_list in reserves.values():
        _enrich_forge_items(r_list)
    return chosen[:count], reserves


def _student_theme_snippet(rec: dict[str, Any]) -> str:
    interests = (rec.get("model") or {}).get("interests") or []
    proj_titles = [p.get("title", "") for p in list_projects()[:4] if p.get("title")]
    bits = []
    if interests:
        bits.append("Interests: " + ", ".join(str(x) for x in interests[:5]))
    if proj_titles:
        bits.append("Player's own story/comic worlds: " + ", ".join(proj_titles))
    if not bits:
        bits.append("Interests: Minecraft (Bedrock & Java), Toronto superheroes, robots, comic adventures, cool inventions")
    return "; ".join(bits)


def _try_ai_pack(game_id: str, rec: dict[str, Any], sa: dict[str, Any], rc: dict[str, Any]) -> list[dict[str, Any]] | None:
    if not api_key():
        return None
    theme = _student_theme_snippet(rec)
    zpd = _game_zpd(rec, sa, game_id)
    target_tier = int(round(zpd))
    now_ts = time.time()
    sub_ids = GAME_MICRO_SKILLS.get(game_id, [])
    weak_subs = sorted(sub_ids, key=lambda sid: -_subskill_need_weight(sa, rc, sid, now_ts))[:2]
    focus_desc = ", ".join(MICRO_SKILL_CATALOG[s]["parent_label"] for s in weak_subs)
    trouble_w = list((sa.get("trouble_words") or {}).keys())[:4]

    schemas = {
        "sentence_surgery": (
            'Return JSON array of 6 items tailored to the target skills: '
            'Runon: {"mode":"runon","tier":2,"skill":"B3.1_boundaries","prompt":"SLASH between the two jammed thoughts!","words":["The","hero","leaped","she","caught","the","drone."],"split_after":2,"fixed":"The hero leaped. She caught the drone.","explain":"Short kid-friendly tip (zero grammar jargon)."}. '
            'Fragment: {"mode":"fragment","tier":2,"skill":"B3.1_simple","prompt":"Lock in the missing piece!","broken":"...","missing":"action","choices":[{"text":"Complete sentence.","ok":true},{"text":"Incomplete 1.","ok":false,"why":"Why."},{"text":"Incomplete 2.","ok":false,"why":"Why."}],"explain":"Short kid-friendly tip."}. '
            'Mechanics: {"mode":"mechanics","tier":2,"skill":"B3.3_dialogue","prompt":"Fix the 3 bugs!","tokens":[{"raw":"watch","fix":"\\"Watch","bug":true,"hint":"Open quotes & capital!"},{"raw":"out","fix":"out","bug":false},{"raw":"now","fix":"now!\\"","bug":true,"hint":"Close quotes!"},{"raw":"yelled","fix":"yelled","bug":false},{"raw":"leo","fix":"Leo.","bug":true,"hint":"Capitalize name & period!"}],"explain":"Short kid-friendly tip."}.'
        ),
        "word_forge": (
            'Return JSON array of 6 real English words with prefixes/suffixes: '
            '[{"tier":2,"word":"unstoppable","prefix":"un","base":"stop","suffix":"able","rule":"double","unit":"Twin-Iron Forge",'
            '"context_sentence":"With enchanted armour, the hero felt unstoppable.","note":"Short clear tip without printing the full fused word and ZERO curriculum codes."}]. '
            'rule MUST mathematically match prefix+base+suffix -> word and be one of: "keep", "double", "drop_e", "y_to_i".'
        ),
        "homophone_asteroids": (
            'Return JSON array of 7 items: [{"tier":2,"skill":"B2.4_vocabulary","sentence":"Sentence with ___ blank.",'
            '"options":["correct","wrong1","wrong2"],"answer":"correct","explain":"Short clear kid-friendly tip."}]. '
            + (f"Include waves testing these exact tricky words if appropriate: {', '.join(trouble_w)}. " if trouble_w else "")
            + "Never repeat the answer word elsewhere in the same sentence. Use pure ASCII punctuation only."
        ),
        "typing_arena": (
            'Return JSON array of 5 items: [{"tier":2,"tag":"Neon Sector","text":"One clean crisp complete sentence 8-13 words long."}]. '
            "STRICT: Use ONLY standard keyboard ASCII characters (no em-dashes, no curly quotes), and NEVER put school labels in tag."
        ),
        "sentence_stretch": (
            'Return JSON array of 5 items: [{"tier":2,"skill":"B3.1_complex","clause_a":"Short sentence 1.","clause_b":"Short sentence 2.",'
            '"weak_verb":"word appearing verbatim in clause_a or clause_b","verb_upgrades":[{"word":"vivid1","power":2,"ok":true},'
            '{"word":"vivid2","power":2,"ok":true},{"word":"bland","power":0,"ok":false}],'
            '"bridges":[{"word":"because","kind":"complex","ok":true,"why":"Why it fits (kid-friendly, zero jargon)."},{"word":"wrong1","kind":"compound","ok":false,"why":"Why not."},'
            '{"word":"wrong2","kind":"complex","ok":false,"why":"Why not."}]}]. '
            "weak_verb MUST appear verbatim in clause_a or clause_b and every vivid verb upgrade MUST fit grammatically."
        ),
        "clue_detective": (
            'Return JSON array of 3 mini-mysteries: [{"tier":2,"skill":"C2.3_inference","case_title":"Case #...: Cool Mystery Title",'
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
        f"Design an exciting, stealth-learning indie video game mission (difficulty tier {target_tier}/3) "
        f"woven around: {theme}.\n"
        f"Secretly emphasize these target micro-skills: {focus_desc}.\n"
        "CRITICAL STEALTH RULE: NEVER mention grades, curriculum codes, morphology, orthography, homophones, clauses, or school terms anywhere in visible text!\n"
        f"{schema_hint}\n"
        "Return ONLY valid raw JSON."
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
                    x.setdefault("tier", target_tier)
                    x.setdefault("skill", "B3.1_boundaries")
                    x.setdefault("prompt", "SLASH right between the two jammed thoughts!")
                    x.setdefault("explain", "Two complete actions need a period and a capital letter between them!")
                    x["subskill"] = _item_subskill(game_id, x)
                    valid.append(x)
                elif m == "fragment" and x.get("broken") and sum(1 for c in (x.get("choices") or []) if c.get("ok")) == 1:
                    x.setdefault("id", f"ai_ss_f{idx_x}")
                    x.setdefault("tier", target_tier)
                    x.setdefault("skill", "B3.1_simple")
                    x["missing"] = str(x.get("missing") or "action").replace("_", " ").replace("clause", "result")
                    x.setdefault("prompt", "Lock in the missing piece so somebody does something!")
                    x.setdefault("explain", "Every full sentence needs Who/What + Does What!")
                    x["subskill"] = _item_subskill(game_id, x)
                    valid.append(x)
                elif m == "mechanics" and isinstance(x.get("tokens"), list) and sum(1 for t in x["tokens"] if t.get("bug")) >= 2:
                    x.setdefault("id", f"ai_ss_m{idx_x}")
                    x.setdefault("tier", target_tier)
                    x.setdefault("skill", "B3.3_mechanics")
                    x.setdefault("prompt", "Tap EVERY buggy word to seal capitals, apostrophes & end marks!")
                    x.setdefault("explain", "Check start capitals, names, apostrophes, quotes, and end marks!")
                    x["subskill"] = _item_subskill(game_id, x)
                    valid.append(x)
            return valid[:6] if len(valid) >= 4 else None
        if game_id == "word_forge":
            valid = []
            for idx_x, x in enumerate(data):
                if not isinstance(x, dict):
                    continue
                w = str(x.get("word") or "").strip().lower()
                p = str(x.get("prefix") or "").strip().lower()
                b = str(x.get("base") or "").strip().lower()
                s = str(x.get("suffix") or "").strip().lower()
                rl = str(x.get("rule") or "").strip().lower()
                if rl in ("keep", "double", "drop_e", "y_to_i") and _verify_forge_rule(p, b, s, rl, w):
                    x.setdefault("id", f"ai_wf_{idx_x}_{w}")
                    x.setdefault("tier", target_tier)
                    x["word"], x["prefix"], x["base"], x["suffix"], x["rule"] = w, p, b, s, rl
                    x["unit"] = _sanitize_forge_unit(str(x.get("unit") or ""), rl)
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
                    x.setdefault("tier", target_tier)
                    x.setdefault("skill", "B2.4_vocabulary" if ans.lower() in _HOMOPHONE_FAMILY_WORDS else "B3.2_grammar")
                    x.setdefault("explain", f"'{ans}' locks into this sentence cleanly!")
                    x["subskill"] = _item_subskill(game_id, x)
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
                    x.setdefault("tier", target_tier)
                    raw_tag = str(x.get("tag") or "World Sector")
                    if re.search(r"\b(homophone|morpholog|orthograph|grammar|grade|ontario|b[23]\.)\b", raw_tag, re.I):
                        raw_tag = "World Sector"
                    x["tag"] = raw_tag
                    x["subskill"] = _item_subskill(game_id, x)
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
                    x.setdefault("tier", target_tier)
                    x.setdefault("skill", "B3.1_complex")
                    for b in bridges:
                        b.setdefault("kind", "complex")
                        b.setdefault("why", "Check the cause, timing, or twist!")
                    x["subskill"] = _item_subskill(game_id, x)
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
                    x.setdefault("tier", target_tier)
                    x.setdefault("skill", "C2.3_inference")
                    x.setdefault("case_title", f"Case #{idx_x + 1}: Field Investigation")
                    x.setdefault("verdict_starter", "I proved this case because")
                    x.setdefault("required_word", "because")
                    x.setdefault("explain", "The highlighted line gives direct proof!")
                    x["subskill"] = _item_subskill(game_id, x)
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
    use_ai: bool | None = None,
    sandbox: bool = False,
) -> dict[str, Any]:
    if game_id not in GAME_BY_ID:
        raise ValueError(f"Unknown skill game: {game_id}")
    rec, sa = _active_rec(sandbox=sandbox)
    rc = curriculum_tracker.ensure_report_card(rec)
    meta = GAME_BY_ID[game_id]
    seen_map = sa.setdefault("seen_ids", {})

    # Auto-weave the player's own story worlds when `use_ai` is True
    ai_generated = False
    items: list[dict[str, Any]] = []
    reserves: dict[str, list[dict[str, Any]]] = {"1": [], "2": [], "3": []}

    if use_ai:
        ai_items = _try_ai_pack(game_id, rec, sa, rc)
        if ai_items:
            items = ai_items
            ai_generated = True
            # On Obsidian Forge with My Worlds enabled, still blend up to 2 due Vault cards so spaced repetition never stalls!
            if game_id == "word_forge":
                deck = spelling_srs.ensure_deck(rec)
                now_f = time.time()
                due_cards = sorted(
                    [c for c in (deck.get("cards") or {}).values() if (c.get("next_due") or 0) <= now_f and c.get("box", 1) < 5],
                    key=lambda c: (c.get("box", 1), -(c.get("lapses", 0))),
                )
                due_forged: list[dict[str, Any]] = []
                ai_words = {x["word"].lower() for x in items}
                for dc in due_cards:
                    if len(due_forged) >= 2:
                        break
                    fi = _parse_parts_to_forge_item(dc)
                    if fi and fi["word"].lower() not in ai_words:
                        ai_words.add(fi["word"].lower())
                        due_forged.append(fi)
                if due_forged:
                    _enrich_forge_items(due_forged)
                    items = (due_forged + items)[:6]
            # Always populate mid-round ZPD `reserves` from unseen curated items WITHOUT consuming `seen_ids`!
            if game_id == "sentence_surgery":
                _, _, r_res = _adaptive_pick_fresh(game_id, [x for x in SENTENCE_SURGERY_BANK if x["mode"] == "runon"], seen_map.get("ss_runon", []), 0, rec=rec, sa=sa, rc=rc)
                _, _, f_res = _adaptive_pick_fresh(game_id, [x for x in SENTENCE_SURGERY_BANK if x["mode"] == "fragment"], seen_map.get("ss_fragment", []), 0, rec=rec, sa=sa, rc=rc)
                _, _, m_res = _adaptive_pick_fresh(game_id, [x for x in SENTENCE_SURGERY_BANK if x["mode"] == "mechanics"], seen_map.get("ss_mechanics", []), 0, rec=rec, sa=sa, rc=rc)
                for tk in ("1", "2", "3"):
                    reserves[tk] = (r_res[tk][:2] + f_res[tk][:2] + m_res[tk][:2])
            elif game_id == "word_forge":
                used_w = {x["word"].lower() for x in items}
                pool_wf = [dict(x, from_deck=False, box=1) for x in WORD_FORGE_CURRICULUM_BANK if x["word"].lower() not in used_w]
                _, _, reserves = _adaptive_pick_fresh(game_id, pool_wf, seen_map.get("word_forge", []), 0, rec=rec, sa=sa, rc=rc)
                for r_list in reserves.values():
                    _enrich_forge_items(r_list)
            else:
                bank_lookup = {
                    "homophone_asteroids": HOMOPHONE_ASTEROIDS_BANK,
                    "sentence_stretch": SENTENCE_STRETCH_BANK,
                    "typing_arena": TYPING_ARENA_BANK,
                    "clue_detective": CLUE_DETECTIVE_BANK,
                }
                _, _, reserves = _adaptive_pick_fresh(game_id, bank_lookup[game_id], seen_map.get(game_id, []), 0, rec=rec, sa=sa, rc=rc)
            sa.setdefault("last_dealt_ids", {})[game_id] = []
            _save_rec(rec, sandbox=sandbox)

    if not items:
        if game_id == "sentence_surgery":
            # Adaptive mode allocation: weight modes with Studio flags / lower accuracy (e.g. 3+2+1 instead of rigid 2+2+2!)
            now_ts = time.time()
            r_need = _subskill_need_weight(sa, rc, "ss_runon", now_ts)
            f_need = max(
                _subskill_need_weight(sa, rc, "ss_frag_core", now_ts),
                _subskill_need_weight(sa, rc, "ss_frag_opener", now_ts),
            )
            m_need = max(
                _subskill_need_weight(sa, rc, "ss_mech_caps", now_ts),
                _subskill_need_weight(sa, rc, "ss_mech_dialogue", now_ts),
            )
            ranked_modes = sorted([("runon", r_need), ("fragment", f_need), ("mechanics", m_need)], key=lambda t: -t[1])
            counts_by_mode = (
                {ranked_modes[0][0]: 3, ranked_modes[1][0]: 2, ranked_modes[2][0]: 1}
                if (ranked_modes[0][1] - ranked_modes[2][1]) >= 0.75
                else {"runon": 2, "fragment": 2, "mechanics": 2}
            )
            r_pick, seen_map["ss_runon"], r_res = _adaptive_pick_fresh(
                game_id, [x for x in SENTENCE_SURGERY_BANK if x["mode"] == "runon"],
                seen_map.get("ss_runon", []), counts_by_mode["runon"], rec=rec, sa=sa, rc=rc
            )
            f_pick, seen_map["ss_fragment"], f_res = _adaptive_pick_fresh(
                game_id, [x for x in SENTENCE_SURGERY_BANK if x["mode"] == "fragment"],
                seen_map.get("ss_fragment", []), counts_by_mode["fragment"], rec=rec, sa=sa, rc=rc
            )
            m_pick, seen_map["ss_mechanics"], m_res = _adaptive_pick_fresh(
                game_id, [x for x in SENTENCE_SURGERY_BANK if x["mode"] == "mechanics"],
                seen_map.get("ss_mechanics", []), counts_by_mode["mechanics"], rec=rec, sa=sa, rc=rc
            )
            items = r_pick + f_pick + m_pick
            random.shuffle(items)
            for tk in ("1", "2", "3"):
                reserves[tk] = (r_res[tk][:2] + f_res[tk][:2] + m_res[tk][:2])
        elif game_id == "word_forge":
            items, reserves = _build_word_forge_pack(rec, sa, rc, count=6)
        elif game_id == "homophone_asteroids":
            items, seen_map["homophone_asteroids"], reserves = _adaptive_pick_fresh(
                game_id, HOMOPHONE_ASTEROIDS_BANK, seen_map.get("homophone_asteroids", []), 7, rec=rec, sa=sa, rc=rc
            )
        elif game_id == "sentence_stretch":
            items, seen_map["sentence_stretch"], reserves = _adaptive_pick_fresh(
                game_id, SENTENCE_STRETCH_BANK, seen_map.get("sentence_stretch", []), 5, rec=rec, sa=sa, rc=rc
            )
        elif game_id == "typing_arena":
            deck = spelling_srs.ensure_deck(rec)
            due_words = [c["word"] for c in (deck.get("cards") or {}).values() if c.get("box", 1) < 5]
            vault_item: dict[str, Any] | None = None
            if len(due_words) >= 2:
                pair = random.sample(due_words, 2)
                inj = _ascii_normalize(f"Watch how fast I drift past {pair[0]} and {pair[1]} tonight!")
                if _is_pure_typeable_ascii(inj):
                    vault_item = {
                        "id": f"deck_ty_{pair[0]}_{pair[1]}", "tier": 2, "tag": "Vault Boost",
                        "text": inj, "subskill": "ty_fluency",
                    }
            need_n = 4 if vault_item else 5
            cur_ty, seen_map["typing_arena"], reserves = _adaptive_pick_fresh(
                game_id, TYPING_ARENA_BANK, seen_map.get("typing_arena", []), need_n, rec=rec, sa=sa, rc=rc
            )
            items = ([vault_item] + cur_ty) if vault_item else cur_ty
        elif game_id == "clue_detective":
            items, seen_map["clue_detective"], reserves = _adaptive_pick_fresh(
                game_id, CLUE_DETECTIVE_BANK, seen_map.get("clue_detective", []), 3, rec=rec, sa=sa, rc=rc
            )

        sa.setdefault("last_dealt_ids", {})[game_id] = [x["id"] for x in items if x.get("id")]
        _save_rec(rec, sandbox=sandbox)

    # Shuffle choices unconditionally on both main items and mid-round ZPD reserve pools!
    _shuffle_pack_choices(game_id, items)
    for r_list in reserves.values():
        _shuffle_pack_choices(game_id, r_list)

    zpd = _game_zpd(rec, sa, game_id)
    gs = (sa.get("games") or {}).get(game_id) or {}
    best_wpm = int(gs.get("best_wpm") or 0)
    target_wpm = max(14, min(55, best_wpm if best_wpm > 0 else int(round(12 + zpd * 6))))
    kid_meta = {k: v for k, v in meta.items() if k not in ("parent_title", "skills")}

    return {
        "game": kid_meta,
        "ai_generated": ai_generated,
        "rank_level": max(1, min(4, int(rc.get("mastery_tier") or 1))),
        "adaptive": {
            "zpd": round(zpd, 2),
            "start_tier": max(1, min(3, int(round(zpd)))),
            "target_wpm": target_wpm,
        },
        "reserve_by_tier": reserves,
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
                issues.append("Show what happened after 'because' (e.g. '...because his boots had oak splinters.')!")
    else:
        m_any_bec = re.search(r"\b(because|since)\b", raw, re.I)
        if m_any_bec and len(re.findall(r"[A-Za-z']+", raw[m_any_bec.end():])) < 2:
            issues.append("Finish your reason after 'because'!")

    # Reject dangling dependent openers at sentence start
    if re.match(r"^(because|when|while|although|if|before|after)\b", raw.lower()) and "," not in raw and len(words) < 7:
        issues.append("Finish the whole thought after your opener!")

    # Reject repeated-word spam
    unique_alpha = {w.lower() for w in words}
    if len(words) >= 4 and len(unique_alpha) <= 2:
        issues.append("Write a real sentence instead of repeating the same words!")

    # Strict action-word presence guard (rejects "The cat their blue dog." AND "Cats dogs their shields.")
    if len(words) >= 4 and not _REAL_VERB_RE.search(raw):
        issues.append("Add an action word so somebody is doing something!")

    if issues:
        return {"ok": False, "issues": issues, "feedback": issues[0], "word_count": len(words), "checked_by": "deterministic"}

    # Full Gemini check_writing & semantic relevance verification
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
                    "issues": ["Make sure every thought is finished!"],
                    "feedback": "Almost! One part is an unfinished thought — make sure every line has Who/What + Does What.",
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
                    "issues": [g0.get("rule") or "Check word choice!"],
                    "feedback": f"Quick tune-up: {g0.get('rule') or 'Check your word choice.'}",
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
        "feedback": "Direct hit — razor-sharp sentence!",
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
    subskill_hits = payload.get("subskill_hits") or {}
    char_errors = payload.get("char_errors") or {}
    word_outcomes = payload.get("word_outcomes") or []
    played_ids = [str(x).strip() for x in (payload.get("played_ids") or []) if str(x).strip()]
    peak_tier = max(1, min(3, int(payload.get("peak_tier") or 1)))

    rec, sa = _active_rec(sandbox=sandbox)
    rc = curriculum_tracker.ensure_report_card(rec)
    ts_iso = now_iso()
    today = ts_iso[:10]
    now_ts = time.time()

    # Reconcile `seen_ids` when mid-round ZPD swaps occurred so swapped-in reserves never immediately repeat
    # and swapped-out unseen items are restored for future rounds!
    if played_ids:
        seen_map = sa.setdefault("seen_ids", {})
        dealt_ids = (sa.get("last_dealt_ids") or {}).get(game_id) or []
        played_set = set(played_ids)
        unplayed_dealt = {did for did in dealt_ids if did not in played_set}
        if game_id == "sentence_surgery":
            ss_by_id = {x["id"]: x["mode"] for x in SENTENCE_SURGERY_BANK}
            bucket_for_mode = {"runon": "ss_runon", "fragment": "ss_fragment", "mechanics": "ss_mechanics"}
            for b_key in ("ss_runon", "ss_fragment", "ss_mechanics"):
                cur_b = [sid for sid in seen_map.get(b_key, []) if sid not in unplayed_dealt]
                seen_map[b_key] = cur_b
            for pid in played_ids:
                m_pid = ss_by_id.get(pid)
                if m_pid in bucket_for_mode:
                    b_key = bucket_for_mode[m_pid]
                    cur_b = seen_map.setdefault(b_key, [])
                    if pid not in cur_b:
                        cur_b.append(pid)
                    seen_map[b_key] = cur_b[-10:]
        else:
            bank_caps = {
                "word_forge": len(WORD_FORGE_CURRICULUM_BANK),
                "homophone_asteroids": len(HOMOPHONE_ASTEROIDS_BANK),
                "sentence_stretch": len(SENTENCE_STRETCH_BANK),
                "typing_arena": len(TYPING_ARENA_BANK),
                "clue_detective": len(CLUE_DETECTIVE_BANK),
            }
            cur_list = [sid for sid in seen_map.get(game_id, []) if sid not in unplayed_dealt]
            valid_curated = {
                x["id"]
                for x in (
                    WORD_FORGE_CURRICULUM_BANK if game_id == "word_forge"
                    else HOMOPHONE_ASTEROIDS_BANK if game_id == "homophone_asteroids"
                    else SENTENCE_STRETCH_BANK if game_id == "sentence_stretch"
                    else TYPING_ARENA_BANK if game_id == "typing_arena"
                    else CLUE_DETECTIVE_BANK
                )
            }
            for pid in played_ids:
                if pid in valid_curated and pid not in cur_list:
                    cur_list.append(pid)
            seen_map[game_id] = cur_list[-bank_caps.get(game_id, 30):]
        sa.setdefault("last_dealt_ids", {})[game_id] = []

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
    old_zpd = _game_zpd(rec, sa, game_id)
    old_sector = int(round(old_zpd))
    if accuracy >= 88:
        new_zpd = min(3.0, max(old_zpd + 0.35, float(peak_tier) - 0.15))
    elif accuracy >= 75:
        new_zpd = min(3.0, old_zpd + 0.15)
    elif accuracy >= 65:
        new_zpd = max(1.0, old_zpd - 0.05)
    else:
        new_zpd = max(1.0, old_zpd - 0.28)
    new_sector = int(round(new_zpd))

    gs = sa.setdefault("games", {}).setdefault(game_id, {
        "runs": 0, "best_score": 0, "best_accuracy": 0, "best_wpm": 0, "mastery_stars": 0, "last_played": "",
    })
    gs["runs"] = int(gs.get("runs") or 0) + 1
    gs["best_score"] = max(int(gs.get("best_score") or 0), score)
    gs["best_accuracy"] = max(int(gs.get("best_accuracy") or 0), accuracy)
    gs["best_wpm"] = max(int(gs.get("best_wpm") or 0), wpm)
    gs["mastery_stars"] = max(int(gs.get("mastery_stars") or 0), stars)
    gs["zpd"] = round(new_zpd, 2)
    gs["last_played"] = ts_iso

    # Update 16-microskill spaced-repetition mastery + clear Studio trouble flags on mastery!
    BOX_INTERVAL_SEC = {1: 6 * 3600, 2: 24 * 3600, 3: 3 * 86400, 4: 7 * 86400, 5: 14 * 86400}
    stealth_badges: list[str] = []
    if new_sector > old_sector:
        stealth_badges.append(f"Sector {new_sector} Unlocked")

    for sub_id, st_sub in subskill_hits.items():
        if sub_id not in MICRO_SKILL_CATALOG or not isinstance(st_sub, dict):
            continue
        sc = max(0, int(st_sub.get("correct") or 0))
        stt = max(1, int(st_sub.get("total") or 1))
        obs_acc = sc / stt
        ms_e = _ensure_micro_entry(sa, sub_id)
        ms_e["attempts"] = int(ms_e.get("attempts") or 0) + stt
        ms_e["ema_acc"] = round(0.62 * float(ms_e.get("ema_acc", 0.72)) + 0.38 * obs_acc, 3)
        if obs_acc >= 0.8:
            ms_e["streak"] = int(ms_e.get("streak") or 0) + 1
            ms_e["box"] = min(5, int(ms_e.get("box") or 1) + 1)
            if int(ms_e.get("studio_flags") or 0) > 0:
                ms_e["studio_flags"] = max(0, int(ms_e["studio_flags"]) - 1)
                stealth_badges.append(f"{MICRO_SKILL_CATALOG[sub_id]['kid_tag']} Sealed ✓")
        elif obs_acc < 0.65:
            ms_e["streak"] = 0
            ms_e["box"] = max(1, int(ms_e.get("box") or 1) - 1)
        ms_e["next_due"] = round(now_ts + BOX_INTERVAL_SEC.get(int(ms_e["box"]), 86400), 1)

    # Update confusable trouble words (Starshield Turret) & mistyped key profile (Neon Drift)
    tw_map = sa.setdefault("trouble_words", {})
    # Sanitize any legacy non-bank entries and gently decay on strong Starshield runs
    for bad_tw in [kw for kw in tw_map if " " in kw or kw not in _ASTEROID_VALID_WORDS]:
        del tw_map[bad_tw]
    if game_id == "homophone_asteroids" and accuracy >= 75:
        for kw in list(tw_map.keys()):
            tw_map[kw] = max(0, int(tw_map[kw]) - 1)
            if tw_map[kw] == 0:
                del tw_map[kw]
    for wo in word_outcomes:
        if not isinstance(wo, dict):
            continue
        ww = str(wo.get("word") or "").strip().lower()
        if not ww or ww not in _ASTEROID_VALID_WORDS:
            continue
        if wo.get("ok"):
            if ww in tw_map:
                tw_map[ww] = max(0, int(tw_map[ww]) - 1)
                if tw_map[ww] <= 0:
                    del tw_map[ww]
        else:
            tw_map[ww] = min(6, int(tw_map.get(ww) or 0) + 2)

    if game_id == "typing_arena" or (char_errors and isinstance(char_errors, dict)):
        ke_map = sa.setdefault("key_errors", {})
        # Always decay on every Neon Drift run (especially 0-error runs!) so mastered keys clear naturally
        for k_old in list(ke_map.keys()):
            ke_map[k_old] = max(0, int(ke_map[k_old]) - 1)
            if ke_map[k_old] == 0:
                del ke_map[k_old]
        if isinstance(char_errors, dict):
            for ch_k, cnt_v in char_errors.items():
                key_s = str(ch_k or "")[:8]
                if key_s:
                    ke_map[key_s] = min(25, int(ke_map.get(key_s) or 0) + max(0, int(cnt_v or 0)))

    # Sync Obsidian Forge retrieval into Spaced-Repetition Vault (preserving AI card metadata!)
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
                    "unit": _sanitize_forge_unit(str(wr.get("unit") or (meta_w or {}).get("unit") or ""), str((meta_w or {}).get("rule") or "keep")),
                    "source": "word_forge",
                    "box": 1,
                    "next_due": now_ts,
                    "successes": 0,
                    "lapses": 0,
                }
            updated_card = spelling_srs.record_retrieval_result(rec, w, correct_first_try=first_try)
            if updated_card:
                srs_updates.append({"word": w, "box": updated_card.get("box", 1), "first_try": first_try})

    # Strict anti-inflation Ontario Report Card updates (Parent-only): REQUIRE accuracy >= 65% to boost ANY level!
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
            _bump_skill("D2.2_keyboarding", k_est, f"{meta['title']}: {wpm} WPM ({cpm} cpm) at {accuracy}% accuracy")
            if accuracy >= 92:
                _bump_skill("B3.3_mechanics", 2 if accuracy < 96 else 3, f"Typed clean capitals & punctuation at {accuracy}% accuracy")
        elif game_id == "word_forge":
            est = 3 if (accuracy >= 85 and total >= 5) else 2
            words_ok = [u["word"] for u in srs_updates if u["first_try"]][:4]
            ev = f"{meta['title']}: {correct}/{total} forged from memory ({', '.join(words_ok) or 'forge run'})"
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
    tier_num = max(1, min(4, int(rc["mastery_tier"] or 1)))

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
        "zpd": round(new_zpd, 2),
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
        "zpd_sector": new_sector,
        "rank_level": tier_num,
        "rank_title": RANK_TITLES.get(tier_num, "Cadet"),
        "stealth_badges": stealth_badges[:3],
        "srs_updates": srs_updates,
        "skills_boosted": skills_boosted,
        "mastery_tier": rc["mastery_tier"],
        "arcade_reward": arcade_reward,
        "arcade": arcade.client_status(sandbox=sandbox),
    }
