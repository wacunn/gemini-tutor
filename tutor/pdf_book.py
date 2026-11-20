"""Publication-quality Graphic Novel & Illustrated Book PDF generator (pure Python + Pillow).

Works offline on macOS, Windows PC, and Chromebook with zero external native libraries.
Exports:
  1. Cover Page (title, hero art, author credit, audience dedication, edition badge)
  2. Story Spine Page (Beginning -> Middle -> End causal blueprint, when present)
  3. Multi-page 2x2 Graphic Novel / Illustrated Codex spreads (up to 100+ panels!)
     with chapter banners, speech bubbles, ink borders, narrative captions, and page numbers.
"""

from __future__ import annotations

import io
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .media import media_path
from .projects import all_panels

PAGE_W, PAGE_H = 1275, 1650  # US Letter @ 150 DPI
MARGIN = 72


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        if bold
        else [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    )
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, max_px: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_px:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _load_panel_img(mid: str | None, w: int, h: int) -> Image.Image | None:
    if not mid:
        return None
    p = media_path(mid)
    if not p.exists():
        return None
    try:
        im = Image.open(p).convert("RGB")
        return ImageOps.fit(im, (w, h), method=Image.Resampling.LANCZOS)
    except Exception:
        return None


def _render_cover(proj: dict[str, Any], panels: list[dict[str, Any]]) -> Image.Image:
    page = Image.new("RGB", (PAGE_W, PAGE_H), (18, 20, 26))
    d = ImageDraw.Draw(page)

    # Outer double border
    d.rectangle([36, 36, PAGE_W - 36, PAGE_H - 36], outline=(235, 230, 218), width=4)
    d.rectangle([48, 48, PAGE_W - 48, PAGE_H - 48], outline=(90, 96, 112), width=2)

    # Top edition banner
    f_badge = _font(22, bold=True)
    kind_label = {
        "epic_graphic_novel": "GRAPHIC NOVEL EDITION",
        "epic_codex": "ILLUSTRATED FIELD CODEX",
        "medium_pitch": "ILLUSTRATED PITCH EDITION",
    }.get(proj.get("kind", ""), "ORIGINAL COMIC EDITION")
    n_panels = len(panels)
    n_ch = len(proj.get("chapters") or [1])
    banner = f"{kind_label}  ·  {n_ch} CHAPTER{'S' if n_ch != 1 else ''}  ·  {n_panels} PANEL{'S' if n_panels != 1 else ''}"
    d.text((MARGIN + 16, 86), banner, fill=(168, 199, 250), font=f_badge)

    # Title
    f_title = _font(64, bold=True)
    title_lines = _wrap(d, (proj.get("title") or "Untitled Graphic Novel").upper(), f_title, PAGE_W - 2 * (MARGIN + 16))
    y = 140
    for ln in title_lines[:3]:
        d.text((MARGIN + 16, y), ln, fill=(248, 246, 240), font=f_title)
        y += 76

    # Cover hero art
    art_w = PAGE_W - 2 * (MARGIN + 16)
    art_h = 820
    art_top = max(y + 28, 360)
    first_mid = next((p.get("image") for p in panels if p.get("image")), None)
    hero = _load_panel_img(first_mid, art_w, art_h)
    if hero:
        page.paste(hero, (MARGIN + 16, art_top))
    else:
        d.rectangle([MARGIN + 16, art_top, MARGIN + 16 + art_w, art_top + art_h], fill=(32, 36, 46))
        f_ph = _font(32, bold=False)
        d.text((MARGIN + 64, art_top + art_h // 2 - 20), "Artwork in progress...", fill=(150, 156, 170), font=f_ph)
    d.rectangle([MARGIN + 16, art_top, MARGIN + 16 + art_w, art_top + art_h], outline=(248, 246, 240), width=6)

    # Author & Audience footer
    foot_y = art_top + art_h + 52
    f_author = _font(36, bold=True)
    f_aud = _font(26, bold=False)
    author = proj.get("author") or "Author"
    d.text((MARGIN + 16, foot_y), f"Written & Created by {author}", fill=(248, 246, 240), font=f_author)
    if proj.get("audience"):
        d.text((MARGIN + 16, foot_y + 52), f"Created for {proj['audience']}", fill=(185, 190, 202), font=f_aud)

    return page


def _render_spine_page(proj: dict[str, Any]) -> Image.Image:
    page = Image.new("RGB", (PAGE_W, PAGE_H), (249, 247, 242))
    d = ImageDraw.Draw(page)
    f_head = _font(42, bold=True)
    f_sub = _font(24, bold=False)
    f_lbl = _font(26, bold=True)
    f_body = _font(26, bold=False)

    d.text((MARGIN, 84), "STORY ARCHITECTURE", fill=(24, 26, 30), font=f_head)
    d.text((MARGIN, 140), "The Beginning → Middle → End causal blueprint behind this book", fill=(100, 104, 112), font=f_sub)

    spine = proj.get("spine") or {}
    sections = [
        ("ACT I · THE BEGINNING (SETUP & WORLD)", spine.get("beginning") or "(In progress)"),
        ("ACT II · THE MIDDLE (COMPLICATION & ESCALATION)", spine.get("middle") or "(In progress)"),
        ("ACT III · THE END (CLIMAX & RESOLUTION)", spine.get("end") or "(In progress)"),
    ]

    y = 220
    box_w = PAGE_W - 2 * MARGIN
    for label, content in sections:
        lines = _wrap(d, content, f_body, box_w - 64) or ["(In progress)"]
        box_h = max(220, 96 + len(lines) * 38)
        d.rounded_rectangle([MARGIN, y, MARGIN + box_w, y + box_h], radius=18, fill=(255, 255, 255), outline=(28, 30, 34), width=4)
        d.text((MARGIN + 32, y + 26), label, fill=(42, 86, 196), font=f_lbl)
        ty = y + 72
        for ln in lines[:8]:
            d.text((MARGIN + 32, ty), ln, fill=(28, 30, 34), font=f_body)
            ty += 38
        y += box_h + 36

    return page


def _draw_speech_bubble(d: ImageDraw.ImageDraw, x: int, y: int, max_w: int, speaker: str, line: str) -> int:
    f_sp = _font(18, bold=True)
    f_tx = _font(20, bold=False)
    full = f"{speaker.upper()}: {line}" if speaker else line
    lines = _wrap(d, full, f_tx, max_w - 28)[:3]
    if not lines:
        return y
    bh = 20 + len(lines) * 26
    bw = min(max_w, max(d.textbbox((0, 0), ln, font=f_tx)[2] for ln in lines) + 32)
    d.rounded_rectangle([x, y, x + bw, y + bh], radius=16, fill=(255, 255, 255), outline=(15, 15, 15), width=3)
    ty = y + 10
    for ln in lines:
        d.text((x + 14, ty), ln, fill=(15, 15, 15), font=f_sp if (speaker and ty == y + 10 and len(lines) == 1) else f_tx)
        ty += 26
    return y + bh + 8


def _render_panel_pages(proj: dict[str, Any], panels: list[dict[str, Any]]) -> list[Image.Image]:
    if not panels:
        return []
    pages: list[Image.Image] = []
    f_hdr = _font(24, bold=True)
    f_cap = _font(21, bold=False)
    f_num = _font(20, bold=True)

    gutter = 28
    grid_w = PAGE_W - 2 * MARGIN
    cell_w = (grid_w - gutter) // 2
    cell_h = 660
    art_h = 450

    for page_idx in range(0, len(panels), 4):
        chunk = panels[page_idx : page_idx + 4]
        page = Image.new("RGB", (PAGE_W, PAGE_H), (252, 251, 248))
        d = ImageDraw.Draw(page)

        # Top running header with book title & active chapter
        ch_title = chunk[0].get("chapter_title") or f"Chapter {chunk[0].get('chapter', 1)}"
        d.text((MARGIN, 46), f"{proj.get('title', 'Comic Book')}  ·  {ch_title}", fill=(85, 90, 98), font=f_hdr)
        d.line([MARGIN, 84, PAGE_W - MARGIN, 84], fill=(210, 208, 200), width=2)

        for i, p in enumerate(chunk):
            col = i % 2
            row = i // 2
            x0 = MARGIN + col * (cell_w + gutter)
            y0 = 110 + row * (cell_h + gutter)

            # Panel outer frame
            d.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], fill=(255, 255, 255), outline=(15, 15, 15), width=5)

            # Panel artwork
            im = _load_panel_img(p.get("image"), cell_w - 10, art_h)
            if im:
                page.paste(im, (x0 + 5, y0 + 5))
            else:
                d.rectangle([x0 + 5, y0 + 5, x0 + cell_w - 5, y0 + 5 + art_h], fill=(236, 238, 242))
                d.text((x0 + 24, y0 + art_h // 2), f"Panel {p.get('number', i + 1)} (rendering)", fill=(130, 134, 142), font=f_cap)

            # Panel number badge
            d.rectangle([x0 + 5, y0 + 5, x0 + 46, y0 + 40], fill=(15, 15, 15))
            d.text((x0 + 16, y0 + 10), str(p.get("number", page_idx + i + 1)), fill=(255, 255, 255), font=f_num)

            # Speech bubbles overlaid cleanly near top of artwork
            by = y0 + 14
            for bub in (p.get("dialogue") or [])[:2]:
                by = _draw_speech_bubble(d, x0 + 56, by, cell_w - 72, bub.get("speaker", ""), bub.get("text", ""))

            # Divider & narrative caption box at bottom of panel
            cap_top = y0 + 5 + art_h
            d.rectangle([x0 + 5, cap_top, x0 + cell_w - 5, y0 + cell_h - 5], fill=(250, 246, 232))
            d.line([x0, cap_top, x0 + cell_w, cap_top], fill=(15, 15, 15), width=4)
            cap_lines = _wrap(d, p.get("caption") or "", f_cap, cell_w - 36)
            cy = cap_top + 14
            for ln in cap_lines[:6]:
                d.text((x0 + 18, cy), ln, fill=(20, 20, 20), font=f_cap)
                cy += 29

        # Page number
        pno = f"Page {len(pages) + 1}"
        d.text((PAGE_W // 2 - 35, PAGE_H - 54), pno, fill=(120, 124, 132), font=f_cap)
        pages.append(page)

    return pages


def build_project_pdf(proj: dict[str, Any]) -> bytes:
    """Renders a complete multi-page PDF byte stream for any project (even mid-progress drafts)."""
    panels = all_panels(proj)
    all_pages: list[Image.Image] = [_render_cover(proj, panels)]
    spine = proj.get("spine") or {}
    if spine.get("beginning") or spine.get("middle") or spine.get("end"):
        all_pages.append(_render_spine_page(proj))
    all_pages.extend(_render_panel_pages(proj, panels))

    buf = io.BytesIO()
    first, rest = all_pages[0], all_pages[1:]
    first.save(buf, format="PDF", resolution=150.0, save_all=True, append_images=rest)
    return buf.getvalue()
