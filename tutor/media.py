"""Pictures and handwriting.

- draw(): one picture, drawn ONLY from the child's words plus a style. That is deliberate:
  vague writing makes a vague picture, specific writing makes a specific one. The picture
  improving IS the feedback on the writing.
- comic panels keep characters consistent by passing earlier panels as reference images.
- read_handwriting(): reads exactly what he wrote (no auto-correct), so spelling stays visible.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from .config import DATA, FALLBACK_MODEL, genai_client
from .record import new_id

MEDIA = DATA / "media"
IMAGE_MODEL = "gemini-3.1-flash-image"
IMAGE_FALLBACK = "nano-banana-pro-preview"
VISION_MODEL = FALLBACK_MODEL  # gemini-3.5-flash


def _client() -> genai.Client:
    return genai_client()


def media_path(mid: str) -> Path:
    MEDIA.mkdir(parents=True, exist_ok=True)
    return MEDIA / f"{re.sub(r'[^a-zA-Z0-9_]', '', mid)}.jpg"


def _to_jpeg(data: bytes, max_side: int = 1280, quality: int = 85) -> bytes:
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(data)).convert("RGB")
        im.thumbnail((max_side, max_side))
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=quality)
        return out.getvalue()
    except Exception:
        return data


def small_jpeg(data: bytes) -> bytes:
    return _to_jpeg(data, max_side=512, quality=70)


def generate_image(
    scene: str,
    style: str = "",
    aspect: str = "4:3",
    references: list[bytes] | None = None,
    continuity: str = "",
) -> tuple[str, bytes]:
    """Returns (media_id, jpeg_bytes)."""
    client = _client()
    parts: list[Any] = []
    for ref in (references or [])[-2:]:
        parts.append(types.Part.from_bytes(data=ref, mime_type="image/jpeg"))
    instr = (
        "Draw ONE single illustration showing ONE moment. It is a single comic panel: do NOT divide the image into multiple "
        "panels, frames, or a strip, and do not draw panel borders.\n"
        "Draw ONLY what the description explicitly names. Do not add characters, objects, actions, effects, or setting details "
        "that are not in the description. If the description is vague or incomplete, the picture must be correspondingly "
        "sparse: e.g. if it names only a place, draw the empty place; if it names only a character, draw that character "
        "standing still on a plain background, doing nothing.\n"
        "Absolutely no words, letters, numbers, sound effects, captions, signs, or speech bubbles anywhere in the image.\n"
        "Age-appropriate for a 9-year-old.\n"
    )
    if style:
        instr += f"Style: {style}\n"
    if continuity:
        instr += f"Keep these consistent with the reference panels: {continuity}\n"
    if references:
        instr += "Match the characters and art style of the reference image(s).\n"
    instr += f"Scene: {scene}"
    parts.append(types.Part(text=instr))

    last_err = None
    for model in (IMAGE_MODEL, IMAGE_FALLBACK):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio=aspect),
                ),
            )
            for p in resp.candidates[0].content.parts:
                if p.inline_data and p.inline_data.data:
                    jpg = _to_jpeg(p.inline_data.data)
                    mid = new_id("img")
                    media_path(mid).write_bytes(jpg)
                    return mid, jpg
            last_err = RuntimeError("no image returned")
        except Exception as e:
            last_err = e
    raise RuntimeError(f"image failed: {last_err}")


def read_handwriting(png_bytes: bytes, context: str = "") -> dict[str, Any]:
    client = _client()
    prompt = (
        "A child wrote this by hand with a stylus or finger. Transcribe EXACTLY the letters and words written, "
        "preserving misspellings, missing letters, capitalization and punctuation as written. Do not correct anything. "
        "Ignore neatness. If a letter is genuinely ambiguous, pick the most likely letter as written (not the correct spelling). "
        + (f"Context (what he may have been trying to write; do NOT use it to fix spelling): {context}. " if context else "")
        + 'Return JSON: {"text": "...", "legible": true|false}'
    )
    resp = client.models.generate_content(
        model=VISION_MODEL,
        contents=[types.Part.from_bytes(data=png_bytes, mime_type="image/png"), prompt],
        config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"),
    )
    try:
        out = json.loads(resp.text or "{}")
    except json.JSONDecodeError:
        out = {"text": (resp.text or "").strip(), "legible": True}
    return out
