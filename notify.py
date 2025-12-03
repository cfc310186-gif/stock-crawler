import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
import datetime
from linebot import LineBotApi
from linebot.models import TextSendMessage

# --- 設定區 ---
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID") # 這可以是您的 User ID 或群組 ID
SHEET_NAME = "Stock_Data"
JSON_FILE_NAME = "service_account.json"

# --- 🎯 監控名單與分類 (連接器供應鏈) ---
# 格式: '代號': {'name': '名稱', 'category': '分類描述'}
WATCHLIST = {
    # 🚀 AI 與高速傳輸概念
    '3533': {'name': '嘉澤', 'category': '🚀 AI/高速傳輸 (CPU Socket龍頭)'},
    '3665': {'name': '貿聯-KY', 'category': '🚀 AI/高速傳輸 (特斯拉/輝達概念)'},
    '3605': {'name': '宏致', 'category': '🚀 AI/高速傳輸 (雲端資料中心)'},
    '3217': {'name': '優群', 'category': '🚀 AI/高速傳輸 (DDR5連接器)'},
    '6197': {'name': '佳必琪', 'category': '🚀 AI/高速傳輸 (NVIDIA供應鏈)'},
    '3526': {'name': '凡甲', 'category': '🚀 AI/高速傳輸 (高功率連接器)'},
    '6213': {'name': '聯茂', 'category': '🚀 AI/高速傳輸 (高頻高速材料)'},

    # 🚗 車用與工控概念
    '6279': {'name': '胡連', 'category': '🚗 車用/工控 (車用端子龍頭)'},
    '3023': {'name': '信邦', 'category': '🚗 車用/工控 (客製化線束龍頭)'},
    '3003': {'name': '健和興', 'category': '🚗 車用/工控 (充電槍/高壓端子)'},
    '2460': {'name': '建通', 'category': '🚗 車用/工控 (異型導體銅材)'},
    '6290': {'name': '良維', 'category': '🚗 車用/工控 (充電樁線材)'},
    '3501': {'name': '維熹', 'category': '🚗 車用/工控 (正崴集團/充電槍)'},

    # 💻 消費性電子、Type-C
    '2317': {'name': '鴻海', 'category': '💻 消費電子 (產業霸主/鴻騰精密)'},
    '2392': {'name': '正崴', 'category': '💻 消費電子 (蘋果供應鏈/Type-C)'},
    '5457': {'name': '宣德', 'category': '💻 消費電子 (立訊入股/Type-C)'},
    '6205': {'name': '詮欣', 'category': '💻 消費電子 (車用影像/USB 4.0)'},
    '3092': {'name': '鴻碩', 'category': '💻 消費電子 (訊號線大廠)'},
    '2462': {'name': '良得電', 'category': '💻 消費電子 (AC電源線)'},
    '3511': {'name': '矽瑪', 'category': '💻 消費電子 (穿戴裝置/醫療)'},

    # ⚙️ 上游材料
    '2009': {'name': '第一銅', 'category': '⚙️ 上游材料 (銅片供應商)'},
    '2476': {'name': '鉅祥', 'category': '⚙️ 上游材料 (精密金屬沖壓)'},
    '1617': {'name': '榮星', 'category': '⚙️ 上游材料 (漆包線廠)'}
}

def send_line_notify():
    # 1. 連線 Google Sheet
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

    # 轉為 DataFrame
    headers = data[0]
    rows = data[1:]
    df = pd.DataFrame(rows, columns=headers)
    
    # 轉換數值型態
    cols_to_num = ["買賣超金額(千)", "收盤價", "估算張數"]
    for col in cols_to_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    df["日期"] = pd.to_datetime(df["日期"])

    # 2. 篩選當日資料 (或最新日期)
    today_date = datetime.date.today()
    # 如果今天是假日沒資料，就找資料庫裡最新的一天
    if not df[df["日期"].dt.date == today_date].empty:
        target_date = today_date
    else:
        target_date = df["日期"].max().date()
        print(f"⚠️ 今日無資料，改用最新日期: {target_date}")

    # 鎖定該日期的資料
    daily_data = df[df["日期"].dt.date == target_date].copy()

    # 3. 比對監控名單
    hits = []
    
    # 針對日報表中的每一行檢查
    for idx, row in daily_data.iterrows():
        stock_id = str(row['代號'])
        
        # 如果這檔股票在我們的監控名單中
        if stock_id in WATCHLIST:
            net_amt = int(row['買賣超金額(千)'])
            est_sheets = int(row['估算張數'])
            price = float(row['收盤價'])
            
            stock_info = WATCHLIST[stock_id]
            
            # 判斷買賣超方向 emoji
            trend_icon = "🔴買超" if net_amt > 0 else "🟢賣超"
            
            # 儲存結果
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
        print("✅ 今日供應鏈名單無動靜，不發送通知。")
        return

    # 4. 依照「金額絕對值」排序 (大戶動作大的排前面)
    hits.sort(key=lambda x: abs(x['amount']), reverse=True)

    # 5. 組合訊息內容
    message = f"⚡【連接器供應鏈】主力動向\n"
    message += f"📅 日期: {target_date}\n"
    message += "----------------------\n"

    for h in hits:
        # 格式：
        # [分類]
        # 🔴買超 3017 奇鋐: +35張 ($120)
        # 金額: 4200千
        
        # 處理張數顯示 (加號)
        sheet_str = f"+{h['sheets']}" if h['sheets'] > 0 else f"{h['sheets']}"
        
        message += f"{h['category']}\n"
        message += f"{h['trend']} {h['name']}({h['id']}): {sheet_str}張\n"
        message += f"💰金額: {h['amount']:,}千 | 股價: {h['price']}\n"
        message += "----------------------\n"

    message += "詳細趨勢請查看 App"

    # 6. 發送 LINE 訊息
    try:
        # 如果訊息太長 (LINE 上限 2000 字)，進行截斷
        if len(message) > 2000:
            message = message[:1900] + "\n...(以下省略)"
            
        line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
        line_bot_api.push_message(LINE_USER_ID, TextSendMessage(text=message))
        print("🎉 LINE 通知發送成功！")
    except Exception as e:
        print(f"❌ 發送失敗: {e}")

if __name__ == "__main__":
    send_line_notify()