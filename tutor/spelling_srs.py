"""Spaced Repetition (Leitner) & Systematic Ontario Grade 3–4 Spelling / Morphology Engine.

Grounds spelling instruction in:
- Graham & Santangelo (2014): formal spelling instruction transfers strongly to writing (ES = 0.94).
- Bowers, Kirby, & Deacon (2010): morphological instruction (bases, prefixes, suffixes, word sums)
  disproportionately benefits struggling spellers (Ontario Gr. 3 B2.3 / Gr. 4 B2.1).
- Cepeda et al. (2006): distributed/spaced retrieval across days (1d -> 3d -> 7d -> 14d -> 30d).

Guarantees EVERY session includes structured word study:
  1. First priority: words the child actually misspelled while writing today.
  2. Second priority: due cards from their Leitner spaced-review deck.
  3. Third priority: systematic progression through the Ontario Language Foundations Continuum
     (so avoiding hard words during drafting never skips spelling & morphology instruction).
"""

from __future__ import annotations

import time
from typing import Any

from . import thinking

# Leitner intervals in seconds: Box 1 = 18h, Box 2 = 3d, Box 3 = 7d, Box 4 = 14d, Box 5 = 30d (Mastered)
BOX_INTERVALS = {
    1: 18 * 3600,
    2: 3 * 86400,
    3: 7 * 86400,
    4: 14 * 86400,
    5: 30 * 86400,
}

# Systematic Ontario Grade 3–4 Orthographic & Morphological Curriculum (B2.1–B2.3, Gr. 4 B2.1)
ONTARIO_CURRICULUM_WORDS: list[dict[str, str]] = [
    # Unit 1: 1-1-1 Consonant Doubling
    {
        "word": "trapped",
        "parts": "trap + p + ed",
        "note": "1-1-1 doubling rule: 1 syllable, 1 short vowel (a), 1 end consonant (p) -> double the p before -ed.",
        "unit": "B2.3 Consonant Doubling",
    },
    {
        "word": "stoppable",
        "parts": "stop + p + able",
        "note": "Short vowel 'o' + single consonant 'p': double the p before adding vowel suffix -able.",
        "unit": "B2.3 Consonant Doubling",
    },
    # Unit 2: Drop Silent-e Before Vowel Suffix
    {
        "word": "exploding",
        "parts": "explode − e + ing",
        "note": "Drop the silent 'e' in 'explode' when adding a suffix that starts with a vowel (-ing).",
        "unit": "B2.3 Drop Silent-e",
    },
    {
        "word": "survivor",
        "parts": "survive − e + or",
        "note": "Drop the silent 'e' in 'survive' before adding the agent suffix -or.",
        "unit": "B2.3 Drop Silent-e",
    },
    # Unit 3: Short-Vowel Positional Spellings (-tch, -dge, -ck)
    {
        "word": "switched",
        "parts": "switch + ed",
        "note": "Right after a single short vowel, /ch/ is spelled 'tch' (switch + ed).",
        "unit": "B2.2 Positional -tch/-dge",
    },
    {
        "word": "bridge",
        "parts": "bridg + e (dge)",
        "note": "English words don't end in plain 'j'; right after a short vowel, /j/ is spelled '-dge'.",
        "unit": "B2.2 Positional -tch/-dge",
    },
    # Unit 4: Change y to i
    {
        "word": "heaviest",
        "parts": "heavy (y→i) + est",
        "note": "When a word ends in consonant + y ('heavy'), change y to i before adding -est.",
        "unit": "B2.3 Change y to i",
    },
    {
        "word": "supplies",
        "parts": "supply (y→i) + es",
        "note": "Consonant + y ('supply') changes y to i and adds -es.",
        "unit": "B2.3 Change y to i",
    },
    # Unit 5: High-Leverage Prefixes (un-, dis-, re-, mis-)
    {
        "word": "disappear",
        "parts": "dis + appear",
        "note": "Prefix 'dis-' (meaning opposite/away) attaches cleanly to 'appear'—just one 's' in dis-.",
        "unit": "B2.3 Prefixes",
    },
    {
        "word": "unbreakable",
        "parts": "un + break + able",
        "note": "Three morphemes: 'un-' (not) + base 'break' + '-able' (can be).",
        "unit": "B2.3 Prefix + Base + Suffix",
    },
    # Unit 6: Derivational Suffixes (-tion, -less, -ness)
    {
        "word": "destruction",
        "parts": "de + struct + ion",
        "note": "Bound root 'struct' means 'build' (construct, structure); 'de-' reverses it + '-ion' makes it a noun.",
        "unit": "Gr.4 B2.1 Bound Roots",
    },
    {
        "word": "erupted",
        "parts": "e + rupt + ed",
        "note": "Root 'rupt' means 'burst/break' (erupt, interrupt, rupture); 'e-' means 'out'.",
        "unit": "Gr.4 B2.1 Bound Roots",
    },
    # Unit 7: High-Frequency Irregulars & Homophones
    {
        "word": "because",
        "parts": "be + cause",
        "note": "'because' means 'by cause of': prefix 'be-' + base word 'cause' (c-a-u-s-e).",
        "unit": "B2.3 High-Frequency Morphology",
    },
    {
        "word": "caught",
        "parts": "c + aught",
        "note": "'caught' and 'taught' share the '-aught' past-tense pattern.",
        "unit": "B2.2 Orthographic Patterns",
    },
]


