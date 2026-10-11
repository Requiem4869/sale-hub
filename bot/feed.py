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


def render_all(posts: list[dict], public_dir: Path, cfg: dict) -> dict[str, int]:
    brand = cfg["brand"]["account_name"].split("｜")[0]
    handle = cfg["brand"].get("instagram_handle", "")
    counts = {}
    for p in posts:
        counts[p["id"]] = len(render_post(p, public_dir / "feed" / p["id"], brand, handle))
    return counts


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


def next_due(posts: list[dict], log: FeedLog, cfg: dict, now: datetime) -> dict | None:
    """今が投稿枠（指定曜日の指定時刻以降）で、今日まだ投稿していなければ、次の承認済み投稿を返す。"""
    ig = cfg["publishing"]["instagram"]
    local = now.astimezone(JST)
    if local.weekday() not in {DAYS[d] for d in ig.get("feed_days", [])}:
        return None
    if local.hour < ig.get("feed_hour_jst", 20) or log.posted_today(now):
        return None
    for p in posts:
        if p.get("approved") and p["id"] not in log.data:
            return p
    return None


def caption_of(post: dict) -> str:
    return post["caption"].rstrip() + "\n\n" + " ".join(post.get("hashtags", []))


def image_urls(post_id: str, count: int, site_url: str) -> list[str]:
    base = site_url.rstrip("/")
    return [f"{base}/feed/{post_id}/{i}.jpg" for i in range(1, count + 1)]
