"""HTML 解析純函式 — 可在無網路情況下以 fixture 做 snapshot 測試。"""
from __future__ import annotations

import math
import re
from io import StringIO
from typing import Any

import pandas as pd

# --- Fubon 富邦分點買賣超 regex ---
# 原始 HTML 片段示例:
#   GenLink2stk('AS2330','台積電');...<td>1,234</td>...<td>5,678</td>...<td>-9,999</td>
# 三個 <td>：買進張數、賣出張數、買賣超金額(千)
_FUBON_PATTERN = re.compile(
    r"GenLink2stk\('AS(\d{4})','([^']+)'\);[\s\S]*?"
    r"<td[^>]*>\s*([0-9,]+)\s*</td>[\s\S]*?"
    r"<td[^>]*>\s*([0-9,]+)\s*</td>[\s\S]*?"
    r"<td[^>]*>\s*(-?[0-9,]+)\s*</td>"
)


def parse_fubon_html(raw_html: str) -> list[dict[str, Any]]:
    """解析富邦分點 HTML，回傳 [{id, name, buy_sheets, sell_sheets, net_amt}]。

    - id: 4 碼股票代號 (去掉 AS 前綴)
    - name: 股票名稱
    - buy_sheets / sell_sheets: 買進 / 賣出張數
    - net_amt: 買賣超金額 (千元，可能為負)

    依 id 去重 (保留第一筆)。
    """
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _FUBON_PATTERN.finditer(raw_html):
        stock_id = match.group(1)
        if stock_id in seen:
            continue
        seen.add(stock_id)
        try:
            buy_sheets = int(match.group(3).replace(",", ""))
            sell_sheets = int(match.group(4).replace(",", ""))
            net_amt = int(match.group(5).replace(",", ""))
        except ValueError:
            continue
        results.append(
            {
                "id": stock_id,
                "name": match.group(2),
                "buy_sheets": buy_sheets,
                "sell_sheets": sell_sheets,
                "net_amt": net_amt,
            }
        )
    return results


# --- HiStock 真實主力成本計算 ---
def calc_real_cost(
    buy_vol: float,
    buy_avg: float,
    sell_vol: float,
    sell_avg: float,
    close_price: float,
) -> dict[str, Any] | None:
    """根據 HiStock 一日分點明細算出真實主力成本。

    回傳 {real_cost, net_vol, net_amt_k}；任何必要欄位為 NaN 或缺失則回傳 None。
    - real_cost: 淨買賣超均價 (net_vol != 0)，否則用 close_price
    - net_vol: 買進 - 賣出 (張)
    - net_amt_k: 買賣超金額 / 1000 (千元)
    """
    vals = [buy_vol, buy_avg, sell_vol, sell_avg, close_price]
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals):
        return None

    net_vol = int(buy_vol - sell_vol)
    net_amount = buy_vol * buy_avg - sell_vol * sell_avg

    if net_vol != 0:
        real_cost = round(net_amount / net_vol, 1)
    else:
        real_cost = round(float(close_price), 1)

    return {
        "real_cost": real_cost,
        "net_vol": net_vol,
        "net_amt_k": int(net_amount / 1000),
    }


def parse_histock_history(raw_html: str) -> dict[str, dict[str, Any]]:
    """解析 HiStock 分點明細頁，回傳 {date_str: {real_cost, net_vol, net_amt_k}}。

    找出含 `買進均價` / `日期` 欄的表格後逐列算成本；無資料或缺欄回傳空 dict。
    """
    try:
        dfs = pd.read_html(StringIO(raw_html))
    except (ValueError, ImportError):
        return {}

    target_df = None
    for df in dfs:
        if "買進均價" in df.columns and "日期" in df.columns:
            target_df = df
            break
    if target_df is None:
        return {}

    history: dict[str, dict[str, Any]] = {}
    for _, row in target_df.iterrows():
        date_str = str(row["日期"]).replace("/", "-")
        try:
            buy_vol = pd.to_numeric(row["買進張數"], errors="coerce")
            buy_avg = pd.to_numeric(row["買進均價"], errors="coerce")
            sell_vol = pd.to_numeric(row["賣出張數"], errors="coerce")
            sell_avg = pd.to_numeric(row["賣出均價"], errors="coerce")
            close_price = pd.to_numeric(row["收盤價"], errors="coerce")
        except (KeyError, TypeError):
            continue

        cost = calc_real_cost(buy_vol, buy_avg, sell_vol, sell_avg, close_price)
        if cost is not None:
            history[date_str] = cost
    return history
