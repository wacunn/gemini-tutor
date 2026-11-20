# Changelog

## 0.3.1
- Generalized learner context across `SessionController` so fresh installs dynamically read the child's name, grade, parent title, and notes from the first-run setup card with zero hardcoded assumptions.
- Added editable child name, grade, and parent title fields to Parent Page → Settings.
- Added Windows PC PowerShell installer (`install.ps1`), cross-platform supervisor (`launch.py`), and automatic update banner on the Parent page.

## 0.3.0
- Added synchronous `SessionController` (`tutor/controller.py`) enforcing Ontario Grade 3–4 sentence structure (B3.1 simple, compound, complex adverbial clauses), conventions (B3.3), and Cover-Copy-Compare morphological/orthographic spelling (B2.1–B2.3).
- Added hard Python tool gates blocking 1-word escape rewards, babyish filler prompts, conversational `wh-` traps, and verbatim sentence dictation.
- Added in-place draft prefill for low-friction editing and auto-covering word study cards.
- Upgraded child modeling, critic, and inventor to `gemini-4-hydrogen` and post-session specialist review to `gemini-4-carbon`.
