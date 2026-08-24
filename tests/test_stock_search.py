from __future__ import annotations

import pandas as pd

from lib.stock_search import build_stock_options, search_stocks


def test_build_stock_options_keeps_latest_name_per_stock() -> None:
    df = pd.DataFrame(
        [
            {"日期": pd.Timestamp("2026-01-01"), "代號": "2330", "名稱": "台積電"},
            {"日期": pd.Timestamp("2026-01-02"), "代號": "2330", "名稱": "台積電新"},
            {"日期": pd.Timestamp("2026-01-01"), "代號": "2303", "名稱": "聯電"},
        ]
    )

    options = build_stock_options(df)

    assert options.to_dict("records") == [
        {"代號": "2303", "名稱": "聯電"},
        {"代號": "2330", "名稱": "台積電新"},
    ]


def test_search_stocks_matches_id_and_name() -> None:
    df = pd.DataFrame(
        [
            {"日期": pd.Timestamp("2026-01-01"), "代號": "2330", "名稱": "台積電"},
            {"日期": pd.Timestamp("2026-01-01"), "代號": "2303", "名稱": "聯電"},
            {"日期": pd.Timestamp("2026-01-01"), "代號": "3231", "名稱": "緯創"},
        ]
    )

    by_id = search_stocks(df, "233")
    by_name = search_stocks(df, "聯")

    assert by_id[["代號", "名稱"]].to_dict("records") == [{"代號": "2330", "名稱": "台積電"}]
    assert by_name[["代號", "名稱"]].to_dict("records") == [{"代號": "2303", "名稱": "聯電"}]


def test_search_stocks_prioritises_exact_id() -> None:
    df = pd.DataFrame(
        [
            {"日期": pd.Timestamp("2026-01-01"), "代號": "2330", "名稱": "台積電"},
            {"日期": pd.Timestamp("2026-01-01"), "代號": "2337", "名稱": "旺宏"},
        ]
    )

    result = search_stocks(df, "2330")

    assert result.iloc[0]["代號"] == "2330"
