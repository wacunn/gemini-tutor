# Changelog

## 1.7.1
- **360° Chromebook / Googlebook USI 2.0 Pen Telemetry & Native Host-Chrome Bridge (`launch.py`, `static/app.js`, `tutor/live.py`):**
  - Prioritized ChromeOS's native `garcon-url-handler` bridge before `xdg-open` in `launch.py` so `http://localhost:8787` always opens in host ChromeOS Chrome rather than Crostini XWayland, preserving raw USI 2.0 stylus `PointerEvent` hardware telemetry.
  - Upgraded `#penCanvas` with 120–240Hz `e.getCoalescedEvents()` sub-frame stroke sampling, per-segment variable pressure, USI barrel/tail eraser detection (`button === 5` / `buttons & 32`), 360°-tablet palm rejection once a stylus is detected (`pointerType === "pen"`), and full `pen_telemetry` logging (stroke count, active ink ms, total span, pressure, tilt, and rejected palm touches).

## 1.7.0
- **Local Video Game Rewards — Fists of Doom & Chromebook Minecraft (`tutor/arcade.py`, `server.py`, `tutor/live.py`, `static/index.html`, `static/app.js`, `static/parent.html`):**
  - **Strict Local Install Detection**: Activated **if and only if** `Fists of Doom` (`~/FistsOfDoom`) and/or `Minecraft` (`org.prismlauncher.PrismLauncher` user Flatpak) is installed locally on the same computer; completely invisible otherwise.
  - **Quality-Gated Active Writing Clock (`SessionArcadeTracker`)**: Never counts idle open-tab time, single-word escapes, or pushback. Bounds each active turn (`<= 75s`) and buffers drafting/revision/spelling effort until a Homework-Standard complete sentence (starting capital, end punctuation, complete clause, clean spelling/grammar) or Cover-Copy-Compare word retrieval is verified.
  - **Cross-Session Point Milestones & Parent Conversion Controls**: Persists earned active writing time across sessions in `learner.json` (`15 min solid writing = 1 Point` by default, `2 Points = 30 min → 15 min of game time`), with full parent customization, bonus/reset controls, and play history on `/parent`.
  - **Embedded Fists of Doom Arcade & Chromebook Minecraft Setup (`setup_minecraft_chromebook.sh`, `bin/prism-gated-launch.sh`, `MINECRAFT_SETUP.md`)**: Launches Fists of Doom directly inside Gemini Tutor with a live countdown and auto-close at `0:00`, and includes an automatic Crostini Chromebook installer (`flatpak --user`, `QT_QPA_PLATFORM=xcb`, ChromeOS shelf `.desktop` gating, 1-minute save warning, and `flatpak kill` enforcement).

## 1.6.0
- **Causal Story-Arc Friction Engine in Oral Story Construction (`tutor/controller.py`, `tutor/projects.py`, `tutor/live.py`, `static/app.js`, `static/style.css`):**
  - **Conservation of Learning Friction**: When transcription/spelling load drops to zero during upfront oral story building (`ORAL_STORY_INTAKE`), cognitive friction shifts explicitly to **causal storytelling & critical thinking** (*Trabasso & van den Broek* causal networks + *Stein & Glenn* story grammar + the *"Because / Therefore / But"* rule).
  - **Diagnostic Story-Editor Pushback (Zero Rubber-Stamping, Zero Sycophancy)**: Deterministically and via LLM rejects non-causal associative chains (*"the cat pooped, the cat farted, the cat jumped on a rocket"*), teleported props/settings (`causal_jump`), stakes-free gags (`missing_motive_or_goal`), frictionless wish-fulfillment (`missing_obstacle`), and random wipeout endings (`deus_ex_machina_ending`) into a `pending_repair` holding buffer instead of `scenes`—pushing back in a dry, respectful Story Editor voice with zero moralizing on gross humor and zero *"That is GOLD! / Wow! Yes!"* hype.
  - **4-Pillar Story Logic Gate + Graduated 3-Rung ADHD Scaffold**: Tracks **1. Who + Problem**, **2. Why It Gets Worse**, **3. Big Obstacle**, and **4. Earned Ending** on a visual **Story Logic Check Bar** (using strictly sanitized `<= 2-word` noun tags + `⚠ Missing cause-and-effect link` indicator that vanishes completely as soon as Panel 1 starts so zero copyable sentences ever appear during writing). Blocks premature `"Start writing Panel 1"` escapes until the arc connects, narrows to an A-to-B bridge prompt on Attempt 2, and scopes down cleanly at Attempt 3 / Turn 6 so oral mode never loops or stalls.
  - **Oral-to-Written Causal Bridge Carry-Over & Anti-Sycophancy Purge (`tutor/controller.py`, `tutor/prompt.py`, `tutor/blackboard.py`, `tutor/observers.py`)**: Carries oral cause-and-effect links into panel writing prompts and enforces a single-pass causal connector expansion (`because` / `so` / `but`) when a panel jumps ahead without showing cause and effect; removed sycophantic hype across all live/reflex prompts and updated session auditors.

