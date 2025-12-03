from linebot import LineBotApi
from linebot.models import TextSendMessage

# ==========================================
# 請將這裡替換成您的真實資料
LINE_ACCESS_TOKEN = "PSP5CGuR5DqHySmP30bngCgBHwBtHv5RloJ6aJW0UuDFDQA10CYQgXu2mbks+f0Zlz4ZTqpmM6NuG85vThFgmhl0N/e0mcsVLbYexBtYC7bJ3tRO2wVXle3drIKqmCCKRJ1Un4jbLPrMOzV1Dnjf8AdB04t89/1O/w1cDnyilFU="
LINE_USER_ID = "U70bef6922f3d2fa111c4de26f86f49d0"
# ==========================================

def test_connection():
    try:
        # 1. 建立連線
        line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
        
        # 2. 發送測試訊息
        print("正在發送訊息...")
        line_bot_api.push_message(
            LINE_USER_ID, 
            TextSendMessage(text="✨ 恭喜！LINE 機器人連線成功！\n這是來自 Python 的測試訊息。")
        )
        
        print("✅ 發送成功！請檢查您的手機 LINE。")
        
    except Exception as e:
        print(f"❌ 發送失敗，請檢查 Token 或 ID 是否正確。\n錯誤訊息: {e}")

if __name__ == "__main__":
    test_connection()