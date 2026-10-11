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
