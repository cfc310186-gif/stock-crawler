print("✅ 正在執行 main.py [v16.0 假日自動休息版]")

import requests
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import datetime
import os
import random
import yfinance as yf
import re
import sys
from io import StringIO

# --- 設定區 ---
SHEET_NAME = "Stock_Data"
JSON_FILE_NAME = "service_account.json"
BROKER_ID = "9A91" 

# --- 📅 日期檢查與設定 ---
def check_and_get_date():
    today = datetime.date.today()
    weekday = today.weekday() # 0=週一, ..., 5=週六, 6=週日
    
    if weekday == 5 or weekday == 6:
        day_str = "週六" if weekday == 5 else "週日"
        print(f"😴 今天是 {today} ({day_str})，股市不開盤，程式自動休眠。")
        sys.exit(0) # 正常結束程式 (Exit Code 0)
    
    return today.strftime('%Y-%m-%d')

# 取得目標日期 (如果是假日，上面那行就會直接結束程式，不會往下跑)
TARGET_DATE_STR = check_and_get_date()
print(f"📅 目標日期: {TARGET_DATE_STR} (平日，開始工作)")

# --- 監控名單 ---
WATCHLIST = [
    '3450', '3689', '3533', '3665', '3605', '3217', '6197', '3526', '6213',
    '6279', '3023', '3003', '2460', '6290', '3501',
    '2317', '2392', '5457', '6205', '3092', '2462', '3511',
    '6274', '2009', '2476', '1617'
]

