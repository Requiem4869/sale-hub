"""編集部：API結果を「載せてよいセール商品」に絞り込む。

設計上の重要ルール（API利用規約 4(n)）:
  価格などの商品データは最長24時間しか保存できない。
  → 自前で価格履歴を貯めて「値下げ」を判定するのは不可。
  → 値下げ判定は Amazon 自身が返す savings.percentage / dealDetails だけで行う。
  → 永続保存するのは ASIN と「いつ投稿したか」だけ（state/posted.json）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class Deal:
    asin: str
    title: str
    brand: str
    url: str
    image_url: str | None
    price: int
    price_display: str
    basis_display: str | None
    saving_percent: int
    deal_badge: str | None
    deal_end_utc: str | None
    fetched_at_utc: str
    category: str = ""   # どの検索キーワード（自分で決めたカテゴリ名）で見つかったか

    def to_dict(self) -> dict:
        return asdict(self)


def _buybox_listing(item: dict) -> dict | None:
    listings = ((item.get("offersV2") or {}).get("listings")) or []
    for lst in listings:
        if lst.get("isBuyBoxWinner"):
            return lst
    return listings[0] if listings else None


def parse_item(item: dict, fetched_at: datetime) -> Deal | None:
    lst = _buybox_listing(item)
    if not lst:
        return None
    if (lst.get("availability") or {}).get("type") not in ("IN_STOCK", "IN_STOCK_SCARCE"):
        return None
    if (lst.get("condition") or {}).get("value", "New") != "New":
        return None
    price = lst.get("price") or {}
    money = price.get("money") or {}
    savings = price.get("savings") or {}
    if not money.get("amount") or not savings.get("percentage"):
        return None  # 割引情報がない＝セールではない
    info = item.get("itemInfo") or {}
    deal = lst.get("dealDetails") or {}
    img = (((item.get("images") or {}).get("primary") or {}).get("large") or {}).get("url")
    return Deal(
        asin=item["asin"],
        title=(info.get("title") or {}).get("displayValue", ""),
        brand=((info.get("byLineInfo") or {}).get("brand") or {}).get("displayValue", ""),
        url=item["detailPageURL"],
        image_url=img,
        price=int(money["amount"]),
        price_display=money.get("displayAmount", f"￥{int(money['amount']):,}"),
        basis_display=((price.get("savingBasis") or {}).get("money") or {}).get("displayAmount"),
        saving_percent=int(savings["percentage"]),
        deal_badge=deal.get("badge"),
        deal_end_utc=deal.get("endTime"),
        fetched_at_utc=fetched_at.astimezone(timezone.utc).isoformat(timespec="minutes"),
    )


def select_deals(items: list[dict], cfg: dict, fetched_at: datetime) -> list[Deal]:
    r = cfg["research"]
    seen: set[str] = set()
    deals: list[Deal] = []
    for it in items:
        d = parse_item(it, fetched_at)
        if not d or d.asin in seen:
            continue
        if d.saving_percent < r["min_saving_percent"]:
            continue
        if not (r["min_price_yen"] <= d.price <= r["max_price_yen"]):
            continue
        seen.add(d.asin)
        deals.append(d)
    # タイムセール（期限あり）を優先し、次に割引率の高い順
    deals.sort(key=lambda d: (d.deal_badge is None, -d.saving_percent))
    return deals[: cfg["editorial"]["max_items_on_site"]]


class PostedLog:
    """投稿済みASINと投稿時刻だけを保存する（価格は保存しない）。"""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}

    def recently_posted(self, asin: str, cooldown_h: int, now: datetime) -> bool:
        ts = self.data.get(asin)
        return bool(ts) and now - datetime.fromisoformat(ts) < timedelta(hours=cooldown_h)

    def mark(self, asin: str, now: datetime) -> None:
        self.data[asin] = now.astimezone(timezone.utc).isoformat(timespec="minutes")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1))
