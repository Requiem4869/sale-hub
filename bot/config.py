"""設定と秘密情報の読み込み。秘密情報は必ず環境変数（GitHub Secrets）から読む。"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
JST_OFFSET_HOURS = 9


def load_config(path: Path | None = None) -> dict:
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def secret(name: str, required: bool = True) -> str | None:
    value = os.environ.get(name)
    if required and not value:
        raise RuntimeError(f"環境変数 {name} が未設定です（GitHub Secretsに登録してください）")
    return value
