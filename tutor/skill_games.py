"""Skill Arcade — Personalized, Curriculum-Aligned Learning Games for Gemini Tutor.

Upgrades classic Grade 3–4 ELA arcade mechanics (Sentence Surgery, Word Forge,
Homophone & Verb Asteroids, Sentence Stretch Lab, Neon Turbo Typing Arena, and
Mystery Clue Detective) with:
  1. Adaptive targeting from the student's live Ontario Grade 3–4 Report Card
     (`curriculum_tracker.py`) and overdue Leitner spelling cards (`spelling_srs.py`).
  2. Real memory retrieval & production gates (Cover-Copy-Compare typing in Word Forge,
     Boss Wave original sentence writing in Asteroids, stylus-slash run-on surgery,
     evidence highlighting + causal verdict writing in Clue Detective) — zero blind guessing.
  3. Optional Gemini (`FAST_MODEL`) custom pack generation themed to the student's own
     saved comics, Minecraft diaries, and interests, with instant offline fallback.
  4. Honest curriculum mastery updates + accuracy-gated credit into the student's
     1:2 Minecraft / Fists of Doom earned-time bank (`arcade.py`).
"""

from __future__ import annotations

import copy
import json
import random
import re
import time
from typing import Any

from . import arcade, curriculum_tracker, spelling_srs
from .config import FAST_MODEL, api_key, genai_client
from .projects import list_projects
from .record import load_learner, now_iso, save_learner

_SANDBOX_SKILL_STATE: dict[str, Any] = {}

# --------------------------------------------------------------------------- Game Catalog

GAME_CATALOG: list[dict[str, Any]] = [
    {
        "id": "sentence_surgery",
        "title": "Sentence Surgery",
        "subtitle": "Slash run-ons with your stylus, repair broken fragments & stamp dialogue punctuation",
        "icon": "⚔️",
        "accent": "#38bdf8",
        "glow": "rgba(56, 189, 248, 0.35)",
        "est_minutes": "3–4 min",
        "controls": "Stylus slash · Tap · Keyboard",
        "skills": ["B3.1_simple", "B3.1_boundaries", "B3.3_mechanics", "B3.3_dialogue", "D2.5_6_revision"],
        "skill_badges": ["Gr.3 B3.1 Sentences", "Gr.3 B3.3 Punctuation", "Dialogue"],
    },
    {
        "id": "word_forge",
        "title": "Word Forge",
        "subtitle": "Snap Prefix + Base + Suffix runes, apply spelling rules, then forge the word from memory",
        "icon": "🔥",
        "accent": "#f97316",
        "glow": "rgba(249, 115, 22, 0.35)",
        "est_minutes": "3–4 min",
        "controls": "Tap/Drag runes · Type from memory",
        "skills": ["B2.1_2_orthography", "B2.3_morphology"],
        "skill_badges": ["Gr.3–4 B2.3 Morphology", "Leitner Spelling Deck"],
    },
    {
        "id": "homophone_asteroids",
        "title": "Homophone & Verb Asteroids",
        "subtitle": "60fps orbital turret! Blast the right twin word or verb, then defeat the Boss with a real sentence",
        "icon": "☄️",
        "accent": "#a855f7",
        "glow": "rgba(168, 85, 247, 0.38)",
        "est_minutes": "3 min",
        "controls": "Tap asteroids · Keys 1 / 2 / 3 · Boss Type",
        "skills": ["B3.2_grammar", "B2.4_vocabulary"],
        "skill_badges": ["Gr.3–4 B3.2 Grammar", "Homophones & Verbs"],
    },
    {
        "id": "sentence_stretch",
        "title": "Sentence Stretch Lab",
        "subtitle": "Fuse choppy sentences with causal bridges (because/when/while/but) and upgrade weak verbs",
        "icon": "⚡",
        "accent": "#10b981",
        "glow": "rgba(16, 185, 129, 0.35)",
        "est_minutes": "3–4 min",
        "controls": "Tap/Drag bridges · Power Overdrive",
        "skills": ["B3.1_compound", "B3.1_complex", "B2.4_vocabulary"],
        "skill_badges": ["Gr.3–4 B3.1 Compound/Complex", "Vivid Verbs"],
    },
    {
        "id": "typing_arena",
        "title": "Neon Turbo Typing",
        "subtitle": "60fps synthwave speedway! Race with live WPM, accuracy boost & finger-zone guidance",
        "icon": "🏎️",
        "accent": "#22d3ee",
        "glow": "rgba(34, 211, 238, 0.38)",
        "est_minutes": "2–3 min",
        "controls": "Keyboard · Live Finger Guide",
        "skills": ["D2.2_keyboarding", "B3.3_mechanics"],
        "skill_badges": ["Gr.4 D2.2 Keyboarding", "Accuracy & Speed"],
    },
    {
        "id": "clue_detective",
        "title": "Mystery Clue Detective",
        "subtitle": "Highlight the proof sentence with your stylus, crack the case & write a causal verdict",
        "icon": "🔎",
        "accent": "#facc15",
        "glow": "rgba(250, 204, 21, 0.35)",
        "est_minutes": "4 min",
        "controls": "Stylus Highlight · Verdict Writing",
        "skills": ["C2.3_inference", "C1.2_3_craft", "C1.5_pov"],
        "skill_badges": ["Gr.3–4 C2.3 Inference", "Literary Craft"],
    },
]

GAME_BY_ID = {g["id"]: g for g in GAME_CATALOG}


# --------------------------------------------------------------------------- Curated Ontario Gr. 3-4 Content Banks

