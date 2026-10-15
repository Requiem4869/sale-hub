"""配信部：承認済みのものだけを投稿する。

X:         POST https://api.x.com/2/tweets（OAuth 1.0a ユーザーコンテキスト）
           料金: 通常投稿 $0.015 / URL付き投稿 $0.20（2026年4月改定）
Instagram: Instagram API with Instagram Login（Facebookページ不要、プロアカウント）
           https://graph.instagram.com/{ver}/{ig-user-id}/media → /media_publish の2段階
           画像はJPEGを公開URLで渡す（GitHub Pages）。カルーセルは子コンテナ→親コンテナ→公開。
"""
from __future__ import annotations

import time
from datetime import datetime

import requests
import yaml

from .compliance import check_sns_text
from .config import secret

IG_API = "https://graph.instagram.com/v26.0"


# ---------- X ----------
def post_to_x(text: str) -> str:
    from requests_oauthlib import OAuth1

    auth = OAuth1(secret("X_API_KEY"), secret("X_API_SECRET"), secret("X_ACCESS_TOKEN"), secret("X_ACCESS_SECRET"))
    r = requests.post("https://api.x.com/2/tweets", json={"text": text}, auth=auth, timeout=30)
    r.raise_for_status()
    return r.json()["data"]["id"]


# ---------- Instagram ----------
def _ig_token() -> str:
    return secret("IG_ACCESS_TOKEN")


def _ig_user_id() -> str:
    uid = secret("IG_USER_ID", required=False)
    if uid:
        return uid
    r = requests.get(f"{IG_API}/me", params={"fields": "user_id,username", "access_token": _ig_token()}, timeout=30)
    r.raise_for_status()
    return str(r.json()["user_id"])


def _ig_post(path: str, data: dict) -> dict:
    r = requests.post(f"{IG_API}/{path}", data={**data, "access_token": _ig_token()}, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram API エラー {r.status_code}: {r.text[:500]}")
    return r.json()


def _ig_wait_ready(container_id: str, tries: int = 30, interval: int = 10) -> None:
    """コンテナの処理完了を待つ（Metaの推奨は1分おき・最大5分。ここでは10秒おき・最大5分）。"""
    last = ""
    for _ in range(tries):
        r = requests.get(f"{IG_API}/{container_id}", params={"fields": "status_code,status", "access_token": _ig_token()}, timeout=30)
        last = f"HTTP {r.status_code}: {r.text[:300]}"
        print(f"  コンテナ {container_id}: {last}", flush=True)
        body = r.json() if r.headers.get("content-type", "").startswith(("application/json", "text/javascript")) else {}
        status = body.get("status_code")
        if status in ("FINISHED", "PUBLISHED"):
            return
        if status in ("ERROR", "EXPIRED") or "error" in body:
            raise RuntimeError(f"Instagram側で画像の処理に失敗: {last}")
        time.sleep(interval)
    raise RuntimeError(f"Instagram側の画像処理が時間内に終わりませんでした（最後の応答 {last}）")


def post_feed_to_instagram(urls: list[str], caption: str) -> str:
    uid = _ig_user_id()
    if len(urls) == 1:
        cid = _ig_post(f"{uid}/media", {"image_url": urls[0], "caption": caption})["id"]
    else:
        children = []
        for u in urls[:10]:  # カルーセルは最大10枚
            children.append(_ig_post(f"{uid}/media", {"image_url": u, "is_carousel_item": "true"})["id"])
            print(f"  子コンテナ作成 {u} → {children[-1]}", flush=True)
        for c in children:
            _ig_wait_ready(c)
        cid = _ig_post(f"{uid}/media", {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})["id"]
    _ig_wait_ready(cid)
    return _ig_post(f"{uid}/media_publish", {"creation_id": cid})["id"]


def post_reel_to_instagram(video_url: str, caption: str, cover_url: str | None = None) -> str:
    """リールを投稿する（フィードにも表示）。動画の処理は数分かかることがあるので最大10分待つ。"""
    uid = _ig_user_id()
    data = {"media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true"}
    if cover_url:
        data["cover_url"] = cover_url
    cid = _ig_post(f"{uid}/media", data)["id"]
    print(f"  リールのコンテナ作成 → {cid}", flush=True)
    _ig_wait_ready(cid, tries=40, interval=15)
    return _ig_post(f"{uid}/media_publish", {"creation_id": cid})["id"]


def post_story_to_instagram(image_url: str) -> str:
    uid = _ig_user_id()
    cid = _ig_post(f"{uid}/media", {"image_url": image_url, "media_type": "STORIES"})["id"]
    _ig_wait_ready(cid)
    return _ig_post(f"{uid}/media_publish", {"creation_id": cid})["id"]


def refresh_ig_token() -> dict:
    """長期トークン（約60日）を延長する。発行から24時間以上経過・期限前である必要がある。"""
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": _ig_token()}, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------- 下書き（X）の投稿 ----------
def publish_drafts(drafts_dir, now: datetime, dry_run: bool = False) -> list[str]:
    results: list[str] = []
    for path in sorted(drafts_dir.glob("*-x-*.yaml")):
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        if d.get("posted") or not d.get("approved"):
            continue
        errors = check_sns_text(d["text"], "x")  # 人が編集した後でも必ず再チェック
        if errors:
            d["compliance_errors"] = errors
            d["approved"] = False
            results.append(f"差し戻し {path.name}: {', '.join(errors)}")
        elif dry_run:
            results.append(f"[dry-run] X投稿予定 {path.name}")
            continue
        else:
            d["post_id"] = post_to_x(d["text"])
            d["posted"] = True
            d["posted_at"] = now.isoformat(timespec="minutes")
            results.append(f"X投稿 {path.name} → {d['post_id']}")
        path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return results
