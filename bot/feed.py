"""広報部（フィード担当）：情報投稿のストックを、決めた曜日・時刻に1件ずつ投稿する。

- 投稿ネタ：content/feed.yaml（approved: true のものだけ）
- 画像：bot/slides.py で描画 → public/feed/<id>/<n>.jpg（GitHub Pagesで公開）
- 記録：state/feed_posted.json（id → 投稿日時・メディアID）
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .slides import render_post

JST = timezone(timedelta(hours=9))
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def load_posts(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def apply_format_defaults(posts: list[dict], cfg: dict) -> list[dict]:
    """format 未指定の投稿に既定の形式を入れる（情報投稿は info_format、PR投稿は pr_format）。"""
    ig = cfg["publishing"]["instagram"]
    for p in posts:
        if not p.get("format"):
            p["format"] = ig.get("pr_format" if p.get("pr") else "info_format", "carousel")
    return posts


def render_all(posts: list[dict], public_dir: Path, cfg: dict, skip_reels: set | None = None) -> dict[str, int]:
    """skip_reels: 投稿済みなど動画を作らなくてよい投稿のid（毎時の処理時間を抑える）。"""
    apply_format_defaults(posts, cfg)
    brand = cfg["brand"]["account_name"].split("｜")[0]
    handle = cfg["brand"].get("instagram_handle", "")
    counts = {}
    for p in posts:
        paths = render_post(p, public_dir / "feed" / p["id"], brand, handle)
        counts[p["id"]] = len(paths)
        if p.get("format") == "reel" and p["id"] not in (skip_reels or set()):
            from .reel import make_reel
            make_reel(paths, public_dir / "feed" / p["id"], reel_title(p))
    return counts


def reel_title(post: dict) -> str:
    """リール上部に出す見出し。reel_title があればそれ、なければ表紙のタイトルをつなげたもの。"""
    if post.get("reel_title"):
        return post["reel_title"]
    cover = post["slides"][0]
    return "".join(t.replace("\n", "") for t in cover.get("title", []))[:22]


class FeedLog:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict = json.loads(path.read_text()) if path.exists() else {}

    def posted_today(self, now: datetime) -> bool:
        today = now.astimezone(JST).date().isoformat()
        return any(v["posted_at"][:10] == today for v in self.data.values())

    def mark(self, post_id: str, media_id: str, now: datetime) -> None:
        self.data[post_id] = {"posted_at": now.astimezone(JST).isoformat(timespec="minutes"), "media_id": media_id}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1))


QUIET_UNTIL = 7  # 0:00〜6:59 JST は投稿しない（深夜の取りこぼし分は朝以降に回す）


def next_due(posts: list[dict], log: FeedLog, cfg: dict, now: datetime) -> dict | None:
    """投稿すべきものを1件返す（1日1件まで）。
    - date 指定のある投稿：その日の指定時刻以降に投稿（曜日に関係なく優先）
    - date 指定のない投稿：指定曜日の指定時刻以降に、上から順に投稿
    - 取りこぼし救済：GitHub Actions の定期実行は数時間遅れることがあるため、
      前日の枠で投稿できなかった分は翌日 7:00 以降に投稿する（翌日中まで）
    """
    ig = cfg["publishing"]["instagram"]
    local = now.astimezone(JST)
    if local.hour < QUIET_UNTIL or log.posted_today(now):
        return None
    today = local.date()
    yesterday = today - timedelta(days=1)
    feed_days = {DAYS[d] for d in ig.get("feed_days", [])}
    posted_dates = {v["posted_at"][:10] for v in log.data.values()}
    slots = ([today] if local.hour >= ig.get("feed_hour_jst", 20) else []) + [yesterday]
    for day in slots:
        for p in posts:
            if p.get("approved") and p["id"] not in log.data and str(p.get("date", "")) == day.isoformat():
                return p
        if day.weekday() in feed_days and day.isoformat() not in posted_dates:
            for p in posts:
                if p.get("approved") and p["id"] not in log.data and not p.get("date"):
                    return p
    return None


def caption_of(post: dict) -> str:
    return post["caption"].rstrip() + "\n\n" + " ".join(post.get("hashtags", []))


def reel_urls(post_id: str, site_url: str) -> tuple[str, str]:
    base = site_url.rstrip("/")
    return f"{base}/feed/{post_id}/reel.mp4", f"{base}/feed/{post_id}/cover.jpg"


def image_urls(post_id: str, count: int, site_url: str) -> list[str]:
    base = site_url.rstrip("/")
    return [f"{base}/feed/{post_id}/{i}.jpg" for i in range(1, count + 1)]
