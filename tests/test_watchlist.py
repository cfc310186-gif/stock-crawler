"""Watchlist CRUD 讀寫 round-trip 測試 — 使用 tmp_path 避免動到 config/watchlist.yaml"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib import watchlist as wl


@pytest.fixture
def empty_path(tmp_path: Path) -> Path:
    return tmp_path / "watchlist.yaml"


@pytest.fixture
def seeded_path(tmp_path: Path) -> Path:
    path = tmp_path / "seeded.yaml"
    path.write_text(
        """
stocks:
  - id: "1111"
    name: Alpha
    category: AI/高速傳輸
  - id: "2222"
    name: Beta
    category: 車用/工控
category_emojis:
  AI/高速傳輸: "🚀"
  車用/工控: "🚗"
""",
        encoding="utf-8",
    )
    return path


def test_load_empty_returns_empty_dict(empty_path: Path) -> None:
    assert wl.load_watchlist(empty_path) == {}


def test_load_seeded(seeded_path: Path) -> None:
    data = wl.load_watchlist(seeded_path)
    assert set(data.keys()) == {"1111", "2222"}
    assert data["1111"]["name"] == "Alpha"
    assert data["1111"]["category"] == "AI/高速傳輸"
    assert "🚀" in data["1111"]["category_display"]


def test_add_new_stock(seeded_path: Path) -> None:
    added = wl.add_stock("3333", "Gamma", "消費電子", path=seeded_path)
    assert added is True
    reloaded = wl.load_watchlist(seeded_path)
    assert "3333" in reloaded
    assert reloaded["3333"]["name"] == "Gamma"


def test_add_existing_stock_updates(seeded_path: Path) -> None:
    added = wl.add_stock("1111", "Alpha2", "車用/工控", path=seeded_path)
    assert added is False  # 已存在 → False
    reloaded = wl.load_watchlist(seeded_path)
    assert reloaded["1111"]["name"] == "Alpha2"
    assert reloaded["1111"]["category"] == "車用/工控"


def test_remove_stock(seeded_path: Path) -> None:
    removed = wl.remove_stock("1111", path=seeded_path)
    assert removed is True
    reloaded = wl.load_watchlist(seeded_path)
    assert "1111" not in reloaded
    assert "2222" in reloaded  # 未動到的股票保留


def test_remove_missing_stock(seeded_path: Path) -> None:
    assert wl.remove_stock("9999", path=seeded_path) is False


def test_list_ids_preserves_order(seeded_path: Path) -> None:
    # 新增第三檔應該排在最後
    wl.add_stock("3333", "Gamma", "消費電子", path=seeded_path)
    assert wl.list_ids(seeded_path) == ["1111", "2222", "3333"]


def test_get_categories(seeded_path: Path) -> None:
    cats = wl.get_categories(seeded_path)
    assert "AI/高速傳輸" in cats
    assert "車用/工控" in cats


def test_get_category_emoji(seeded_path: Path) -> None:
    assert wl.get_category_emoji("AI/高速傳輸", path=seeded_path) == "🚀"
    # 未定義分類 fallback 空字串
    assert wl.get_category_emoji("未知分類", path=seeded_path) == ""