SENTENCE_SURGERY_BANK: list[dict[str, Any]] = [
    # Mode 1: runon — student physically slashes between the two clauses!
    {
        "mode": "runon",
        "tier": 1,
        "skill": "B3.1_boundaries",
        "prompt": "SLASH right between the two mashed-together sentences!",
        "words": ["The", "creeper", "hissed", "it", "blew", "up", "the", "stone", "bridge."],
        "split_after": 2,
        "fixed": "The creeper hissed. It blew up the stone bridge.",
        "explain": "Two complete actions ('The creeper hissed' + 'It blew up...') need a period and a new capital letter!",
    },
    {
        "mode": "runon",
        "tier": 1,
        "skill": "B3.1_boundaries",
        "prompt": "SLASH between the two separate sentences!",
        "words": ["Maya", "grabbed", "her", "jetpack", "she", "launched", "off", "the", "CN", "Tower."],
        "split_after": 3,
        "fixed": "Maya grabbed her jetpack. She launched off the CN Tower.",
        "explain": "Split right after 'jetpack' so both complete thoughts stand cleanly on their own.",
    },
    {
        "mode": "runon",
        "tier": 1,
        "skill": "B3.1_boundaries",
        "prompt": "SLASH this run-on in half cleanly!",
        "words": ["Our", "minecart", "jumped", "the", "broken", "rail", "we", "landed", "in", "deep", "water."],
        "split_after": 5,
        "fixed": "Our minecart jumped the broken rail. We landed in deep water.",
        "explain": "'Our minecart jumped the broken rail' is complete — start 'We landed...' as sentence two.",
    },
    {
        "mode": "runon",
        "tier": 2,
        "skill": "B3.1_boundaries",
        "prompt": "SLASH where sentence one ends and sentence two starts!",
        "words": ["The", "rogue", "robot", "charged", "down", "Yonge", "Street", "citizens", "ducked", "behind", "a", "streetcar."],
        "split_after": 6,
        "fixed": "The rogue robot charged down Yonge Street. Citizens ducked behind a streetcar.",
        "explain": "Place a period after 'Street' and capitalize 'Citizens'.",
    },
    {
        "mode": "runon",
        "tier": 2,
        "skill": "B3.1_boundaries",
        "prompt": "SLASH the run-on cleanly!",
        "words": ["A", "giant", "squid", "inked", "the", "submarine", "window", "the", "radar", "alarm", "started", "beeping."],
        "split_after": 6,
        "fixed": "A giant squid inked the submarine window. The radar alarm started beeping.",
        "explain": "Two independent clauses mashed together become a run-on — end after 'window'.",
    },
    {
        "mode": "runon",
        "tier": 3,
        "skill": "B3.1_boundaries",
        "prompt": "Find the hidden sentence boundary and SLASH it!",
        "words": ["After", "midnight", "the", "Redstone", "door", "jammed", "nobody", "could", "escape", "the", "vault."],
        "split_after": 5,
        "fixed": "After midnight, the Redstone door jammed. Nobody could escape the vault.",
        "explain": "'After midnight' belongs to the first sentence; the second sentence begins at 'Nobody'.",
    },
    # Mode 2: fragment — student diagnoses what's missing & repairs it!
    {
        "mode": "fragment",
        "tier": 1,
        "skill": "B3.1_simple",
        "prompt": "This fragment is missing a main action (verb)! Pick the repair that makes a complete sentence:",
        "broken": "The silver dragon on top of the obsidian tower.",
        "missing": "verb",
        "choices": [
            {"text": "The silver dragon on top of the obsidian tower breathed blue fire.", "ok": True},
            {"text": "On top of the very tall obsidian tower.", "ok": False, "why": "Still just a place — nobody is doing anything!"},
            {"text": "The silver dragon with giant glowing wings.", "ok": False, "why": "Adds detail, but still has no action verb."},
        ],
        "explain": "A complete sentence needs WHO/WHAT ('The silver dragon') + DOES WHAT ('breathed blue fire').",
    },
    {
        "mode": "fragment",
        "tier": 1,
        "skill": "B3.1_simple",
        "prompt": "Who did this action? Repair the missing subject!",
        "broken": "Sprinted past the laser grid before it shut.",
        "missing": "subject",
        "choices": [
            {"text": "Very quickly past the laser grid before it shut.", "ok": False, "why": "Still doesn't tell us WHO sprinted!"},
            {"text": "Captain Maple sprinted past the laser grid before it shut.", "ok": True},
            {"text": "Sprinting past the buzzing red laser grid.", "ok": False, "why": "An '-ing' phrase with no subject is still a fragment."},
        ],
        "explain": "Adding 'Captain Maple' supplies the explicit subject who performed the action.",
    },
    {
        "mode": "fragment",
        "tier": 2,
        "skill": "B3.1_simple",
        "prompt": "This 'Because...' clause was left hanging! Complete the thought:",
        "broken": "Because the diamond pickaxe broke right next to the lava.",
        "missing": "main_clause",
        "choices": [
            {"text": "Because the diamond pickaxe broke right next to the lava, Alex built a cobblestone bridge.", "ok": True},
            {"text": "Because the glowing hot lava bubbled underground.", "ok": False, "why": "Still starts with 'Because' and never tells what happened as a result!"},
            {"text": "Right next to the deep glowing lava pit.", "ok": False, "why": "That's just a location phrase, not a complete thought."},
        ],
        "explain": "A clause starting with 'Because' needs a main clause showing the result!",
    },
    {
        "mode": "fragment",
        "tier": 2,
        "skill": "B3.1_simple",
        "prompt": "Complete this hanging 'When...' fragment!",
        "broken": "When the alien disguise flickered in the stadium lights.",
        "missing": "main_clause",
        "choices": [
            {"text": "Inside the bright Rogers Centre stadium lights.", "ok": False, "why": "No subject and no action verb!"},
            {"text": "When the alien disguise flickered in the stadium lights, the crowd gasped.", "ok": True},
            {"text": "Flickering brightly under the huge stadium lights.", "ok": False, "why": "Still missing who did what."},
        ],
        "explain": "Pairing the 'When...' opener with 'the crowd gasped' completes the sentence!",
    },
    # Mode 3: mechanics & dialogue — tap exact buggy tokens to fix capitals, apostrophes, quotes, end marks!
    {
        "mode": "mechanics",
        "tier": 1,
        "skill": "B3.3_mechanics",
        "prompt": "Tap EVERY buggy word to fix capitals, apostrophes & end punctuation!",
        "tokens": [
            {"raw": "dylan", "fix": "Dylan", "bug": True, "hint": "Capitalize the start & proper name!"},
            {"raw": "didnt", "fix": "didn't", "bug": True, "hint": "Contraction 'did not' needs an apostrophe!"},
            {"raw": "drop", "fix": "drop", "bug": False},
            {"raw": "his", "fix": "his", "bug": False},
            {"raw": "shield", "fix": "shield.", "bug": True, "hint": "Add ending punctuation!"},
        ],
        "explain": "Sentence-start capital ('Dylan'), contraction apostrophe ('didn't'), and a period at the end.",
    },
    {
        "mode": "mechanics",
        "tier": 2,
        "skill": "B3.3_mechanics",
        "prompt": "Fix the 3 punctuation & capital bugs in this Toronto adventure!",
        "tokens": [
            {"raw": "we", "fix": "We", "bug": True, "hint": "Start every sentence with a capital letter."},
            {"raw": "cant", "fix": "can't", "bug": True, "hint": "'can not' contracts to can't!"},
            {"raw": "let", "fix": "let", "bug": False},
            {"raw": "the", "fix": "the", "bug": False},
            {"raw": "robots", "fix": "robots", "bug": False},
            {"raw": "escape", "fix": "escape!", "bug": True, "hint": "Add an exclamation mark or period at the end!"},
        ],
        "explain": "Fixed start capital ('We'), contraction ('can't'), and end mark ('escape!').",
    },
    {
        "mode": "mechanics",
        "tier": 2,
        "skill": "B3.3_dialogue",
        "prompt": "DIALOGUE SURGERY: Fix the 3 bugs in this spoken line!",
        "tokens": [
            {"raw": "Watch", "fix": "\"Watch", "bug": True, "hint": "Open quotation marks before the spoken words!"},
            {"raw": "out", "fix": "out", "bug": False},
            {"raw": "for", "fix": "for", "bug": False},
            {"raw": "lava", "fix": "lava!\"", "bug": True, "hint": "Close the exclamation & quotation marks!"},
            {"raw": "shouted", "fix": "shouted", "bug": False},
            {"raw": "kai", "fix": "Kai.", "bug": True, "hint": "Capitalize the speaker's name and add a period!"},
        ],
        "explain": "Put quotation marks around exact spoken words (\"Watch out for lava!\") and capitalize speaker names.",
    },
    {
        "mode": "mechanics",
        "tier": 3,
        "skill": "B3.3_dialogue",
        "prompt": "DIALOGUE SURGERY: Stamp the missing quotation marks, comma & capitals!",
        "tokens": [
            {"raw": "the", "fix": "\"The", "bug": True, "hint": "Open quotes AND capitalize the first spoken word!"},
            {"raw": "portal", "fix": "portal", "bug": False},
            {"raw": "is", "fix": "is", "bug": False},
            {"raw": "closing", "fix": "closing,\"", "bug": True, "hint": "Comma + closing quote before 'warned'!"},
            {"raw": "warned", "fix": "warned", "bug": False},
            {"raw": "nova", "fix": "Nova.", "bug": True, "hint": "Capitalize Nova and end with a period!"},
        ],
        "explain": "Use a comma inside the closing quote before a dialogue tag like 'warned Nova.'",
    },
]


