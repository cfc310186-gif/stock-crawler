import json
import random
import time

import pandas as pd
import requests

from lib.logger import get_logger
from lib.parsers import parse_histock_history
from lib.sheet import SheetNotReady, open_sheet, overwrite_sheet
from settings import BROKER_ID, PROGRESS_FILE

log = get_logger(__name__)


def _load_progress() -> dict:
    """讀取進度檔；格式 {'last_completed_index': int, 'timestamp': iso}"""
    if not PROGRESS_FILE.exists():
        return {}
    try:
        with PROGRESS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log.warning(f"⚠️ 進度檔讀取失敗，從頭開始: {e}")
        return {}


def _save_progress(last_completed_index: int) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_completed_index": last_completed_index,
        "timestamp": pd.Timestamp.now().isoformat(),
    }
    with PROGRESS_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _clear_progress() -> None:
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()

# 【Cookie 設定】
# 請填入您的 HiStock Cookie (三個引號包住)
HISTOCK_COOKIE = """fastivalName_Mall_20250901=closeday_fastivalName_Mall_20250901; bottomADName_20250901=closeday_bottomADName_20250901; _ga=GA1.2.883474851.1764853127; _gid=GA1.2.1138309835.1764853127; _gcl_au=1.1.1514633677.1764853127; ASP.NET_SessionId=ysaqiwctn35yvzrnghvmhwkx; fastivalName_Mall_20250901=closeday_fastivalName_Mall_20250901; bottomADName_20250901=closeday_bottomADName_20250901; _fbp=fb.1.1764853128332.914008156798017180; g_state={"i_l":0,"i_ll":1764859240603}; NickName=%e6%9c%b1%e6%88%90%e7%99%bc; MemberNo=237143; Email=cfc310186@gmail.com; FCCDCF=%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%2236fa5694-a897-4e1f-a361-0f21781bab77%5C%22%2C%5B1764853128%2C194000000%5D%5D%22%5D%5D%5D; FCNEC=%5B%5B%22AKsRol_SigZcC3HeRtE-2rN2YV6X0yl1u0Eap3N3jBnhcNudbLVyCoMNGMWcFYU5L_NQ0PFTHKNopt3CW0dlENaRbPcQSB909TRJ38vmMY6hPbmJS2zNjNBYN8TzMBb_PAT8uu_8pnaTImFr1yEap40SdYaHDRdDQg%3D%3D%22%5D%5D; _gat=1; _ga_S0YRRCXLNT=GS2.2.s1764858769$o2$g1$t1764859759$j60$l0$h0; __gads=ID=4e063a2b00eaa2bb:T=1764853127:RT=1764859758:S=ALNI_MbcZbkYFsYhcx-uy0GZW8Nz4brloQ; __gpi=UID=000011c2a0390cee:T=1764853127:RT=1764859758:S=ALNI_MYwDOZCjzWjIjuLF4qbz9AzClUyHw; __eoi=ID=b2587e00649fb403:T=1764853127:RT=1764859758:S=AA-AfjZbhiNRzqABXzKSn0Ty7qpf"""

def get_google_sheet_data():
    """讀取目前 Sheet 裡的所有資料 (沿用 lib.sheet 連線)"""
    sheet = open_sheet()
    return sheet, sheet.get_all_values()


def fetch_histock_history(stock_id):
    url = f"https://histock.tw/stock/brokertrace.aspx?bno={BROKER_ID}&no={stock_id}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": HISTOCK_COOKIE
    }

    max_retries = 3
    for _attempt in range(max_retries):
        try:
            sleep_time = random.uniform(5.0, 10.0)
            log.info(f"(休息 {int(sleep_time)}s)...")
            time.sleep(sleep_time)

            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code != 200:
                log.warning(f"⚠️ 狀態 {response.status_code}")
                if response.status_code in [403, 503, 429]:
                    log.warning("⛔ 被擋，冷卻 2 分鐘...")
                    time.sleep(120)
                    continue
                if response.status_code == 302:
                    log.error("⛔ Cookie 失效，請更新！")
                    return {}
                return {}

            return parse_histock_history(response.text)

        except requests.RequestException as e:
            log.warning(f"❌ 網路錯誤: {e}，重試...")
            time.sleep(10)

    return {}

