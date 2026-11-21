"""Pictures, cool kid-authentic comic styles, and primary-lined handwriting vision.

- generate_image(): single comic panel drawn ONLY from the child's words in their chosen comic style
  (Dog Man-style zany marker, Wimpy Kid lined-notebook doodle, Shonen Manga, Epic Metal Ink,
  Blocky Voxel, or Indie Adventure Comic)—explicitly banning wholesome baby-book / Hallmark clipart.
- read_handwriting(): transcribes literally AND spots single-letter formation / line-placement issues
  against the 4 primary handwriting lines (Sky line, dashed Fence line, Grass baseline, Worm line)
  so the tutor can act playfully confused about just ONE letter and let the child erase & fix that
  single letter in place.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from .config import DATA, FALLBACK_MODEL, FAST_MODEL, genai_client
from .record import new_id

MEDIA = DATA / "media"
IMAGE_MODEL = "gemini-3.1-flash-image"
IMAGE_FALLBACK = "nano-banana-pro-preview"
VISION_MODEL = FAST_MODEL  # gemini-3.5-flash

DEFAULT_STYLE_KEY = "zany_hand_drawn"

ART_STYLES: list[dict[str, str]] = [
    {
        "key": "zany_hand_drawn",
        "label": "Zany Marker Comic",
        "vibe": "Dog Man / Captain Underpants vibe",
        "sample": "/static/style_samples/zany_hand_drawn.jpg",
        "prompt": (
            "Scrappy, hilarious hand-drawn kids' comic book art inspired by Dav Pilkey (Dog Man, Captain Underpants): "
            "thick slightly wobbly black felt-tip marker outlines, wildly expressive cartoon faces (bugged-out eyes, "
            "chaotic grins, hilarious gross-out or panicked reactions, motion lines), energetic hand-colored marker fills "
            "with visible paper texture, bold slapstick cartoon energy. Zero smooth 3D rendering, zero cute Hallmark polish."
        ),
    },
    {
        "key": "notebook_doodle",
        "label": "Notebook Ink Doodle",
        "vibe": "Diary of a Wimpy Kid vibe",
        "sample": "/static/style_samples/notebook_doodle.jpg",
        "prompt": (
            "Crisp black rollerball-pen cartoon doodle drawn directly on white wide-ruled school notebook paper with faint "
            "horizontal blue ruled lines, inspired by Jeff Kinney (Diary of a Wimpy Kid): clean black ink linework ONLY, "
            "minimalist cartoon characters with hilarious deadpan or panicked expressions, zero color fills, zero painted shading."
        ),
    },
    {
        "key": "shonen_manga",
        "label": "Action Manga Ink",
        "vibe": "Screentones & speed lines",
        "sample": "/static/style_samples/shonen_manga.jpg",
        "prompt": (
            "Authentic Japanese shonen action-comedy manga panel: razor-sharp black G-pen ink linework, classic black-and-white "
            "screentone dot shading, kinetic speed lines, intense exaggerated manga facial expressions, dynamic low-angle camera."
        ),
    },
    {
        "key": "heavy_metal_ink",
        "label": "Epic Metal Zine",
        "vibe": "80s fantasy & rock-poster ink",
        "sample": "/static/style_samples/heavy_metal_ink.jpg",
        "prompt": (
            "Gritty 1980s underground adventure & heavy-metal comic art (kid-safe PG content): bold black India-ink crosshatching, "
            "deep dramatic comic shadows, electric storm-blue, acid-green, and fiery orange comic ink colors, epic monsters and "
            "contraptions, high-voltage rock-zine attitude."
        ),
    },
    {
        "key": "blocky_voxel",
        "label": "Blocky Voxel World",
        "vibe": "Minecraft-style cubic world",
        "sample": "/static/style_samples/blocky_voxel.jpg",
        "prompt": (
            "Crisp 3D blocky voxel sandbox art: every character, creature, prop, and environment is constructed from chunky cubic "
            "voxel blocks with crisp 16x16 pixel-art textures, dramatic torchlight and glowing voxel particles, expressive blocky faces."
        ),
    },
    {
        "key": "indie_graphic_novel",
        "label": "Indie Adventure Comic",
        "vibe": "Last Kids on Earth / Bone vibe",
        "sample": "/static/style_samples/indie_graphic_novel.jpg",
        "prompt": (
            "Modern middle-grade action-comedy graphic novel art (inspired by The Last Kids on Earth and Bone): expressive angular "
            "brush-ink outlines, moody cinematic rim-lighting, bold cel-shaded colors, funny exaggerated cartoon acting, mid-action framing."
        ),
    },
]

STYLE_BY_KEY: dict[str, dict[str, str]] = {s["key"]: s for s in ART_STYLES}


def resolve_style_prompt(style_or_key: str) -> str:
    s = (style_or_key or "").strip()
    if s in STYLE_BY_KEY:
        return STYLE_BY_KEY[s]["prompt"]
    # Legacy default upgrade: never use generic "wholesome flat colors" anymore
    if not s or s == "comic book ink with bold lines and vibrant flat colors":
        return STYLE_BY_KEY[DEFAULT_STYLE_KEY]["prompt"]
    return s


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
    resolved_style = resolve_style_prompt(style)
    instr = (
        "Draw ONE single comic illustration showing ONE moment. Do NOT divide the image into multiple panels or frames.\n"
        "Draw ONLY the characters, objects, actions, and setting explicitly named in the Scene description. If the description "
        "is sparse, keep the scene sparse so adding more detail to the sentence visibly upgrades the next drawing.\n"
        "CRITICAL AESTHETIC RULES:\n"
        "- Make the art genuinely COOL, funny, irreverent, and expressive like comics 9-year-olds actually read (Dog Man, "
        "Diary of a Wimpy Kid, Last Kids on Earth, Bone, shonen manga).\n"
        "- STRICTLY FORBID babyish preschool picture-book art, wholesome Hallmark greeting-card illustration, soft pastel "
        "nursery colors, glossy 3D Pixar/toddler dolls, or generic stock-clipart smiles.\n"
        "- Commit 100% to the requested Art Style, with comedic/dramatic cartoon expressions and dynamic framing (kid-safe PG).\n"
        "- Absolutely NO words, letters, numbers, captions, signs, or speech bubbles anywhere in the image.\n"
        f"Art Style: {resolved_style}\n"
    )
    if continuity:
        instr += f"Keep these character/world details consistent with reference panels: {continuity}\n"
    if references:
        instr += "Match the exact character designs and art style of the reference image(s).\n"
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


HANDWRITING_SYSTEM = """You read a child's stylus/finger handwriting written on 4-line primary handwriting paper:
- SKY LINE (solid blue top line): tall letters (b, d, f, h, k, l, t) and ALL capital letters reach up toward the Sky line.
- FENCE LINE (dashed middle line): small letters (a, c, e, i, m, n, o, r, s, u, v, w, x, z) top out around the Fence line.
- GRASS LINE (solid green baseline): every letter sits on the Grass line.
- WORM LINE (bottom brown descender line): tail/worm letters (g, j, p, q, y) hang their tails below the Grass line down toward the Worm line.

