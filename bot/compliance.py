"""法務部：投稿前の自動チェック。1つでも違反があれば投稿しない。

チェック根拠:
- ステマ規制（景品表示法、2023年10月〜）: 広告である旨の表示 → 「PR」必須
- Creators API利用規約 1(a)・4(m): API由来の価格・画像をSNSに載せない → 金額表記を禁止
- 景品表示法（有利誤認・優良誤認）: 根拠なく断定する表現を禁止
- X: 1投稿280字（日本語は1文字=2カウント → 実質140字）
"""
from __future__ import annotations

import re

BANNED_PHRASES = [
    "最安値", "日本一", "業界一", "No.1", "絶対", "必ず", "100%", "完全無料",
    "今だけ", "在庫限り", "激安", "破格", "神コスパ", "誰でも", "痩せ", "効果",
]
PRICE_PATTERN = re.compile(r"(¥|￥|円|\d+\s*%|\d+％|OFF|オフ)", re.IGNORECASE)


def x_weighted_length(text: str) -> int:
    """Xの文字数カウント（全角=2、URLは一律23）。"""
    text = re.sub(r"https?://\S+", "x" * 23, text)
    return sum(1 if ord(c) < 0x1100 else 2 for c in text)


def check_sns_text(text: str, platform: str) -> list[str]:
    errors: list[str] = []
    if "PR" not in text and "#PR" not in text and "広告" not in text:
        errors.append("広告である旨の表示（PR）がない")
    if PRICE_PATTERN.search(text):
        errors.append("価格・割引率の表記がある（API由来データをSNSに載せられない）")
    for w in BANNED_PHRASES:
        if w.lower() in text.lower():
            errors.append(f"禁止表現『{w}』を含む")
    if platform == "x" and x_weighted_length(text) > 280:
        errors.append("Xの文字数上限を超えている")
    if platform == "instagram" and text.count("#") > 30:
        errors.append("ハッシュタグが30個を超えている")
    return errors
