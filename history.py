import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
from datetime import timedelta
import urllib3
import re
import time
import yfinance as yf

from settings import SHEET_NAME, JSON_FILE_NAME

BASE_URL = "https://fubon-ebrokerdj.fbs.com.tw/z/zg/zgb/zgb0.djhtm?a=9A00&b=0039004100390031&c=B"
DAYS_TO_CRAWL = 30  # 要往回抓幾天

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 輔助函式：查詢"特定日期"的股價 ---
def get_historical_price(stock_id, date_str):
    try:
        # yfinance 需要下一天才能鎖定當天，例如要抓 12-01，end 必須設 12-02
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        next_day = date_obj + timedelta(days=1)
        next_day_str = next_day.strftime('%Y-%m-%d')

        # 1. 嘗試上市
        ticker = f"{stock_id}.TW"
        data = yf.download(ticker, start=date_str, end=next_day_str, progress=False)
        
        if data.empty:
            # 2. 嘗試上櫃
            ticker = f"{stock_id}.TWO"
            data = yf.download(ticker, start=date_str, end=next_day_str, progress=False)
        
        if not data.empty:
            # 取得當日收盤價
            price = data['Close'].iloc[0]
            # 處理有時候回傳是 Series 的情況
            return float(price) if not isinstance(price, list) else float(price[0])
        else:
            return None 
            
    except Exception as e:
        return None

def crawl_history():
    # 準備 Google Sheet 連線
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE_NAME, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    
    # 若表格全空，先寫入標題
    if len(sheet.get_all_values()) == 0:
        header = ["日期", "代號", "名稱", "買賣別", "買賣超金額(千)", "收盤價", "估算張數"]
        sheet.append_row(header)

    # 設定迴圈：從 30 天前開始，一路跑到昨天
    # (為什麼不含今天？因為今天通常會由 main.py 自動跑，避免重複)
    today = datetime.date.today()
    
    print(f"🚀 啟動歷史爬蟲：預計爬取過去 {DAYS_TO_CRAWL} 天資料...")
    print("--------------------------------------------------")

    # range(30, 0, -1) 代表從 30 倒數到 1
    # 這樣寫入順序就是：30天前 -> 29天前 -> ... -> 昨天 (時間軸由舊到新)
    for i in range(DAYS_TO_CRAWL, 0, -1):
        target_date = today - timedelta(days=i)
        date_str = target_date.strftime('%Y-%m-%d')
        
        # --- 判斷假日 ---
        # weekday(): 0=週一, 4=週五, 5=週六, 6=週日
        if target_date.weekday() >= 5:
            print(f"[{date_str}] 是週末 (週{'六日'[target_date.weekday()-5]})，自動跳過。")
            continue

        print(f"\n[{date_str}] 正在處理中...")

        # 組合網址
        target_url = f"{BASE_URL}&e={date_str}&f={date_str}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

        try:
            # 抓取網頁
            response = requests.get(target_url, headers=headers, verify=False)
            response.encoding = 'cp950'
            raw_text = response.text
            
            # 正規表達式抓取
            pattern = r"GenLink2stk\('([A-Z0-9]+)','([^']+)'\);[\s\S]*?>([-0-9,]+)<[\s\S]*?>([-0-9,]+)<[\s\S]*?>([-0-9,]+)<"
            matches = re.findall(pattern, raw_text)

            if not matches:
                print(f"   ⚠️  該日期無資料 (可能是國定假日或颱風假)。")
                time.sleep(1) # 休息一下再換下一天
                continue

            print(f"   🔍 找到 {len(matches)} 筆分點資料，開始查歷史股價...")
            
            daily_data = []
            for m in matches:
                stock_id = m[0].replace('AS', '')
                stock_name = m[1]
                net_amt = int(m[4].replace(',', ''))
                
                # 買賣別
                if net_amt > 0: status = "買超"
                elif net_amt < 0: status = "賣超"
                else: status = "平"

                # 查詢歷史股價
                price = get_historical_price(stock_id, date_str)
                
                # 換算張數
                estimated_sheets = 0
                if price and price > 0:
                    estimated_sheets = int(round(net_amt / price, 0))
                else:
                    estimated_sheets = "N/A"

                row = [date_str, stock_id, stock_name, status, net_amt, price if price else "查無", estimated_sheets]
                daily_data.append(row)

            # 寫入該日資料 (整批寫入比較快)
            sheet.append_rows(daily_data)
            print(f"   ✅ 已寫入 {len(daily_data)} 筆資料。")

        except Exception as e:
            print(f"   ❌ 發生錯誤: {e}")

        # --- 關鍵：休息時間 ---
        # 每跑完一天，休息 3 秒，避免伺服器覺得我們是攻擊者
        print("   💤 休息 3 秒後繼續...")
        time.sleep(3)

    print("\n🎉 歷史資料補完計畫執行完畢！")

if __name__ == "__main__":
    crawl_history()