def get_today_stock_list_from_fubon():
    print("🔍 正在從富邦證券抓取交易名單...")
    
    # 網址拼接
    base = "https://fubon-ebrokerdj.fbs.com.tw/z/zg/zgb/zgb0.djhtm"
    params_str = f"?a=9A00&b=0039004100390031&c=B&e={TARGET_DATE_STR}&f={TARGET_DATE_STR}"
    real_url = base + params_str
    
    print(f"   ☁️ 實際請求網址: {real_url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        res = requests.get(real_url, headers=headers, timeout=15)
        
        # 強制 Big5 解碼
        try:
            raw_html = res.content.decode('big5', errors='ignore')
        except:
            raw_html = res.content.decode('cp950', errors='ignore')

        # Regex 解析 (允許 td 內有空白)
        pattern = r"GenLink2stk\('AS(\d{4})','(.*?)'\);[\s\S]*?<td[^>]*>\s*([0-9,]+)\s*</td>[\s\S]*?<td[^>]*>\s*([0-9,]+)\s*</td>[\s\S]*?<td[^>]*>\s*(-?[0-9,]+)\s*</td>"
        
        matches = re.findall(pattern, raw_html)
        
        if not matches:
            print("❌ Regex 找不到資料，請確認今日是否為交易日或報表尚未產出。")
            return []
            
        print(f"   🎉 成功抓取！Regex 掃描到 {len(matches)} 筆資料")
        
        stock_data = []
        for match in matches:
            try:
                stock_id = match[0]
                stock_name = match[1]
                # match[4] 是差額(淨買賣)，需移除逗號
                raw_net_amt = match[4].replace(',', '')
                net_amt_val = int(raw_net_amt) # 單位已是千元
                
                stock_data.append({
                    'id': stock_id,
                    'name': stock_name,
                    'net_amt': net_amt_val
                })
            except:
                continue
        
        # 去重
        seen = set()
        unique_stocks = []
        for s in stock_data:
            if s['id'] not in seen:
                unique_stocks.append(s)
                seen.add(s['id'])
                
        print(f"✅ 解析完成，抓到 {len(unique_stocks)} 檔股票。")
        return unique_stocks

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        return []

def get_close_price_fallback(stock_id):
    try:
        stock = yf.Ticker(f"{stock_id}.TW")
        hist = stock.history(period="1d")
        if not hist.empty:
            return float(hist.iloc[-1]['Close'])
        return 0.0
    except:
        return 0.0

def get_histock_details(stock_id, target_date_str):
    url = f"https://histock.tw/stock/brokertrace.aspx?bno={BROKER_ID}&no={stock_id}"
    cookie_val = os.environ.get("HISTOCK_COOKIE", "")
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": cookie_val}

    try:
        time.sleep(random.uniform(1.0, 3.0)) 
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200: return None

        dfs = pd.read_html(StringIO(response.text))
        target_df = None
        for df in dfs:
            if "買進均價" in df.columns and "日期" in df.columns:
                target_df = df
                break
        if target_df is None: return None

        found_row = None
        for index, row in target_df.iterrows():
            raw_date = str(row["日期"])
            formatted_date = raw_date.replace("/", "-")
            try:
                parts = formatted_date.split("-")
                if len(parts) == 3:
                    formatted_date = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
            except: pass
                
            if formatted_date == target_date_str:
                found_row = row
                break
        
        if found_row is None: return None

        buy_vol = pd.to_numeric(found_row["買進張數"], errors='coerce')
        sell_vol = pd.to_numeric(found_row["賣出張數"], errors='coerce')
        close_price = pd.to_numeric(found_row["收盤價"], errors='coerce')

        # 成本計算
        buy_avg = pd.to_numeric(found_row["買進均價"], errors='coerce')
        sell_avg = pd.to_numeric(found_row["賣出均價"], errors='coerce')
        
        net_vol = int(buy_vol - sell_vol)
        total_buy_val = buy_vol * buy_avg
        total_sell_val = sell_vol * sell_avg
        net_amount_calc = total_buy_val - total_sell_val
        
        real_cost = 0.0
        if net_vol != 0:
            real_cost = round((net_amount_calc / net_vol), 1)
        else:
            real_cost = close_price

        # HiStock 金額轉千元
        net_amt_k = int(net_amount_calc / 1000)
        
        return {
            'date': target_date_str,
            'net_vol': net_vol, 
            'cost': real_cost, 
            'net_amt_k': net_amt_k
        }
        
    except Exception as e:
        return None

def update_google_sheet_overwrite(new_rows, target_date_str):
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
        
        print("💾 正在讀取 Google Sheet 現有資料...")
        all_values = sheet.get_all_values()
        
        if not all_values:
            header = ["日期", "代號", "名稱", "買賣別", "買賣超金額(千)", "收盤價", "估算張數"]
            final_data = [header] + new_rows
            sheet.update(final_data)
            print(f"✅ 寫入完成 (全新資料)！共 {len(new_rows)} 筆")
            return

        header = all_values[0]
        old_data = all_values[1:]
        
        kept_data = []
        deleted_count = 0
        target_clean = target_date_str.replace("/", "-")
        
        for row in old_data:
            if not row: continue
            row_date = str(row[0]).replace("/", "-")
            
            if row_date != target_clean:
                kept_data.append(row)
            else:
                deleted_count += 1
                
        print(f"🧹 已清除 Sheet 中 {deleted_count} 筆舊的 {target_date_str} 資料。")
        
        final_data = [header] + kept_data + new_rows
        
        print(f"💾 正在回寫 Google Sheet (總筆數: {len(final_data)-1})...")
        sheet.clear()
        sheet.update(final_data)
        print("✅ 更新成功！")

    except Exception as e:
        print(f"❌ Google Sheet 寫入失敗: {e}")

def main():
    print("🚀 啟動 main() 主程式...")
    stock_list = get_today_stock_list_from_fubon()
    if not stock_list: return

    all_data = []
    
    print(f"📝 準備分析 {len(stock_list)} 檔股票 (目標日期: {TARGET_DATE_STR})...")
    
    for i, stock_info in enumerate(stock_list):
        stock_id = stock_info['id']
        stock_name = stock_info['name']
        fubon_net_amt = stock_info['net_amt'] 
        
        print(f"[{i+1}/{len(stock_list)}] 分析 {stock_name} ({stock_id})...", end="\r")
        
        final_date = TARGET_DATE_STR
        final_net_amt_k = fubon_net_amt
        final_cost = 0.0
        final_vol = 0
        
        is_precise_data = False
        if stock_id in WATCHLIST:
            data = get_histock_details(stock_id, TARGET_DATE_STR)
            if data:
                final_date = data['date']
                final_net_amt_k = data['net_amt_k']
                final_cost = data['cost']
                final_vol = data['net_vol']
                is_precise_data = True
        
        if not is_precise_data:
            final_cost = get_close_price_fallback(stock_id)
            final_vol = int(final_net_amt_k / final_cost) if final_cost > 0 else 0

        bs_type = "買超" if final_net_amt_k > 0 else "賣超"
        if final_net_amt_k == 0: bs_type = "平盤"

        row_data = [
            final_date,
            stock_id,
            stock_name,
            bs_type,
            final_net_amt_k,
            final_cost,
            final_vol
        ]

        all_data.append(row_data)
        
    print(f"\n✅ 分析完成，共 {len(all_data)} 筆。")
    if all_data:
        all_data.sort(key=lambda x: abs(x[4]), reverse=True)
        update_google_sheet_overwrite(all_data, TARGET_DATE_STR)

if __name__ == "__main__":
    main()