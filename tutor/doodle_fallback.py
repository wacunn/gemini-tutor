"""Guaranteed Notebook-Paper Ink Cartoon Illustrator for Free-Tier API keys & offline fallback.

On Google AI Studio's Free Tier, raster image models (`gemini-*-image`, `imagen-*`) often have
`limit: 0` (Paid Tier 1 required) or tight 2 RPM caps. Rather than leaving blank grey boxes,
this module draws a crisp *Diary of a Wimpy Kid*-style black rollerball-pen cartoon on wide-ruled
school notebook paper using `gemini-3.1-flash-lite` (or a 0ms keyword cartoon sketcher if 429'd).
"""

from __future__ import annotations

import io
import json
import math
import random
import re
from typing import Any

from google.genai import types
from PIL import Image, ImageDraw

from .config import LITE_MODEL, genai_client

DOODLE_W, DOODLE_H = 800, 600

DOODLE_SYSTEM = """You draw funny, edgy *Diary of a Wimpy Kid*-style black-pen cartoons on an 800x600 school notebook page for an 8-year-old who loves heavy metal, monsters, and comic-book battles (skulls, skeletons, tombstones, and dramatic comic action are welcome; zero graphic gore or sexual content).
Given the child's comic sentence, return STRICT JSON listing 2 to 6 scene elements using ONLY these element kinds:
- {"kind":"kid","x":220,"y":360,"scale":1.0,"face":"panicked|shocked|grinning|grumpy|sick","arms":"up|nose_pinch|running|pointing"}
- {"kind":"cat","x":540,"y":360,"scale":1.0,"mood":"smug|grumpy|crazy"}
- {"kind":"dog","x":520,"y":380,"scale":1.0,"mood":"happy|wild"}
- {"kind":"monster","x":560,"y":330,"scale":1.1}
- {"kind":"skull","x":540,"y":320,"scale":1.1}
- {"kind":"grave","x":550,"y":415,"scale":1.0}
- {"kind":"machine","x":520,"y":430,"scale":1.0}
- {"kind":"stink","x":540,"y":250,"scale":1.0}
- {"kind":"splat","x":380,"y":430,"scale":1.0}
- {"kind":"burst","x":480,"y":280,"scale":1.0}
- {"kind":"prop_box","x":400,"y":450,"w":110,"h":80}
- {"kind":"motion_lines","x":140,"y":340}
Keep coordinates inside x: 110..730, y: 140..520 so everything fits cleanly on the page. No text or letters!
Return JSON: {"elements":[...]}"""


def _wobble_line(
    d: ImageDraw.ImageDraw,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    width: int = 4,
    rng: random.Random | None = None,
) -> None:
    r = rng or random
    dist = math.hypot(x2 - x1, y2 - y1)
    steps = max(2, int(dist / 22))
    pts = [(x1, y1)]
    for i in range(1, steps):
        t = i / steps
        jx = r.uniform(-1.6, 1.6)
        jy = r.uniform(-1.6, 1.6)
        pts.append((x1 + (x2 - x1) * t + jx, y1 + (y2 - y1) * t + jy))
    pts.append((x2, y2))
    d.line(pts, fill=(22, 24, 28), width=width, joint="curve")


def _wobble_oval(
    d: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    width: int = 4,
    fill: tuple[int, int, int] | None = (252, 252, 250),
    rng: random.Random | None = None,
) -> None:
    r = rng or random
    pts = []
    n = 28
    for i in range(n + 1):
        ang = (2 * math.pi * i) / n
        jr = 1.0 + r.uniform(-0.035, 0.035)
        pts.append((cx + math.cos(ang) * rx * jr, cy + math.sin(ang) * ry * jr))
    if fill is not None:
        d.polygon(pts[:-1], fill=fill)
    d.line(pts, fill=(22, 24, 28), width=width, joint="curve")


