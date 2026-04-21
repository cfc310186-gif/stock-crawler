import datetime
import re
import sys

import requests
import yfinance as yf

from lib.logger import get_logger
from lib.sheet import SheetNotReady, open_sheet

log = get_logger(__name__)
log.info("✅ 正在執行 main.py [v20.0 共用模組版]")

HEADER_ROW = ["日期", "代號", "名稱", "買賣別", "買賣超金額(千)", "收盤價", "估算張數"]


def check_and_get_date() -> str:
    today = datetime.date.today()
    weekday = today.weekday()  # 0=週一, ..., 5=週六, 6=週日
    if weekday >= 5:
        day_str = "週六" if weekday == 5 else "週日"
        log.info(f"😴 今天是 {today} ({day_str})，股市不開盤，程式自動休眠。")
        sys.exit(0)
    return today.strftime("%Y-%m-%d")


TARGET_DATE_STR = check_and_get_date()
log.info(f"📅 目標日期: {TARGET_DATE_STR}")


def get_today_stock_list_from_fubon():
    log.info("🔍 正在從富邦證券抓取交易名單...")

    base = "https://fubon-ebrokerdj.fbs.com.tw/z/zg/zgb/zgb0.djhtm"
    params_str = f"?a=9A00&b=0039004100390031&c=B&e={TARGET_DATE_STR}&f={TARGET_DATE_STR}"
    real_url = base + params_str

    log.info(f"   ☁️ 實際請求網址: {real_url}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        res = requests.get(real_url, headers=headers, timeout=15)
    except requests.RequestException as e:
        log.error(f"❌ 富邦請求失敗: {e}")
        return []

    raw_html = res.content.decode("big5", errors="ignore")

    pattern = (
        r"GenLink2stk\('AS(\d{4})','(.*?)'\);[\s\S]*?"
        r"<td[^>]*>\s*([0-9,]+)\s*</td>[\s\S]*?"
        r"<td[^>]*>\s*([0-9,]+)\s*</td>[\s\S]*?"
        r"<td[^>]*>\s*(-?[0-9,]+)\s*</td>"
    )
    matches = re.findall(pattern, raw_html)

    if not matches:
        log.warning("❌ Regex 找不到資料，請確認今日是否為交易日。")
        return []

    log.info(f"   🎉 成功抓取！Regex 掃描到 {len(matches)} 筆資料")

    stock_data = []
    for match in matches:
        try:
            stock_id = match[0]
            stock_name = match[1]
            net_amt_val = int(match[4].replace(",", ""))  # 單位已是千元
        except ValueError:
            continue
        stock_data.append({"id": stock_id, "name": stock_name, "net_amt": net_amt_val})

    seen = set()
    unique_stocks = []
    for s in stock_data:
        if s["id"] not in seen:
            unique_stocks.append(s)
            seen.add(s["id"])

    log.info(f"✅ 解析完成，抓到 {len(unique_stocks)} 檔股票。")
    return unique_stocks


def get_close_price_fallback(stock_id: str) -> float:
    """智慧嘗試 .TW (上市) 和 .TWO (上櫃)"""
    for suffix in (".TW", ".TWO"):
        ticker = f"{stock_id}{suffix}"
        try:
            hist = yf.Ticker(ticker).history(period="1d")
        except Exception as e:  # yfinance 內部例外類型多變
            log.debug(f"   yfinance {ticker} 失敗: {e}")
            continue
        if not hist.empty:
            return float(hist.iloc[-1]["Close"])

    log.warning(f"   ⚠️ 無法取得股價: {stock_id} (嘗試過 .TW/.TWO 皆失敗)")
    return 0.0


def update_google_sheet_overwrite(new_rows, target_date_str: str) -> None:
    try:
        sheet = open_sheet()
    except SheetNotReady as e:
        log.error(f"❌ Sheet 連線失敗: {e}")
        return

    log.info("💾 正在讀取 Google Sheet 現有資料...")
    all_values = sheet.get_all_values()

    if not all_values:
        final_data = [HEADER_ROW] + new_rows
        sheet.update(final_data)
        log.info(f"✅ 寫入完成 (全新資料)！共 {len(new_rows)} 筆")
        return

    header, old_data = all_values[0], all_values[1:]

    kept_data = []
    deleted_count = 0
    target_clean = target_date_str.replace("/", "-")

    for row in old_data:
        if not row:
            continue
        row_date = str(row[0]).replace("/", "-")
        if row_date != target_clean:
            kept_data.append(row)
        else:
            deleted_count += 1

    log.info(f"🧹 已清除 Sheet 中 {deleted_count} 筆舊的 {target_date_str} 資料。")

    final_data = [header] + kept_data + new_rows
    log.info(f"💾 正在回寫 Google Sheet (總筆數: {len(final_data) - 1})...")
    sheet.clear()
    sheet.update(final_data)
    log.info("✅ 更新成功！")


def main():
    log.info("🚀 啟動 main() 主程式...")
    stock_list = get_today_stock_list_from_fubon()
    if not stock_list:
        return

    all_data = []
    log.info(f"📝 準備分析 {len(stock_list)} 檔股票...")

    for i, stock_info in enumerate(stock_list):
        stock_id = stock_info["id"]
        stock_name = stock_info["name"]
        fubon_net_amt = stock_info["net_amt"]

        log.info(f"[{i + 1}/{len(stock_list)}] 分析 {stock_name} ({stock_id})...")

        final_cost = get_close_price_fallback(stock_id)
        final_vol = int(fubon_net_amt / final_cost) if final_cost > 0 else 0
        bs_type = "買超" if fubon_net_amt > 0 else ("賣超" if fubon_net_amt < 0 else "平盤")

        all_data.append(
            [
                TARGET_DATE_STR,
                stock_id,
                stock_name,
                bs_type,
                fubon_net_amt,
                final_cost,
                final_vol,
            ]
        )

    log.info(f"✅ 分析完成，共 {len(all_data)} 筆。")
    if all_data:
        all_data.sort(key=lambda x: abs(x[4]), reverse=True)
        update_google_sheet_overwrite(all_data, TARGET_DATE_STR)


if __name__ == "__main__":
    main()
