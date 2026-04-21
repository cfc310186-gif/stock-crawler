print("✅ 正在執行 main.py [v19.0 設定集中化版]")

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

from settings import SHEET_NAME, JSON_FILE_NAME

# --- 📅 日期檢查與設定 ---
def check_and_get_date():
    today = datetime.date.today()
    weekday = today.weekday() # 0=週一, ..., 5=週六, 6=週日

    if weekday == 5 or weekday == 6:
        day_str = "週六" if weekday == 5 else "週日"
        print(f"😴 今天是 {today} ({day_str})，股市不開盤，程式自動休眠。")
        sys.exit(0) # 正常結束

    return today.strftime('%Y-%m-%d')

TARGET_DATE_STR = check_and_get_date()
#TARGET_DATE_STR = "2025-12-8"
print(f"📅 目標日期: {TARGET_DATE_STR}")

def get_today_stock_list_from_fubon():
    print("🔍 正在從富邦證券抓取交易名單...")
    
    base = "https://fubon-ebrokerdj.fbs.com.tw/z/zg/zgb/zgb0.djhtm"
    params_str = f"?a=9A00&b=0039004100390031&c=B&e={TARGET_DATE_STR}&f={TARGET_DATE_STR}"
    real_url = base + params_str
    
    print(f"   ☁️ 實際請求網址: {real_url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        res = requests.get(real_url, headers=headers, timeout=15)
        
        try:
            raw_html = res.content.decode('big5', errors='ignore')
        except:
            raw_html = res.content.decode('cp950', errors='ignore')

        pattern = r"GenLink2stk\('AS(\d{4})','(.*?)'\);[\s\S]*?<td[^>]*>\s*([0-9,]+)\s*</td>[\s\S]*?<td[^>]*>\s*([0-9,]+)\s*</td>[\s\S]*?<td[^>]*>\s*(-?[0-9,]+)\s*</td>"
        
        matches = re.findall(pattern, raw_html)
        
        if not matches:
            print("❌ Regex 找不到資料，請確認今日是否為交易日。")
            return []
            
        print(f"   🎉 成功抓取！Regex 掃描到 {len(matches)} 筆資料")
        
        stock_data = []
        for match in matches:
            try:
                stock_id = match[0]
                stock_name = match[1]
                raw_net_amt = match[4].replace(',', '')
                net_amt_val = int(raw_net_amt) # 單位已是千元
                
                stock_data.append({
                    'id': stock_id,
                    'name': stock_name,
                    'net_amt': net_amt_val
                })
            except:
                continue
        
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
    """
    智慧嘗試 .TW (上市) 和 .TWO (上櫃)
    """
    suffixes = ['.TW', '.TWO'] # 優先試上市，再試上櫃
    
    for suffix in suffixes:
        try:
            ticker = f"{stock_id}{suffix}"
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            
            if not hist.empty:
                price = float(hist.iloc[-1]['Close'])
                # print(f"   ✅ 成功抓取股價: {ticker} = {price}") # 除錯用
                return price
        except:
            continue # 失敗就換下一個後綴試試看
            
    print(f"   ⚠️ 無法取得股價: {stock_id} (嘗試過 .TW/.TWO 皆失敗)")
    return 0.0

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
    print(f"📝 準備分析 {len(stock_list)} 檔股票...")
    
    for i, stock_info in enumerate(stock_list):
        stock_id = stock_info['id']
        stock_name = stock_info['name']
        fubon_net_amt = stock_info['net_amt'] 
        
        print(f"[{i+1}/{len(stock_list)}] 分析 {stock_name} ({stock_id})...", end="\r")
        
        final_date = TARGET_DATE_STR
        final_net_amt_k = fubon_net_amt
        
        # 取得股價 (智慧判斷 .TW/.TWO)
        final_cost = get_close_price_fallback(stock_id)
        
        # 估算張數
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