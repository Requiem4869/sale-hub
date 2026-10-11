"""配信部：承認済み（approved: true）の下書きだけを投稿する。

X:         POST https://api.x.com/2/tweets（OAuth 1.0a ユーザーコンテキスト）
           料金: 通常投稿 $0.015 / URL付き投稿 $0.20（2026年4月改定）
Instagram: Graph API コンテンツ公開（ビジネス/クリエイターアカウント必須、24時間25件まで）
           1) POST /{ig-user-id}/media  image_url=..., media_type=STORIES
           2) POST /{ig-user-id}/media_publish  creation_id=...
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import requests
import yaml

from .compliance import check_sns_text
from .config import secret

GRAPH_VERSION = "v23.0"  # Meta側の現行バージョンに合わせて更新すること


def post_to_x(text: str) -> str:
    from requests_oauthlib import OAuth1

    auth = OAuth1(secret("X_API_KEY"), secret("X_API_SECRET"), secret("X_ACCESS_TOKEN"), secret("X_ACCESS_SECRET"))
    r = requests.post("https://api.x.com/2/tweets", json={"text": text}, auth=auth, timeout=30)
    r.raise_for_status()
    return r.json()["data"]["id"]


def post_story_to_instagram(image_url: str) -> str:
    ig_id, token = secret("IG_USER_ID"), secret("IG_ACCESS_TOKEN")
    base = f"https://graph.facebook.com/{GRAPH_VERSION}/{ig_id}"
    r = requests.post(f"{base}/media", data={"image_url": image_url, "media_type": "STORIES", "access_token": token}, timeout=60)
    r.raise_for_status()
    r2 = requests.post(f"{base}/media_publish", data={"creation_id": r.json()["id"], "access_token": token}, timeout=60)
    r2.raise_for_status()
    return r2.json()["id"]


def publish_drafts(drafts_dir: Path, now: datetime, dry_run: bool = False) -> list[str]:
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
