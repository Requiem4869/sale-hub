"""制作部：ハブサイト（GitHub Pages）を生成する。

なぜハブサイトが必要か（API利用規約 1(a)・4(m)）:
  APIで取った商品画像・価格は「自分のサイト上でのみ」表示できる。
  X/Instagramに直接載せるのは不可 → SNSは自分の言葉で告知し、詳細はこのサイトへ誘導する。

規約対応:
  4(o) 価格の横に取得時刻、免責文言を表示
  4(q) Amazon提供コンテンツである旨の免責文言
  ステマ規制 ページ冒頭に広告（PR）である旨を明示
"""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .editorial import Deal

JST = timezone(timedelta(hours=9))

PRICE_DISCLAIMER = (
    "価格および発送可能時期は表示された日付/時刻の時点のものであり、変更される場合があります。"
    "本商品の購入においては、購入の時点でAmazon.co.jpに表示されている価格および発送可能時期の情報が適用されます。"
)
CONTENT_DISCLAIMER = (
    "本サイト上で表示されるコンテンツの一部は、アマゾンジャパン合同会社またはその関連会社により提供されたものです。"
    "これらのコンテンツは「現状有姿」で提供されており、随時変更または削除される場合があります。"
)
ASSOCIATE_NOTICE = "当サイトはAmazonアソシエイト・プログラムに参加しています。適格販売により収入を得ています。"
PR_NOTICE = "【PR】このページには広告（アフィリエイトリンク）が含まれます。"

CSS = """
:root{--bg:#fffaf7;--fg:#2b2320;--muted:#8a7a72;--card:#fff;--accent:#c4506a;--line:#efe3dc}
@media (prefers-color-scheme:dark){:root{--bg:#1d1917;--fg:#f3ebe6;--muted:#b3a59d;--card:#2a2421;--accent:#f08aa2;--line:#3a322e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:"Hiragino Sans","Noto Sans JP",sans-serif;line-height:1.6}
header,main,footer{max-width:960px;margin:0 auto;padding:16px}
h1{font-size:1.4rem;margin:.2em 0}.pr{display:inline-block;background:var(--accent);color:#fff;border-radius:4px;padding:2px 8px;font-size:.8rem}
.updated{color:var(--muted);font-size:.85rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;display:flex;flex-direction:column}
.card img{width:100%;aspect-ratio:1;object-fit:contain;background:#fff;border-radius:8px}
.badge{color:var(--accent);font-weight:700;font-size:.8rem}.title{font-size:.9rem;margin:.4em 0;flex:1}
.price{font-size:1.15rem;font-weight:700}.basis{color:var(--muted);text-decoration:line-through;font-size:.85rem;margin-left:6px}
.off{color:var(--accent);font-weight:700}.ts{color:var(--muted);font-size:.75rem}
.btn{display:block;text-align:center;margin-top:8px;padding:9px;border-radius:999px;background:var(--accent);color:#fff;text-decoration:none;font-weight:700}
footer{color:var(--muted);font-size:.75rem}
.hero{padding:8px 0 4px}.hero p{margin:.3em 0}
h2{font-size:1.1rem;margin:28px 0 12px;padding-left:10px;border-left:4px solid var(--accent)}
.empty{background:var(--card);border:1px dashed var(--line);border-radius:12px;padding:20px;text-align:center;color:var(--muted)}
.cal{list-style:none;padding:0;margin:0;display:grid;gap:8px}
.cal li{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;display:flex;gap:14px;align-items:baseline}
.cal b{color:var(--accent);min-width:3.2em}.cal small{color:var(--muted);margin-left:auto}
.tips{padding-left:1.2em}.tips li{margin:.4em 0}
.ig{display:inline-block;margin-top:6px;padding:9px 18px;border-radius:999px;border:1px solid var(--accent);color:var(--accent);text-decoration:none;font-weight:700}
"""

CALENDAR = [("1月", "初売り", "冬物・福袋"), ("3月", "新生活セール", "通勤靴・バッグ"), ("7月", "プライムデー", "夏物・定番品"),
            ("10月", "プライム感謝祭", "秋冬ブーツ"), ("11月", "ブラックフライデー", "年間で最大級")]
TIPS = ["サイズ感はレビューの「大きめ」「小さめ」の声を確認する",
        "サイズが合わないときに備えて、返品・交換の条件を購入前に見る",
        "合成皮革は雨に強くお手入れが簡単、本革は長く使えて足になじむ"]


