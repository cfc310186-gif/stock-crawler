import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
from io import StringIO
import time
import os
import random

# --- 設定區 ---
SHEET_NAME = "Stock_Data"
JSON_FILE_NAME = "service_account.json"
BROKER_ID = "9A91"  # 永豐金-松山

# 【設定接關點】
# 如果上次跑到第 50 筆被擋，請將這裡改成 50，程式會跳過前 50 檔
START_INDEX = 48 

# 【Cookie 設定】
# 請填入您的 HiStock Cookie (三個引號包住)
HISTOCK_COOKIE = """fastivalName_Mall_20250901=closeday_fastivalName_Mall_20250901; bottomADName_20250901=closeday_bottomADName_20250901; _ga=GA1.2.883474851.1764853127; _gid=GA1.2.1138309835.1764853127; _gcl_au=1.1.1514633677.1764853127; ASP.NET_SessionId=ysaqiwctn35yvzrnghvmhwkx; fastivalName_Mall_20250901=closeday_fastivalName_Mall_20250901; bottomADName_20250901=closeday_bottomADName_20250901; _fbp=fb.1.1764853128332.914008156798017180; g_state={"i_l":0,"i_ll":1764859240603}; NickName=%e6%9c%b1%e6%88%90%e7%99%bc; MemberNo=237143; Email=cfc310186@gmail.com; FCCDCF=%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%2236fa5694-a897-4e1f-a361-0f21781bab77%5C%22%2C%5B1764853128%2C194000000%5D%5D%22%5D%5D%5D; FCNEC=%5B%5B%22AKsRol_SigZcC3HeRtE-2rN2YV6X0yl1u0Eap3N3jBnhcNudbLVyCoMNGMWcFYU5L_NQ0PFTHKNopt3CW0dlENaRbPcQSB909TRJ38vmMY6hPbmJS2zNjNBYN8TzMBb_PAT8uu_8pnaTImFr1yEap40SdYaHDRdDQg%3D%3D%22%5D%5D; _gat=1; _ga_S0YRRCXLNT=GS2.2.s1764858769$o2$g1$t1764859759$j60$l0$h0; __gads=ID=4e063a2b00eaa2bb:T=1764853127:RT=1764859758:S=ALNI_MbcZbkYFsYhcx-uy0GZW8Nz4brloQ; __gpi=UID=000011c2a0390cee:T=1764853127:RT=1764859758:S=ALNI_MYwDOZCjzWjIjuLF4qbz9AzClUyHw; __eoi=ID=b2587e00649fb403:T=1764853127:RT=1764859758:S=AA-AfjZbhiNRzqABXzKSn0Ty7qpf"""

def get_google_sheet_data():
    """讀取目前 Sheet 裡的所有資料"""
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE_NAME, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    data = sheet.get_all_values()
    return sheet, data

