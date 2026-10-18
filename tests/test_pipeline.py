"""APIキーなしで、全部署の動作と規約ルールを確認するテスト。"""
from datetime import datetime, timezone
from pathlib import Path

import yaml

from bot import posts
from bot.amazon import MockClient
from bot.compliance import check_sns_text
from bot.config import ROOT, load_config
from bot.editorial import PostedLog, select_deals
from bot.site import build_site

NOW = datetime(2026, 10, 10, 3, 7, tzinfo=timezone.utc)


def _deals(cfg):
    client = MockClient(ROOT / "fixtures" / "search_sample.json")
    out = []
    for kw in cfg["research"]["keywords"]:
        for d in select_deals(client.search_items(kw, cfg["research"]), cfg, NOW):
            d.category = posts.category_of(kw)
            out.append(d)
    return out


def test_filters_follow_config():
    cfg = load_config()
    deals = _deals(cfg)
    assert deals, "サンプルからセール商品が1件以上選ばれるはず"
    r = cfg["research"]
    for d in deals:
        assert d.saving_percent >= r["min_saving_percent"]
        assert r["min_price_yen"] <= d.price <= r["max_price_yen"]
    assert all("サンプル4" not in d.title for d in deals), "在庫切れは除外されるはず"


def test_site_has_required_disclaimers(tmp_path):
    cfg = load_config()
    html = build_site(tmp_path, cfg, _deals(cfg), [], NOW).read_text(encoding="utf-8")
    assert "【PR】" in html
    assert "時点" in html
    assert "購入の時点でAmazon.co.jpに表示されている価格" in html
    assert "アマゾンジャパン合同会社" in html
    assert "Amazonアソシエイト・プログラムに参加" in html


def test_x_drafts_are_compliant_and_capped(tmp_path):
    cfg = load_config()
    log = PostedLog(tmp_path / "posted.json")
    created = posts.make_x_drafts(_deals(cfg), cfg, log, NOW, tmp_path)
    assert 0 < len(created) <= cfg["publishing"]["x"]["max_posts_per_day"]
    cats = set()
    for p in created:
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert d["compliance_errors"] == [], d
        assert d["approved"] is False  # 初期設定では人の承認が必要
        cats.add(d["category"])
    assert len(cats) == len(created), "1日の投稿でカテゴリが重複しない"
    # 同日にもう一度走らせても上限を超えない
    again = posts.make_x_drafts(_deals(cfg), cfg, log, NOW, tmp_path)
    assert len(created) + len(again) <= cfg["publishing"]["x"]["max_posts_per_day"]


def test_compliance_blocks_bad_text():
    assert check_sns_text("レディース靴が安い", "x")                     # PRなし
    assert check_sns_text("【PR】今なら30%OFF ￥3,980", "x")             # 価格・割引率
    assert check_sns_text("【PR】最安値のブーツ", "x")                   # 景表法リスク
    assert check_sns_text("【PR】秋のブーツがセール対象です", "x") == []


def test_story_image_has_no_product_data(tmp_path):
    cfg = load_config()
    p = posts.make_story_image(_deals(cfg), cfg, NOW, tmp_path)
    assert p and p.exists() and p.stat().st_size > 10_000


def test_feed_content_and_schedule(tmp_path):
    from datetime import datetime, timezone
    from bot import feed
    from bot.compliance import check_info_text
    cfg = load_config()
    posts_ = feed.load_posts(ROOT / "content" / "feed.yaml")
    assert len({p["id"] for p in posts_}) == len(posts_), "idが重複していない"
    for p in posts_:
        assert check_info_text(feed.caption_of(p)) == [], p["id"]
        if p.get("pr"):
            assert "PR" in feed.caption_of(p)
        assert 1 <= len(p["slides"]) <= 10
    counts = feed.render_all(posts_[:2], tmp_path, cfg)
    assert all((tmp_path / "feed" / pid / "1.jpg").exists() for pid in counts)
    for p in posts_:
        p["approved"] = True
    log = feed.FeedLog(tmp_path / "feed_posted.json")
    wed_21 = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)   # 水曜 21:00 JST
    wed_10 = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)    # 水曜 10:00 JST
    thu_21 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)   # 木曜
    assert feed.next_due(posts_, log, cfg, wed_10) is None
    assert feed.next_due(posts_, log, cfg, thu_21)["id"] == "pr-autumn-bags", "日付指定の投稿は曜日に関係なく出る"
    thu_other = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)   # 日付指定のない木曜（前日の水曜は未投稿）
    assert feed.next_due(posts_, log, cfg, thu_other)["id"] == posts_[0]["id"], "前日の取りこぼしは翌日に救済"
    tue_03 = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)      # 火曜 3:00 JST
    tue_09 = datetime(2026, 10, 13, 0, 0, tzinfo=timezone.utc)       # 火曜 9:00 JST
    tue_21 = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    assert feed.next_due(posts_, log, cfg, tue_03) is None, "深夜は投稿しない"
    assert feed.next_due(posts_, log, cfg, tue_09)["id"] == posts_[0]["id"], "月曜分を火曜の朝に救済"
    mon_log = feed.FeedLog(tmp_path / "mon.json")
    mon_log.mark("x", "m0", datetime(2026, 10, 12, 11, 30, tzinfo=timezone.utc))  # 月曜 20:30 に投稿済み
    assert feed.next_due(posts_, mon_log, cfg, tue_21) is None, "月曜に出ていれば火曜は何もしない"
    sat_lost = datetime(2026, 10, 19, 13, 0, tzinfo=timezone.utc)    # 月曜 22:00：10/17 の日付指定は2日前なので救済しない
    assert feed.next_due([p for p in posts_ if p.get("date") and str(p["date"]) <= "2026-10-17"], feed.FeedLog(tmp_path / "y.json"), cfg, sat_lost) is None
    first = feed.next_due(posts_, log, cfg, wed_21)
    assert first["id"] == posts_[0]["id"]
    log.mark(first["id"], "m1", wed_21)
    assert feed.next_due(posts_, log, cfg, wed_21) is None, "1日1件まで"
    fri = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    assert feed.next_due(posts_, log, cfg, fri)["id"] == posts_[1]["id"]
    posts_[0]["approved"] = False
    assert feed.next_due(posts_[:1], feed.FeedLog(tmp_path / "x.json"), cfg, wed_21) is None, "未承認は投稿しない"
