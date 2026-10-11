"""広報部：SNS投稿の下書き（X）とストーリーズ画像（Instagram）を作る。

方針: 商品の価格・写真・割引率（API由来データ）は使わない。
      自分の言葉で「何のセールが始まったか」を告知し、ハブサイトへ誘導する。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

from .compliance import check_sns_text
from .editorial import Deal

JST = timezone(timedelta(hours=9))

CATEGORY_LABELS = {
    "スニーカー": ("スニーカー", "👟"), "パンプス": ("パンプス", "👠"), "ブーツ": ("ブーツ", "🥾"),
    "ショルダーバッグ": ("ショルダーバッグ", "👜"), "トートバッグ": ("トートバッグ", "👜"), "財布": ("お財布", "👛"),
}

HOOKS = [
    "通勤にも休日にも使えるデザインが入ってました",
    "秋冬コーデに合わせやすいカラーも対象です",
    "気になってた人はチェックしてみてください",
    "サイズが残っているうちにどうぞ",
    "レビュー評価の高いものだけ集めています",
    "毎時更新の特設ページでまとめて見られます",
]

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
]


def category_of(keyword: str) -> str:
    return keyword.split()[-1]


def _label(cat: str) -> tuple[str, str]:
    return CATEGORY_LABELS.get(cat, (cat, "✨"))


def build_x_text(deal: Deal, cfg: dict, now: datetime) -> str:
    name, emoji = _label(deal.category)
    seed = int(hashlib.md5(f"{deal.asin}{now:%Y%m%d}".encode()).hexdigest(), 16)
    hook = HOOKS[seed % len(HOOKS)]
    pub = cfg["publishing"]
    link = pub["site_url"] if pub["x"]["link_mode"] == "url" else "▶プロフィールのリンクから"
    tags = " ".join(cfg["brand"]["hashtags"])
    badge = "期間限定のタイムセール中" if deal.deal_badge else "セール対象になっています"
    return f"【PR】レディース{name}が{badge}{emoji}\n{hook}\n{link}\n{tags}"


def make_x_drafts(deals: list[Deal], cfg: dict, log, now: datetime, drafts_dir: Path) -> list[Path]:
    """カテゴリが偏らないように1カテゴリ1件ずつ、1日の上限まで下書きを作る。"""
    limit = cfg["publishing"]["x"]["max_posts_per_day"]
    today = now.astimezone(JST).strftime("%Y%m%d")
    existing = list(drafts_dir.glob(f"{today}-*-x-*.yaml"))
    room = max(0, limit - len(existing))
    used_cats: set[str] = set()
    created: list[Path] = []
    for d in deals:
        if room <= 0:
            break
        if d.category in used_cats or log.recently_posted(d.asin, cfg["editorial"]["repost_cooldown_hours"], now):
            continue
        text = build_x_text(d, cfg, now)
        errors = check_sns_text(text, "x")
        draft = {
            "platform": "x", "asin": d.asin, "category": d.category, "text": text,
            "created_at": now.isoformat(timespec="minutes"),
            "approved": bool(cfg.get("auto_approve")) and not errors,
            "compliance_errors": errors, "posted": False,
        }
        path = drafts_dir / f"{today}-{now.astimezone(JST):%H%M}-x-{d.asin}.yaml"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(draft, allow_unicode=True, sort_keys=False), encoding="utf-8")
        log.mark(d.asin, now)  # 下書き化した時点で重複防止
        used_cats.add(d.category)
        created.append(path)
        room -= 1
    return created


def _font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def make_story_image(deals: list[Deal], cfg: dict, now: datetime, out_dir: Path) -> Path | None:
    """1080x1920 のお知らせ画像。商品写真・価格は使わず、カテゴリ名だけを載せる。"""
    cats = []
    for d in deals:
        if d.category not in cats:
            cats.append(d.category)
    if not cats:
        return None
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), (255, 244, 240))
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, 0, W, 260], fill=(196, 80, 106))
    dr.text((60, 70), "PR", font=_font(56), fill=(255, 255, 255))
    dr.text((60, 150), cfg["brand"]["account_name"], font=_font(52), fill=(255, 255, 255))
    dr.text((60, 360), now.astimezone(JST).strftime("%-m月%-d日の"), font=_font(72), fill=(60, 40, 40))
    dr.text((60, 460), "セール速報を更新しました", font=_font(76), fill=(196, 80, 106))
    y = 680
    for c in cats[:5]:
        name, _ = _label(c)
        dr.rounded_rectangle([60, y, W - 60, y + 140], radius=40, fill=(255, 255, 255), outline=(239, 210, 200), width=4)
        dr.text((110, y + 34), f"・{name}", font=_font(64), fill=(60, 40, 40))
        y += 170
    if len(cats) > 5:
        dr.text((110, y), f"ほか {len(cats) - 5}カテゴリ", font=_font(48), fill=(130, 110, 105))
    dr.text((60, H - 260), "くわしくはプロフィールのリンクから", font=_font(56), fill=(60, 40, 40))
    dr.text((60, H - 170), "※当アカウントはAmazonアソシエイトに参加しています", font=_font(34), fill=(130, 110, 105))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"story-{now.astimezone(JST):%Y%m%d}.png"
    img.save(path, optimize=True)
    return path
