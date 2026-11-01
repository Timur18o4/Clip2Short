"""Pillow artwork shared by the preview and the exported video."""
from __future__ import annotations

from functools import lru_cache
import math
import os
from pathlib import Path
import re

from PIL import Image, ImageColor, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1920
BACKGROUND = (16, 16, 21)


@lru_cache(maxsize=256)
def _font(size: int, black: bool = False):
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    names = [windows / ("ariblk.ttf" if black else "arialbd.ttf"),
             windows / "arialbd.ttf", "Arial Black.ttf" if black else "Arial Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    for path in names:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def _measure(text, font, tracking=0):
    if tracking:
        return sum(float(font.getlength(char)) for char in text) + max(0, len(text) - 1) * tracking
    return float(font.getlength(text))


def _baseline_for_top(font, text):
    # One line shares one baseline. Using each glyph's ink top separately would
    # raise periods and hyphens to capital height and misalign lowercase text.
    return -font.getbbox(text or "Hg", anchor="ls")[1]


def _wrap(text, font, width, tracking=0):
    lines = []
    for paragraph in str(text).split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if line and _measure(candidate, font, tracking) > width:
                lines.append(line)
                line = ""
            if _measure(word, font, tracking) > width:
                for char in word:
                    if line and _measure(line + char, font, tracking) > width:
                        lines.append(line)
                        line = ""
                    line += char
            else:
                line = f"{line} {word}" if line else word
        lines.append(line)
    return lines or [""]


def _text_tile(text, width, height, size, color="white", max_lines=2,
               tracking=0, line_height=1.12, black=False, shadow=False):
    """Fit text and physically clip the result to its assigned rectangle."""
    text = str(text).strip()
    if text.count("\n") >= max_lines:
        text = " ".join(text.split())
    for current in range(size, 7, -1):
        font = _font(current, black)
        spacing = tracking * current / size
        lines = _wrap(text, font, width, spacing)
        step = math.ceil(current * line_height)
        if len(lines) <= max_lines and len(lines) * step <= height:
            break
    else:
        font, spacing, step = _font(8, black), 0, 10
        lines = _wrap(text, font, width)[:max_lines]
        if lines:
            last = lines[-1]
            while last and _measure(last + "…", font) > width:
                last = last[:-1]
            lines[-1] = last + "…"
    tile = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(tile)
    for index, line in enumerate(lines):
        y = index * step
        if not spacing:
            draw.text((0, y), line, font=font, fill=color, anchor="lt",
                      stroke_width=1 if shadow else 0, stroke_fill=(0, 0, 0, 220))
        else:
            x = 0.0
            baseline = y + _baseline_for_top(font, line)
            for char in line:
                draw.text((round(x), baseline), char, font=font, fill=color, anchor="ls")
                x += font.getlength(char) + spacing
    return tile, {"font": font, "lines": lines, "step": step,
                  "width": min(width, math.ceil(max((_measure(s, font, spacing) for s in lines), default=0))),
                  "height": min(height, len(lines) * step)}


def _paste_text(canvas, text, box, size, **kwargs):
    x, y, width, height = box
    tile, _ = _text_tile(text, width, height, size, **kwargs)
    canvas.alpha_composite(tile, (x, y))


def _fit_crop(crop: dict, box: tuple[int, int, int, int]) -> dict:
    x, y, width, height = box
    scale = min(width / crop["width"], height / crop["height"])
    fitted_width = min(width, max(1, round(crop["width"] * scale)))
    fitted_height = min(height, max(1, round(crop["height"] * scale)))
    return {"crop": crop, "x": x + (width - fitted_width) // 2,
            "y": y, "width": fitted_width, "height": fitted_height}


def build_layout(project: dict, metadata: dict) -> dict:
    mode = project.get("mode", "just_chatting")
    if mode not in ("just_chatting", "gameplay"):
        raise ValueError("Unbekannter Modus.")
    crops = project.get("crops", {})
    full = {"x": 0, "y": 0, "width": metadata["width"], "height": metadata["height"]}
    checked = {}
    for key in ("main", "facecam") if mode == "gameplay" else ("main",):
        raw = crops.get(key, full)
        try:
            crop = {item: int(round(float(raw[item]))) for item in ("x", "y", "width", "height")}
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"Ungültiger Bildausschnitt: {key}") from exc
        if (crop["x"] < 0 or crop["y"] < 0 or crop["width"] <= 0 or crop["height"] <= 0
                or crop["x"] + crop["width"] > metadata["width"]
                or crop["y"] + crop["height"] > metadata["height"]):
            raise ValueError(f"Bildausschnitt {key} liegt außerhalb des Quellbildes.")
        checked[key] = crop
    layout = {"main": _fit_crop(checked["main"], (0, 666, 1080, 1152 if mode == "gameplay" else 1120)),
              "caption_box": (80, 440, 480, 160) if mode == "gameplay" else (80, 482, 920, 150)}
    if mode == "gameplay":
        layout["facecam"] = _fit_crop(checked["facecam"], (588, 100, 420, 494))
        layout["facecam"]["y"] += (494 - layout["facecam"]["height"]) // 2
    if project.get('chat_quote'):
        layout['quote_box']=(80,330,480,96) if mode=='gameplay' else (80,340,920,120)
    return layout


