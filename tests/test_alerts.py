"""告警規則引擎測試"""
from __future__ import annotations

import pandas as pd

from lib.alerts import (
    _compute_consecutive_days,
    _safe_eval_condition,
    compute_rankings,
    evaluate_conditions,
    evaluate_rankings,
)

# ---- _safe_eval_condition ----

def test_safe_eval_basic_true() -> None:
    assert _safe_eval_condition("net_sheets > 0", {"net_sheets": 10})


def test_safe_eval_basic_false() -> None:
    assert not _safe_eval_condition("net_sheets > 0", {"net_sheets": -5})


def test_safe_eval_unknown_var_is_zero() -> None:
    # undefined vars default to 0
    assert not _safe_eval_condition("foo > 0", {})


def test_safe_eval_compound() -> None:
    vars_ = {"concentration": 8, "net_sheets": 100}
    assert _safe_eval_condition(
        "concentration >= 5 and net_sheets > 0", vars_
    )


def test_safe_eval_blocks_builtins() -> None:
    # __import__ 不應被允許
    assert not _safe_eval_condition("__import__('os')", {})


def test_safe_eval_blocks_print() -> None:
    assert not _safe_eval_condition("print('hi')", {})


def test_safe_eval_invalid_expr() -> None:
    assert not _safe_eval_condition("!@# not python", {})


# ---- _compute_consecutive_days ----

def _make_df(rows: list[tuple[str, str, int]]) -> pd.DataFrame:
    """rows: [(date_str, stock_id, net_sheets)]"""
    data = []
    for date, sid, sheets in rows:
        data.append({
            "日期": pd.Timestamp(date),
            "代號": sid,
            "名稱": f"股{sid}",
            "估算張數": sheets,
            "買賣超金額(千)": sheets * 50,
            "收盤價": 50.0,
        })
    return pd.DataFrame(data)


def test_consecutive_days_buy_streak() -> None:
    df = _make_df([
        ("2025-01-01", "1234", 100),
        ("2025-01-02", "1234", 200),
        ("2025-01-03", "1234", 50),
    ])
    buy, sell = _compute_consecutive_days(df, "1234", pd.Timestamp("2025-01-03"))
    assert buy == 3
    assert sell == 0


def test_consecutive_days_broken_by_sell() -> None:
    df = _make_df([
        ("2025-01-01", "1234", 100),
        ("2025-01-02", "1234", -50),  # 中斷
        ("2025-01-03", "1234", 200),
    ])
    buy, sell = _compute_consecutive_days(df, "1234", pd.Timestamp("2025-01-03"))
    assert buy == 1
    assert sell == 0


def test_consecutive_days_sell_streak() -> None:
    df = _make_df([
        ("2025-01-01", "1234", -100),
        ("2025-01-02", "1234", -200),
    ])
    buy, sell = _compute_consecutive_days(df, "1234", pd.Timestamp("2025-01-02"))
    assert buy == 0
    assert sell == 2


def test_consecutive_days_neutral_today() -> None:
    df = _make_df([
        ("2025-01-01", "1234", 100),
        ("2025-01-02", "1234", 0),
    ])
    buy, sell = _compute_consecutive_days(df, "1234", pd.Timestamp("2025-01-02"))
    assert buy == 0 and sell == 0


# ---- evaluate_conditions ----

def test_evaluate_conditions_hits() -> None:
    df = _make_df([
        ("2025-01-01", "1234", 100),
        ("2025-01-02", "1234", 200),
        ("2025-01-03", "1234", 50),
    ])
    rules = [
        {
            "kind": "condition",
            "name": "連買",
            "when": "consecutive_buy_days >= 3",
            "emoji": "⚡",
        },
        {
            "kind": "condition",
            "name": "無關規則",
            "when": "consecutive_sell_days >= 3",
            "emoji": "🧊",
        },
    ]
    hits = evaluate_conditions(
        df_full=df,
        stock_id="1234",
        stock_name="股1234",
        target_date=pd.Timestamp("2025-01-03"),
        market_price=50.0,
        concentration=0.0,
        rules=rules,
    )
    assert len(hits) == 1
    assert hits[0].rule_name == "連買"
    assert hits[0].stock_id == "1234"