RULES:
1. "text": Transcribe EXACTLY the letters and words written, preserving spelling mistakes, missing letters, capitalization, and punctuation as written. Never silently fix spelling.
2. "legible": false ONLY if you genuinely cannot tell what words were attempted at all; otherwise true.
3. "letter_issue": Inspect physical letter formation and line placement.
   - Set "letter_issue" to null if every letter is reasonably recognizable as the letter the child wrote (even if a word is phonetically misspelled like "smelee"—that is a spelling issue, NOT a handwriting letter-shape issue!).
   - Set "letter_issue" ONLY when a physical letter's shape or line height makes it look like a DIFFERENT letter, backwards, or hard to read:
     * Uncrossed 't' looking like 'l', open 'a' looking like 'u', unlooped 'e' looking like 'c', short-stem 'h' looking like 'n', 'r' looking like 'v', backwards 'b'/'d' or 'p'/'q'/'s', squished illegible letter, OR
     * Severe line-zone confusion that alters or obscures the letter (e.g. 'p'/'g'/'y' tail floating completely above the Grass line instead of dipping to the Worm line, or 'l'/'b'/'h'/'k' shrunk below the Fence line so 'h' looks like 'n' or 'l' looks like 'i').
   - Pick AT MOST ONE single letter (the most confusing one) so the child only has to erase and touch up ONE letter!
   - Give approximate normalized center coordinates "x_frac" (0.0=left edge, 1.0=right edge) and "y_frac" (0.0=top edge, 1.0=bottom edge) of that single letter in the image.
   - Phrase "line_tip" using the exact kid line names ("Sky line", "Fence line", "Grass line", "Worm line").

Return strict JSON:
{
  "text": "...",
  "legible": true,
  "letter_issue": null | {
    "word_written": "cal",
    "word_intended": "cat",
    "letter_intended": "t",
    "looks_like": "l",
    "x_frac": 0.45,
    "y_frac": 0.32,
    "line_tip": "Reach up toward the Sky line and cross your 't' right on the dashed Fence line so it doesn't look like 'l'."
  }
}"""


def read_handwriting(png_bytes: bytes, context: str = "", skip_letter_check: bool = False) -> dict[str, Any]:
    client = _client()
    user_prompt = "Read this child's handwritten submission."
    if context:
        user_prompt += f"\nPrompt context (do NOT use to auto-correct spelling): {context}"
    if skip_letter_check:
        user_prompt += "\nThe child just touched up a letter—set letter_issue to null unless completely illegible."
    resp = client.models.generate_content(
        model=VISION_MODEL,
        contents=[types.Part.from_bytes(data=png_bytes, mime_type="image/png"), user_prompt],
        config=types.GenerateContentConfig(
            system_instruction=HANDWRITING_SYSTEM,
            temperature=0.0,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    try:
        out = json.loads(resp.text or "{}")
    except json.JSONDecodeError:
        out = {"text": (resp.text or "").strip(), "legible": True, "letter_issue": None}
    if skip_letter_check:
        out["letter_issue"] = None
    return out