@lru_cache(maxsize=1)
def _background():
    result = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    pixels = result.load()
    # Three-stop radial gradient from the original Clip2Short composition.
    stops = ((0.0, (48, 36, 20)), (0.48, (22, 20, 25)), (0.85, BACKGROUND))
    for y in range(660):
        for x in range(WIDTH):
            distance = math.sqrt(((x - 972) / 1080) ** 2 + ((y - 100) / 666) ** 2)
            value = BACKGROUND
            for (left, a), (right, b) in zip(stops, stops[1:]):
                if distance <= right:
                    t = min(1, max(0, (distance - left) / (right - left)))
                    value = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
                    break
            pixels[x, y] = value
    return result


def build_artwork(project: dict, layout: dict) -> tuple[Image.Image, Image.Image]:
    accent_text = project.get("accent", "#ffd13f")
    if not isinstance(accent_text, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent_text):
        raise ValueError("Akzentfarbe muss als #RRGGBB angegeben werden.")
    accent = ImageColor.getrgb(accent_text)
    background = _background().copy()
    ImageDraw.Draw(background).rectangle((0, 660, WIDTH - 1, 665), fill=accent)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(overlay)
    for y in range(1710, HEIGHT):
        alpha = round(255 * min(1, (y - 1710) / (210 * .65)))
        draw.line((0, y, WIDTH, y), fill=(*BACKGROUND, alpha))
    gameplay = project.get("mode") == "gameplay"
    label = project.get("label", "GAMEPLAY" if gameplay else "JUST CHATTING")
    _paste_text(overlay, label, (80, 118 if gameplay else 90, 490 if gameplay else 920, 65),
                44, color=accent, max_lines=1, tracking=5)
    title = project.get("title", "")
    quote = str(project.get("chat_quote", "")).strip()
    _paste_text(overlay, title, (80, (210 if quote else 222) if gameplay else 184, 490 if gameplay else 920,
                                (110 if quote else 202) if gameplay else (140 if quote else 270)),
                (68 if quote else 90) if gameplay else (90 if quote else 102), max_lines=2,
                tracking=-4, line_height=1.03, black=True)
    if quote:
        x,y,width,height=layout['quote_box']
        draw.rectangle((x,y,x+4,y+height), fill=accent)
        quote_text = quote if quote.lower().startswith("chat:") else f"Chat: „{quote}“"
        _paste_text(overlay, quote_text, (x+22,y,width-22,height), 32 if gameplay else 42,
                    color=(212, 207, 212), max_lines=3, line_height=1.12)
    if gameplay:
        camera = layout["facecam"]
        draw.rectangle((camera["x"], camera["y"], camera["x"] + camera["width"] - 1,
                        camera["y"] + camera["height"] - 1), outline=(255, 255, 255, 36), width=2)
    brand = str(project.get("brand", "CNG-PLATTFORM.COM"))
    channel = str(project.get("channel", ""))
    pieces = [(brand, accent), (" / ", (119, 114, 122)), (channel, (255, 255, 255))]
    for size in range(43, 7, -1):
        font = _font(size)
        spacing = 2 * size / 43
        length = _measure("".join(text for text, _ in pieces), font, spacing)
        if length <= 920:
            break
    footer = Image.new("RGBA", (920, 75))
    fdraw = ImageDraw.Draw(footer)
    cursor = 0.0
    baseline = _baseline_for_top(font, "".join(text for text, _ in pieces))
    for text, color in pieces:
        for char in text:
            fdraw.text((round(cursor), baseline), char, font=font, fill=color, anchor="ls")
            cursor += font.getlength(char) + spacing
    overlay.alpha_composite(footer, (80, 1804))
    return background, overlay


def caption_artwork(project: dict, layout: dict, text: str = "") -> Image.Image:
    """Transparent header-sized PNG, never allowing caption pixels into the video."""
    result = Image.new("RGBA", (WIDTH, 660))
    if not str(text).strip():
        return result
    x, y, width, height = layout["caption_box"]
    content, metrics = _text_tile(text, width - 36, height - 24, 52,
                                  max_lines=2, line_height=1.12, shadow=True)
    block = Image.new("RGBA", (width, height))
    ImageDraw.Draw(block).rounded_rectangle(
        (0, 0, min(width - 1, metrics["width"] + 35), min(height - 1, metrics["height"] + 23)),
        radius=8, fill=(12, 12, 16, 230))
    block.alpha_composite(content, (18, 12))
    result.alpha_composite(block, (x, y))
    return result
