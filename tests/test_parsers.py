"""Parser 純函式 snapshot tests — 擋住富邦 / HiStock HTML 格式變動的迴歸點。"""
from __future__ import annotations

import pytest

from lib.parsers import (
    calc_real_cost,
    parse_fubon_html,
    parse_histock_history,
)


def test_parse_fubon_html_basic(fubon_html: str) -> None:
    results = parse_fubon_html(fubon_html)

    assert len(results) == 3  # 2330 重複應去重

    # 第一筆
    assert results[0] == {
        "id": "2330",
        "name": "台積電",
        "buy_sheets": 1234,
        "sell_sheets": 567,
        "net_amt": -12345,
    }
    # 第二筆
    assert results[1]["id"] == "3035"
    assert results[1]["net_amt"] == 8888
    # 平盤
    assert results[2]["id"] == "3443"
    assert results[2]["net_amt"] == 0


def test_parse_fubon_html_empty() -> None:
    assert parse_fubon_html("") == []
    assert parse_fubon_html("<html>no data</html>") == []


def test_parse_fubon_html_dedup() -> None:
    """同 id 重複只保留第一次出現"""
    html = """
    GenLink2stk('AS1234','Foo');<td>1</td><td>2</td><td>3</td>
    GenLink2stk('AS1234','Bar');<td>99</td><td>99</td><td>99</td>
    """
    results = parse_fubon_html(html)
    assert len(results) == 1
    assert results[0]["name"] == "Foo"
    assert results[0]["net_amt"] == 3


def test_calc_real_cost_net_buy() -> None:
    # 買 100 張 @ 50, 賣 50 張 @ 55 → net_vol=50, net_amount=(5000-2750)=2250
    # real_cost = 2250/50 = 45
    result = calc_real_cost(100, 50.0, 50, 55.0, 52.0)
    assert result == {"real_cost": 45.0, "net_vol": 50, "net_amt_k": 2}


def test_calc_real_cost_balanced_uses_close() -> None:
    # net_vol == 0 時，real_cost = close_price
    result = calc_real_cost(200, 48.5, 200, 49.0, 48.8)
    assert result["net_vol"] == 0
    assert result["real_cost"] == 48.8


def test_calc_real_cost_nan_returns_none() -> None:
    assert calc_real_cost(float("nan"), 50, 10, 55, 52) is None
    assert calc_real_cost(None, 50, 10, 55, 52) is None


def test_parse_histock_history(histock_html: str) -> None:
    pytest.importorskip("lxml")  # pd.read_html 需要 lxml/bs4
    history = parse_histock_history(histock_html)

    assert set(history.keys()) == {"2025-12-10", "2025-12-09", "2025-12-08"}

    dec10 = history["2025-12-10"]
    assert dec10["net_vol"] == 50
    assert dec10["real_cost"] == 45.0

    dec09 = history["2025-12-09"]
    assert dec09["net_vol"] == 0
    assert dec09["real_cost"] == 48.8


def test_parse_histock_history_missing_columns() -> None:
    pytest.importorskip("lxml")
    html = "<table><tr><th>代號</th><th>名稱</th></tr><tr><td>1234</td><td>Foo</td></tr></table>"
    assert parse_histock_history(html) == {}


def test_parse_histock_history_invalid() -> None:
    assert parse_histock_history("not html at all") == {}
