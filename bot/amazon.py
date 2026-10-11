"""リサーチ部：Amazon Creators API クライアント。

仕様の出典: Creators API ドキュメント（Using cURL / GetItems / SearchItems / OffersV2）
- トークン: Login with Amazon（日本は api.amazon.co.jp/auth/o2/token）, scope=creatorsapi::default
- API: https://creatorsapi.amazon/catalog/v1/getItems （searchItems は同じ命名規則と想定）
- 利用条件: 直近30日で10件以上の適格販売が必要（満たさないとAPIが使えない）
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

RESOURCES = [
    "itemInfo.title",
    "itemInfo.byLineInfo",
    "images.primary.large",
    "offersV2.listings.price",
    "offersV2.listings.availability",
    "offersV2.listings.dealDetails",
    "offersV2.listings.isBuyBoxWinner",
    "offersV2.listings.condition",
]


class CreatorsApiClient:
    def __init__(self, cfg: dict, client_id: str, client_secret: str):
        self.cfg = cfg["amazon"]
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._token_exp = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        r = requests.post(
            self.cfg["token_endpoint"],
            json={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "creatorsapi::default",
            },
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + int(body.get("expires_in", 3600))
        return self._token

    def _post(self, op: str, payload: dict, retries: int = 3) -> dict:
        url = f"{self.cfg['api_base']}/catalog/v1/{op}"
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "x-marketplace": self.cfg["marketplace"],
        }
        payload = {"marketplace": self.cfg["marketplace"], "partnerTag": self.cfg["partner_tag"], **payload}
        for attempt in range(retries):
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt * 2)  # 指数バックオフ（公式ベストプラクティス）
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return {}

    def search_items(self, keywords: str, research_cfg: dict) -> list[dict]:
        payload = {
            "keywords": keywords,
            "searchIndex": research_cfg.get("search_index", "All"),
            "itemCount": research_cfg.get("items_per_keyword", 10),
            "minSavingPercent": research_cfg.get("min_saving_percent"),
            "minPrice": research_cfg.get("min_price_yen"),   # 円は最小通貨単位＝1円
            "maxPrice": research_cfg.get("max_price_yen"),
            "minReviewsRating": research_cfg.get("min_reviews_rating"),
            "resources": RESOURCES,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        body = self._post("searchItems", payload)
        time.sleep(1.1)  # 1秒あたりの呼び出し上限を超えないように
        return (body.get("searchResult") or {}).get("items", [])

    def get_items(self, asins: list[str]) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(asins), 10):  # 1リクエスト最大10件
            body = self._post("getItems", {"itemIds": asins[i:i + 10], "itemIdType": "ASIN", "resources": RESOURCES})
            out += (body.get("itemsResult") or body.get("itemResults") or {}).get("items", [])
            time.sleep(1.1)
        return out


class MockClient:
    """APIキーなしで全工程をテストするための偽クライアント（fixtures/ のJSONを返す）。"""

    def __init__(self, fixture: Path):
        self.items = json.loads(fixture.read_text(encoding="utf-8"))["searchResult"]["items"]

    def search_items(self, keywords: str, research_cfg: dict) -> list[dict]:
        word = keywords.split()[-1]
        return [i for i in self.items if word in i["itemInfo"]["title"]["displayValue"]]

    def get_items(self, asins: list[str]) -> list[dict]:
        return [i for i in self.items if i["asin"] in asins]
