# Changelog

## 0.3.0
- Added synchronous `SessionController` (`tutor/controller.py`) enforcing Ontario Grade 3–4 sentence structure (B3.1 simple, compound, complex adverbial clauses), conventions (B3.3), and Cover-Copy-Compare morphological/orthographic spelling (B2.1–B2.3).
- Added hard Python tool gates blocking 1-word escape rewards, babyish filler prompts, conversational `wh-` traps, and verbatim sentence dictation.
- Added in-place draft prefill for low-friction editing and auto-covering word study cards.
- Upgraded writing checker and per-turn auditor to `gemini-3.5-flash` and isolated `?test=1` evaluation runs from `data/learner.json`.

## 0.2.0
- Added one-line Mac & Chromebook installer (`install.sh`), launcher (`start.sh`), and one-click in-app Software Update on the Parent page.