def fetch_histock_history(stock_id):
    url = f"https://histock.tw/stock/brokertrace.aspx?bno={BROKER_ID}&no={stock_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": HISTOCK_COOKIE
    }

    # 重試機制
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 【策略調整】休息久一點 (5 ~ 10 秒)
            sleep_time = random.uniform(5.0, 10.0)
            print(f"(休息 {int(sleep_time)}s)...", end=" ", flush=True)
            time.sleep(sleep_time)
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                print(f"⚠️ 狀態 {response.status_code}", end=" ")
                if response.status_code in [403, 503, 429]:
                    print("⛔ 被擋，冷卻 2 分鐘...")
                    time.sleep(120) # 延長冷卻到 2 分鐘
                    continue 
                if response.status_code == 302:
                     print("⛔ Cookie 失效，請更新！")
                     return {}
                return {} 

            dfs = pd.read_html(StringIO(response.text))
            target_df = None
            
            for df in dfs:
                if "買進均價" in df.columns and "日期" in df.columns:
                    target_df = df
                    break
            
            if target_df is None:
                return {}

            history_map = {}
            for _, row in target_df.iterrows():
                date_str = str(row["日期"]).replace("/", "-")
                try:
                    buy_vol = pd.to_numeric(row["買進張數"], errors='coerce')
                    buy_avg = pd.to_numeric(row["買進均價"], errors='coerce')
                    sell_vol = pd.to_numeric(row["賣出張數"], errors='coerce')
                    sell_avg = pd.to_numeric(row["賣出均價"], errors='coerce')
                    close_price = pd.to_numeric(row["收盤價"], errors='coerce')

                    net_vol = int(buy_vol - sell_vol)
                    total_buy_val = buy_vol * buy_avg
                    total_sell_val = sell_vol * sell_avg
                    net_amount = total_buy_val - total_sell_val
                    
                    real_cost = 0.0
                    if net_vol != 0:
                        real_cost = round((net_amount / net_vol), 1)
                    else:
                        real_cost = close_price 

                    net_amount_k = int(net_amount / 1000)
                    
                    history_map[date_str] = {
                        "real_cost": real_cost,
                        "net_vol": net_vol,
                        "net_amt_k": net_amount_k
                    }
                except:
                    continue
            
            return history_map

        except Exception as e:
            print(f"❌ 錯誤: {e}，重試...", end=" ")
            time.sleep(10)
    
    return {}

def main():
    print(f"🚀 啟動歷史資料清洗 (從第 {START_INDEX} 筆開始)...")
    
    if len(HISTOCK_COOKIE) < 10:
        print("❌ 請填入 Cookie！")
        return

    sheet, raw_data = get_google_sheet_data()
    
    if len(raw_data) < 2:
        print("⚠️ Sheet 是空的")
        return

    headers = raw_data[0]
    df = pd.DataFrame(raw_data[1:], columns=headers)
    
    unique_stocks = df["代號"].unique()
    print(f"📊 總股票數: {len(unique_stocks)}")
    
    # 【關鍵】切片：只處理從 START_INDEX 開始的股票
    target_stocks = unique_stocks[START_INDEX:]
    print(f"👉 本次將處理: {len(target_stocks)} 檔 (索引 {START_INDEX} ~ {len(unique_stocks)})")
    
    total_updated = 0
    
    for i, stock_id in enumerate(target_stocks):
        current_idx = START_INDEX + i
        print(f"\n[{current_idx}/{len(unique_stocks)}] 處理 {stock_id}", end=" ")
        
        hist_data = fetch_histock_history(stock_id)
        
        if not hist_data:
            print("無資料/跳過", end="")
            continue
            
        mask = df["代號"] == stock_id
        target_indices = df[mask].index
        
        match_count = 0
        for idx_row in target_indices:
            row_date = pd.to_datetime(df.at[idx_row, "日期"]).strftime('%Y-%m-%d')
            if row_date in hist_data:
                new_data = hist_data[row_date]
                df.at[idx_row, "買賣超金額(千)"] = new_data["net_amt_k"]
                df.at[idx_row, "收盤價"] = new_data["real_cost"]
                df.at[idx_row, "估算張數"] = new_data["net_vol"]
                match_count += 1
                total_updated += 1
        
        print(f"✅ 更新 {match_count} 筆", end=" ")
        
        # 每 10 檔存一次 (頻率高一點比較保險)
        if (i + 1) % 10 == 0:
            print(f"\n💾 存檔中...", end=" ")
            try:
                output_data = [df.columns.values.tolist()] + df.values.tolist()
                sheet.clear()
                sheet.update(output_data)
                print("🆗", end=" ")
            except Exception as e:
                print(f"⚠️ 失敗: {e}", end=" ")

    print(f"\n\n🎉 全部完成！共更新 {total_updated} 筆。")
    output_data = [df.columns.values.tolist()] + df.values.tolist()
    try:
        sheet.clear()
        sheet.update(output_data)
        print("✅ 最終寫入成功！")
    except Exception as e:
        print(f"❌ 最終寫入失敗: {e}")

if __name__ == "__main__":
    main()