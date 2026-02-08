import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
import datetime
from linebot import LineBotApi
from linebot.models import TextSendMessage
import warnings
import yfinance as yf

# 忽略警告
warnings.filterwarnings("ignore", category=UserWarning)

# --- 設定區 ---
SHEET_NAME = "Stock_Data"
JSON_FILE_NAME = "service_account.json"
LINE_SECRET_FILE = "line_secret.json"

LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

if (not LINE_ACCESS_TOKEN or not LINE_USER_ID) and os.path.exists(LINE_SECRET_FILE):
    try:
        with open(LINE_SECRET_FILE, "r", encoding="utf-8") as f:
            secrets = json.load(f)
            LINE_ACCESS_TOKEN = secrets.get("LINE_ACCESS_TOKEN")
            LINE_USER_ID = secrets.get("LINE_USER_ID")
        print("💻 偵測到本機密碼檔，已載入 LINE 設定。")
    except Exception as e:
        print(f"⚠️ 讀取 line_secret.json 失敗: {e}")

# --- 監控名單 ---
WATCHLIST = {
    # 🚀 AI 與高速傳輸
    '3450': {'name': '聯鈞', 'category': '🚀 AI/高速傳輸'},
    '3689': {'name': '湧德', 'category': '🚀 AI/高速傳輸'},
    '3533': {'name': '嘉澤', 'category': '🚀 AI/高速傳輸'},
    '3665': {'name': '貿聯-KY', 'category': '🚀 AI/高速傳輸'},
    '3605': {'name': '宏致', 'category': '🚀 AI/高速傳輸'},
    '3217': {'name': '優群', 'category': '🚀 AI/高速傳輸'},
    '6197': {'name': '佳必琪', 'category': '🚀 AI/高速傳輸'},
    '3526': {'name': '凡甲', 'category': '🚀 AI/高速傳輸'},
    '6213': {'name': '聯茂', 'category': '🚀 AI/高速傳輸'},
    '3581': {'name': '博磊', 'category': '🚀 AI/高速傳輸'},
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
    '6274': {'name': '台燿', 'category': '⚙️ 上游材料'},
    '2009': {'name': '第一銅', 'category': '⚙️ 上游材料'},
    '2476': {'name': '鉅祥', 'category': '⚙️ 上游材料'},
    '1617': {'name': '榮星', 'category': '⚙️ 上游材料'}
}

def get_market_data(stock_id, target_date_str):
    """取得當日收盤價、漲跌幅、總成交量"""
    try:
        stock = yf.Ticker(f"{stock_id}.TW")
        hist = stock.history(period="1mo")
        hist.index = hist.index.strftime('%Y-%m-%d')
        
        if target_date_str in hist.index:
            target_idx = hist.index.get_loc(target_date_str)
            total_vol = int(hist.iloc[target_idx]['Volume'] / 1000)
            close_price = hist.iloc[target_idx]['Close'] # 當日市價
            
            if target_idx > 0:
                prev_close = hist.iloc[target_idx - 1]['Close']
                pct_change = round(((close_price - prev_close) / prev_close) * 100, 2)
            else:
                pct_change = 0.0
                
            return close_price, pct_change, total_vol
        else:
            return 0, 0, 0
    except Exception as e:
        print(f"⚠️ yfinance 失敗 ({stock_id}): {e}")
        return 0, 0, 0

def send_line_notify():
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        print("❌ 錯誤：找不到 LINE 金鑰。")
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

    headers = data[0]
    rows = data[1:]
    df = pd.DataFrame(rows, columns=headers)
    
    # 讀取 Sheet 時，請注意：對於 Watchlist 股票，'收盤價' 欄位其實是 '真實成本'
    # 對於非 Watchlist 股票，'收盤價' 欄位就是 '收盤價'
    
    df["日期"] = pd.to_datetime(df["日期"])
    today_date = datetime.date.today()
    if not df[df["日期"].dt.date == today_date].empty:
        target_date = today_date
    else:
        target_date = df["日期"].max().date()
        print(f"⚠️ 今日無資料，改用最新日期: {target_date}")

    target_date_str = target_date.strftime('%Y-%m-%d')
    daily_data = df[df["日期"].dt.date == target_date].copy()

    hits = []
    print(f"🔍 開始分析 {target_date} 資料 (讀取 Sheet 成本)...")

    for idx, row in daily_data.iterrows():
        stock_id = str(row['代號'])
        if stock_id in WATCHLIST:
            # 從 Sheet 讀取 (已經是 main.py 算好的結果)
            net_amt = int(row['買賣超金額(千)'].replace(',', ''))
            est_sheets = int(row['估算張數'].replace(',', '')) # 其實是真實淨張數
            sheet_cost_val = float(row['收盤價'].replace(',', '')) # 這是主力成本
            
            stock_info = WATCHLIST[stock_id]
            
            # 1. 取得今日市價行情 (yfinance)
            # 因為 Sheet 裡存的是成本，我們要另外抓市價來比較
            market_price, pct_change, total_vol = get_market_data(stock_id, target_date_str)
            
            # 如果 yfinance 抓不到 (假日或盤中)，市價暫時用成本價代替顯示，或顯示 N/A
            if market_price == 0: market_price = sheet_cost_val

            # 2. 集中度計算
            concentration = 0.0
            if total_vol > 0:
                concentration = round((est_sheets / total_vol) * 100, 1)
            
            # 3. 準備顯示字串
            if pct_change != 0:
                pct_str = f"+{pct_change}%" if pct_change > 0 else f"{pct_change}%"
                price_display = f"{market_price} ({pct_str})"
            else:
                price_display = f"{market_price}"

            trend_icon = "🔴" if net_amt > 0 else "🟢"
            
            hits.append({
                'id': stock_id,
                'name': stock_info['name'],
                'category': stock_info['category'],
                'price_display': price_display,
                'trend': trend_icon,
                'sheets': est_sheets,
                'amount': net_amt,
                'concentration': concentration,
                'cost': sheet_cost_val # 直接用 Sheet 裡的數值
            })

    if not hits:
        print("✅ 今日無供應鏈股票動態，不發送。")
        return

    hits.sort(key=lambda x: abs(x['amount']), reverse=True)

    # 組合訊息
    message = f"【連接器供應鏈】主力動向\n"
    message += f"📅 {target_date}\n"
    message += "----------------------\n"

    for h in hits:
        sheet_str = f"+{h['sheets']}" if h['sheets'] > 0 else f"{h['sheets']}"
        
        message += f"{h['category']}\n"
        message += f"{h['trend']} {h['name']} ({h['id']})\n"
        message += f"張數: {sheet_str} 張\n"
        message += f"集中: {h['concentration']}%\n"
        message += f"成本: {h['cost']}\n"
        message += f"金額: {h['amount']:,} 千\n"
        message += f"股價: {h['price_display']}\n"
        message += "----------------------\n"

    message += "詳細分析請看 App"

    try:
        line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
        line_bot_api.push_message(LINE_USER_ID, TextSendMessage(text=message))
        print("🎉 LINE 通知發送成功！")
    except Exception as e:
        print(f"❌ 發送失敗: {e}")

if __name__ == "__main__":
    send_line_notify()
