import json
import os

from flask import Flask, abort, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from pyngrok import ngrok

app = Flask(__name__)

# --- 設定區 ---
# 1. 讀取原本的 Token (直接讀取 line_secret.json 最快)
if os.path.exists("line_secret.json"):
    with open("line_secret.json", encoding="utf-8") as f:
        secrets = json.load(f)
        LINE_ACCESS_TOKEN = secrets.get("LINE_ACCESS_TOKEN")
else:
    print("❌ 找不到 line_secret.json")
    exit()

# 2. 【請在此填入】您的 Channel Secret (在 LINE Developers -> Basic settings)
LINE_CHANNEL_SECRET = "202aee735dea28cb80810b1df857966a"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    # LINE 驗證簽章
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 當收到文字訊息時
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # 判斷來源是群組還是個人
    if event.source.type == 'group':
        target_id = event.source.group_id
        msg_type = "群組 ID (GroupId)"
    elif event.source.type == 'user':
        target_id = event.source.user_id
        msg_type = "個人 ID (UserId)"
    else:
        target_id = "未知"
        msg_type = "未知來源"

    print(f"✅ 抓到了！{msg_type}: {target_id}")

    # 機器人回話告訴你 ID
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"本群組 ID 為：\n{target_id}\n\n請複製這串 C 開頭的代碼！")
    )

if __name__ == "__main__":
    # 啟動 ngrok 通道 (讓外網能連到你的電腦)
    try:
        # 開啟 5000 port
        public_url = ngrok.connect(5000).public_url
        print("\n👉 【重要】請複製這個網址 (Webhook URL):")
        print(f"{public_url}/callback")
        print("\n請將上方網址貼到 LINE Developers -> Messaging API -> Webhook URL 欄位並啟用！\n")
        app.run(port=5000)
    except Exception as e:
        print(f"❌ 錯誤: {e}")
