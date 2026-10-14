"""分析部：Instagramの数字を集める（instagram_business_manage_insights 権限が必要）。

- アカウント：フォロワー数・投稿数
- 投稿ごと：リーチ・保存・いいね・コメント・シェア・合計反応（state/feed_posted.json の投稿が対象）
- 記録：state/insights.json（日付ごとのスナップショット。自分のアカウントの数字なので保存してよい）
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .config import secret
from .publish import IG_API

JST = timezone(timedelta(hours=9))
MEDIA_METRICS = ["reach", "saved", "likes", "comments", "shares", "total_interactions", "views"]


def _get(path: str, params: dict) -> requests.Response:
    return requests.get(f"{IG_API}/{path}", params={**params, "access_token": secret("IG_ACCESS_TOKEN")}, timeout=30)


def media_insights(media_id: str) -> dict:
    """まとめて取得し、失敗したら（未対応の指標が混ざっている等）1指標ずつ取り直す。"""
    r = _get(f"{media_id}/insights", {"metric": ",".join(MEDIA_METRICS)})
    if r.status_code == 200:
        return {d["name"]: d["values"][0]["value"] for d in r.json().get("data", [])}
    out: dict = {}
    for m in MEDIA_METRICS:
        r1 = _get(f"{media_id}/insights", {"metric": m})
        if r1.status_code == 200 and r1.json().get("data"):
            out[m] = r1.json()["data"][0]["values"][0]["value"]
    if not out:
        raise RuntimeError(f"インサイト取得に失敗（{r.status_code}）: {r.text[:300]}")
    return out


def collect(feed_state: Path, out_path: Path, now: datetime) -> dict:
    me = _get("me", {"fields": "user_id,username,followers_count,media_count"})
    if me.status_code != 200:
        raise RuntimeError(f"アカウント情報の取得に失敗（{me.status_code}）: {me.text[:300]}")
    acc = me.json()
    posted = json.loads(feed_state.read_text()) if feed_state.exists() else {}
    posts = {}
    for pid, rec in posted.items():
        posts[pid] = {"posted_at": rec["posted_at"], **media_insights(rec["media_id"])}
    snap = {"followers": acc.get("followers_count"), "media_count": acc.get("media_count"), "posts": posts}
    data = json.loads(out_path.read_text()) if out_path.exists() else {}
    data[now.astimezone(JST).date().isoformat()] = snap
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return snap


def summary(snap: dict) -> str:
    lines = [f"フォロワー {snap['followers']} ／ 投稿数 {snap['media_count']}"]
    for pid, m in snap["posts"].items():
        lines.append(f"- {pid}（{m['posted_at'][:10]}）: リーチ {m.get('reach', '-')} / 保存 {m.get('saved', '-')} / "
                     f"いいね {m.get('likes', '-')} / コメント {m.get('comments', '-')} / シェア {m.get('shares', '-')}")
    return "\n".join(lines)
