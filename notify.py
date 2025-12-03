import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
import datetime
from linebot import LineBotApi
from linebot.models import TextSendMessage
import warnings

# 忽略 LINE SDK 的舊版警告
warnings.filterwarnings("ignore", category=UserWarning)

# --- 設定區 (雙模式讀取) ---
SHEET_NAME = "Stock_Data"
JSON_FILE_NAME = "service_account.json"
LINE_SECRET_FILE = "line_secret.json"

# 1. 先嘗試從環境變數讀取 (GitHub 模式)
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

# 2. 如果環境變數是空的，且本地有密碼檔，就從檔案讀取 (本機模式)
if (not LINE_ACCESS_TOKEN or not LINE_USER_ID) and os.path.exists(LINE_SECRET_FILE):
    try:
        with open(LINE_SECRET_FILE, "r", encoding="utf-8") as f:
            secrets = json.load(f)
            LINE_ACCESS_TOKEN = secrets.get("LINE_ACCESS_TOKEN")
            LINE_USER_ID = secrets.get("LINE_USER_ID")
        print("💻 偵測到本機密碼檔，已載入 LINE 設定。")
    except Exception as e:
        print(f"⚠️ 讀取 line_secret.json 失敗: {e}")

# --- 🎯 監控名單與分類 ---
WATCHLIST = {
    # 🚀 AI 與高速傳輸
    '3533': {'name': '嘉澤', 'category': '🚀 AI/高速傳輸'},
    '3665': {'name': '貿聯-KY', 'category': '🚀 AI/高速傳輸'},
    '3605': {'name': '宏致', 'category': '🚀 AI/高速傳輸'},
    '3217': {'name': '優群', 'category': '🚀 AI/高速傳輸'},
    '6197': {'name': '佳必琪', 'category': '🚀 AI/高速傳輸'},
    '3526': {'name': '凡甲', 'category': '🚀 AI/高速傳輸'},
    '6213': {'name': '聯茂', 'category': '🚀 AI/高速傳輸'},

    # 🚗 車用與工控
    '6279': {'name': '胡連', 'category': '🚗 車用/工控'},
    '3023': {'name': '信邦', 'category': '🚗 車用/工控'},
    '3003': {'name': '健和興', 'category': '🚗 車用/工控'},
    '2460': {'name': '建通', 'category': '🚗 車用/工控'},
    '6290': {'name': '良維', 'category': '🚗 車用/工控'},
    '3501': {'name': '維熹', 'category': '🚗 車用/工控'},

    # 💻 消費性電子
    '2317': {'name': '鴻海', 'category': '💻 消費電子'},
    '2392': {'name': '正崴', 'category': '💻 消費電子'},
    '5457': {'name': '宣德', 'category': '💻 消費電子'},
    '6205': {'name': '詮欣', 'category': '💻 消費電子'},
    '3092': {'name': '鴻碩', 'category': '💻 消費電子'},
    '2462': {'name': '良得電', 'category': '💻 消費電子'},
    '3511': {'name': '矽瑪', 'category': '💻 消費電子'},

    # ⚙️ 上游材料
    '2009': {'name': '第一銅', 'category': '⚙️ 上游材料'},
    '2476': {'name': '鉅祥', 'category': '⚙️ 上游材料'},
    '1617': {'name': '榮星', 'category': '⚙️ 上游材料'}
}

def send_line_notify():
    # 檢查 Token 是否存在
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        print("❌ 錯誤：找不到 LINE 金鑰。請確認 GitHub Secrets 或 line_secret.json 設定正確。")
        return

    # 連線 Google Sheet
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
    if os.path.exists(JSON_FILE_NAME):
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE_NAME, scope)
    else:
        print("❌ 找不到 service_account.json")
        return

    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    data = sheet.get_all_values()
    
    if not data:
        print("⚠️ 試算表無資料")
        return

    # 資料處理
    headers = data[0]
    rows = data[1:]
    df = pd.DataFrame(rows, columns=headers)
    
    cols_to_num = ["買賣超金額(千)", "收盤價", "估算張數"]
    for col in cols_to_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    df["日期"] = pd.to_datetime(df["日期"])

    # 篩選日期
    today_date = datetime.date.today()
    if not df[df["日期"].dt.date == today_date].empty:
        target_date = today_date
    else:
        target_date = df["日期"].max().date()
        print(f"⚠️ 今日無資料，改用最新日期: {target_date}")

    daily_data = df[df["日期"].dt.date == target_date].copy()

    # 比對名單
    hits = []
    for idx, row in daily_data.iterrows():
        stock_id = str(row['代號'])
        if stock_id in WATCHLIST:
            net_amt = int(row['買賣超金額(千)'])
            est_sheets = int(row['估算張數'])
            price = float(row['收盤價'])
            stock_info = WATCHLIST[stock_id]
            
            # 設定漲跌圖示
            trend_icon = "🔴" if net_amt > 0 else "🟢"
            
            hits.append({
                'id': stock_id,
                'name': stock_info['name'],
                'category': stock_info['category'],
                'price': price,
                'trend': trend_icon,
                'sheets': est_sheets,
                'amount': net_amt
            })

    if not hits:
        print("✅ 今日無供應鏈股票動態，不發送。")
        return

    # 排序
    hits.sort(key=lambda x: abs(x['amount']), reverse=True)

    # 3. 組合訊息 (排版優化)
    message = f"⚡【連接器供應鏈】主力動向\n"
    message += f"📅 日期: {target_date}\n"
    message += "----------------------\n"

    for h in hits:
        sheet_str = f"+{h['sheets']}" if h['sheets'] > 0 else f"{h['sheets']}"
        
        # 類別標題
        message += f"{h['category']}\n"
        
        # 股名 + 代號 + 趨勢燈號
        message += f"{h['trend']} {h['name']} ({h['id']})\n"
        
        # 【新增】獨立一行顯示張數 (加強視覺)
        message += f"📊 張數: {sheet_str} 張\n"
        
        # 金額
        message += f"💰 金額: {h['amount']:,} 千\n"
        
        # 股價
        message += f"💵 股價: {h['price']}\n"
        
        message += "----------------------\n"

    message += "詳細分析請看 App"

    # 發送
    try:
        line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
        line_bot_api.push_message(LINE_USER_ID, TextSendMessage(text=message))
        print("🎉 LINE 通知發送成功！")
    except Exception as e:
        print(f"❌ 發送失敗: {e}")

if __name__ == "__main__":
    send_line_notify()