WORD_FORGE_CURRICULUM_BANK: list[dict[str, Any]] = [
    # 1-1-1 Consonant Doubling
    {"word": "trapped", "prefix": "", "base": "trap", "suffix": "ed", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "note": "1-1-1 rule: 1 syllable, 1 short vowel (a), 1 end consonant (p) -> double 'p' before -ed!"},
    {"word": "stopped", "prefix": "", "base": "stop", "suffix": "ed", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "note": "Short vowel 'o' + single 'p' -> double the 'p' before adding vowel suffix -ed."},
    {"word": "running", "prefix": "", "base": "run", "suffix": "ing", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "note": "Short 'u' + single 'n' -> double 'n' before -ing (run + n + ing)."},
    {"word": "grabbing", "prefix": "", "base": "grab", "suffix": "ing", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "note": "Short 'a' + single 'b' -> double 'b' before -ing so the vowel stays short!"},
    {"word": "unstoppable", "prefix": "un", "base": "stop", "suffix": "able", "rule": "double", "unit": "B2.3 Prefix + Doubling",
     "note": "Prefix 'un-' + 'stop' (double 'p'!) + '-able' = unstoppable."},
    {"word": "slipped", "prefix": "", "base": "slip", "suffix": "ed", "rule": "double", "unit": "B2.3 Consonant Doubling",
     "note": "Short 'i' + single 'p' -> double the 'p' before -ed so it doesn't look like 'slīped'."},
    # Drop silent e
    {"word": "exploding", "prefix": "", "base": "explode", "suffix": "ing", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "note": "Drop the silent 'e' in 'explode' before adding vowel suffix '-ing'."},
    {"word": "survivor", "prefix": "", "base": "survive", "suffix": "or", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "note": "Drop silent 'e' in 'survive' before adding agent suffix '-or'."},
    {"word": "chasing", "prefix": "", "base": "chase", "suffix": "ing", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "note": "Drop silent 'e' in 'chase' before adding '-ing'."},
    {"word": "gliding", "prefix": "", "base": "glide", "suffix": "ing", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "note": "Drop silent 'e' in 'glide' before adding '-ing'."},
    {"word": "invader", "prefix": "", "base": "invade", "suffix": "er", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "note": "Drop silent 'e' in 'invade' before adding '-er'."},
    {"word": "upgrading", "prefix": "up", "base": "grade", "suffix": "ing", "rule": "drop_e", "unit": "B2.3 Drop Silent-e",
     "note": "Prefix 'up' + 'grade' (drop silent e!) + 'ing' = upgrading."},
    # Change y to i
    {"word": "heaviest", "prefix": "", "base": "heavy", "suffix": "est", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "note": "Consonant + y ('heavy') -> change 'y' to 'i' before adding '-est'."},
    {"word": "supplies", "prefix": "", "base": "supply", "suffix": "es", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "note": "Consonant + y ('supply') -> change 'y' to 'i' and add '-es'."},
    {"word": "carried", "prefix": "", "base": "carry", "suffix": "ed", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "note": "Consonant + y ('carry') -> change 'y' to 'i' before '-ed'."},
    {"word": "enemies", "prefix": "", "base": "enemy", "suffix": "es", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "note": "Consonant + y ('enemy') -> change 'y' to 'i' and add '-es'."},
    {"word": "happily", "prefix": "", "base": "happy", "suffix": "ly", "rule": "y_to_i", "unit": "B2.3 Change y to i",
     "note": "Consonant + y ('happy') -> change 'y' to 'i' before adding '-ly'."},
    # Keep base clean (prefixes, consonant suffixes, bound roots, -tch/-dge)
    {"word": "unbreakable", "prefix": "un", "base": "break", "suffix": "able", "rule": "keep", "unit": "B2.3 Prefix + Suffix",
     "note": "Three clean morphemes: 'un-' (not) + 'break' + '-able' (can be) — base stays unchanged!"},
    {"word": "disappear", "prefix": "dis", "base": "appear", "suffix": "", "rule": "keep", "unit": "B2.3 Prefixes",
     "note": "'dis-' (away/opposite) + 'appear' — just one 's' in 'dis' and two 'p's in 'appear'!"},
    {"word": "rebuilding", "prefix": "re", "base": "build", "suffix": "ing", "rule": "keep", "unit": "B2.3 Prefix + Suffix",
     "note": "'re-' (again) + 'build' + '-ing' — keep the base intact!"},
    {"word": "misplaced", "prefix": "mis", "base": "place", "suffix": "ed", "rule": "drop_e", "unit": "B2.3 Prefix + Drop-e",
     "note": "'mis-' (wrongly) + 'place' (drop silent e) + '-ed' = misplaced."},
    {"word": "fearless", "prefix": "", "base": "fear", "suffix": "less", "rule": "keep", "unit": "B2.3 Suffixes",
     "note": "Base 'fear' + consonant suffix '-less' (without) — no spelling change needed."},
    {"word": "destruction", "prefix": "de", "base": "struct", "suffix": "ion", "rule": "keep", "unit": "Gr.4 B2.1 Bound Roots",
     "note": "Latin root 'struct' means 'build' + 'de-' (reverse) + '-ion' (noun) = destruction."},
    {"word": "erupted", "prefix": "e", "base": "rupt", "suffix": "ed", "rule": "keep", "unit": "Gr.4 B2.1 Bound Roots",
     "note": "Latin root 'rupt' means 'burst' (erupt, interrupt) + 'e-' (out) + '-ed'."},
    {"word": "switched", "prefix": "", "base": "switch", "suffix": "ed", "rule": "keep", "unit": "B2.2 Positional -tch",
     "note": "Right after a short vowel ('i'), /ch/ is spelled '-tch' -> switch + ed."},
]