def ensure_deck(rec: dict[str, Any]) -> dict[str, Any]:
    deck = rec.get("spelling_deck")
    if not isinstance(deck, dict) or "cards" not in deck:
        deck = {"cards": {}, "curriculum_index": 0}
        rec["spelling_deck"] = deck
    deck.setdefault("curriculum_index", 0)
    return deck


def ingest_misspellings(rec: dict[str, Any], misspellings: list[dict[str, str]]) -> None:
    """Adds or resets any word the child misspelled into Box 1 (due immediately)."""
    deck = ensure_deck(rec)
    cards = deck["cards"]
    now = time.time()
    for m in misspellings or []:
        wrote = (m.get("wrote") or "").strip()
        meant = (m.get("meant") or "").strip()
        if not wrote or not meant or wrote.lower() == meant.lower():
            continue
        key = meant.lower()
        if key in cards:
            cards[key]["box"] = 1
            cards[key]["next_due"] = now
            cards[key]["wrote"] = wrote
            cards[key]["lapses"] = cards[key].get("lapses", 0) + 1
        else:
            cards[key] = {
                "word": meant,
                "wrote": wrote,
                "parts": "",
                "note": "",
                "unit": "From student writing",
                "source": "error",
                "box": 1,
                "next_due": now,
                "successes": 0,
                "lapses": 1,
            }


def select_word_for_session(rec: dict[str, Any], session_misspellings: list[dict[str, str]], studied_today: set[str]) -> dict[str, Any]:
    """Picks 1 high-leverage target word: (1) today's error, (2) due Leitner card, or (3) next Ontario curriculum unit."""
    ingest_misspellings(rec, session_misspellings)
    deck = ensure_deck(rec)
    cards = deck["cards"]
    now = time.time()

    # 1. Error from today not yet studied today
    for m in session_misspellings:
        key = (m.get("meant") or "").strip().lower()
        if key and key not in studied_today and key in cards:
            c = cards[key]
            if not c.get("parts"):
                ws = thinking.analyze_word_study(c.get("wrote", ""), c["word"])
                c["parts"] = ws["parts"]
                c["note"] = ws["note"]
            return c

    # 2. Due spaced-repetition card from earlier sessions
    due = [
        c
        for k, c in cards.items()
        if k not in studied_today and c.get("box", 1) < 5 and (c.get("next_due") or 0) <= now
    ]
    if due:
        due.sort(key=lambda x: (x.get("box", 1), -(x.get("lapses", 0))))
        c = due[0]
        if not c.get("parts"):
            ws = thinking.analyze_word_study(c.get("wrote", ""), c["word"])
            c["parts"] = ws["parts"]
            c["note"] = ws["note"]
        return c

    # 3. Systematic Ontario Grade 3–4 Orthography / Morphology Progression
    for item in ONTARIO_CURRICULUM_WORDS:
        key = item["word"].lower()
        if key not in cards and key not in studied_today:
            cards[key] = {
                "word": item["word"],
                "wrote": "",
                "parts": item["parts"],
                "note": item["note"],
                "unit": item["unit"],
                "source": "curriculum",
                "box": 1,
                "next_due": now,
                "successes": 0,
                "lapses": 0,
            }
            return cards[key]

    # Fallback: lowest-box card
    fallback = ONTARIO_CURRICULUM_WORDS[0]
    return cards.get(fallback["word"], {**fallback, "wrote": "", "box": 1, "source": "curriculum"})


def record_retrieval_result(rec: dict[str, Any], word: str, correct_first_try: bool) -> dict[str, Any]:
    """Updates Leitner box & next review timestamp after memory retrieval."""
    deck = ensure_deck(rec)
    key = (word or "").strip().lower()
    now = time.time()
    c = deck["cards"].get(key)
    if not c:
        return {}
    if correct_first_try:
        c["box"] = min(5, c.get("box", 1) + 1)
        c["successes"] = c.get("successes", 0) + 1
    else:
        c["box"] = 1
        c["lapses"] = c.get("lapses", 0) + 1
    c["next_due"] = now + BOX_INTERVALS.get(c["box"], 86400)
    c["last_practiced"] = now
    return c


def deck_summary(rec: dict[str, Any]) -> dict[str, Any]:
    deck = ensure_deck(rec)
    cards = list(deck["cards"].values())
    now = time.time()
    return {
        "total_words": len(cards),
        "mastered": sum(1 for c in cards if c.get("box", 1) >= 4),
        "in_progress": sum(1 for c in cards if c.get("box", 1) < 4),
        "due_now": sum(1 for c in cards if c.get("box", 1) < 5 and (c.get("next_due") or 0) <= now),
        "cards": sorted(cards, key=lambda x: (-x.get("box", 1), x.get("word", "")))[:30],
    }
