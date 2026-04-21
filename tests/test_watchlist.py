"""Watchlist CRUD 讀寫 round-trip 測試 — 以 FakeWorksheet 取代真實 Google Sheet。"""
from __future__ import annotations

import pytest

from lib import watchlist as wl


class FakeWorksheet:
    """模擬 gspread.Worksheet：支援 get_all_values / clear / update。"""

    def __init__(self, rows: list[list[str]] | None = None) -> None:
        self._rows: list[list[str]] = [list(r) for r in (rows or [])]

    def get_all_values(self) -> list[list[str]]:
        return [list(r) for r in self._rows]

    def update(self, data: list[list[str]]) -> None:
        self._rows = [list(r) for r in data]

    def clear(self) -> None:
        self._rows = []


@pytest.fixture
def empty_ws() -> FakeWorksheet:
    return FakeWorksheet()


@pytest.fixture
def seeded_ws() -> FakeWorksheet:
    return FakeWorksheet([
        ["id", "name", "category"],
        ["1111", "Alpha", "AI/高速傳輸"],
        ["2222", "Beta", "車用/工控"],
    ])


def test_load_empty_returns_empty_dict(empty_ws: FakeWorksheet) -> None:
    assert wl.load_watchlist(empty_ws) == {}


def test_load_seeded(seeded_ws: FakeWorksheet) -> None:
    data = wl.load_watchlist(seeded_ws)
    assert set(data.keys()) == {"1111", "2222"}
    assert data["1111"]["name"] == "Alpha"
    assert data["1111"]["category"] == "AI/高速傳輸"
    assert "🚀" in data["1111"]["category_display"]


def test_add_new_stock(seeded_ws: FakeWorksheet) -> None:
    added = wl.add_stock("3333", "Gamma", "消費電子", ws=seeded_ws)
    assert added is True
    reloaded = wl.load_watchlist(seeded_ws)
    assert "3333" in reloaded
    assert reloaded["3333"]["name"] == "Gamma"


def test_add_existing_stock_updates(seeded_ws: FakeWorksheet) -> None:
    added = wl.add_stock("1111", "Alpha2", "車用/工控", ws=seeded_ws)
    assert added is False  # 已存在 → False
    reloaded = wl.load_watchlist(seeded_ws)
    assert reloaded["1111"]["name"] == "Alpha2"
    assert reloaded["1111"]["category"] == "車用/工控"


def test_remove_stock(seeded_ws: FakeWorksheet) -> None:
    removed = wl.remove_stock("1111", ws=seeded_ws)
    assert removed is True
    reloaded = wl.load_watchlist(seeded_ws)
    assert "1111" not in reloaded
    assert "2222" in reloaded  # 未動到的股票保留


def test_remove_missing_stock(seeded_ws: FakeWorksheet) -> None:
    assert wl.remove_stock("9999", ws=seeded_ws) is False


def test_list_ids_preserves_order(seeded_ws: FakeWorksheet) -> None:
    wl.add_stock("3333", "Gamma", "消費電子", ws=seeded_ws)
    assert wl.list_ids(seeded_ws) == ["1111", "2222", "3333"]


def test_get_categories(seeded_ws: FakeWorksheet) -> None:
    cats = wl.get_categories(seeded_ws)
    assert "AI/高速傳輸" in cats
    assert "車用/工控" in cats


def test_get_category_emoji() -> None:
    assert wl.get_category_emoji("AI/高速傳輸") == "🚀"
    # 未定義分類 fallback 空字串
    assert wl.get_category_emoji("未知分類") == ""