HOMOPHONE_ASTEROIDS_BANK: list[dict[str, Any]] = [
    # Homophones
    {"tier": 1, "skill": "B2.4_vocabulary", "sentence": "The knights dropped ___ shields when the dragon roared.",
     "options": ["their", "there", "they're"], "answer": "their",
     "explain": "'their' = belongs to them (their shields)!"},
    {"tier": 1, "skill": "B2.4_vocabulary", "sentence": "Watch out—___ is a hidden pressure plate by the door!",
     "options": ["there", "their", "they're"], "answer": "there",
     "explain": "'there' points to a place (has 'here' inside it!)."},
    {"tier": 1, "skill": "B2.4_vocabulary", "sentence": "Hurry up, ___ already building the Nether portal!",
     "options": ["they're", "their", "there"], "answer": "they're",
     "explain": "'they're' = 'they are' ('they are already building')."},
    {"tier": 1, "skill": "B2.4_vocabulary", "sentence": "My backpack was ___ heavy to carry up the cliff.",
     "options": ["too", "to", "two"], "answer": "too",
     "explain": "'too' means 'excessively' or 'also' (extra 'o' = extra much!)."},
    {"tier": 1, "skill": "B2.4_vocabulary", "sentence": "We crafted ___ iron swords before entering the cave.",
     "options": ["two", "too", "to"], "answer": "two",
     "explain": "'two' is the number 2."},
    {"tier": 1, "skill": "B2.4_vocabulary", "sentence": "Grab ___ flashlight before the power grid cuts out!",
     "options": ["your", "you're", "yore"], "answer": "your",
     "explain": "'your' shows ownership (your flashlight)."},
    {"tier": 1, "skill": "B2.4_vocabulary", "sentence": "Wait—___ the only pilot who knows the secret code!",
     "options": ["you're", "your", "yore"], "answer": "you're",
     "explain": "'you're' = 'you are' ('you are the only pilot')."},
    {"tier": 2, "skill": "B2.4_vocabulary", "sentence": "The rover spun ___ wheels in the Martian sand.",
     "options": ["its", "it's", "its'"], "answer": "its",
     "explain": "Possessive 'its' has NO apostrophe (like 'his' and 'her')!"},
    {"tier": 2, "skill": "B2.4_vocabulary", "sentence": "Check the radar—___ tracking three incoming drones!",
     "options": ["it's", "its", "is"], "answer": "it's",
     "explain": "'it's' = 'it is' ('it is tracking')."},
    {"tier": 2, "skill": "B2.4_vocabulary", "sentence": "Do you ___ where the hidden Redstone switch is?",
     "options": ["know", "no", "now"], "answer": "know",
     "explain": "'know' (with silent k, like 'knowledge') means to understand."},
    {"tier": 2, "skill": "B2.4_vocabulary", "sentence": "We could ___ the wolf howling across the snow biome.",
     "options": ["hear", "here", "hare"], "answer": "hear",
     "explain": "'hear' has the word 'ear' right inside it!"},
    {"tier": 2, "skill": "B2.4_vocabulary", "sentence": "She ___ a flaming arrow straight into the target block.",
     "options": ["threw", "through", "thorough"], "answer": "threw",
     "explain": "'threw' is the past tense of 'throw'."},
    {"tier": 2, "skill": "B2.4_vocabulary", "sentence": "The tunnel led straight ___ the hollow mountain.",
     "options": ["through", "threw", "true"], "answer": "through",
     "explain": "'through' means passing from one side to the other."},
    {"tier": 3, "skill": "B2.4_vocabulary", "sentence": "The storm knocked out power across the ___ city.",
     "options": ["whole", "hole", "hold"], "answer": "whole",
     "explain": "'whole' (with 'w') means complete/entire; 'hole' is an opening."},
    # Irregular past-tense verbs & subject-verb agreement (Ontario B3.2)
    {"tier": 1, "skill": "B3.2_grammar", "sentence": "Yesterday, Leo ___ a rare golden axolotl in the cave.",
     "options": ["caught", "catched", "catch"], "answer": "caught",
     "explain": "'catch' is irregular in the past tense: 'caught' (like 'taught')."},
    {"tier": 1, "skill": "B3.2_grammar", "sentence": "Our goalkeeper ___ across the goal and blocked the shot!",
     "options": ["flew", "flied", "flowed"], "answer": "flew",
     "explain": "Past tense of 'fly' is 'flew' (not 'flied')."},
    {"tier": 2, "skill": "B3.2_grammar", "sentence": "She ___ extra torches so nobody would get lost underground.",
     "options": ["brought", "brang", "bringed"], "answer": "brought",
     "explain": "Past tense of 'bring' is 'brought'."},
    {"tier": 2, "skill": "B3.2_grammar", "sentence": "The two robotic guards ___ watching the main gate.",
     "options": ["were", "was", "is"], "answer": "were",
     "explain": "Plural subject ('two robotic guards') takes 'were'."},
    {"tier": 2, "skill": "B3.2_grammar", "sentence": "Each explorer ___ a glowing compass before sunset.",
     "options": ["carries", "carry", "carrying"], "answer": "carries",
     "explain": "'Each explorer' is singular, so the verb takes '-ies' ('carries')."},
    {"tier": 3, "skill": "B3.2_grammar", "sentence": "Before the bridge collapsed, the squad had already ___ across.",
     "options": ["driven", "drove", "drived"], "answer": "driven",
     "explain": "With 'had', use the past participle 'driven' ('had driven')."},
]


SENTENCE_STRETCH_BANK: list[dict[str, Any]] = [
    {
        "tier": 1,
        "skill": "B3.1_compound",
        "clause_a": "The creeper hissed behind the wall.",
        "clause_b": "Alex jumped into the river.",
        "weak_verb": "jumped",
        "verb_upgrades": [
            {"word": "dove", "power": 2, "ok": True},
            {"word": "vaulted", "power": 2, "ok": True},
            {"word": "walked", "power": 0, "ok": False},
        ],
        "bridges": [
            {"word": "so", "kind": "compound", "ok": True, "why": "'so' shows the exact cause-and-effect result!"},
            {"word": "but", "kind": "compound", "ok": False, "why": "'but' shows contrast—jumping into the river was the RESULT of the hiss, not the opposite!"},
            {"word": "or", "kind": "compound", "ok": False, "why": "'or' offers a choice instead of showing what happened next."},
        ],
        "target_example": "The creeper hissed behind the wall, so Alex dove into the river.",
    },
    {
        "tier": 1,
        "skill": "B3.1_compound",
        "clause_a": "Our drone's battery was almost dead.",
        "clause_b": "It still made the rooftop landing.",
        "weak_verb": "made",
        "verb_upgrades": [
            {"word": "nailed", "power": 2, "ok": True},
            {"word": "pulled off", "power": 2, "ok": True},
            {"word": "did", "power": 0, "ok": False},
        ],
        "bridges": [
            {"word": "but", "kind": "compound", "ok": True, "why": "'but' connects two surprising/contrasting ideas!"},
            {"word": "so", "kind": "compound", "ok": False, "why": "A dead battery wouldn't CAUSE a safe landing—you need a contrast word!"},
            {"word": "because", "kind": "complex", "ok": False, "why": "The landing didn't cause the dead battery—use a contrast connector!"},
        ],
        "target_example": "Our drone's battery was almost dead, but it still nailed the rooftop landing.",
    },
    {
        "tier": 2,
        "skill": "B3.1_complex",
        "clause_a": "The whole stadium went dark.",
        "clause_b": "A rogue android cut the main cable.",
        "weak_verb": "cut",
        "verb_upgrades": [
            {"word": "severed", "power": 2, "ok": True},
            {"word": "sliced", "power": 2, "ok": True},
            {"word": "touched", "power": 0, "ok": False},
        ],
        "bridges": [
            {"word": "because", "kind": "complex", "ok": True, "why": "'because' explains the exact reason the stadium went dark!"},
            {"word": "but", "kind": "compound", "ok": False, "why": "Cutting the cable explains WHY it went dark—use a cause connector!"},
            {"word": "until", "kind": "complex", "ok": False, "why": "'until' reverses the timing—cutting the cable happened first!"},
        ],
        "target_example": "The whole stadium went dark because a rogue android severed the main cable.",
    },
    {
        "tier": 2,
        "skill": "B3.1_complex",
        "clause_a": "Nova grabbed the golden key.",
        "clause_b": "The stone trapdoor snapped shut.",
        "weak_verb": "grabbed",
        "verb_upgrades": [
            {"word": "snatched", "power": 2, "ok": True},
            {"word": "yanked", "power": 2, "ok": True},
            {"word": "got", "power": 0, "ok": False},
        ],
        "bridges": [
            {"word": "before", "kind": "complex", "ok": True, "why": "'before' builds real suspense by showing exact timing!"},
            {"word": "because", "kind": "complex", "ok": False, "why": "The trapdoor closing wasn't the reason she wanted the key—show the timing!"},
            {"word": "although", "kind": "complex", "ok": False, "why": "Check the timing—she got it JUST IN TIME!"},
        ],
        "target_example": "Nova snatched the golden key before the stone trapdoor snapped shut.",
    },
    {
        "tier": 2,
        "skill": "B3.1_complex",
        "clause_a": "The iron golem guarded the village gate.",
        "clause_b": "The builders fixed the broken wall.",
        "weak_verb": "fixed",
        "verb_upgrades": [
            {"word": "reinforced", "power": 2, "ok": True},
            {"word": "rebuilt", "power": 2, "ok": True},
            {"word": "did", "power": 0, "ok": False},
        ],
        "bridges": [
            {"word": "while", "kind": "complex", "ok": True, "why": "'while' shows two heroic actions happening at the exact same time!"},
            {"word": "so", "kind": "compound", "ok": False, "why": "Guarding didn't cause the wall to break—both happened at once!"},
            {"word": "unless", "kind": "complex", "ok": False, "why": "'unless' changes the meaning completely."},
        ],
        "target_example": "The iron golem guarded the village gate while the builders reinforced the broken wall.",
    },
    {
        "tier": 3,
        "skill": "B3.1_complex",
        "clause_a": "The snowstorm buried the runway.",
        "clause_b": "The rescue jet took off safely.",
        "weak_verb": "took off",
        "verb_upgrades": [
            {"word": "rocketed", "power": 2, "ok": True},
            {"word": "soared", "power": 2, "ok": True},
            {"word": "went up", "power": 0, "ok": False},
        ],
        "bridges": [
            {"word": "although", "kind": "complex", "ok": True, "why": "'Although' at the front creates a crisp Grade 4 complex contrast sentence!"},
            {"word": "because", "kind": "complex", "ok": False, "why": "A buried runway doesn't HELP a jet take off—this is a contrast!"},
            {"word": "so", "kind": "compound", "ok": False, "why": "Try a subordinating contrast connector!"},
        ],
        "front_connector": True,
        "target_example": "Although the snowstorm buried the runway, the rescue jet soared safely.",
    },
]