def _flush_sheet(sheet, df: pd.DataFrame) -> None:
    """把目前的 DataFrame 覆寫回 Sheet"""
    overwrite_sheet(sheet, df)


def main():
    progress = _load_progress()
    start_index = int(progress.get("last_completed_index", -1)) + 1
    if start_index > 0:
        log.info(
            f"🔁 偵測到上次進度：從第 {start_index} 筆繼續 "
            f"({progress.get('timestamp', '?')})"
        )
    else:
        log.info("🚀 啟動歷史資料清洗 (從頭開始)...")

    if len(HISTOCK_COOKIE) < 10:
        log.error("❌ 請填入 Cookie！")
        return

    try:
        sheet, raw_data = get_google_sheet_data()
    except SheetNotReady as e:
        log.error(f"❌ Sheet 連線失敗: {e}")
        return

    if len(raw_data) < 2:
        log.warning("⚠️ Sheet 是空的")
        return

    headers = raw_data[0]
    df = pd.DataFrame(raw_data[1:], columns=headers)

    unique_stocks = df["代號"].unique()
    log.info(f"📊 總股票數: {len(unique_stocks)}")

    if start_index >= len(unique_stocks):
        log.info("✅ 所有股票都已處理過，重置進度並從頭開始。")
        _clear_progress()
        start_index = 0

    target_stocks = unique_stocks[start_index:]
    log.info(
        f"👉 本次將處理: {len(target_stocks)} 檔 "
        f"(索引 {start_index} ~ {len(unique_stocks) - 1})"
    )

    total_updated = 0

    try:
        for i, stock_id in enumerate(target_stocks):
            current_idx = start_index + i
            log.info(f"[{current_idx}/{len(unique_stocks)}] 處理 {stock_id}")

            hist_data = fetch_histock_history(stock_id)

            if not hist_data:
                log.info("   無資料/跳過")
                _save_progress(current_idx)
                continue

            mask = df["代號"] == stock_id
            target_indices = df[mask].index

            match_count = 0
            for idx_row in target_indices:
                row_date = pd.to_datetime(df.at[idx_row, "日期"]).strftime("%Y-%m-%d")
                if row_date in hist_data:
                    new_data = hist_data[row_date]
                    df.at[idx_row, "買賣超金額(千)"] = new_data["net_amt_k"]
                    df.at[idx_row, "收盤價"] = new_data["real_cost"]
                    df.at[idx_row, "估算張數"] = new_data["net_vol"]
                    match_count += 1
                    total_updated += 1

            log.info(f"   ✅ 更新 {match_count} 筆")
            _save_progress(current_idx)

            if (i + 1) % 10 == 0:
                log.info("💾 存檔中...")
                try:
                    _flush_sheet(sheet, df)
                    log.info("🆗 已寫入 Sheet。")
                except Exception as e:  # gspread 例外類型多樣
                    log.warning(f"⚠️ 寫入失敗: {e}")
    except KeyboardInterrupt:
        log.warning("⏸️ 手動中斷。進度已保存，下次執行將自動接續。")
        try:
            _flush_sheet(sheet, df)
            log.info("✅ 中斷前已寫入 Sheet。")
        except Exception as e:
            log.warning(f"⚠️ 中斷寫入失敗: {e}")
        return

    log.info(f"🎉 全部完成！共更新 {total_updated} 筆。")
    try:
        _flush_sheet(sheet, df)
        log.info("✅ 最終寫入成功！")
        _clear_progress()
        log.info("🧹 已清除進度檔。")
    except Exception as e:
        log.error(f"❌ 最終寫入失敗: {e}")


if __name__ == "__main__":
    main()
