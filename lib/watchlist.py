"""Watchlist 讀寫模組 — 單一資料來源為 Google Sheet 的 Watchlist 分頁。

欄位格式：id | name | category
此設計讓 Streamlit Cloud (會寫入) 與 GitHub Actions (會讀取) 看到同一份資料，
避免檔案系統 ephemeral 導致的同步問題。
"""
from __future__ import annotations

from typing import Any

from settings import SHEET_NAME, WATCHLIST_SHEET_TAB

_DEFAULT_CATEGORY_EMOJIS = {
    "AI/高速傳輸": "🚀",
    "車用/工控": "🚗",
    "消費電子": "💻",
    "上游材料": "⚙️",
}

_HEADERS = ["id", "name", "category"]


def _get_worksheet() -> Any:
    """取得 Watchlist 分頁，找不到時自動建立並寫入標題列。"""
    import gspread  # 延遲 import，避免測試環境無 gspread 時炸掉

    from lib.sheet import get_client

    client = get_client()
    spreadsheet = client.open(SHEET_NAME)
    try:
        return spreadsheet.worksheet(WATCHLIST_SHEET_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(
            title=WATCHLIST_SHEET_TAB, rows=100, cols=len(_HEADERS)
        )
        ws.update([_HEADERS])
        return ws


def _load_rows(ws: Any = None) -> list[dict[str, str]]:
    """從 Sheet 讀出 [{id, name, category}]，保留原始順序。"""
    ws = ws if ws is not None else _get_worksheet()
    values = ws.get_all_values()
    if not values:
        return []
    header = values[0]
    try:
        idx_id = header.index("id")
        idx_name = header.index("name")
        idx_cat = header.index("category")
    except ValueError:
        return []

    rows: list[dict[str, str]] = []
    for row in values[1:]:
        # 容忍列長度不足
        padded = row + [""] * (len(header) - len(row))
        stock_id = str(padded[idx_id]).strip()
        if not stock_id:
            continue
        rows.append({
            "id": stock_id,
            "name": str(padded[idx_name]).strip() or stock_id,
            "category": str(padded[idx_cat]).strip() or "其他",
        })
    return rows


def _save_rows(rows: list[dict[str, str]], ws: Any = None) -> None:
    """把完整 rows 覆寫回 Sheet (含 header)。"""
    ws = ws if ws is not None else _get_worksheet()
    payload: list[list[str]] = [list(_HEADERS)]
    for item in rows:
        payload.append([
            str(item.get("id", "")),
            str(item.get("name", "")),
            str(item.get("category", "")),
        ])
    ws.clear()
    ws.update(payload)


def load_watchlist(ws: Any = None) -> dict[str, dict]:
    """回傳 {stock_id: {name, category, category_display}} dict。"""
    rows = _load_rows(ws)
    result: dict[str, dict] = {}
    for item in rows:
        stock_id = item["id"]
        category = item["category"]
        emoji = _DEFAULT_CATEGORY_EMOJIS.get(category, "")
        result[stock_id] = {
            "name": item["name"],
            "category": category,
            "category_display": f"{emoji} {category}".strip(),
        }
    return result


def list_ids(ws: Any = None) -> list[str]:
    """回傳所有 watchlist 股票代號 (保留 Sheet 中的順序)"""
    return [row["id"] for row in _load_rows(ws)]


def add_stock(
    stock_id: str,
    name: str,
    category: str,
    ws: Any = None,
) -> bool:
    """新增股票到 watchlist。已存在則更新 name/category，回傳 False。"""
    ws = ws if ws is not None else _get_worksheet()
    rows = _load_rows(ws)
    stock_id = str(stock_id)
    for item in rows:
        if item["id"] == stock_id:
            item["name"] = name
            item["category"] = category
            _save_rows(rows, ws)
            return False
    rows.append({"id": stock_id, "name": name, "category": category})
    _save_rows(rows, ws)
    return True


def remove_stock(stock_id: str, ws: Any = None) -> bool:
    """從 watchlist 移除股票。找不到回傳 False。"""
    ws = ws if ws is not None else _get_worksheet()
    rows = _load_rows(ws)
    stock_id = str(stock_id)
    before = len(rows)
    rows = [item for item in rows if item["id"] != stock_id]
    if len(rows) == before:
        return False
    _save_rows(rows, ws)
    return True


def get_categories(ws: Any = None) -> list[str]:
    """回傳目前所有使用中的分類名稱 (保留出現順序)，含預設分類兜底。"""
    rows = _load_rows(ws)
    seen: list[str] = []
    for item in rows:
        cat = item["category"]
        if cat not in seen:
            seen.append(cat)
    for cat in _DEFAULT_CATEGORY_EMOJIS:
        if cat not in seen:
            seen.append(cat)
    return seen


def get_category_emoji(category: str) -> str:
    return _DEFAULT_CATEGORY_EMOJIS.get(category, "")