TYPING_ARENA_BANK: list[dict[str, Any]] = [
    {"tier": 1, "tag": "Minecraft", "text": "Always carry a water bucket when you mine near deep lava."},
    {"tier": 1, "tag": "Toronto", "text": "The CN Tower rises 553 meters above downtown Toronto."},
    {"tier": 1, "tag": "Science", "text": "Octopuses have three hearts and blue blood inside their bodies."},
    {"tier": 1, "tag": "Minecraft", "text": "Redstone dust carries power from a lever to an iron door."},
    {"tier": 2, "tag": "Action", "text": "Captain Maple vaulted over the streetcar and blocked the laser."},
    {"tier": 2, "tag": "Minecraft", "text": "Enchanting an unbreakable diamond pickaxe saves time in obsidian caves."},
    {"tier": 2, "tag": "Space", "text": "Mars rovers beam sharp photos across millions of kilometers of space."},
    {"tier": 2, "tag": "Invention", "text": "Engineers test every bridge cable before opening it to real traffic."},
    {"tier": 3, "tag": "Dialogue", "text": "\"Watch the radar!\" shouted Nova, because three drones just appeared."},
    {"tier": 3, "tag": "Morphology", "text": "Although the heavy supply cart slipped, the fearless team kept rebuilding."},
]


CLUE_DETECTIVE_BANK: list[dict[str, Any]] = [
    {
        "tier": 1,
        "skill": "C2.3_inference",
        "case_title": "Case #104: The Missing Diamond Pickaxe",
        "question": "Who actually took the diamond pickaxe from the storage chest?",
        "sentences": [
            "At 4:00 PM, Leo locked his enchanted diamond pickaxe inside the oak base.",
            "Maya spent the whole afternoon fishing by the frozen river with zero tools.",
            "At 4:15 PM, Sam walked out of the base with fresh oak splinters stuck to his muddy boots and a glowing purple glint inside his satchel.",
            "Later, the village iron golem patrolled the wheat field without entering any houses.",
        ],
        "clue_index": 2,
        "choices": [
            {"label": "Sam", "ok": True},
            {"label": "Maya", "ok": False, "why": "Maya was out at the frozen river with zero tools."},
            {"label": "The Iron Golem", "ok": False, "why": "The golem never entered any houses."},
        ],
        "verdict_starter": "I know Sam took the pickaxe because",
        "required_word": "because",
        "explain": "Oak splinters + a glowing purple enchanted glint in Sam's satchel prove Sam was the culprit!",
    },
    {
        "tier": 1,
        "skill": "C2.3_inference",
        "case_title": "Case #208: The Midnight CN Tower Glitch",
        "question": "What caused the neon beacon on the roof to flicker off?",
        "sentences": [
            "Every night, the tall beacon guides helicopters safely over Toronto's harbour.",
            "Last Tuesday, the sky was crystal clear with no wind and no thunder.",
            "At midnight, the backup power lights blinked red right as a raccoon squeezed out of the chewed-open fuse box holding shiny copper wire.",
            "Security guards checked the lobby doors and found every lock still bolted.",
        ],
        "clue_index": 2,
        "choices": [
            {"label": "A raccoon chewed the fuse box wire", "ok": True},
            {"label": "A huge thunderstorm hit Toronto", "ok": False, "why": "Line 2 says the sky was crystal clear with no thunder."},
            {"label": "Someone unlocked the lobby door", "ok": False, "why": "Every lobby lock was still bolted."},
        ],
        "verdict_starter": "I know a raccoon caused the glitch because",
        "required_word": "because",
        "explain": "The chewed-open fuse box + copper wire in the raccoon's paws is direct text evidence!",
    },
    {
        "tier": 2,
        "skill": "C1.2_3_craft",
        "case_title": "Case #312: Literary Craft Radar (Metaphor)",
        "question": "Highlight the sentence that uses a METAPHOR (comparing two things WITHOUT 'like' or 'as')!",
        "sentences": [
            "The rocket boosters rumbled loudly across the concrete launchpad.",
            "Engineers checked their glowing tablets one final time before ignition.",
            "As the countdown hit zero, the rocket became a blazing spear slicing through the night sky.",
            "Everyone inside mission control cheered when it cleared the clouds.",
        ],
        "clue_index": 2,
        "choices": [
            {"label": "Metaphor ('became a blazing spear')", "ok": True},
            {"label": "Simile (uses 'like' or 'as')", "ok": False, "why": "Notice it says the rocket BECAME a blazing spear—no 'like' or 'as' comparison!"},
            {"label": "Plain fact with no imagery", "ok": False, "why": "Calling a rocket a 'blazing spear' is strong figurative imagery!"},
        ],
        "verdict_starter": "That sentence is a metaphor because",
        "required_word": "because",
        "explain": "A metaphor says one thing IS (or became) another thing directly ('a blazing spear').",
    },
    {
        "tier": 2,
        "skill": "C1.2_3_craft",
        "case_title": "Case #405: Sound Effects & Simile Scan",
        "question": "Highlight the sentence that uses a SIMILE (comparing two things using 'like' or 'as')!",
        "sentences": [
            "A cold northern gust swept across the hockey rink at dusk.",
            "Kai laced up his skates and tapped his stick on the ice.",
            "He burst down the right wing as fast as a peregrine falcon diving for prey.",
            "The puck rattled the back of the net before the goalie could blink.",
        ],
        "clue_index": 2,
        "choices": [
            {"label": "Simile ('as fast as a peregrine falcon')", "ok": True},
            {"label": "Onomatopoeia (sound word)", "ok": False, "why": "This sentence compares speed using 'as...as', which makes it a simile!"},
            {"label": "First-person narrator ('I')", "ok": False, "why": "Notice it uses 'He' and 'Kai'—that's 3rd-person point of view."},
        ],
        "verdict_starter": "That sentence is a simile because",
        "required_word": "because",
        "explain": "'as fast as a peregrine falcon' compares Kai's speed using 'as...as' — classic simile!",
    },
    {
        "tier": 3,
        "skill": "C1.5_pov",
        "case_title": "Case #519: Point-of-View Tracker",
        "question": "Which sentence proves this story is told in FIRST-PERSON point of view?",
        "sentences": [
            "The ancient stone gate groaned open into a cavern lit by glowing moss.",
            "Blue crystals hummed along the ceiling like giant tuning forks.",
            "My boots slipped on the wet rock, and I barely caught the ledge before falling.",
            "Far below, an underground river rushed toward the dark chasm.",
        ],
        "clue_index": 2,
        "choices": [
            {"label": "First-person ('My' and 'I')", "ok": True},
            {"label": "Third-person ('he / she / they')", "ok": False, "why": "Look closely at the narrator pronouns in line 3: 'My' and 'I'!"},
            {"label": "Second-person ('you')", "ok": False, "why": "The narrator is telling their own experience using 'I'."},
        ],
        "verdict_starter": "I know it is first-person because",
        "required_word": "because",
        "explain": "First-person narration uses 'I', 'me', and 'my' so we experience the scene through the narrator's eyes.",
    },
]