def _jst(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(JST).strftime("%Y年%-m月%-d日 %H:%M")


def _card(d: Deal) -> str:
    e = html.escape
    img = f'<img src="{e(d.image_url)}" alt="{e(d.title[:60])}" loading="lazy">' if d.image_url else ""
    badge = f'<div class="badge">{e(d.deal_badge)}</div>' if d.deal_badge else ""
    basis = f'<span class="basis">{e(d.basis_display)}</span>' if d.basis_display else ""
    return f"""<article class="card">{img}{badge}
<div class="title">{e(d.title)}</div>
<div><span class="price">{e(d.price_display)}</span>{basis} <span class="off">{d.saving_percent}%OFF</span></div>
<div class="ts">（{_jst(d.fetched_at_utc)}時点 – <a href="#disclaimer">詳細はこちら</a>）</div>
<a class="btn" href="{e(d.url)}" rel="sponsored noopener" target="_blank">Amazonで見る</a></article>"""


def _manual_card(p: dict) -> str:
    e = html.escape
    cat = f'<div class="badge">{e(p["category"])}</div>' if p.get("category") else ""
    return f"""<article class="card">{cat}<div class="title"><strong>{e(p['name'])}</strong><br>{e(p.get('comment', ''))}</div>
<a class="btn" href="{e(p['link'])}" rel="sponsored noopener" target="_blank">Amazonで見る</a></article>"""


def build_site(out_dir: Path, cfg: dict, deals: list[Deal], manual_picks: list[dict], now: datetime) -> Path:
    name = html.escape(cfg["brand"]["account_name"])
    cards = "\n".join(_card(d) for d in deals) + "\n".join(_manual_card(p) for p in manual_picks)
    items = f'<div class="grid">{cards}</div>' if cards else \
        '<div class="empty">ただいま掲載中のアイテムはありません。<br>セールが始まったら、ここに一覧で掲載します。</div>'
    ig = html.escape(cfg["brand"].get("instagram_url", ""))
    ig_btn = f'<a class="ig" href="{ig}" target="_blank" rel="noopener">Instagramでセール開始をチェック</a>' if ig else ""
    cal = "".join(f"<li><b>{m}</b>{html.escape(n)}<small>{html.escape(t)}</small></li>" for m, n, t in CALENDAR)
    tips = "".join(f"<li>{html.escape(t)}</li>" for t in TIPS)
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{name}</title>
<meta name="robots" content="index,follow"><style>{CSS}</style></head><body>
<header><span class="pr">PR</span><h1>{name}</h1>
<p>{PR_NOTICE}</p><p class="updated">最終更新：{now.astimezone(JST).strftime('%Y年%-m月%-d日 %H:%M')}（1時間ごとに自動更新）</p></header>
<main>
<section class="hero"><p>20〜40代の女性に向けて、Amazonで見つけたレディースの靴・バッグ・お財布のセール情報をまとめています。</p>{ig_btn}</section>
<h2>掲載中のアイテム</h2>{items}
<h2>Amazonの大型セール 年間カレンダー</h2><ul class="cal">{cal}</ul>
<p class="ts">※開催時期は例年の目安です。年によって変わります。</p>
<h2>Amazonで靴やバッグを買うときのコツ</h2><ol class="tips">{tips}</ol>
</main>
<footer id="disclaimer"><p>{ASSOCIATE_NOTICE}</p><p><a href="privacy.html">プライバシーポリシー</a></p><p>{PRICE_DISCLAIMER}</p><p>{CONTENT_DISCLAIMER}</p></footer>
</body></html>"""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(page, encoding="utf-8")
    (out_dir / "privacy.html").write_text(_privacy_page(name), encoding="utf-8")
    return path


def _privacy_page(name: str) -> str:
    """プライバシーポリシー（Pinterest等のAPI申請に必要）。"""
    items = [
        ("収集する情報", "当サイトは、閲覧者の氏名・メールアドレスなどの個人情報を収集しません。お問い合わせフォームやコメント機能もありません。"),
        ("アクセス解析・Cookie", "当サイト自体はCookieを使用しません。ホスティング（GitHub Pages）の提供元がアクセスログを取得する場合があります。"),
        ("アフィリエイト", "当サイトはAmazonアソシエイト・プログラムに参加しています。Amazonへのリンクを経由して購入された場合、Amazonが購入の計測のためにCookieを使用することがあります。詳しくはAmazonのプライバシー規約をご確認ください。"),
        ("SNS連携", "当サイトの運営者は、自身のInstagram・Pinterestアカウントへの投稿のために各社のAPIを使用します。取得するのは運営者自身のアカウントの投稿・統計情報のみで、閲覧者の情報は取得しません。"),
        ("お問い合わせ", "本ポリシーに関するお問い合わせは、Instagramアカウント（@trend.information）のメッセージからお願いします。"),
    ]
    body = "".join(f"<h2>{html.escape(h)}</h2><p>{html.escape(t)}</p>" for h, t in items)
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>プライバシーポリシー｜{name}</title>
<style>{CSS}</style></head><body><header><h1>プライバシーポリシー</h1><p class="updated">制定日：2026年10月19日</p></header>
<main>{body}<p><a href="./">トップへ戻る</a></p></main></body></html>"""
