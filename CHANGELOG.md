# Changelog

## 0.4.0
- Added **Multi-Week Persistent Book Projects** (`tutor/projects.py`) across time scales:
  - **Full Graphic Novel / Comic Book (up to 100+ panels):** Maps causal *Beginning → Middle ('But/When') → End ('So/Finally')* Story Spine first, then zooms in chapter-by-chapter with consistent character art, speech bubbles, and auto-saves across sessions.
  - **Illustrated Monster & Invention Codex:** Multi-session expository field guide teaching paragraph structure.
  - **4-Page Persuasive Pitch Book** + **Quick 10-Minute Sprints** (3-Panel Strip, Live Mini-Game).
- Added **Publication-Quality PDF Book Exporter** (`tutor/pdf_book.py`, `/api/project/{id}/pdf`) generating cover pages, Story Spine architecture pages, chapter spreads, rendered speech bubbles, and captions at any draft or final stage.
- Added **14-Expectation Ontario Grade 3–4 Language Curriculum Report Card & Mastery Escalator (Tiers 1–5)** (`tutor/curriculum_tracker.py`, Parent page) tracking longitudinal mastery across Strands B3, B2, and D and escalating tutor expectations automatically as skills solidify.

## 0.3.2
- Deterministic immediate panel/scene rendering as soon as each complete punctuated sentence is verified, WebSocket auto-reconnect, and one-click **Clear test sessions**.

## 0.3.1
- Generalized learner setup context and added editable profile fields on the Parent page, Windows PowerShell installer (`install.ps1`), and automatic update banner.