# --------------------------------------------------------------------------- State & Persistence Helpers

def _default_skill_arcade() -> dict[str, Any]:
    return {
        "total_runs": 0,
        "total_correct": 0,
        "total_attempts": 0,
        "streak_days": 0,
        "last_played_date": "",
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


def _skill_need_score(rc: dict[str, Any], deck_due: int, game: dict[str, Any]) -> tuple[float, str]:
    """Computes priority score (higher = more valuable for this learner right now) + short reason."""
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

    enriched = []
    scored = []
    for g in GAME_CATALOG:
        gid = g["id"]
        gs = games_stats.get(gid) or {}
        need, reason = _skill_need_score(rc, due_now, g)
        scored.append((need, gid))
        enriched.append({
            **g,
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

def _parse_parts_to_forge_item(card: dict[str, Any]) -> dict[str, Any] | None:
    """Converts a Leitner spelling card into a Word Forge morpheme puzzle if cleanly structured."""
    word = (card.get("word") or "").strip().lower()
    if not word or not word.isalpha() or len(word) < 4:
        return None
    # Check if already in our exact morphology bank
    for item in WORD_FORGE_CURRICULUM_BANK:
        if item["word"].lower() == word:
            return {**item, "from_deck": True, "box": int(card.get("box") or 1)}

    # Infer simple morphological structure from `parts` or common affixes
    parts_raw = (card.get("parts") or "").strip()
    note = (card.get("note") or "").strip() or f"Spell '{word}' carefully piece by piece!"
    unit = card.get("unit") or "From your spelling deck"

    # Try parsing `un + break + able` or `explode - e + ing`
    clean_p = parts_raw.replace("−", "-").replace("→", "->")
    if "+" in clean_p:
        segs = [re.sub(r"[^a-z]", "", s.lower()) for s in clean_p.split("+")]
        segs = [s for s in segs if s]
        if len(segs) >= 2:
            if "drop" in note.lower() or "- e" in clean_p or "-e" in clean_p:
                rule = "drop_e"
            elif "y->i" in clean_p or "y to i" in note.lower():
                rule = "y_to_i"
            elif "double" in note.lower() or (len(segs) == 3 and len(segs[1]) == 1):
                rule = "double"
            else:
                rule = "keep"
            if len(segs) == 3 and len(segs[1]) == 1:
                return {"word": word, "prefix": "", "base": segs[0], "suffix": segs[2], "rule": "double",
                        "unit": unit, "note": note, "from_deck": True, "box": int(card.get("box") or 1)}
            if len(segs) == 2:
                if segs[0] in ("un", "dis", "re", "mis", "pre", "sub", "de", "in", "im", "up"):
                    return {"word": word, "prefix": segs[0], "base": segs[1], "suffix": "", "rule": rule,
                            "unit": unit, "note": note, "from_deck": True, "box": int(card.get("box") or 1)}
                return {"word": word, "prefix": "", "base": segs[0], "suffix": segs[1], "rule": rule,
                        "unit": unit, "note": note, "from_deck": True, "box": int(card.get("box") or 1)}
            return {"word": word, "prefix": segs[0], "base": segs[1], "suffix": segs[2], "rule": rule,
                    "unit": unit, "note": note, "from_deck": True, "box": int(card.get("box") or 1)}

    # Fallback: syllable/chunk forge (keep rule) so student's real misspellings ALWAYS appear!
    mid = max(2, len(word) // 2)
    return {
        "word": word,
        "prefix": "",
        "base": word[:mid],
        "suffix": word[mid:],
        "rule": "keep",
        "unit": unit,
        "note": note,
        "from_deck": True,
        "box": int(card.get("box") or 1),
    }


def _build_word_forge_pack(rec: dict[str, Any], count: int = 6) -> list[dict[str, Any]]:
    deck = spelling_srs.ensure_deck(rec)
    cards = list((deck.get("cards") or {}).values())
    now = time.time()
    # Priority 1: overdue cards & error cards in low boxes
    cards.sort(key=lambda c: (0 if (c.get("next_due") or 0) <= now else 1, c.get("box", 1), -(c.get("lapses", 0))))

    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in cards:
        if len(chosen) >= min(3, count):
            break
        if c.get("box", 1) >= 5 and (c.get("next_due") or 0) > now:
            continue
        item = _parse_parts_to_forge_item(c)
        if item and item["word"] not in seen:
            seen.add(item["word"])
            chosen.append(item)

    # Fill remainder with varied rule types from our Ontario morphology bank
    pool = [dict(x, from_deck=False, box=1) for x in WORD_FORGE_CURRICULUM_BANK if x["word"] not in seen]
    random.shuffle(pool)
    # Guarantee variety across double / drop_e / y_to_i / keep
    by_rule: dict[str, list[dict[str, Any]]] = {}
    for x in pool:
        by_rule.setdefault(x["rule"], []).append(x)
    while len(chosen) < count and any(by_rule.values()):
        for rkey in ("double", "drop_e", "y_to_i", "keep"):
            if len(chosen) >= count:
                break
            lst = by_rule.get(rkey)
            if lst:
                chosen.append(lst.pop())

    # Attach distractor morpheme tiles so the student actively picks & snaps the right blocks!
    all_prefixes = ["un", "dis", "re", "mis", "de", "up", "pre"]
    all_suffixes = ["ed", "ing", "er", "or", "es", "est", "ly", "able", "less", "ion"]
    for it in chosen:
        tiles = []
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
    return chosen


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
    """Optionally asks FAST_MODEL for a fresh custom JSON pack themed to the student's worlds."""
    if not api_key():
        return None
    theme = _student_theme_snippet(rec)
    grade = int(rec.get("grade") or 3)
    schemas = {
        "homophone_asteroids": (
            'Return JSON array of 6 items: [{"tier":2,"skill":"B2.4_vocabulary","sentence":"Sentence with ___ blank.",'
            '"options":["correct","wrong1","wrong2"],"answer":"correct","explain":"Short clear rule."}]. '
            "Mix 4 homophone items (their/there/they're, to/too/two, your/you're, its/it's, threw/through, hear/here, know/no) "
            "and 2 irregular past-tense/agreement items (caught/brought/flew/were/carries). answer MUST be inside options."
        ),
        "typing_arena": (
            'Return JSON array of 5 items: [{"tier":2,"tag":"ThemeTag","text":"One clean crisp complete sentence 8-14 words long."}]. '
            "Use proper capitals, punctuation, and vivid Grade 3-4 words. Zero weird symbols."
        ),
        "sentence_stretch": (
            'Return JSON array of 5 items: [{"tier":2,"skill":"B3.1_complex","clause_a":"Short sentence 1.","clause_b":"Short sentence 2.",'
            '"weak_verb":"word appearing verbatim in clause_a or clause_b","verb_upgrades":[{"word":"vivid1","power":2,"ok":true},'
            '{"word":"vivid2","power":2,"ok":true},{"word":"bland","power":0,"ok":false}],'
            '"bridges":[{"word":"because","kind":"complex","ok":true,"why":"Why it fits."},{"word":"wrong1","kind":"compound","ok":false,"why":"Why not."},'
            '{"word":"wrong2","kind":"complex","ok":false,"why":"Why not."}],"target_example":"Combined vivid sentence."}]. '
            "Ensure weak_verb appears verbatim inside clause_a or clause_b."
        ),
        "clue_detective": (
            'Return JSON array of 3 mini-mysteries: [{"tier":2,"skill":"C2.3_inference","case_title":"Case #...: Title",'
            '"question":"Deduction question?","sentences":["S1.","S2.","S3 clue.","S4."],"clue_index":2,'
            '"choices":[{"label":"Right Answer","ok":true},{"label":"Wrong 1","ok":false,"why":"Why wrong."},{"label":"Wrong 2","ok":false,"why":"Why wrong."}],'
            '"verdict_starter":"I know ... because","required_word":"because","explain":"Why clue proves it."}]. '
            "sentences must have exactly 4 strings and clue_index must be 0..3."
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
        client = genai_client(timeout_ms=8000)
        resp = client.models.generate_content(model=FAST_MODEL, contents=prompt)
        raw = (resp.text or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) < 3:
            return None
        # Validate essential structure per game so malformed LLM output NEVER breaks gameplay
        if game_id == "homophone_asteroids":
            valid = [x for x in data if isinstance(x, dict) and "___" in str(x.get("sentence", "")) and x.get("answer") in (x.get("options") or []) and len(x.get("options") or []) == 3]
            return valid[:6] if len(valid) >= 4 else None
        if game_id == "typing_arena":
            valid = [x for x in data if isinstance(x, dict) and 28 <= len(str(x.get("text", "")).strip()) <= 95]
            return valid[:5] if len(valid) >= 3 else None
        if game_id == "sentence_stretch":
            valid = []
            for x in data:
                if not isinstance(x, dict):
                    continue
                wv = str(x.get("weak_verb") or "")
                comb = f"{x.get('clause_a','')} {x.get('clause_b','')}"
                if wv and re.search(rf"\b{re.escape(wv)}\b", comb) and any(b.get("ok") for b in (x.get("bridges") or [])):
                    valid.append(x)
            return valid[:5] if len(valid) >= 3 else None
        if game_id == "clue_detective":
            valid = [
                x for x in data
                if isinstance(x, dict)
                and isinstance(x.get("sentences"), list) and len(x["sentences"]) == 4
                and isinstance(x.get("clue_index"), int) and 0 <= x["clue_index"] <= 3
                and any(c.get("ok") for c in (x.get("choices") or []))
            ]
            return valid[:3] if len(valid) >= 2 else None
    except Exception:
        return None
    return None


def generate_game_pack(
    game_id: str,
    *,
    use_ai: bool = False,
    sandbox: bool = False,
) -> dict[str, Any]:
    if game_id not in GAME_BY_ID:
        raise ValueError(f"Unknown skill game: {game_id}")
    rec, _ = _active_rec(sandbox=sandbox)
    rc = curriculum_tracker.ensure_report_card(rec)
    meta = GAME_BY_ID[game_id]
    ai_generated = False

    items: list[dict[str, Any]] = []
    if use_ai:
        ai_items = _try_ai_pack(game_id, rec)
        if ai_items:
            items = ai_items
            ai_generated = True

    if not items:
        if game_id == "sentence_surgery":
            # Pick balanced mix: 2 run-ons + 2 fragments + 2 mechanics/dialogue
            runons = [copy.deepcopy(x) for x in SENTENCE_SURGERY_BANK if x["mode"] == "runon"]
            frags = [copy.deepcopy(x) for x in SENTENCE_SURGERY_BANK if x["mode"] == "fragment"]
            mechs = [copy.deepcopy(x) for x in SENTENCE_SURGERY_BANK if x["mode"] == "mechanics"]
            random.shuffle(runons)
            random.shuffle(frags)
            random.shuffle(mechs)
            items = runons[:2] + frags[:2] + mechs[:2]
            random.shuffle(items)
            for it in items:
                if it["mode"] == "fragment":
                    random.shuffle(it["choices"])
        elif game_id == "word_forge":
            items = _build_word_forge_pack(rec, count=6)
        elif game_id == "homophone_asteroids":
            pool = [copy.deepcopy(x) for x in HOMOPHONE_ASTEROIDS_BANK]
            random.shuffle(pool)
            items = pool[:7]
            for it in items:
                random.shuffle(it["options"])
        elif game_id == "sentence_stretch":
            pool = [copy.deepcopy(x) for x in SENTENCE_STRETCH_BANK]
            random.shuffle(pool)
            items = pool[:5]
            for it in items:
                random.shuffle(it["bridges"])
                random.shuffle(it["verb_upgrades"])
        elif game_id == "typing_arena":
            pool = [copy.deepcopy(x) for x in TYPING_ARENA_BANK]
            # Inject a custom sentence built from his due Leitner spelling cards if available!
            deck = spelling_srs.ensure_deck(rec)
            due_words = [c["word"] for c in (deck.get("cards") or {}).values() if c.get("box", 1) < 5][:3]
            random.shuffle(pool)
            items = pool[:5]
            if len(due_words) >= 2:
                items[0] = {
                    "tier": 2,
                    "tag": "Your Spelling Deck",
                    "text": f"Watch how cleanly I spell {due_words[0]} and {due_words[1]} today!",
                }
        elif game_id == "clue_detective":
            pool = [copy.deepcopy(x) for x in CLUE_DETECTIVE_BANK]
            random.shuffle(pool)
            items = pool[:3]
            for it in items:
                random.shuffle(it["choices"])

    return {
        "game": meta,
        "ai_generated": ai_generated,
        "mastery_tier": int(rc.get("mastery_tier") or 1),
        "items": items,
    }


# --------------------------------------------------------------------------- Live Sentence / Boss Verification

def verify_production_sentence(
    text: str,
    *,
    required_word: str = "",
    require_because: bool = False,
) -> dict[str, Any]:
    """Deterministic, instant Homework-Standard verifier for Boss Waves & Detective Verdicts."""
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
    if require_because and not re.search(r"\b(because|since|so)\b", raw.lower()):
        issues.append("Use 'because' to prove WHY your evidence solves the case!")

    # Basic fragment guard: starting with 'Because ...' without a second clause/comma
    if re.match(r"^(because|when|while|although)\b", raw.lower()) and "," not in raw and len(words) < 7:
        issues.append("Finish the whole thought after your opener!")

    ok = len(issues) == 0
    return {
        "ok": ok,
        "issues": issues,
        "feedback": "Clean Homework-Standard sentence — Direct hit!" if ok else issues[0],
        "word_count": len(words),
    }


# --------------------------------------------------------------------------- Completion, Mastery & Arcade Credit

def record_game_completion(payload: dict[str, Any], *, sandbox: bool = False) -> dict[str, Any]:
    """Persists Skill Arcade telemetry, updates Leitner SRS + Ontario Report Card + 1:2 Arcade Bank."""
    game_id = str(payload.get("game_id") or "")
    if game_id not in GAME_BY_ID:
        raise ValueError(f"Unknown skill game: {game_id}")
    meta = GAME_BY_ID[game_id]

    correct = max(0, int(payload.get("correct") or 0))
    total = max(1, int(payload.get("total") or 1))
    accuracy = max(0, min(100, int(round(100.0 * correct / total))))
    score = max(0, int(payload.get("score") or 0))
    active_seconds = max(0.0, min(300.0, float(payload.get("active_seconds") or 0.0)))
    wpm = max(0, int(payload.get("wpm") or 0))
    cpm = max(0, int(payload.get("cpm") or 0))
    production_passed = bool(payload.get("production_passed", False))
    production_sentence = str(payload.get("production_sentence") or "").strip()[:180]
    word_results = payload.get("word_results") or []  # [{"word": ..., "first_try": bool, "wrote": ...}]
    skill_hits = payload.get("skill_hits") or {}  # {"B3.1_boundaries": {"correct": 2, "total": 2}}

    rec, sa = _active_rec(sandbox=sandbox)
    rc = curriculum_tracker.ensure_report_card(rec)
    ts_iso = now_iso()
    today = ts_iso[:10]

    # 1. Update Skill Arcade stats & day streak
    sa["total_runs"] = int(sa.get("total_runs") or 0) + 1
    sa["total_correct"] = int(sa.get("total_correct") or 0) + correct
    sa["total_attempts"] = int(sa.get("total_attempts") or 0) + total
    if sa.get("last_played_date") != today:
        sa["streak_days"] = int(sa.get("streak_days") or 0) + 1
        sa["last_played_date"] = today

    stars = 3 if (accuracy >= 90 and (production_passed or game_id in ("sentence_surgery", "sentence_stretch", "typing_arena"))) else (2 if accuracy >= 75 else (1 if accuracy >= 50 else 0))
    gs = sa.setdefault("games", {}).setdefault(game_id, {
        "runs": 0, "best_score": 0, "best_accuracy": 0, "best_wpm": 0, "mastery_stars": 0, "last_played": "",
    })
    gs["runs"] = int(gs.get("runs") or 0) + 1
    gs["best_score"] = max(int(gs.get("best_score") or 0), score)
    gs["best_accuracy"] = max(int(gs.get("best_accuracy") or 0), accuracy)
    gs["best_wpm"] = max(int(gs.get("best_wpm") or 0), wpm)
    gs["mastery_stars"] = max(int(gs.get("mastery_stars") or 0), stars)
    gs["last_played"] = ts_iso

    # 2. Sync Word Forge retrieval straight into Leitner Spaced-Repetition Deck!
    srs_updates: list[dict[str, Any]] = []
    if word_results:
        deck = spelling_srs.ensure_deck(rec)
        for wr in word_results:
            w = str(wr.get("word") or "").strip().lower()
            if not w:
                continue
            first_try = bool(wr.get("first_try", False))
            wrote = str(wr.get("wrote") or "").strip()
            # Ensure card exists in deck before updating Leitner box
            if w not in deck["cards"]:
                meta_w = next((x for x in WORD_FORGE_CURRICULUM_BANK if x["word"].lower() == w), None)
                deck["cards"][w] = {
                    "word": w,
                    "wrote": wrote if not first_try else "",
                    "parts": " + ".join(p for p in [meta_w.get("prefix"), meta_w.get("base"), meta_w.get("suffix")] if p) if meta_w else w,
                    "note": (meta_w or {}).get("note", ""),
                    "unit": (meta_w or {}).get("unit", "Word Forge"),
                    "source": "word_forge",
                    "box": 1,
                    "next_due": time.time(),
                    "successes": 0,
                    "lapses": 0,
                }
            updated_card = spelling_srs.record_retrieval_result(rec, w, correct_first_try=first_try)
            if updated_card:
                srs_updates.append({"word": w, "box": updated_card.get("box", 1), "first_try": first_try})

    # 3. Conservative, honest Ontario Grade 3–4 Report Card updates
    sk = rc["skills"]
    skills_boosted: list[str] = []

    def _bump_skill(sid: str, est_level: int, evidence_txt: str) -> None:
        if sid not in sk or est_level <= 0:
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

    if game_id == "typing_arena" and cpm >= 25:
        k_est = 4 if (cpm >= 140 and accuracy >= 92) else (3 if (cpm >= 95 and accuracy >= 90) else (2 if (cpm >= 55 and accuracy >= 85) else 1))
        _bump_skill("D2.2_keyboarding", k_est, f"Neon Turbo Typing: {wpm} WPM ({cpm} cpm) at {accuracy}% accuracy")
        if accuracy >= 92:
            _bump_skill("B3.3_mechanics", 2 if accuracy < 96 else 3, f"Typed clean capitals & punctuation at {accuracy}% accuracy")
    elif game_id == "word_forge":
        est = 3 if (accuracy >= 85 and total >= 5) else (2 if accuracy >= 60 else 1)
        words_ok = [u["word"] for u in srs_updates if u["first_try"]][:4]
        ev = f"Word Forge: {correct}/{total} forged from memory ({', '.join(words_ok) or 'practice'})"
        _bump_skill("B2.3_morphology", est, ev)
        if accuracy >= 80:
            _bump_skill("B2.1_2_orthography", est, ev)
    else:
        # Generic skill_hits mapping + overall performance gate
        base_est = 3 if (accuracy >= 85 and (production_passed or game_id in ("sentence_surgery", "sentence_stretch"))) else (2 if accuracy >= 60 else 1)
        ev_tail = f" · “{production_sentence}”" if production_sentence else ""
        if skill_hits:
            for sid, stats_s in skill_hits.items():
                sc = int(stats_s.get("correct") or 0)
                st = max(1, int(stats_s.get("total") or 1))
                s_acc = 100.0 * sc / st
                s_est = min(base_est, 3 if s_acc >= 85 else (2 if s_acc >= 50 else 1))
                _bump_skill(sid, s_est, f"{meta['title']}: {sc}/{st} ({round(s_acc)}%){ev_tail}")
        else:
            for sid in meta["skills"][:2]:
                _bump_skill(sid, base_est, f"{meta['title']}: {correct}/{total} ({accuracy}%){ev_tail}")

    rc["mastery_tier"] = curriculum_tracker.compute_mastery_tier(rc)
    rc["updated"] = ts_iso

    # Record run summary for Parent Dashboard
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

    # 4. Feed verified, accuracy-gated active work seconds into 1:2 Minecraft / Fists of Doom bank!
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
