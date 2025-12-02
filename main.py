import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import urllib3
import re 
import time
import yfinance as yf

# --- 設定區 ---
SHEET_NAME = "Stock_Data"
JSON_FILE_NAME = "service_account.json"
BASE_URL = "https://fubon-ebrokerdj.fbs.com.tw/z/zg/zgb/zgb0.djhtm?a=9A00&b=0039004100390031&c=B"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 輔助函式：查詢股價 ---
def get_stock_price(stock_id, date_str):
    try:
        # 1. 先嘗試上市股票代碼 (加 .TW)
        ticker = f"{stock_id}.TW"
        data = yf.download(ticker, period="1d", progress=False)
        
        if data.empty:
            # 2. 如果找不到，嘗試上櫃股票代碼 (加 .TWO)
            ticker = f"{stock_id}.TWO"
            data = yf.download(ticker, period="1d", progress=False)
        
        if not data.empty:
            price = data['Close'].iloc[-1]
            return float(price)
        else:
            return None 
            
    except Exception as e:
        # print(f"股價查詢失敗 ({stock_id}): {e}") # 保持版面乾淨，先不印錯誤
        return None

def crawl_and_save():
    # 1. 設定日期
    # 若要上線自動跑當天，請用這行：
    today = datetime.date.today().strftime('%Y-%m-%d')
    # 若要測試特定日期 (例如昨天)，請用這行：
    #today = "2025-12-02"
    
    print(f"[{today}] 開始執行爬蟲與計算任務 (精簡版)...")

    target_url = f"{BASE_URL}&e={today}&f={today}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        response = requests.get(target_url, headers=headers, verify=False)
        response.encoding = 'cp950'
        raw_text = response.text

        print("連線成功，正在抓取資料...")
        
        # 正規表達式 (抓取 ID, 名稱, 買進, 賣出, 差額)
        pattern = r"GenLink2stk\('([A-Z0-9]+)','([^']+)'\);[\s\S]*?>([-0-9,]+)<[\s\S]*?>([-0-9,]+)<[\s\S]*?>([-0-9,]+)<"
        matches = re.findall(pattern, raw_text)
        
        if not matches:
            print("❌ 找不到資料，可能是今日休市。")
            return

        print(f"🔍 抓到 {len(matches)} 筆資料，開始計算股價與張數...")

        cleaned_data = []
        for i, m in enumerate(matches):
            stock_id = m[0].replace('AS', '')
            stock_name = m[1]
            
            # 我們只需要計算 買賣超金額 (net_amt)
            # m[2]=買進, m[3]=賣出 (這兩個這次不存), m[4]=差額
            net_amt = int(m[4].replace(',', ''))
            
            # --- 判斷買賣別 ---
            if net_amt > 0:
                status = "買超"
            elif net_amt < 0:
                status = "賣超"
            else:
                status = "平"

            # --- 查詢收盤價 ---
            price = get_stock_price(stock_id, today)
            
            # --- 換算張數 (取整數) ---
            # 公式：金額(千元) / 收盤價 = 張數
            estimated_sheets = 0
            if price and price > 0:
                # 使用 round 四捨五入，再用 int 轉成整數
                estimated_sheets = int(round(net_amt / price, 0))
            else:
                estimated_sheets = "N/A"

            # 顯示進度
            if (i + 1) % 10 == 0:
                print(f"已處理 {i + 1}/{len(matches)} 筆...")

            # 整理資料列 (移除了買進/賣出金額)
            row = [
                today,            # 日期
                stock_id,         # 代號
                stock_name,       # 名稱
                status,           # 買賣別
                net_amt,          # 買賣超金額(千)
                price if price else "查無", # 收盤價
                estimated_sheets  # 估算張數(整數)
            ]
            cleaned_data.append(row)

        # 寫入 Google Sheet
        print("正在寫入 Google Sheet...")
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE_NAME, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1
        
        # 檢查標題列 (若為空則寫入新標題)
        if len(sheet.get_all_values()) == 0:
            header = ["日期", "代號", "名稱", "買賣別", "買賣超金額(千)", "收盤價", "估算張數"]
            sheet.append_row(header)

        sheet.append_rows(cleaned_data)
        print(f"🎉 成功！已將 {len(cleaned_data)} 筆精簡資料寫入試算表！")

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")

if __name__ == "__main__":
    crawl_and_save()