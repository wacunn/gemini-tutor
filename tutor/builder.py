"""Builds new interactive activities on the spot from the tutor's description.

Output is one self-contained HTML document that runs in a sandboxed iframe and talks to the
tutor through a tiny injected bridge: window.tutor.send(event) / window.tutor.onMessage(fn).
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, AsyncIterator

from google import genai
from google.genai import types

from .config import BUILDER_MODEL, FALLBACK_MODEL, genai_client

BRIDGE = """<script>
(function(){
  var handlers = [];
  var last = 0, queue = [];
  window.tutor = {
    send: function(evt){
      try { parent.postMessage({__tutor: true, type: 'activity_event', data: evt}, '*'); } catch(e) {}
    },
    onMessage: function(fn){ handlers.push(fn); }
  };
  window.addEventListener('message', function(e){
    var m = e.data;
    if (m && m.__tutor && m.type === 'to_activity') handlers.forEach(function(h){ try { h(m.data); } catch(err) {} });
  });
  window.addEventListener('error', function(e){
    try { parent.postMessage({__tutor: true, type: 'activity_error', data: String(e.message || e)}, '*'); } catch(_) {}
  });
})();
</script>"""

BUILDER_SYSTEM = """You build small, polished, self-contained interactive learning activities and games for an 8-year-old child,
designed live by his tutor. ALWAYS keep every word, theme, and mechanic 100% safe and age-appropriate for an 8-year-old (zero gore, horror, adult/sexual themes, self-harm, or secrecy from parents).
You write one complete HTML document (inline CSS and JS, no external resources, no network).

Hard requirements:
- Return ONLY the HTML document. No markdown fences, no commentary.
- Keep it compact: aim for under 400 lines. Ship something that works now over something elaborate.
- It runs in a sandboxed iframe filling the area (100% width/height). Make it responsive; no scrollbars at ~900x560.
- Keyboard-first for typing activities (autofocus the input), but also works with mouse/touch.
- Large, readable text. Clean, modern, restrained visual design. Dark or neutral backgrounds are fine.
  Not babyish: no cartoon mascots, no rainbow confetti, no "Great job!!!" text. Feedback should be informational or in-world.
  No AI character presented as a friend or companion; the tutor is an AI tool, not a buddy.
- Do not use alert/confirm/prompt. Do not use localStorage (sandboxed). Do not use speech synthesis.
- Simple WebAudio sound effects are fine if subtle.
- A global object window.tutor is already defined. Call window.tutor.send({...}) for MEANINGFUL events only:
  every word or sentence he types/submits (include the target if there is one and exactly what he typed),
  choices he makes, rounds completed, score changes worth knowing, when he finishes or quits, and anything the spec asks for.
  Never send per-frame or per-keystroke events. Keep each event small (short strings).
  Send {kind:'ready', summary:'...'} once on load describing in one sentence what's on screen.
- If the spec says the tutor will send data, handle it with window.tutor.onMessage(function(data){...}).
- Must not crash: guard against undefined values. Start immediately or with a single clear start button.
- Spelling targets/word lists: use real English words spelled correctly. Accept case-insensitive answers; trim whitespace.
"""


def _client() -> genai.Client:
    return genai_client()


def _clean_html(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```(?:html)?\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    start = t.lower().find("<!doctype")
    if start == -1:
        start = t.lower().find("<html")
    if start > 0:
        t = t[start:]
    return t


def inject_bridge(html: str) -> str:
    low = html.lower()
    idx = low.find("<head>")
    if idx != -1:
        return html[: idx + 6] + BRIDGE + html[idx + 6 :]
    idx = low.find("<html")
    if idx != -1:
        end = html.find(">", idx)
        return html[: end + 1] + "<head>" + BRIDGE + "</head>" + html[end + 1 :]
    return BRIDGE + html


def _learner_context(rec: dict[str, Any]) -> str:
    m = rec.get("model", {})
    bits = [f"Child: {rec.get('name','')} (grade {rec.get('grade',3)})."]
    if m.get("interests"):
        bits.append("Interests: " + ", ".join(m["interests"]))
    if m.get("typing"):
        bits.append("Typing: " + m["typing"])
    if m.get("spelling", {}).get("stage"):
        bits.append("Spelling stage: " + m["spelling"]["stage"])
    return " ".join(bits)


async def stream_build(
    title: str,
    description: str,
    rec: dict[str, Any],
    previous_html: str | None = None,
    change_request: str | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    """Yields ("progress", chars_so_far) while building, then ("done", html)."""
    client = _client()
    if previous_html and change_request:
        user = (
            f"Here is the current activity HTML:\n\n{strip_bridge(previous_html)}\n\n"
            f"Change request from the tutor: {change_request}\n\n"
            "Return the full updated HTML document. Keep everything that works; change what was asked."
        )
    else:
        user = (
            f"Activity title: {title}\n\nTutor's spec:\n{description}\n\n"
            f"Context: {_learner_context(rec)}\n\nBuild it."
        )

    cfg = types.GenerateContentConfig(
        system_instruction=BUILDER_SYSTEM,
        temperature=0.6,
        thinking_config=types.ThinkingConfig(thinking_budget=512),
    )

    last_err: Exception | None = None
    for model in (BUILDER_MODEL, FALLBACK_MODEL):
        try:
            buf = []
            n = 0
            last_emit = 0.0
            stream = await client.aio.models.generate_content_stream(model=model, contents=user, config=cfg)
            async for chunk in stream:
                if chunk.text:
                    buf.append(chunk.text)
                    n += len(chunk.text)
                    if time.time() - last_emit > 0.5:
                        last_emit = time.time()
                        yield ("progress", n)
            html = _clean_html("".join(buf))
            if "<" not in html:
                raise RuntimeError("builder returned no HTML")
            yield ("done", inject_bridge(strip_bridge(html)))
            return
        except Exception as e:  # try the fallback model
            last_err = e
            continue
    raise RuntimeError(f"build failed: {last_err}")


def strip_bridge(html: str) -> str:
    return html.replace(BRIDGE, "")
