"""Watchlist 讀寫模組 — 單一資料來源為 config/watchlist.yaml"""
from __future__ import annotations

from pathlib import Path

import yaml

from settings import WATCHLIST_FILE

_DEFAULT_CATEGORY_EMOJIS = {
    "AI/高速傳輸": "🚀",
    "車用/工控": "🚗",
    "消費電子": "💻",
    "上游材料": "⚙️",
}


def _load_raw(path: Path = WATCHLIST_FILE) -> dict:
    if not path.exists():
        return {"stocks": [], "category_emojis": {}}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("stocks", [])
    data.setdefault("category_emojis", {})
    return data


def _save_raw(data: dict, path: Path = WATCHLIST_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_watchlist(path: Path = WATCHLIST_FILE) -> dict[str, dict]:
    """回傳 {stock_id: {name, category, category_display}} dict。

    category_display 預先組好 emoji + 名稱，方便 notify / app 直接顯示。
    """
    raw = _load_raw(path)
    emoji_map = {**_DEFAULT_CATEGORY_EMOJIS, **(raw.get("category_emojis") or {})}

    result: dict[str, dict] = {}
    for item in raw.get("stocks", []):
        stock_id = str(item["id"])
        category = item.get("category", "其他")
        emoji = emoji_map.get(category, "")
        result[stock_id] = {
            "name": item.get("name", stock_id),
            "category": category,
            "category_display": f"{emoji} {category}".strip(),
        }
    return result


def list_ids(path: Path = WATCHLIST_FILE) -> list[str]:
    """回傳所有 watchlist 股票代號 (保留 YAML 順序)"""
    return list(load_watchlist(path).keys())


def add_stock(
    stock_id: str,
    name: str,
    category: str,
    path: Path = WATCHLIST_FILE,
) -> bool:
    """新增股票到 watchlist。已存在則更新 name/category，回傳 False。"""
    raw = _load_raw(path)
    stock_id = str(stock_id)
    for item in raw["stocks"]:
        if str(item["id"]) == stock_id:
            item["name"] = name
            item["category"] = category
            _save_raw(raw, path)
            return False
    raw["stocks"].append({"id": stock_id, "name": name, "category": category})
    _save_raw(raw, path)
    return True


def remove_stock(stock_id: str, path: Path = WATCHLIST_FILE) -> bool:
    """從 watchlist 移除股票。找不到回傳 False。"""
    raw = _load_raw(path)
    stock_id = str(stock_id)
    before = len(raw["stocks"])
    raw["stocks"] = [s for s in raw["stocks"] if str(s["id"]) != stock_id]
    if len(raw["stocks"]) == before:
        return False
    _save_raw(raw, path)
    return True


def get_categories(path: Path = WATCHLIST_FILE) -> list[str]:
    """回傳目前所有使用中的分類名稱 (保留出現順序)"""
    raw = _load_raw(path)
    seen: list[str] = []
    for item in raw["stocks"]:
        cat = item.get("category", "其他")
        if cat not in seen:
            seen.append(cat)
    for cat in (raw.get("category_emojis") or {}).keys():
        if cat not in seen:
            seen.append(cat)
    return seen


def get_category_emoji(category: str, path: Path = WATCHLIST_FILE) -> str:
    raw = _load_raw(path)
    emoji_map = {**_DEFAULT_CATEGORY_EMOJIS, **(raw.get("category_emojis") or {})}
    return emoji_map.get(category, "")
