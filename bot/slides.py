"""広報部（デザイン担当）：投稿スライドを content/feed/*.yaml から描画する。

商品写真・価格は使わない（API規約）。文字と図形だけのオリジナル画像。
Instagram APIはJPEGのみ受け付けるため、1080x1350（4:5）のJPEGで出力する。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
BG = (36, 30, 33)
PINK = (246, 190, 204)
INK = (246, 238, 240)
MUTED = (190, 172, 178)
CARD = (52, 44, 48)
RULE = (80, 68, 72)

_FONT_DIRS = ["/usr/share/fonts/opentype/noto/", "/usr/share/fonts/truetype/noto/"]
_WEIGHTS = {"black": ["NotoSansCJK-Black.ttc", "NotoSansCJK-Bold.ttc"],
            "bold": ["NotoSansCJK-Bold.ttc"],
            "regular": ["NotoSansCJK-Regular.ttc", "NotoSansCJK-Bold.ttc"]}
_cache: dict = {}


def font(weight: str, size: int):
    key = (weight, size)
    if key not in _cache:
        for name in _WEIGHTS[weight]:
            for d in _FONT_DIRS:
                p = Path(d) / name
                if p.exists():
                    _cache[key] = ImageFont.truetype(str(p), size, index=0)
                    break
            if key in _cache:
                break
        else:
            raise RuntimeError("日本語フォント（Noto Sans CJK）が見つかりません")
    return _cache[key]


def _wrap(d, text, f, maxw):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur); cur = ""; continue
        if d.textlength(cur + ch, font=f) > maxw:
            lines.append(cur); cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def _para(d, x, y, text, f, fill, maxw, lh):
    for ln in _wrap(d, text, f, maxw):
        d.text((x, y), ln, font=f, fill=fill)
        y += lh
    return y


def _base(brand: str, handle: str):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((72, 64), brand, font=font("bold", 34), fill=PINK)
    d.text((W - 72 - d.textlength(handle, font=font("regular", 28)), 70), handle, font=font("regular", 28), fill=MUTED)
    d.line([72, 124, W - 72, 124], fill=RULE, width=2)
    return im, d


def _footer(d, left: str, i: int, n: int):
    d.text((72, H - 110), left, font=font("regular", 30), fill=MUTED)
    if n > 1:
        s = f"{i}/{n}"
        d.text((W - 72 - d.textlength(s, font=font("bold", 30)), H - 110), s, font=font("bold", 30), fill=PINK)


def render_slide(s: dict, i: int, n: int, brand: str, handle: str) -> Image.Image:
    im, d = _base(brand, handle)
    kind = s["type"]
    maxw = W - 144
    if kind == "cover":
        y = 250
        if s.get("kicker"):
            y = _para(d, 72, y, s["kicker"], font("bold", 54), MUTED, maxw, 80) + 10
        for k, line in enumerate(s["title"]):
            fill = PINK if k == len(s["title"]) - 1 else INK
            y = _para(d, 72, y, line, font("black", 104), fill, maxw, 136)
        y += 40
        for k, b in enumerate(s.get("items", []), 1):
            d.text((72, y), f"{k:02d}", font=font("black", 56), fill=PINK)
            _para(d, 180, y + 10, b, font("bold", 42), INK, maxw - 120, 56)
            y += 104
        _footer(d, "スワイプで詳しく →" if n > 1 else s.get("footer", ""), i, n)
    elif kind == "point":
        d.text((72, 280), s["num"], font=font("black", 170), fill=PINK)
        y = _para(d, 72, 520, s["heading"], font("black", 70), INK, maxw, 94)
        y = _para(d, 72, y + 36, s["body"], font("regular", 40), INK, maxw, 66)
        if s.get("point"):
            lines = _wrap(d, s["point"], font("bold", 38), maxw - 80)
            h = 90 + 54 * len(lines)
            d.rounded_rectangle([72, y + 44, W - 72, y + 44 + h], radius=28, fill=CARD)
            d.text((112, y + 66), "POINT", font=font("bold", 30), fill=PINK)
            _para(d, 112, y + 108, s["point"], font("bold", 38), INK, maxw - 80, 54)
        _footer(d, "保存しておくと、あとで見返せます", i, n)
    elif kind == "rows":
        y = _para(d, 72, 220, s["heading"], font("black", 72), INK, maxw, 96) + 30
        lf, mf, sf = font("black", 42), font("bold", 40), font("regular", 30)
        col = 112 + max(d.textlength(r[0], font=lf) for r in s["rows"]) + 40
        textw = W - 72 - 32 - col
        for label, main, sub in s["rows"]:
            mlines, slines = _wrap(d, main, mf, textw), _wrap(d, sub, sf, textw)
            h = 44 + 54 * len(mlines) + 40 * len(slines) + 24
            d.rounded_rectangle([72, y, W - 72, y + h], radius=24, fill=CARD)
            d.text((112, y + (h - 52) / 2), label, font=lf, fill=PINK)
            yy = _para(d, col, y + 28, main, mf, INK, textw, 54)
            _para(d, col, yy + 4, sub, sf, MUTED, textw, 40)
            y += h + 22
        if s.get("note"):
            _para(d, 72, y + 12, s["note"], font("regular", 28), MUTED, maxw, 40)
        _footer(d, "保存しておくと、あとで見返せます", i, n)
    elif kind == "closing":
        y = _para(d, 72, 380, s["title"], font("black", 84), INK, maxw, 116)
        y = _para(d, 72, y + 30, s.get("body", ""), font("regular", 40), MUTED, maxw, 64)
        d.rounded_rectangle([72, y + 60, W - 72, y + 190], radius=65, outline=PINK, width=4)
        label = "フォローでセール情報を受け取る"
        f = font("bold", 42)
        d.text(((W - d.textlength(label, font=f)) / 2, y + 100), label, font=f, fill=PINK)
        _footer(d, handle, i, n)
    else:
        raise ValueError(f"未知のスライド種別: {kind}")
    return im


def render_post(post: dict, out_dir: Path, brand: str, handle: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    slides = post["slides"]
    paths = []
    for i, s in enumerate(slides, 1):
        p = out_dir / f"{i}.jpg"
        render_slide(s, i, len(slides), brand, handle).save(p, "JPEG", quality=90, optimize=True)
        paths.append(p)
    return paths
