"""歷史資料補抓 (過去 N 日)。與 main.py 使用同一份解析邏輯，差別在於資料寫入方式。"""
from __future__ import annotations

import datetime
import time
from datetime import timedelta

import requests
import urllib3
import yfinance as yf

from lib.logger import get_logger
from lib.parsers import parse_fubon_html
from lib.sheet import SheetNotReady, open_sheet

log = get_logger(__name__)

BASE_URL = (
    "https://fubon-ebrokerdj.fbs.com.tw/z/zg/zgb/zgb0.djhtm"
    "?a=9A00&b=0039004100390031&c=B"
)
HEADER_ROW = ["日期", "代號", "名稱", "買賣別", "買賣超金額(千)", "收盤價", "估算張數"]
DAYS_TO_CRAWL = 30
REQUEST_SLEEP = 3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_historical_price(stock_id: str, date_str: str) -> float | None:
    """查詢指定日期的收盤價，依序嘗試 .TW / .TWO。"""
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        next_day_str = (date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
    except ValueError:
        return None

    for suffix in (".TW", ".TWO"):
        ticker = f"{stock_id}{suffix}"
        try:
            data = yf.download(
                ticker, start=date_str, end=next_day_str, progress=False
            )
        except Exception as e:  # yfinance 內部例外類型多變
            log.debug(f"   yfinance {ticker} 失敗: {e}")
            continue
        if not data.empty:
            price = data["Close"].iloc[0]
            return float(price) if not isinstance(price, list) else float(price[0])
    return None


def _fetch_day(date_str: str) -> list[list]:
    """抓取單一日期的分點買賣超資料"""
    target_url = f"{BASE_URL}&e={date_str}&f={date_str}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(target_url, headers=headers, verify=False, timeout=15)
    except requests.RequestException as e:
        log.error(f"   ❌ 富邦請求失敗: {e}")
        return []

    response.encoding = "cp950"
    stocks = parse_fubon_html(response.text)
    if not stocks:
        log.warning("   ⚠️  該日期無資料 (可能是國定假日或颱風假)。")
        return []

    log.info(f"   🔍 找到 {len(stocks)} 筆分點資料，開始查歷史股價...")

    daily_data: list[list] = []
    for s in stocks:
        stock_id = s["id"]
        net_amt = s["net_amt"]
        status = "買超" if net_amt > 0 else ("賣超" if net_amt < 0 else "平")
        price = get_historical_price(stock_id, date_str)
        estimated_sheets = int(round(net_amt / price)) if price and price > 0 else "N/A"
        daily_data.append(
            [
                date_str,
                stock_id,
                s["name"],
                status,
                net_amt,
                price if price else "查無",
                estimated_sheets,
            ]
        )
    return daily_data


def crawl_history() -> None:
    try:
        sheet = open_sheet()
    except SheetNotReady as e:
        log.error(f"❌ Sheet 連線失敗: {e}")
        return

    if len(sheet.get_all_values()) == 0:
        sheet.append_row(HEADER_ROW)

    today = datetime.date.today()
    log.info(f"🚀 啟動歷史爬蟲：預計爬取過去 {DAYS_TO_CRAWL} 天資料...")
    log.info("-" * 50)

    for i in range(DAYS_TO_CRAWL, 0, -1):
        target_date = today - timedelta(days=i)
        date_str = target_date.strftime("%Y-%m-%d")

        if target_date.weekday() >= 5:
            day_char = "六日"[target_date.weekday() - 5]
            log.info(f"[{date_str}] 是週末 (週{day_char})，自動跳過。")
            continue

        log.info(f"[{date_str}] 正在處理中...")
        daily_data = _fetch_day(date_str)
        if daily_data:
            sheet.append_rows(daily_data)
            log.info(f"   ✅ 已寫入 {len(daily_data)} 筆資料。")

        log.info(f"   💤 休息 {REQUEST_SLEEP} 秒後繼續...")
        time.sleep(REQUEST_SLEEP)

    log.info("🎉 歷史資料補完計畫執行完畢！")


if __name__ == "__main__":
    crawl_history()