## 1.5.0
- **Bounded Latent Oral Plot Intake → Full Writing Tutoring (`tutor/projects.py`, `tutor/controller.py`, `tutor/live.py`, `static/app.js`, `static/index.html`, `static/style.css`, `tutor/pdf_book.py`):**
  - Replaced open-ended Verbal Story Jam with a bounded upfront **Oral Plot Intake** (`<= 4` turns, zero panels drawn, zero reward chimes while talking, zero mid-book `"Talk Out More Story"` escape buttons, and **zero AI-written sentences displayed on the student's screen**).
  - Extracts the student's plot, characters, world rules, causal arc, and ending into a **private tutor-only `latent_plan`**, then permanently locks into **full rigorous panel-by-panel writing tutoring** (enforcing complete sentences, capitals, periods, spelling, grammar, and Mastery Tiers while using `latent_plan` to ask sharp Socratic/causal questions across up to 100 panels).
- **Pure Written How-To Guides — Zero Cartoons (`tutor/projects.py`, `tutor/controller.py`, `tutor/live.py`, `static/app.js`, `static/style.css`, `tutor/pdf_book.py`, `server.py`):**
  - Converted **How-to guide** (`how_to_tutorial`) into a pure written procedural document—never generates cartoons/comic panels, never pauses for picture checks, renders a crisp numbered **How-To Guide** document page on the right, and exports a clean typography-only PDF and Web View.
- **Fixed Post-Speech `"No speech!"` Audio/Caption Bug (`tutor/live.py`, `tutor/prompt.py`, `static/app.js`):**
  - Removed controller-owned UI tools (`ask_input`, `show_choices`, `show_card`, `show_word`, `turn_on_mic`, `draw`, `comic_new`, `comic_panel`) from Live audio tool declarations and removed `"End your turn silently"` `FunctionResponse` strings so the Live audio model never triggers a post-speech turn vocalizing `"No speech!"`; hardened `upsertTutor`, `tutor_clear`, and `showCenterMic` wait-until-silent gating.

## 1.4.1
- **100% Student-Led How-To Guide Topics & Steps (`tutor/controller.py`, `tutor/projects.py`, `static/index.html`, `static/app.js`):**
  - Removed pre-suggested tutorial topics and step assumptions from **How-to guide** (`how_to_tutorial`)—asks openly what his guide is about, keeps his exact title, and asks openly for Step 1, Step 2, Step 3… without suggesting what the steps should be.

## 1.4.0
- **Three New Studio Modes: 100-Page Verbal Story Jam, Illustrated How-To Tutorials, & Minecraft Today Diary (`tutor/projects.py`, `tutor/controller.py`, `tutor/live.py`, `tutor/pdf_book.py`, `static/index.html`, `static/app.js`, `static/style.css`):**
  - **100-Page Story Jam (`Talk First → Write Panels`)**: New option in the Start Screen & Sidebar (plus a **`🎙️ Story Jam`** button inside any Graphic Novel). Opens back-and-forth verbal brainstorming via the Center Green Mic—asking *"what happens next?"* and challenging/probing story details with zero spelling interruptions—while building a live **Story Jam Outline** on the right. Tapping **`✍️ Ready — Start Writing Panel 1!`** switches to panel-by-panel comic writing guided beat-by-beat from his spoken outline.
  - **Illustrated How-To Tutorial (*e.g. How to Play Minecraft*)**: Step-by-step procedural guide builder (defaulting to **Blocky Voxel World** art for Minecraft) where the tutor acts like a beginner following his instructions (`STEP 1`, `STEP 2`, `STEP 3`…), illustrating every step with speech/tip bubbles and exporting an **Official Illustrated How-To Guide PDF**.
  - **What I Did in Minecraft Today (*Illustrated Diary*)**: Ongoing dated illustrated adventure log (`Minecraft Log · Nov 21`) turning what he built, mined, or survived in Minecraft today into comic/journal panels and a printable **Illustrated Minecraft Diary PDF**.

## 1.3.1
- **Clean, Neutral Parent Page & Prompt Copy (`static/parent.html`, `tutor/guardian.py`, `tutor/prompt.py`, `tutor/blackboard.py`, `tutor/controller.py`, `tutor/media.py`, `tutor/doodle_fallback.py`, `tutor/builder.py`, `tutor/research_packs.py`):**
  - Replaced Editorial/filter-tuning blurbs on `/parent` and in system prompts with clean, neutral copy (*"Summarizes session topics and pauses only for genuine child-safety concerns"*), keeping the background distinction between thoughtful/philosophical curiosity and actual child-safety danger completely understated.

## 1.3.0
- **Authentic Comic Panels, Draggable Speech/Shout/Thought Bubbles & Editable Yellow Captions Everywhere (`static/app.js`, `static/style.css`, `tutor/projects.py`, `tutor/controller.py`, `tutor/live.py`, `tutor/pdf_book.py`, `server.py`, `tutor/prompt.py`):**
  - **Every Beat Renders as a Real Comic Panel Immediately**: Upgraded Graphic Novel Plot Board beats (**Cover/Kickoff**, **Middle Twists**, **Big Finale**), Chapter Panels, Quick 3-Panel Strips, and Standalone Drawings into ink-framed comic panels with classic yellow narrator caption boxes and real comic speech balloons (pointed tails for **Speech**, spiky yellow bursts for **SHOUT!**, and cloud circles for **Thought** bubbles).
  - **1-Click `💬 + Speech Bubble` & `✎ Caption` Right Under Every Panel (+ Drag Bubbles Anywhere)**:
    - Add, edit, or delete speech/shout/thought bubbles (with optional speaker name and **`🎤` voice dictation**) or edit/hide the yellow narrator caption box (so panels can be dialogue-only, caption-only, or both).
    - **Drag any speech bubble directly on the artwork** to place it away from characters' faces—saved automatically and rendered at the exact same `(x, y)` spot in both **Web view** and the **Downloadable PDF**.
  - **Homework-Consistent Comic Lettering Check (Zero "Fragment" Rejections on Dialogue)**: Short comic exclamations (`"Gross!"`, `"Get off me!"`, `"KABOOM!"`) are accepted naturally as real comic dialogue while still gently checking starting capitals, end marks (`! . ?`), and spelling (with 1-tap multiple-choice + *"Why it works"* chips right inside the panel's bubble tray).
  - **Smart Quote Splitting & Natural Chat Commands**: Writing `"Get off me!" yelled Dylan.` automatically puts `"Get off me!"` into a speech bubble without repeating the quote in the bottom caption box; saying *"it isn't a comic"*, *"add dialogue"*, or *`make Dylan say "..."`* opens or adds comic lettering instead of triggering a textless image redraw; and downloading the PDF even during Plot Board stages renders real 2-panel-per-page comic spreads.

## 1.2.1
- **Proportional Child-Safety Watcher Calibration (`tutor/guardian.py`, `tutor/prompt.py`, `tutor/blackboard.py`, `tutor/thinking.py`, `tutor/media.py`):**
  - Calibrated the Watching Agent and prompts to distinguish big philosophical/scientific questions, dramatic comic fiction, and casual off-color humor (logged quietly for parent context without scolding or interrupting) from genuine child-safety risks (first-person self-harm, abuse or secrecy from parents, explicit sexual content, actionable real-world harm, or AI boundary violations).

## 1.2.0
- **Child-Safety Watching Agent, Conversation Topics Report & Protective “App Bug” Pause (`tutor/guardian.py`, `tutor/live.py`, `server.py`, `static/parent.html`, `static/index.html`, `static/app.js`):**
  - Added an independent **Child-Safety & Topic Watching Agent** (`tutor/guardian.py`) tailored for an 8-year-old child that inspects both the child's inputs and the AI's responses on every turn (plus a `0ms` synchronous pre-screen before any LLM/image call).
  - **Conversation Topics on `/parent`**: Logs scannable topic tags, a 1-sentence summary of what he wrote/talked about, and sample lines for every session—distinguishing normal 8-year-old potty/cartoon humor (`ok`) from mild emotional/social concerns (`watch` notes logged quietly for parents).
  - **Protective “App Bug” Stop (`ERR-G42`)**: Whenever a conversation makes the Watching Agent nervous for an 8-year-old (self-harm, abuse/secrecy from parents, sexual/adult content, severe real-world danger, or AI boundary drift), the app calmly freezes on a zero-shame *"Oops — Gemini hit a little saving bug (`ERR-G42`). Grab Dad or Mom to reset it on the Parent page"* screen (persisting across refreshes) and surfaces the exact quote & reason at the top of `/parent` with a 1-click **Clear Bug Screen & Resume Tutor** button.
  - Added explicit **8-Year-Old Child Awareness** anchors across every agent prompt (`prompt.py`, `blackboard.py`, `controller.py`, `media.py`, `doodle_fallback.py`, `builder.py`).

## 1.1.1
- **Fix Every Real Error Gently Unless Frustrated (`tutor/controller.py`, `tutor/coach.py`, `tutor/thinking.py`, `tutor/blackboard.py`):**
  - Re-verifies the full sentence after every spelling/word pick instead of accepting early after one fix—so `"Dylan get stinke cat."` → `"stinky"` now immediately catches `"get"` (`gets` / `got` with a *"Why it works"* card and tappable choices) and missing articles (`"a stinky cat"`) until the sentence is clean Grade 3 English.
  - Added deterministic 3rd-person singular bare-verb detection (`"Dylan get"`, `"Bob barf"`, `"He run"`) alongside expanded LLM grammar diagnostics, only easing off early if genuine frustration signals appear.

## 1.1.0
- **Tutor-Controlled Center Green Microphone (`static/index.html`, `static/style.css`, `static/app.js`, `tutor/media.py`, `tutor/controller.py`, `tutor/live.py`, `tutor/prompt.py`):**
  - Hid the manual corner mic button so the tutor controls when the microphone turns on and off.
  - When a misspelling is phonetic or unclear (e.g. `"uoos"`, `"wurs"`), when fixing a picture (**↻ Not quite — fix picture**), or when stuck, the tutor asks *"Maybe say out loud what word `'uoos'` is supposed to be?"* and pops up a large, pulsing **green microphone right in the center of the screen** (`● Mic is ON — speak now!`, waiting until the tutor finishes speaking so it never records itself).
  - Automatically detects end-of-speech (~1s after a word, ~1.4s after a sentence), turns the green mic OFF and hides it immediately, transcribes the clip in context via `transcribe_voice_clip` (resolving homophones like `whose` vs `who's` from his sentence), and displays the exact spelling breakdown (`wh + ose`) to lock into his sentence.

## 1.0.3
- **Warm Story Reactions + Direct Grammar Terms (`tutor/blackboard.py`, `tutor/controller.py`, `tutor/prompt.py`, `tutor/coach.py`, `tutor/live.py`):**
  - Restored playful, warm reactions to his story ("Oh no, poor guy!", "That's a super stinky situation!") while keeping writing-rule instructions strictly plain and direct ("Capitalize the first letter", "Add a period at the end"—never "big and tall like a superhero" or "little dot").

## 1.0.2
- **Plain, Matter-of-Fact Voice — Zero "Blippi" / Preschool Metaphors (`tutor/prompt.py`, `tutor/blackboard.py`, `tutor/coach.py`, `tutor/controller.py`, `tutor/live.py`):**
  - Eliminated kids'-TV cheerleading and cringe metaphors ("put a little dot", "big and tall like a superhero", "super stinky situation!"). Routine mechanics now speak plain, direct sentences ("Add a period at the end.", "Capitalize the first letter.").
- **Explicit Structural Plot Board Prompts & Zero Plot-Suggesting (`tutor/controller.py`, `tutor/blackboard.py`):**
  - Removed unsolicited plot-suggesting starter chips ("Dylan drinks a potion…") and either/or leading plot questions. Every Plot Board step now explicitly names the structural slot (**Step 1 — The Beginning**, **Step 2 — The Ending at the very end of the whole book**, **Step 3 — Middle Event #1 right after the beginning**) so the child never confuses "what happens next" with the book's Finale, and book titles only use concepts from the child's own sentence.
- **Wrong-Slot / Undo Recovery & 1-Word Fix Recovery (`tutor/projects.py`, `tutor/controller.py`, `static/app.js`):**
  - Saying *"that wasn't the end, you asked what happened next"* automatically moves that sentence into **Middle Event #1** and reopens **The Ending** instead of treating the complaint as a picture redraw; added **`↶ Undo / change this sentence`** directly on the picture-check card.
  - Missing-capital prompts now highlight only the first character (`select_range: [0, 1]`), and typing just the capitalized first word (`"He"`) or punctuation (`"."`) splices cleanly into the pending sentence instead of triggering disengagement prompts.

## 1.0.1
- **Homework Standard — Capitals, End Punctuation & Zero Skipped Spelling (`tutor/controller.py`, `tutor/live.py`):**
  - Every sentence now requires a starting capital letter and ending `.`, `!`, or `?` before unlocking artwork (fast ~1.5s turn with the sentence pre-filled in the box and cursor placed right at the fix).
  - Never silently skips a spelling error: whenever the coach would otherwise skip a misspelling for momentum (or when multiple misspellings appear in one sentence), it now presents a **1-tap Multiple-Choice Spelling Check** WITH a plain-English **"Why it works"** rule card (e.g. `fac + e`, `fly + ing`, `who + se`), splices the chosen word into the sentence on tap, and verifies capital + period before drawing.

## 1.0.0
- **Fast Small-Model Talker + Shared Working-Memory Blackboard (`tutor/blackboard.py`, `tutor/config.py`, `tutor/controller.py`, `tutor/live.py`):**
  - Replaced serial multi-LLM per-turn calls with a single `<1s` `gemini-3.1-flash-lite` reflex call (`3.2s` hard cap + `0ms` local fallback) reading a Shared Working-Memory Blackboard updated asynchronously by background specialists.
  - Set `HttpRetryOptions(attempts=1)` to eliminate `google-genai`'s hidden 5-attempt × 60s retry sleep on Free-Tier `429` limits, paused background observers automatically under rate limits, and added a Live speech watchdog so turns never hang.
- **Guaranteed Artwork on Both Paid & Free-Tier API Keys (`tutor/media.py`, `tutor/doodle_fallback.py`):**
  - Automatically falls back to a custom *Diary of a Wimpy Kid*-style lined-notebook ink cartoon renderer when Free-Tier keys return `429`/`403` on paid image endpoints so panels never fail blank.
- **Picture Approval Gate, Chronological Scene Isolation & Director Corrections (`tutor/projects.py`, `tutor/controller.py`, `tutor/live.py`, `static/app.js`):**
  - Pauses after each Cover, Finale, Twist, and Panel drawing to ask *"Did I draw your scene right, or did I miss something?"* (**Looks right — next part!** / **Not quite — fix picture**) BEFORE prompting the next story beat, taking friendly blame and redrawing with added details when needed.
  - Isolated reference images and scene context strictly chronologically so future Finale settings (e.g. *"on the moon"*) never bleed into earlier Earth scenes, added a Director Meta-Correction detector so complaints like *"why are you having the spaceship stuck on the moon and not earth?"* trigger a redraw instead of becoming a story twist, and added **↻ Fix art** / **✕ Remove** buttons on every beat and panel.
- **Sacred Composer Input, Spelling Retry Escalation, One-Shot Word Mic & Web View Back Button (`static/app.js`, `server.py`, `tutor/controller.py`, `tutor/thinking.py`):**
  - Never overwrites text the child is actively typing (`turnEpoch` staleness cancellation + safe restore chip).
  - Escalates failed spelling retries (`"fase"` → `"fasse"`, `"fkying"`, `"uoos"` → `"whose"`) directly to the full Word Card (`f + ace`) with a **🎤 Say the word out loud so I can help** one-shot mic button, strips all `"no speech detected"` variants, blocks unprompted mid-story `save_piece` goodbyes, and adds a sticky **← Back to Studio** bar on Web view pages.

## 0.9.2
- **The coach decides "can we just draw it" from context (`tutor/coach.py`, `tutor/controller.py`):**
  - If he has a real sentence waiting on a fix, the coach can choose to draw it as-is right away (the issue is just logged), offer a quick deal ("add the period and it draws instantly", with his sentence back in the box and no further asks), or pick another move.
  - It's told about escape learning: if pushing back always skips the fix, he learns that pushing back gets him out of writing. So it tracks how often it has already given in this session and leans toward the quick deal when it's becoming a pattern.
  - With nothing pending, it doesn't hand out free art; it gives a twist or starters instead.

## 0.9.1
- **The coach now handles "idk", "this is boring", one-word answers, and "can we just draw it" (`tutor/coach.py`, `tutor/controller.py`):**
  - Instead of fixed scripted replies, the coach looks at how he's doing and what it already tried this session, then picks a move: sentence starters, a half-finished sentence from his story, a surprise twist, "say it with the mic," switching to a mini-game or new comic, or stopping for today on a win. It changes tactics if a move doesn't work and never nags. The old rules remain only as a fallback.
  - New buttons: **Surprise me with a twist**, **Talk it out with the mic**, **Pause for today**.
  - Starter chips are always short openers ending in "…", never whole sentences to copy.
- **No separate editing pass:** issues the coach chooses not to raise are just logged for the parent; the existing **Download PDF** button is the book.

## 0.9.0
- **Adaptive AI Coach replaces the hard-coded correction rules (`tutor/coach.py`, `tutor/controller.py`):**
  - Each writing turn, an AI coach reads the writing check, how he is behaving right now (speed, backspaces, pushback, whether he followed the last ask, starter-chip use, minutes in), and a saved learner model (unprompted skill evidence, hypotheses being tested on him, what works, recent days' energy). It then decides: draw it now, or ask for ONE change, and how much help to give.
  - Help levels: a story question, tappable sentence starters (e.g. "Bob barfed because…") that fade as he uses linking words on his own, a partial frame, or an example.
  - 5-step spelling ladder: find it yourself → "I spot 2 words" → highlighted word → "which of these is it?" then type it → word-part card. Words he finds himself are tracked separately.
  - Guardrails in code only: at most 2 asks in a row before drawing, spelling help always names the exact word on the pointing steps, no school vocabulary in anything he sees or hears, every ask checked against the actual writing check, and a fallback to the old rules if the coach is unavailable.
- **Faster turns using smaller models where they're good enough (`tutor/config.py`):**
  - Clean sentences skip the coach entirely and draw instantly; the coach learns from them in the background.
  - The next story question + starters now use `gemini-3.1-flash-lite` (about 40% faster, same quality in tests). The coach and writing check stay on `gemini-3.5-flash` (the small model was less accurate and less consistent in simulations).
- **Kid-facing language cleanup:** removed "Tier", "complete sentence", "connector", and "Act I/II/III" from prompts, the goal pill, and the voice tutor's instructions.
- **Parent page:** new "How the coach is adapting to him" panel (unprompted skill rates, today's energy, hypotheses with evidence for/against, what works, things it chose to let go), a full coach decision log with reasons, and a "Ready to start cursive" setting.

## 0.8.1
- **Defaulted Art Style to Notebook Ink Doodle (`tutor/media.py`, `tutor/projects.py`, `tutor/live.py`, `static/app.js`):**
  - Made **Notebook Ink Doodle** (*Diary of a Wimpy Kid* black-pen doodle on blue-lined school notebook paper) the #1 default style across all books, comic strips, and sentence drawings.

## 0.8.0
- **Verb Endings & Subject-Verb Agreement Check (`tutor/thinking.py`, `tutor/controller.py`, `tutor/curriculum_tracker.py`):**
  - Catches missing `-s` / `-es` / `-ed` verb endings, subject-verb agreement slips, irregular past forms, and missing required articles (Ontario `B3.2`, e.g. `"Because the cat is smelly, Bob barf."` → highlights `"barf"` in the pre-filled sentence and asks to change it to `"barfs"` or `"barfed"` instead of letting the tutor silently fix it).
- **Pre-Filled Sentence + Highlighted Word on Spelling & Grammar Help (`tutor/controller.py`, `static/app.js`):**
  - Keeps the child's full sentence in the prompt box with the exact target word (`smeleey`, `barf`) highlighted so they can edit just that word in place without retyping their sentence; removed duplicate in-chat instruction box and fixed `<no speech>` tags across split streaming chunks.
- **Primary-Lined Handwriting Pad (`Sky / Fence / Grass / Worm`) + Single-Letter Touch-Up (`static/index.html`, `static/style.css`, `static/app.js`, `tutor/media.py`, `tutor/controller.py`):**
  - Added authentic 4-line handwriting guides (**Sky line**, dashed **Fence line**, **Grass line**, **Worm line**) plus **Pen / Erase** buttons. When a handwritten letter looks ambiguous or sits on the wrong line, Gemini acts playfully confused about **just that one letter** and re-opens the pad with the child's writing intact and a soft circle over that single letter so they only erase and fix one letter.
- **Richer Graphic Novel Plotting (`Beginning → Big Finale → As Many Middle Twists As You Want`) (`tutor/projects.py`, `tutor/controller.py`, `tutor/pdf_book.py`, `static/app.js`):**
  - Graphic novels now lock the **Kickoff**, jump to the **Big Finale**, and then iteratively ask **"What else happens in the middle?"** across Twist #1, Twist #2, Twist #3+ (each unlocking its own art and mapping to chapters) until the child is ready to draw Chapter 1 panels.
- **6 Kid-Cool Comic Art Styles with Visual Examples (`tutor/media.py`, `static/style_samples/`, `static/app.js`):**
  - Replaced generic wholesome picture-book art with 6 distinct comic styles (**Zany Marker Comic** [*Dog Man* vibe], **Notebook Ink Doodle** [*Diary of a Wimpy Kid* vibe], **Action Manga Ink**, **Epic Metal Zine**, **Blocky Voxel World**, and **Indie Adventure Comic**), complete with visual example thumbnails in the Book Studio.
- **Plain-English README & Repo Copy (`README.md`):**
  - Removed tech jargon (`"local-first"`, `"multi-scale"`, etc.) in favor of clear, plain English.

## 0.7.1
- **Restored Clean, Uncluttered Gemini App UX (`static/index.html`, `static/style.css`, `static/app.js`, `tutor/controller.py`):**
  - Replaced hero box grids, top-bar buttons, and in-stream instruction boxes with a **Gemini-style slide-out left sidebar (`☰`)** for creating/switching books, strips, games, and toggling Parent Sandbox, leaving the center start screen (`Hi …` + minimal borderless suggestion pills) and chat stream calm and clutter-free.

## 0.7.0
- **Fixed Fresh-Install / `.app` LLM Connection Error (`tutor/config.py`, `tutor/live.py`, `requirements.txt`):**
  - `google-genai` 3.x (installed on fresh `uv` setups via `install.sh` / `install.ps1`) changed `aio.live.connect()`'s default endpoint away from `v1alpha`, causing `HTTP 404` WebSocket rejections (`Reconnecting…`). Added `genai_client(live=True)` forcing `http_options={"api_version": "v1alpha"}` plus native OS Keychain / `truststore` + `certifi` SSL setup, Live model fallbacks, and a one-click **Test Gemini connection** check on `/parent`.
- **Live AI Story & Inquiry Director — Zero Static Worksheet Scripts (`tutor/controller.py`, `tutor/prompt.py`):**
  - Replaced static Spine, Panel, and Persuasive Pitch templates with `ai_direct_next_beat()`, which reads the child's exact characters/plot, reminds them of what they already wrote (zero working-memory tax), and asks curious, story-specific `where / why / how` questions paired with complete-sentence goals.
- **Immediate Visual Rewards & Progress Unlocks Starting on Sentence 1 (`tutor/controller.py`, `tutor/live.py`, `tutor/pdf_book.py`, `static/app.js`):**
  - Every Graphic Novel Story Spine beat now immediately unlocks live artwork on the Book Canvas and in the PDF (**Act I unlocks Cover & Beginning Art**, **Act II unlocks Twist Art**, **Act III unlocks Climax Art**), Codex Step 0 unlocks a **Specimen Blueprint Sketch**, and every beat triggers a progress bar step + subtle WebAudio unlock chime.
- **Filtered `<no speech detected>` Mic Noise (`tutor/live.py`):**
  - Stripped `<no speech detected>` and silence/noise ASR tags from `input_transcription` so room silence never renders phantom bubbles.

## 0.6.0
- **Multi-Book Library & Switcher Across All Studios (`tutor/projects.py`, `tutor/record.py`, `static/app.js`):**
  - Save multiple separate Graphic Novels, 3-Source Fact Codices, 4-Page Persuasive Pitches, Quick 3-Panel Strips, and Live Mini-Games simultaneously—switch between books or start a brand-new one anytime via the **Books / New** shelf or **Save & Switch / New** header button without overwriting earlier work, plus one-click **Rename** and **Delete**.
  - Lazy project persistence prevents empty 0-word `"Untitled"` files from cluttering the shelf if a user browses options before writing.
- **Parent Try-It Sandbox Mode (`/?sandbox=1`):**
  - One-click **Parent Try-It** mode on both the Start Screen and Parent Page lets parents test Graphic Novels, Codices, Pitches, Strips, Mini-Games, and PDF downloads in an isolated ephemeral sandbox with **zero writes** to the child's books, report card, spelling deck, session logs, or learner model.
- **2-Stage Specific Inline Spelling Help (`tutor/controller.py`):**
  - **Attempt 1:** Never says vague `"fix spelling"`—always names the **exact misspelled word** (with phrase context for short words like `"at" in "bought at new"` and an age-appropriate morphological/orthographic clue at early tiers) while keeping the draft pre-filled in the box.
  - **Attempt 2 ("Start All the Help"):** If the word isn't fixed on retry, immediately launches full spelling support on screen—displaying the **Morpheme / Chunk Word Card** (`trap + p + ed`, Cover-Copy-Compare) plus a **Sentence Context Card** highlighting `[meant]`. Typing/writing just the target word from memory automatically splices the corrected spelling into the student's sentence and locks/renders their panel or story beat.

## 0.5.0
- **Full Grade 3–4 Language Replacement Engine (Strands B, C, and D):**
  - **Enforced Multi-Genre Studios (`tutor/controller.py`, `tutor/research_packs.py`):**
    - **Narrative Graphic Novel (`epic_graphic_novel`):** Enforces causal connectors on Story Spine Act II (*But / When / Because*) and Act III (*So / Therefore / Finally*), enforces Mastery Tier 2–4 upgrades (*Power-Up Pass* for causal clauses, direct speech bubbles, and vivid-verb revision), and verifies Ontario `B3.3` dialogue quotation marks, capitals, and inside-quote punctuation.
    - **3-Source Reading-to-Write Research Codex (`epic_codex`):** Covers Ontario Strand C Comprehension (`C1–C3`) + `D1.3` Multi-Source Research + `D2.1` Expository Writing. Presents 3 factual mini-sources (or generates a custom 3-source dossier on any student-chosen topic via `gemini-4-hydrogen`), checks causal inference, scaffolds a 3-sentence Topic → Mechanism → Impact paragraph, and renders wide 2-entry-per-page Encyclopedia PDF spreads (`tutor/pdf_book.py`).
    - **4-Page Persuasive Pitch Book (`medium_pitch`):** Implements SRSD `POW+TREE` (*Topic/Claim → Reason with `because/since` → Counter-Argument with `although/even though` → Final Deal*) exported as an illustrated PDF Case File.
  - **Leitner Spaced Spelling & Systematic Ontario Morphology (`tutor/spelling_srs.py`):** 5-box Leitner spaced-retrieval deck (`18h → 3d → 7d → 14d → 30d`) persisted in `learner.json` + 8-unit systematic Ontario Continuum progression (`1-1-1` doubling, drop silent-`e`, `-tch/-dge`, `y→i`, prefixes, bound roots) guaranteed in every session even when the child avoids hard words during drafting.
  - **Voice-to-Draft Dictation & Edit (`ORAL_DRAFT`):** Externalizes spoken drafts into the editable composer (`prefill`) for low-energy ADHD days while gating rendering until the student checks capitals, connectors, and punctuation (MacArthur speech-to-text + post-dictation editing).
  - **18-Expectation Longitudinal Ontario Report Card:** Expanded `tutor/curriculum_tracker.py` and `/parent` to track all 18 expectations across Strands B2, B3, C1–C3, and D1–D3 alongside the live Spaced Spelling Deck.

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
