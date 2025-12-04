import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
from io import StringIO
import time
import datetime
import os
import random
import yfinance as yf

# --- 設定區 ---
SHEET_NAME = "Stock_Data"
JSON_FILE_NAME = "service_account.json"
BROKER_ID = "9A91"  # 永豐金-松山

# 富邦證券網址
FUBON_URL = f"https://fubon-ebrokerdj.fubon.com.tw/z/zg/zgb/zgb0.djhtm?b={BROKER_ID}"

# --- 監控名單 (只針對這些股票抓精確成本) ---
WATCHLIST = [
    '3450', '3689', '3533', '3665', '3605', '3217', '6197', '3526', '6213', # AI
    '6279', '3023', '3003', '2460', '6290', '3501', # 車用
    '2317', '2392', '5457', '6205', '3092', '2462', '3511', # 消費電
    '6274', '2009', '2476', '1617' # 上游
]

def get_today_stock_list_from_fubon():
    print("🔍 正在從富邦證券抓取今日交易名單...")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(FUBON_URL, headers=headers, timeout=10)
        res.encoding = 'big5' 
        dfs = pd.read_html(StringIO(res.text))
        target_df = None
        for df in dfs:
            if '名稱' in df.columns and '買賣超金額' in df.columns:
                target_df = df
                break
        if target_df is None: return []

        stock_data = []
        for index, row in target_df.iterrows():
            try:
                raw_id = str(row[0]).strip()
                if not (raw_id.isdigit() and len(raw_id) >= 4): continue
                
                stock_id = raw_id
                stock_name = str(row[1]).strip()
                raw_amt = row['買賣超金額']
                net_amt_val = int(str(raw_amt).replace(',', ''))
                
                stock_data.append({
                    'id': stock_id,
                    'name': stock_name,
                    'net_amt': net_amt_val
                })
            except: continue
        
        seen = set()
        unique_stocks = []
        for s in stock_data:
            if s['id'] not in seen:
                unique_stocks.append(s)
                seen.add(s['id'])
        return unique_stocks
    except Exception as e:
        print(f"❌ 富邦爬取失敗: {e}")
        return []

def get_close_price_fallback(stock_id):
    """一般模式：使用 yfinance 抓取今日收盤價"""
    try:
        stock = yf.Ticker(f"{stock_id}.TW")
        hist = stock.history(period="1d")
        if not hist.empty:
            return float(hist.iloc[-1]['Close'])
        return 0.0
    except:
        return 0.0

def get_histock_details(stock_id):
    """精準模式：爬取 HiStock 真實成本"""
    url = f"https://histock.tw/stock/brokertrace.aspx?bno={BROKER_ID}&no={stock_id}"
    cookie_val = os.environ.get("HISTOCK_COOKIE", "")
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": cookie_val
    }

    try:
        time.sleep(random.uniform(1.0, 3.0)) # 只有監控名單會跑這裡，延遲可以保留
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200: return None

        dfs = pd.read_html(StringIO(response.text))
        target_df = None
        for df in dfs:
            if "買進均價" in df.columns and "日期" in df.columns:
                target_df = df
                break
        if target_df is None: return None

        latest_row = target_df.iloc[0]
        date_str = latest_row["日期"].replace("/", "-")
        
        buy_vol = pd.to_numeric(latest_row["買進張數"], errors='coerce')
        buy_avg = pd.to_numeric(latest_row["買進均價"], errors='coerce')
        sell_vol = pd.to_numeric(latest_row["賣出張數"], errors='coerce')
        sell_avg = pd.to_numeric(latest_row["賣出均價"], errors='coerce')
        close_price = pd.to_numeric(latest_row["收盤價"], errors='coerce')

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
        return {
            'date': date_str,
            'net_vol': net_vol,
            'cost': real_cost,
            'net_amt_k': net_amount_k
        }
    except Exception as e:
        print(f"   ⚠️ HiStock 異常 ({stock_id}): {e}")
        return None

def update_google_sheet(new_rows):
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
    if not os.path.exists(JSON_FILE_NAME):
        if "GCP_CREDENTIALS" in os.environ:
            with open(JSON_FILE_NAME, "w") as f:
                f.write(os.environ["GCP_CREDENTIALS"])
        else:
            print("❌ 找不到 service_account.json")
            return

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE_NAME, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1
        
        existing_data = sheet.get_all_values()
        existing_keys = set()
        if len(existing_data) > 1:
            for row in existing_data[1:]:
                if len(row) >= 2: existing_keys.add(f"{row[0]}_{row[1]}")
        
        rows_to_append = []
        for row in new_rows:
            key = f"{row[0]}_{row[1]}"
            if key not in existing_keys: rows_to_append.append(row)
        
        if rows_to_append:
            sheet.append_rows(rows_to_append)
            print(f"✅ 成功寫入 {len(rows_to_append)} 筆資料！")
        else:
            print("⚠️ 無新資料需寫入。")
    except Exception as e:
        print(f"❌ 寫入失敗: {e}")

def main():
    print("🚀 啟動混合式爬蟲 (Watchlist 精準 / 其他 估算)...")
    stock_list = get_today_stock_list_from_fubon()
    if not stock_list: return

    all_data = []
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    print(f"📝 準備分析 {len(stock_list)} 檔股票...")
    
    for i, stock_info in enumerate(stock_list):
        stock_id = stock_info['id']
        stock_name = stock_info['name']
        fubon_net_amt = stock_info['net_amt']
        
        print(f"[{i+1}/{len(stock_list)}] 分析 {stock_name} ({stock_id})...", end="\r")
        
        # 核心邏輯分支
        if stock_id in WATCHLIST:
            # 策略 A: 監控名單 -> 爬 HiStock 抓真實成本
            data = get_histock_details(stock_id)
            if data:
                row_data = [data['date'], stock_id, stock_name, data['net_amt_k'], data['cost'], data['net_vol']]
            else:
                # 備援: 監控名單但 HiStock 失敗 -> 降級為估算
                net_amt_k = int(fubon_net_amt / 1000)
                close = get_close_price_fallback(stock_id)
                est_vol = int(net_amt_k / close) if close > 0 else 0
                row_data = [today_str, stock_id, stock_name, net_amt_k, close, est_vol]
        else:
            # 策略 B: 非監控名單 -> 直接用富邦+yfinance 估算
            net_amt_k = int(fubon_net_amt / 1000)
            close = get_close_price_fallback(stock_id)
            est_vol = int(net_amt_k / close) if close > 0 else 0
            row_data = [today_str, stock_id, stock_name, net_amt_k, close, est_vol]

        all_data.append(row_data)
        
    print(f"\n✅ 分析完成，共 {len(all_data)} 筆。")
    if all_data:
        all_data.sort(key=lambda x: x[0], reverse=True)
        update_google_sheet(all_data)

if __name__ == "__main__":
    main()