def _notebook_background() -> Image.Image:
    im = Image.new("RGB", (DOODLE_W, DOODLE_H), (252, 252, 249))
    d = ImageDraw.Draw(im)
    # Horizontal blue wide-ruled notebook lines
    for y in range(68, DOODLE_H - 16, 34):
        d.line([(0, y), (DOODLE_W, y)], fill=(196, 219, 244), width=2)
    # Left pink margin line
    d.line([(76, 0), (76, DOODLE_H)], fill=(238, 178, 188), width=2)
    # Binder holes
    for hy in (96, DOODLE_H // 2, DOODLE_H - 96):
        d.ellipse([24, hy - 13, 50, hy + 13], fill=(236, 236, 234), outline=(210, 210, 208), width=2)
    return im


def _draw_kid(d: ImageDraw.ImageDraw, x: float, y: float, s: float, face: str, arms: str, rng: random.Random) -> None:
    # Spiky hair + round Wimpy-Kid cartoon head
    head_y = y - 95 * s
    _wobble_oval(d, x, head_y, 40 * s, 38 * s, width=4, rng=rng)
    # Spiky hair tufts
    for dx, dy in ((-22, -34), (-6, -46), (12, -44), (26, -32)):
        _wobble_line(d, x + dx * s * 0.6, head_y - 32 * s, x + dx * s, head_y + dy * s, 4, rng)
    # Ear
    _wobble_oval(d, x - 41 * s, head_y + 4 * s, 8 * s, 11 * s, width=3, rng=rng)
    # Bugged-out cartoon eyes
    _wobble_oval(d, x - 11 * s, head_y - 6 * s, 10 * s, 11 * s, width=3, fill=(255, 255, 255), rng=rng)
    _wobble_oval(d, x + 13 * s, head_y - 6 * s, 10 * s, 11 * s, width=3, fill=(255, 255, 255), rng=rng)
    d.ellipse([x - 13 * s, head_y - 8 * s, x - 7 * s, head_y - 2 * s], fill=(20, 20, 20))
    d.ellipse([x + 11 * s, head_y - 8 * s, x + 17 * s, head_y - 2 * s], fill=(20, 20, 20))
    # Mouth by expression
    if face in ("panicked", "shocked"):
        _wobble_oval(d, x + 4 * s, head_y + 18 * s, 14 * s, 10 * s, width=3, fill=(30, 30, 30), rng=rng)
        # Sweat drops
        _wobble_oval(d, x - 54 * s, head_y - 14 * s, 4 * s, 7 * s, width=2, rng=rng)
    elif face == "sick":
        _wobble_line(d, x - 12 * s, head_y + 18 * s, x + 4 * s, head_y + 13 * s, 4, rng)
        _wobble_line(d, x + 4 * s, head_y + 13 * s, x + 16 * s, head_y + 21 * s, 4, rng)
    elif face == "grumpy":
        _wobble_line(d, x - 14 * s, head_y + 18 * s, x + 14 * s, head_y + 15 * s, 4, rng)
        _wobble_line(d, x - 20 * s, head_y - 20 * s, x - 4 * s, head_y - 14 * s, 4, rng)
        _wobble_line(d, x + 22 * s, head_y - 20 * s, x + 6 * s, head_y - 14 * s, 4, rng)
    else:
        d.arc([x - 14 * s, head_y + 6 * s, x + 18 * s, head_y + 26 * s], start=10, end=170, fill=(22, 24, 28), width=4)

    # Bean torso (black band t-shirt!)
    body_top = head_y + 38 * s
    body_bot = y + 36 * s
    d.polygon(
        [
            (x - 24 * s, body_top),
            (x + 24 * s, body_top),
            (x + 28 * s, body_bot),
            (x - 28 * s, body_bot),
        ],
        fill=(28, 30, 34),
        outline=(20, 20, 20),
    )
    # Arms
    if arms == "nose_pinch":
        _wobble_line(d, x + 22 * s, body_top + 14 * s, x + 46 * s, head_y + 8 * s, 4, rng)
        _wobble_line(d, x + 46 * s, head_y + 8 * s, x + 8 * s, head_y + 5 * s, 4, rng)
        _wobble_line(d, x - 22 * s, body_top + 14 * s, x - 52 * s, body_top + 28 * s, 4, rng)
    elif arms == "up":
        _wobble_line(d, x - 22 * s, body_top + 14 * s, x - 52 * s, head_y - 8 * s, 4, rng)
        _wobble_line(d, x + 22 * s, body_top + 14 * s, x + 52 * s, head_y - 8 * s, 4, rng)
    else:
        _wobble_line(d, x - 22 * s, body_top + 14 * s, x - 48 * s, body_top + 42 * s, 4, rng)
        _wobble_line(d, x + 22 * s, body_top + 14 * s, x + 52 * s, body_top + 24 * s, 4, rng)
    # Legs + sneakers
    _wobble_line(d, x - 12 * s, body_bot, x - 22 * s, y + 92 * s, 4, rng)
    _wobble_line(d, x + 12 * s, body_bot, x + 24 * s, y + 92 * s, 4, rng)
    _wobble_oval(d, x - 28 * s, y + 96 * s, 14 * s, 7 * s, width=3, rng=rng)
    _wobble_oval(d, x + 30 * s, y + 96 * s, 14 * s, 7 * s, width=3, rng=rng)


def _draw_cat(d: ImageDraw.ImageDraw, x: float, y: float, s: float, mood: str, rng: random.Random) -> None:
    # Scruffy comic cat body + pointy ears + smug/grumpy eyes + upright tail
    _wobble_oval(d, x, y + 18 * s, 44 * s, 28 * s, width=4, rng=rng)
    hx, hy = x - 26 * s, y - 18 * s
    _wobble_oval(d, hx, hy, 28 * s, 24 * s, width=4, rng=rng)
    # Ears
    d.polygon([(hx - 22 * s, hy - 12 * s), (hx - 14 * s, hy - 38 * s), (hx - 4 * s, hy - 18 * s)], fill=(252, 252, 250), outline=(22, 24, 28), width=3)
    d.polygon([(hx + 4 * s, hy - 18 * s), (hx + 16 * s, hy - 38 * s), (hx + 22 * s, hy - 12 * s)], fill=(252, 252, 250), outline=(22, 24, 28), width=3)
    # Eyes + whiskers
    _wobble_oval(d, hx - 9 * s, hy - 3 * s, 6 * s, 6 * s, width=3, fill=(255, 255, 255), rng=rng)
    _wobble_oval(d, hx + 9 * s, hy - 3 * s, 6 * s, 6 * s, width=3, fill=(255, 255, 255), rng=rng)
    d.ellipse([hx - 10 * s, hy - 4 * s, hx - 6 * s, hy], fill=(20, 20, 20))
    d.ellipse([hx + 8 * s, hy - 4 * s, hx + 12 * s, hy], fill=(20, 20, 20))
    if mood in ("grumpy", "smug"):
        _wobble_line(d, hx - 16 * s, hy - 11 * s, hx - 2 * s, hy - 6 * s, 3, rng)
        _wobble_line(d, hx + 16 * s, hy - 11 * s, hx + 2 * s, hy - 6 * s, 3, rng)
    _wobble_line(d, hx - 20 * s, hy + 5 * s, hx - 42 * s, hy + 2 * s, 2, rng)
    _wobble_line(d, hx - 20 * s, hy + 9 * s, hx - 42 * s, hy + 13 * s, 2, rng)
    _wobble_line(d, hx + 20 * s, hy + 5 * s, hx + 40 * s, hy + 2 * s, 2, rng)
    # Legs + jagged scruffy tail
    for lx in (-26, -10, 14, 28):
        _wobble_line(d, x + lx * s, y + 42 * s, x + lx * s, y + 72 * s, 4, rng)
    _wobble_line(d, x + 42 * s, y + 8 * s, x + 64 * s, y - 42 * s, 5, rng)


def _draw_stink(d: ImageDraw.ImageDraw, x: float, y: float, s: float, rng: random.Random) -> None:
    for dx in (-36, 0, 36):
        pts = []
        for step in range(9):
            py = y + 40 * s - step * 14 * s
            px = x + dx * s + math.sin(step * 1.1 + dx) * 12 * s
            pts.append((px, py))
        d.line(pts, fill=(40, 44, 50), width=3, joint="curve")


def _draw_burst(d: ImageDraw.ImageDraw, x: float, y: float, s: float, rng: random.Random) -> None:
    pts = []
    n = 16
    for i in range(n):
        ang = (2 * math.pi * i) / n
        rad = (68 if i % 2 == 0 else 32) * s
        pts.append((x + math.cos(ang) * rad, y + math.sin(ang) * rad))
    pts.append(pts[0])
    d.line(pts, fill=(22, 24, 28), width=4)


def _draw_monster(d: ImageDraw.ImageDraw, x: float, y: float, s: float, rng: random.Random) -> None:
    _wobble_oval(d, x, y, 62 * s, 72 * s, width=5, rng=rng)
    # Horns
    _wobble_line(d, x - 36 * s, y - 58 * s, x - 56 * s, y - 92 * s, 5, rng)
    _wobble_line(d, x + 36 * s, y - 58 * s, x + 56 * s, y - 92 * s, 5, rng)
    # Three goofy eyes + jagged teeth
    for ex in (-22, 0, 22):
        _wobble_oval(d, x + ex * s, y - 24 * s, 9 * s, 10 * s, width=3, fill=(255, 255, 255), rng=rng)
        d.ellipse([x + ex * s - 3, y - 24 * s - 3, x + ex * s + 3, y - 24 * s + 3], fill=(20, 20, 20))
    _wobble_oval(d, x, y + 14 * s, 34 * s, 18 * s, width=4, fill=(30, 30, 30), rng=rng)


def _draw_machine(d: ImageDraw.ImageDraw, x: float, y: float, s: float, rng: random.Random) -> None:
    d.rounded_rectangle([x - 46 * s, y - 34 * s, x + 46 * s, y + 34 * s], radius=10, fill=(244, 244, 240), outline=(22, 24, 28), width=4)
    _wobble_oval(d, x - 18 * s, y + 6 * s, 10 * s, 10 * s, width=3, rng=rng)
    _wobble_line(d, x + 46 * s, y - 8 * s, x + 62 * s, y - 22 * s, 4, rng)
    # Sparks
    for ang in (-2.4, -1.8, -0.9, -0.4):
        _wobble_line(d, x + math.cos(ang) * 44 * s, y - 36 * s, x + math.cos(ang) * 72 * s, y - 62 * s, 3, rng)


def _draw_skull(d: ImageDraw.ImageDraw, x: float, y: float, s: float, rng: random.Random) -> None:
    _wobble_oval(d, x, y - 10 * s, 40 * s, 36 * s, width=4, rng=rng)
    d.rectangle([x - 20 * s, y + 18 * s, x + 20 * s, y + 40 * s], fill=(252, 252, 250), outline=(22, 24, 28), width=4)
    for tx in (-10, 0, 10):
        _wobble_line(d, x + tx * s, y + 20 * s, x + tx * s, y + 39 * s, 3, rng)
    _wobble_oval(d, x - 14 * s, y - 12 * s, 9 * s, 10 * s, width=3, fill=(24, 24, 28), rng=rng)
    _wobble_oval(d, x + 14 * s, y - 12 * s, 9 * s, 10 * s, width=3, fill=(24, 24, 28), rng=rng)
    d.polygon([(x, y + 2 * s), (x - 5 * s, y + 12 * s), (x + 5 * s, y + 12 * s)], fill=(24, 24, 28))


def _draw_grave(d: ImageDraw.ImageDraw, x: float, y: float, s: float, rng: random.Random) -> None:
    d.rounded_rectangle([x - 36 * s, y - 48 * s, x + 36 * s, y + 42 * s], radius=32, fill=(240, 242, 245), outline=(22, 24, 28), width=4)
    _wobble_line(d, x, y - 26 * s, x, y + 8 * s, 4, rng)
    _wobble_line(d, x - 14 * s, y - 14 * s, x + 14 * s, y - 14 * s, 4, rng)


def _heuristic_elements(scene: str) -> list[dict[str, Any]]:
    low = (scene or "").lower()
    els: list[dict[str, Any]] = []
    stinky = any(w in low for w in ("smell", "stink", "skunk", "fart", "barf", "puke", "poop", "rotten"))
    spooky_death = any(w in low for w in ("die", "died", "dead", "death", "grave", "tomb", "coffin", "skeleton", "skull", "ghost", "reaper"))
    scared = any(w in low for w in ("scare", "scream", "yell", "panic", "run", "explod", "crash", "monst", "burglar")) or spooky_death
    face = "sick" if ("barf" in low or "puke" in low) else ("panicked" if (stinky or scared) else "grinning")
    arms = "nose_pinch" if stinky else ("up" if scared else "pointing")
    els.append({"kind": "kid", "x": 230, "y": 360, "scale": 1.05, "face": face, "arms": arms})
    if "cat" in low or "kitten" in low or "skunk" in low:
        els.append({"kind": "cat", "x": 545, "y": 375, "scale": 1.15, "mood": "smug"})
    elif "dog" in low:
        els.append({"kind": "cat", "x": 545, "y": 375, "scale": 1.2, "mood": "crazy"})
    elif any(w in low for w in ("skeleton", "skull", "reaper", "ghost")):
        els.append({"kind": "skull", "x": 555, "y": 335, "scale": 1.15})
    elif any(w in low for w in ("grave", "tomb", "coffin", "die", "died", "dead", "death")):
        els.append({"kind": "grave", "x": 555, "y": 420, "scale": 1.1})
    elif any(w in low for w in ("monster", "creeper", "zombie", "rat", "spider", "boss", "burglar", "alien")):
        els.append({"kind": "monster", "x": 555, "y": 345, "scale": 1.05})
    else:
        els.append({"kind": "machine", "x": 545, "y": 405, "scale": 1.15})
    if stinky:
        els.append({"kind": "stink", "x": 535, "y": 250, "scale": 1.1})
    if scared or "boom" in low or "blast" in low:
        els.append({"kind": "burst", "x": 420, "y": 215, "scale": 0.75})
    els.append({"kind": "motion_lines", "x": 125, "y": 330})
    return els


def render_notebook_doodle(scene: str, allow_llm: bool = True) -> bytes:
    """Renders a 4:3 JPEG Notebook Ink Doodle cartoon for `scene` in <=2.5s (0ms if allow_llm=False)."""
    elements: list[dict[str, Any]] = []
    if allow_llm:
        try:
            client = genai_client(timeout_ms=3200)
            resp = client.models.generate_content(
                model=LITE_MODEL,
                contents=f"Comic sentence: {scene}",
                config=types.GenerateContentConfig(
                    system_instruction=DOODLE_SYSTEM,
                    temperature=0.4,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            parsed = json.loads((resp.text or "").strip())
            if isinstance(parsed, dict) and isinstance(parsed.get("elements"), list):
                elements = parsed["elements"][:7]
        except Exception:
            elements = []

    if not elements:
        elements = _heuristic_elements(scene)

    im = _notebook_background()
    d = ImageDraw.Draw(im)
    rng = random.Random(hash(scene) & 0xFFFFFFFF)

    # Hand-drawn ground line
    _wobble_line(d, 96, 488, DOODLE_W - 44, 488, width=3, rng=rng)

    for el in elements:
        if not isinstance(el, dict):
            continue
        k = str(el.get("kind") or "")
        x = float(el.get("x") or 400)
        y = float(el.get("y") or 360)
        sc = max(0.5, min(1.5, float(el.get("scale") or 1.0)))
        if k == "kid":
            _draw_kid(d, x, y, sc, str(el.get("face") or "shocked"), str(el.get("arms") or "up"), rng)
        elif k in ("cat", "dog"):
            _draw_cat(d, x, y, sc, str(el.get("mood") or "smug"), rng)
        elif k == "monster":
            _draw_monster(d, x, y, sc, rng)
        elif k == "skull":
            _draw_skull(d, x, y, sc, rng)
        elif k == "grave":
            _draw_grave(d, x, y, sc, rng)
        elif k == "machine":
            _draw_machine(d, x, y, sc, rng)
        elif k == "stink":
            _draw_stink(d, x, y, sc, rng)
        elif k == "burst":
            _draw_burst(d, x, y, sc, rng)
        elif k == "splat":
            _wobble_oval(d, x, y, 42 * sc, 16 * sc, width=3, fill=(210, 212, 216), rng=rng)
        elif k == "prop_box":
            bw = float(el.get("w") or 90)
            bh = float(el.get("h") or 70)
            d.rectangle([x - bw / 2, y - bh / 2, x + bw / 2, y + bh / 2], fill=(248, 248, 244), outline=(22, 24, 28), width=4)
        elif k == "motion_lines":
            for dy in (-22, 0, 22):
                _wobble_line(d, x - 26, y + dy, x + 12, y + dy, 3, rng)

    out = io.BytesIO()
    im.save(out, format="JPEG", quality=88)
    return out.getvalue()
