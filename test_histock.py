from io import StringIO

import pandas as pd
import requests

# 設定目標：永豐金-松山 (9A91) 買賣 湧德 (3689)
broker_id = "9A91"
stock_id = "3689"
url = f"https://histock.tw/stock/brokertrace.aspx?bno={broker_id}&no={stock_id}"

# 偽裝成瀏覽器 (非常重要，不然會被擋)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    response = requests.get(url, headers=headers)
    response.encoding = "utf-8" # 確保中文不亂碼

    # 檢查是否成功
    if response.status_code == 200:
        # 使用 pandas 直接解析網頁中的表格
        dfs = pd.read_html(StringIO(response.text))

        # 通常主要資料在第一個表格，但 HiStock 有時候會有排版表格，我們找欄位對的那個
        target_df = None
        for df in dfs:
            if "買進均價" in df.columns:
                target_df = df
                break

        if target_df is not None:
            print("✅ 成功抓取資料！預覽如下：")
            print(target_df.head())

            # --- 簡單計算示範 ---
            # 清理資料 (把文字轉數字)
            target_df["買進張數"] = pd.to_numeric(target_df["買進張數"], errors='coerce').fillna(0)
            target_df["買進均價"] = pd.to_numeric(target_df["買進均價"], errors='coerce').fillna(0)

            # 假設算最近 5 筆的買進成本
            recent_days = target_df.head(5)
            total_money = (recent_days["買進張數"] * recent_days["買進均價"]).sum()
            total_sheets = recent_days["買進張數"].sum()

            if total_sheets > 0:
                avg_cost = round(total_money / total_sheets, 2)
                print(f"\n📊 近 5 日主力買進均價 (成本): {avg_cost}")
            else:
                print("\n⚠️ 近 5 日無買進紀錄")

        else:
            print("❌ 找不到包含 '買進均價' 的表格，可能網頁改版了")
    else:
        print(f"❌ 連線失敗，狀態碼: {response.status_code}")

except Exception as e:
    print(f"❌ 發生錯誤: {e}")
