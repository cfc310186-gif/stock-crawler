"""通知告警規則引擎 — 由 config/alerts.yaml 驅動"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from settings import ALERTS_FILE

_ALLOWED_VARS = {
    "net_sheets",
    "net_amount_k",
    "concentration",
    "market_price",
    "avg_cost",
    "consecutive_buy_days",
    "consecutive_sell_days",
}


@dataclass
class AlertHit:
    """單一告警命中結果"""
    rule_name: str
    emoji: str
    stock_id: str
    stock_name: str
    extra: dict = field(default_factory=dict)


def load_alerts(path: Path = ALERTS_FILE) -> list[dict]:
    """讀取並過濾掉 disabled 規則"""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    rules = data.get("alerts") or []
    return [r for r in rules if r.get("enabled", True)]


def _safe_eval_condition(expr: str, variables: dict) -> bool:
    """受限 eval — 僅放行允許的變數，並禁用所有 builtins。

    表達式若引用未知變數或拋出例外，都視為不命中。
    """
    safe_globals = {"__builtins__": {}}
    safe_locals = {k: variables.get(k, 0) for k in _ALLOWED_VARS}
    try:
        return bool(eval(expr, safe_globals, safe_locals))
    except Exception:
        return False


def _compute_consecutive_days(
    df_full: pd.DataFrame,
    stock_id: str,
    target_date: pd.Timestamp,
) -> tuple[int, int]:
    """計算截至 target_date (含) 的連續買超 / 賣超日數"""
    rows = df_full[
        (df_full["代號"] == stock_id) & (df_full["日期"] <= target_date)
    ].sort_values("日期", ascending=False)

    buy_streak = 0
    sell_streak = 0
    first = True
    for _, r in rows.iterrows():
        sheets = r.get("估算張數", 0) or 0
        if first:
            if sheets > 0:
                buy_streak = 1
            elif sheets < 0:
                sell_streak = 1
            else:
                break
            first = False
            continue
        if buy_streak > 0 and sheets > 0:
            buy_streak += 1
        elif sell_streak > 0 and sheets < 0:
            sell_streak += 1
        else:
            break
    return buy_streak, sell_streak


def build_stock_metrics(
    df_full: pd.DataFrame,
    stock_id: str,
    target_date: pd.Timestamp,
    market_price: float,
    concentration: float,
) -> dict:
    """組出 condition 規則可用的變數集"""
    today_row = df_full[
        (df_full["代號"] == stock_id) & (df_full["日期"] == target_date)
    ]
    if today_row.empty:
        return {}

    row = today_row.iloc[0]
    buy_days, sell_days = _compute_consecutive_days(df_full, stock_id, target_date)

    return {
        "net_sheets": int(row.get("估算張數", 0) or 0),
        "net_amount_k": int(row.get("買賣超金額(千)", 0) or 0),
        "concentration": float(concentration or 0),
        "market_price": float(market_price or 0),
        "avg_cost": float(row.get("收盤價", 0) or 0),
        "consecutive_buy_days": buy_days,
        "consecutive_sell_days": sell_days,
    }


def evaluate_conditions(
    df_full: pd.DataFrame,
    stock_id: str,
    stock_name: str,
    target_date: pd.Timestamp,
    market_price: float,
    concentration: float,
    rules: list[dict],
) -> list[AlertHit]:
    """對單檔股票跑所有 condition 規則"""
    metrics = build_stock_metrics(
        df_full, stock_id, target_date, market_price, concentration
    )
    if not metrics:
        return []

    hits: list[AlertHit] = []
    for rule in rules:
        if rule.get("kind") != "condition":
            continue
        expr = rule.get("when", "")
        if _safe_eval_condition(expr, metrics):
            hits.append(
                AlertHit(
                    rule_name=rule.get("name", "未命名規則"),
                    emoji=rule.get("emoji", "📌"),
                    stock_id=stock_id,
                    stock_name=stock_name,
                    extra=dict(metrics),
                )
            )
    return hits


def compute_rankings(
    df_full: pd.DataFrame,
    target_date: pd.Timestamp,
    window_days: int,
    metric: str,
    direction: str,
    top_n: int,
    watchlist_ids: set[str] | None = None,
) -> list[dict]:
    """計算「近 N 日買/賣超前 M 大」— 預設對全 Sheet；傳入 watchlist_ids 則過濾到該集合。"""
    if metric not in {"net_sheets", "net_amount_k"}:
        return []

    col_map = {"net_sheets": "估算張數", "net_amount_k": "買賣超金額(千)"}
    target_col = col_map[metric]

    # 取最近 window_days 個「有資料」的交易日 (不是曆日)
    available_dates = sorted(
        df_full[df_full["日期"] <= target_date]["日期"].unique(), reverse=True
    )
    window_dates = available_dates[:window_days]
    if not window_dates:
        return []

    window_df = df_full[df_full["日期"].isin(window_dates)]
    if watchlist_ids:
        window_df = window_df[window_df["代號"].astype(str).isin(watchlist_ids)]

    if window_df.empty:
        return []

    agg = (
        window_df.groupby(["代號", "名稱"])[target_col]
        .sum()
        .reset_index()
        .rename(columns={target_col: "total"})
    )

    if direction == "buy":
        agg = agg[agg["total"] > 0].sort_values("total", ascending=False)
    elif direction == "sell":
        agg = agg[agg["total"] < 0].sort_values("total", ascending=True)
    else:
        return []

    return agg.head(top_n).to_dict("records")


def evaluate_rankings(
    df_full: pd.DataFrame,
    target_date: pd.Timestamp,
    rules: list[dict],
    watchlist_ids: set[str] | None = None,
) -> dict[str, dict]:
    """跑所有 ranking 規則。回傳 {rule_name: {emoji, records, metric, direction, window_days}}"""
    result: dict[str, list[dict]] = {}
    for rule in rules:
        if rule.get("kind") != "ranking":
            continue
        records = compute_rankings(
            df_full=df_full,
            target_date=target_date,
            window_days=int(rule.get("window_days", 3)),
            metric=str(rule.get("metric", "net_sheets")),
            direction=str(rule.get("direction", "buy")),
            top_n=int(rule.get("top_n", 3)),
            watchlist_ids=watchlist_ids,
        )
        if records:
            result[rule.get("name", "未命名排行")] = {
                "emoji": rule.get("emoji", "🏅"),
                "records": records,
                "metric": rule.get("metric", "net_sheets"),
                "direction": rule.get("direction", "buy"),
                "window_days": rule.get("window_days", 3),
            }
    return result