def test_evaluate_conditions_skips_ranking_rules() -> None:
    df = _make_df([("2025-01-01", "1234", 100)])
    rules = [{"kind": "ranking", "name": "不會跑", "metric": "net_sheets"}]
    hits = evaluate_conditions(
        df_full=df,
        stock_id="1234",
        stock_name="股1234",
        target_date=pd.Timestamp("2025-01-01"),
        market_price=50.0,
        concentration=0.0,
        rules=rules,
    )
    assert hits == []


# ---- compute_rankings / evaluate_rankings ----

def test_compute_rankings_buy_top_n() -> None:
    df = _make_df([
        # 三日視窗
        ("2025-01-01", "1111", 100),
        ("2025-01-02", "1111", 200),
        ("2025-01-03", "1111", 300),  # 1111 總 600
        ("2025-01-01", "2222", 50),
        ("2025-01-02", "2222", 50),
        ("2025-01-03", "2222", 50),   # 2222 總 150
        ("2025-01-03", "3333", 400),  # 3333 總 400 (僅一日)
        ("2025-01-03", "4444", -500), # 賣超 → 不該進榜
    ])
    records = compute_rankings(
        df_full=df,
        target_date=pd.Timestamp("2025-01-03"),
        window_days=3,
        metric="net_sheets",
        direction="buy",
        top_n=2,
    )
    assert len(records) == 2
    assert records[0]["代號"] == "1111"
    assert records[0]["total"] == 600
    assert records[1]["代號"] == "3333"


def test_compute_rankings_sell_direction() -> None:
    df = _make_df([
        ("2025-01-01", "1111", -100),
        ("2025-01-02", "1111", -200),
        ("2025-01-01", "2222", -50),
        ("2025-01-01", "3333", 300),  # 買超 → 不會上榜
    ])
    records = compute_rankings(
        df_full=df,
        target_date=pd.Timestamp("2025-01-02"),
        window_days=2,
        metric="net_sheets",
        direction="sell",
        top_n=3,
    )
    assert len(records) == 2
    assert records[0]["代號"] == "1111"
    assert records[0]["total"] == -300


def test_compute_rankings_watchlist_filter() -> None:
    df = _make_df([
        ("2025-01-01", "1111", 500),
        ("2025-01-01", "2222", 1000),  # 金額大但不在 watchlist
    ])
    records = compute_rankings(
        df_full=df,
        target_date=pd.Timestamp("2025-01-01"),
        window_days=1,
        metric="net_sheets",
        direction="buy",
        top_n=5,
        watchlist_ids={"1111"},
    )
    assert len(records) == 1
    assert records[0]["代號"] == "1111"


def test_compute_rankings_unknown_metric() -> None:
    df = _make_df([("2025-01-01", "1111", 100)])
    assert compute_rankings(
        df_full=df,
        target_date=pd.Timestamp("2025-01-01"),
        window_days=1,
        metric="bogus",
        direction="buy",
        top_n=3,
    ) == []


def test_evaluate_rankings_returns_payload() -> None:
    df = _make_df([("2025-01-01", "1111", 500)])
    rules = [
        {
            "kind": "ranking",
            "name": "買超排行",
            "window_days": 1,
            "metric": "net_sheets",
            "direction": "buy",
            "top_n": 3,
            "emoji": "🏆",
        }
    ]
    result = evaluate_rankings(
        df_full=df,
        target_date=pd.Timestamp("2025-01-01"),
        rules=rules,
    )
    assert "買超排行" in result
    payload = result["買超排行"]
    assert payload["emoji"] == "🏆"
    assert payload["metric"] == "net_sheets"
    assert len(payload["records"]) == 1
