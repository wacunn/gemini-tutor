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
from .projects import all_panels, extract_dialogue, middle_beats_list, project_ui_payload

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

    # Cover hero art (uses Act I / Cover Concept Art immediately, even before Panel 1!)
    art_w = PAGE_W - 2 * (MARGIN + 16)
    art_h = 820
    art_top = max(y + 28, 360)
    sp = proj.get("spine") or {}
    first_mid = (
        proj.get("cover_image")
        or sp.get("beginning_image")
        or next((p.get("image") for p in panels if p.get("image")), None)
        or proj.get("codex_sketch_image")
    )
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


def _draw_speech_bubble(
    d: ImageDraw.ImageDraw,
    art_x: int,
    art_y: int,
    art_w: int,
    art_h: int,
    bub: dict[str, Any],
    idx: int = 0,
) -> None:
    """Draws a positioned comic Speech (with pointed tail), Shout (spiky yellow burst), or Thought (cloud circles) bubble inside the artwork box."""
    f_tx = _font(20, bold=True)
    speaker = str(bub.get("speaker") or "").strip()
    line = str(bub.get("text") or "").strip()
    if not line:
        return
    kind = str(bub.get("kind") or "speech").strip().lower()
    full = f"{speaker.upper()}: {line}" if speaker else line
    max_bw = max(180, min(int(art_w * 0.78), art_w - 28))
    lines = _wrap(d, full, f_tx, max_bw - 32)[:4]
    if not lines:
        return
    bh = 20 + len(lines) * 26
    bw = min(max_bw, max(d.textbbox((0, 0), ln, font=f_tx)[2] for ln in lines) + 34)

    x_pct = float(bub.get("x", 10 if idx % 2 == 0 else 44))
    y_pct = float(bub.get("y", 8 + idx * 18))
    bx = art_x + int((x_pct / 100.0) * art_w)
    by = art_y + int((y_pct / 100.0) * art_h)
    bx = max(art_x + 8, min(art_x + art_w - bw - 8, bx))
    by = max(art_y + 8, min(art_y + art_h - bh - 18, by))

    # Hard comic drop shadow
    d.rounded_rectangle([bx + 4, by + 4, bx + bw + 4, by + bh + 4], radius=18, fill=(15, 15, 15))
    bg_fill = (255, 250, 208) if kind == "shout" else (255, 255, 255)
    rad = 6 if kind == "shout" else 20
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=rad, fill=bg_fill, outline=(15, 15, 15), width=4 if kind == "shout" else 3)

    # Tail by bubble kind
    tail_cx = bx + min(bw - 26, max(26, bw // 3))
    if kind == "thought":
        d.ellipse([tail_cx - 7, by + bh + 3, tail_cx + 7, by + bh + 15], fill=(255, 255, 255), outline=(15, 15, 15), width=3)
        d.ellipse([tail_cx - 14, by + bh + 16, tail_cx - 5, by + bh + 24], fill=(255, 255, 255), outline=(15, 15, 15), width=2)
    elif kind == "shout":
        pts = [(tail_cx - 12, by + bh - 2), (tail_cx - 22, by + bh + 18), (tail_cx + 4, by + bh - 2)]
        d.polygon(pts, fill=bg_fill)
        d.line([pts[0], pts[1], pts[2]], fill=(15, 15, 15), width=4)
    else:
        pts = [(tail_cx - 10, by + bh - 2), (tail_cx - 18, by + bh + 16), (tail_cx + 8, by + bh - 2)]
        d.polygon(pts, fill=bg_fill)
        d.line([pts[0], pts[1], pts[2]], fill=(15, 15, 15), width=3)

    ty = by + 10
    for ln in lines:
        d.text((bx + 16, ty), ln, fill=(15, 15, 15), font=f_tx)
        ty += 26


def _spine_as_comic_panels(proj: dict[str, Any]) -> list[dict[str, Any]]:
    """Converts Plot Board beats (`Beginning`, `Middle Twists`, `Big Finale`) into full comic panels with captions & speech bubbles!"""
    payload = project_ui_payload(proj)
    sp = payload.get("spine") or {}
    out: list[dict[str, Any]] = []
    if sp.get("beginning") or sp.get("beginning_image"):
        out.append(
            {
                "number": "1",
                "badge": "KICKOFF",
                "chapter_title": "Story Arc",
                "image": sp.get("beginning_image") or proj.get("cover_image"),
                "caption": sp.get("beginning_caption", sp.get("beginning") or ""),
                "dialogue": sp.get("beginning_dialogue") or [],
            }
        )
    for idx, mb in enumerate(sp.get("middle_beats") or [], 1):
        out.append(
            {
                "number": str(len(out) + 1),
                "badge": f"TWIST {idx}",
                "chapter_title": "Story Arc",
                "image": mb.get("image"),
                "caption": mb.get("caption", mb.get("text") or ""),
                "dialogue": mb.get("dialogue") or [],
            }
        )
    if sp.get("end") or sp.get("end_image"):
        out.append(
            {
                "number": str(len(out) + 1),
                "badge": "FINALE",
                "chapter_title": "Story Arc",
                "image": sp.get("end_image"),
                "caption": sp.get("end_caption", sp.get("end") or ""),
                "dialogue": sp.get("end_dialogue") or [],
            }
        )
    return out


def _render_codex_pages(proj: dict[str, Any], panels: list[dict[str, Any]]) -> list[Image.Image]:
    """Renders wide 2-entry-per-page Illustrated Field Codex spreads so full 3-5 sentence synthesized paragraphs never clip."""
    if not panels:
        return []
    pages: list[Image.Image] = []
    f_hdr = _font(24, bold=True)
    f_lbl = _font(22, bold=True)
    f_body = _font(22, bold=False)
    f_body_sm = _font(19, bold=False)

    grid_w = PAGE_W - 2 * MARGIN
    row_h = 640
    art_w = 480
    art_h = row_h - 10

    for page_idx in range(0, len(panels), 2):
        chunk = panels[page_idx : page_idx + 2]
        page = Image.new("RGB", (PAGE_W, PAGE_H), (252, 251, 248))
        d = ImageDraw.Draw(page)

        d.text((MARGIN, 46), f"{proj.get('title', 'Illustrated Field Codex')}  ·  Research & Synthesis Entries", fill=(85, 90, 98), font=f_hdr)
        d.line([MARGIN, 84, PAGE_W - MARGIN, 84], fill=(210, 208, 200), width=2)

        for r_idx, p in enumerate(chunk):
            y0 = 114 + r_idx * (row_h + 36)
            x0 = MARGIN
            d.rectangle([x0, y0, x0 + grid_w, y0 + row_h], fill=(255, 255, 255), outline=(18, 20, 24), width=5)

            # Left: framed encyclopedia illustration
            im = _load_panel_img(p.get("image"), art_w, art_h)
            if im:
                page.paste(im, (x0 + 5, y0 + 5))
            else:
                d.rectangle([x0 + 5, y0 + 5, x0 + 5 + art_w, y0 + 5 + art_h], fill=(236, 238, 242))
                d.text((x0 + 30, y0 + art_h // 2), f"Entry {p.get('number', r_idx + 1)} (rendering)", fill=(130, 134, 142), font=f_body)
            d.line([x0 + 5 + art_w, y0, x0 + 5 + art_w, y0 + row_h], fill=(18, 20, 24), width=4)

            # Right: full synthesized expository paragraph
            tx0 = x0 + 5 + art_w + 28
            tw = grid_w - art_w - 56
            entry_no = p.get("number", page_idx + r_idx + 1)
            d.text((tx0, y0 + 26), f"CODEX ENTRY #{entry_no}", fill=(36, 84, 190), font=f_lbl)
            d.line([tx0, y0 + 62, tx0 + tw, y0 + 62], fill=(220, 218, 210), width=2)

            cap_txt = p.get("caption") or ""
            lines = _wrap(d, cap_txt, f_body, tw)
            use_font = f_body
            line_h = 34
            max_lines = 15
            if len(lines) > max_lines:
                use_font = f_body_sm
                lines = _wrap(d, cap_txt, use_font, tw)
                line_h = 29
                max_lines = 18
            cy = y0 + 82
            for ln in lines[:max_lines]:
                d.text((tx0, cy), ln, fill=(22, 24, 28), font=use_font)
                cy += line_h

        pno = f"Page {len(pages) + 1}"
        d.text((PAGE_W // 2 - 35, PAGE_H - 54), pno, fill=(120, 124, 132), font=f_body_sm)
        pages.append(page)

    return pages


def _render_panel_pages(proj: dict[str, Any], panels: list[dict[str, Any]]) -> list[Image.Image]:
    if not panels:
        return []
    if proj.get("kind") == "epic_codex":
        return _render_codex_pages(proj, panels)
    pages: list[Image.Image] = []
    f_hdr = _font(24, bold=True)
    f_cap = _font(21, bold=False)
    f_cap_sm = _font(17, bold=False)
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
            cap_txt = (p.get("caption") or "").strip()
            this_art_h = art_h if cap_txt else (cell_h - 10)

            # Panel outer frame
            d.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], fill=(255, 255, 255), outline=(15, 15, 15), width=5)

            # Panel artwork
            im = _load_panel_img(p.get("image"), cell_w - 10, this_art_h)
            if im:
                page.paste(im, (x0 + 5, y0 + 5))
            else:
                d.rectangle([x0 + 5, y0 + 5, x0 + cell_w - 5, y0 + 5 + this_art_h], fill=(236, 238, 242))
                d.text((x0 + 24, y0 + this_art_h // 2), f"Panel {p.get('number', i + 1)} (rendering)", fill=(130, 134, 142), font=f_cap)

            # Panel badge
            badge_str = str(p.get("badge") or p.get("number", page_idx + i + 1))
            bw_num = max(42, d.textbbox((0, 0), badge_str, font=f_num)[2] + 24)
            d.rectangle([x0 + 5, y0 + 5, x0 + 5 + bw_num, y0 + 40], fill=(255, 245, 194), outline=(15, 15, 15), width=3)
            d.text((x0 + 16, y0 + 10), badge_str, fill=(15, 15, 15), font=f_num)

            # Speech / Shout / Thought bubbles overlaid at their saved (x%, y%) coordinates
            for b_idx, bub in enumerate((p.get("dialogue") or [])[:5]):
                _draw_speech_bubble(d, x0 + 5, y0 + 5, cell_w - 10, this_art_h, bub, idx=b_idx)

            # Divider & classic yellow narrative caption box at bottom (hidden cleanly if dialogue-only panel!)
            if cap_txt:
                cap_top = y0 + 5 + this_art_h
                d.rectangle([x0 + 5, cap_top, x0 + cell_w - 5, y0 + cell_h - 5], fill=(255, 245, 194))
                d.line([x0, cap_top, x0 + cell_w, cap_top], fill=(15, 15, 15), width=4)
                cap_lines = _wrap(d, cap_txt, f_cap, cell_w - 36)
                use_f = f_cap
                lh = 29
                max_l = 6
                if len(cap_lines) > 6:
                    use_f = f_cap_sm
                    cap_lines = _wrap(d, cap_txt, use_f, cell_w - 32)
                    lh = 22
                    max_l = 8
                cy = cap_top + 12
                for ln in cap_lines[:max_l]:
                    d.text((x0 + 18, cy), ln, fill=(20, 20, 20), font=use_f)
                    cy += lh

        # Page number
        pno = f"Page {len(pages) + 1}"
        d.text((PAGE_W // 2 - 35, PAGE_H - 54), pno, fill=(120, 124, 132), font=f_cap)
        pages.append(page)

    return pages


def build_project_pdf(proj: dict[str, Any]) -> bytes:
    """Renders a complete multi-page Comic Book PDF byte stream for any project (even mid-progress drafts)."""
    panels = all_panels(proj)
    spine_panels = _spine_as_comic_panels(proj)
    all_pages: list[Image.Image] = [_render_cover(proj, panels or spine_panels)]
    if spine_panels:
        all_pages.extend(_render_panel_pages(proj, spine_panels))
    if panels:
        all_pages.extend(_render_panel_pages(proj, panels))

    buf = io.BytesIO()
    first, rest = all_pages[0], all_pages[1:]
    first.save(buf, format="PDF", resolution=150.0, save_all=True, append_images=rest)
    return buf.getvalue()
