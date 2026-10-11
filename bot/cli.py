"""社長室：全部署を順番に動かすコマンド。

  python -m bot.cli run [--mock]        毎時：リサーチ→編集→サイト生成→投稿下書き
  python -m bot.cli publish [--dry-run] 承認済み下書きの投稿＋ストーリーズ投稿
  python -m bot.cli status              下書きの状況を表示
  python -m bot.cli preview-feed        情報投稿の画像を一覧画像にまとめる（確認用）
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import feed, posts
from .amazon import CreatorsApiClient, MockClient
from .config import ROOT, load_config, secret
from .editorial import PostedLog, select_deals
from .site import build_site

JST = timezone(timedelta(hours=9))
PUBLIC = ROOT / "public"
DRAFTS = ROOT / "drafts"
STATE = ROOT / "state" / "posted.json"
FEED_YAML = ROOT / "content" / "feed.yaml"
FEED_STATE = ROOT / "state" / "feed_posted.json"


def cmd_run(args, cfg) -> None:
    now = datetime.now(timezone.utc)
    deals = []
    if cfg["phase"] >= 1 or args.mock:
        client = MockClient(ROOT / "fixtures" / "search_sample.json") if args.mock else \
            CreatorsApiClient(cfg, secret("AMAZON_CLIENT_ID"), secret("AMAZON_CLIENT_SECRET"))
        for kw in cfg["research"]["keywords"]:
            for d in select_deals(client.search_items(kw, cfg["research"]), cfg, now):
                d.category = posts.category_of(kw)
                deals.append(d)
        uniq = {d.asin: d for d in deals}
        deals = sorted(uniq.values(), key=lambda d: (d.deal_badge is None, -d.saving_percent))
        deals = deals[: cfg["editorial"]["max_items_on_site"]]
    picks_path = ROOT / "manual_picks.yaml"
    picks = (yaml.safe_load(picks_path.read_text(encoding="utf-8")) or []) if picks_path.exists() else []
    build_site(PUBLIC, cfg, deals, picks, now)
    print(f"サイト生成: 自動 {len(deals)}件 / 手動 {len(picks)}件")

    if FEED_YAML.exists():
        counts = feed.render_all(feed.load_posts(FEED_YAML), PUBLIC, cfg)
        print(f"情報投稿の画像: {len(counts)}件分を生成")

    if cfg["publishing"]["instagram"]["enabled"] and deals:
        story = posts.make_story_image(deals, cfg, now, PUBLIC / "stories")
        print(f"ストーリーズ画像: {story.name if story else 'なし'}")

    if cfg["publishing"]["x"]["enabled"] and deals:
        log = PostedLog(STATE)
        created = posts.make_x_drafts(deals, cfg, log, now, DRAFTS)
        log.save()
        for p in created:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
            mark = "自動承認" if d["approved"] else ("要修正" if d["compliance_errors"] else "承認待ち")
            print(f"X下書き [{mark}] {p.name}")


def cmd_publish(args, cfg) -> None:
    from .compliance import check_info_text
    from .config import secret
    from .publish import post_feed_to_instagram, post_story_to_instagram, publish_drafts

    now = datetime.now(timezone.utc)
    for line in publish_drafts(DRAFTS, now, dry_run=args.dry_run):
        print(line)

    ig = cfg["publishing"]["instagram"]
    if ig.get("feed_enabled") and FEED_YAML.exists():
        if not secret("IG_ACCESS_TOKEN", required=False) and not args.dry_run:
            print("情報投稿: Instagramのトークン未設定のためスキップ")
        else:
            log = feed.FeedLog(FEED_STATE)
            posts_ = feed.load_posts(FEED_YAML)
            post = feed.next_due(posts_, log, cfg, now)
            if not post:
                print("情報投稿: 今は投稿枠ではない、または承認済みのストックがない")
            else:
                cap = feed.caption_of(post)
                errors = check_info_text(cap)
                if errors:
                    print(f"情報投稿 差し戻し {post['id']}: {', '.join(errors)}")
                else:
                    urls = feed.image_urls(post["id"], len(post["slides"]), cfg["publishing"]["site_url"])
                    if args.dry_run:
                        print(f"[dry-run] 情報投稿予定 {post['id']}（{len(urls)}枚）")
                    else:
                        media_id = post_feed_to_instagram(urls, cap)
                        log.mark(post["id"], media_id, now)
                        log.save()
                        print(f"情報投稿 {post['id']} → {media_id}")
    if cfg["phase"] >= 1 and cfg["publishing"]["instagram"]["enabled"]:
        story = PUBLIC / "stories" / f"story-{now.astimezone(JST):%Y%m%d}.png"
        marker = ROOT / "state" / f"ig-{now.astimezone(JST):%Y%m%d}.done"
        if story.exists() and not marker.exists():
            url = cfg["publishing"]["site_url"].rstrip("/") + f"/stories/{story.name}"
            if args.dry_run:
                print(f"[dry-run] ストーリーズ投稿予定 {url}")
            else:
                print(f"ストーリーズ投稿 → {post_story_to_instagram(url)}")
                marker.write_text(now.isoformat())


def cmd_status(args, cfg) -> None:
    rows = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(DRAFTS.glob("*.yaml"))]
    summary = {
        "承認待ち": sum(1 for r in rows if not r["approved"] and not r["posted"] and not r["compliance_errors"]),
        "要修正": sum(1 for r in rows if r["compliance_errors"] and not r["posted"]),
        "投稿待ち": sum(1 for r in rows if r["approved"] and not r["posted"]),
        "投稿済み": sum(1 for r in rows if r["posted"]),
    }
    print(json.dumps(summary, ensure_ascii=False))


def cmd_preview_feed(args, cfg) -> None:
    from PIL import Image

    posts_ = feed.load_posts(FEED_YAML)
    out = ROOT / "preview"
    feed.render_all(posts_, out, cfg)
    for p in posts_:
        files = sorted((out / "feed" / p["id"]).glob("*.jpg"), key=lambda x: int(x.stem))
        sheet = Image.new("RGB", (len(files) * 280 + 20, 370), (240, 240, 240))
        for k, f in enumerate(files):
            sheet.paste(Image.open(f).resize((270, 338)), (10 + k * 280, 16))
        sheet.save(out / f"{p['id']}.png")
    print(f"確認用の一覧画像: {out}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="bot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--mock", action="store_true")
    p = sub.add_parser("publish"); p.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    sub.add_parser("preview-feed")
    args = ap.parse_args()
    cfg = load_config()
    {"run": cmd_run, "publish": cmd_publish, "status": cmd_status, "preview-feed": cmd_preview_feed}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
