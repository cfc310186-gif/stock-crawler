# stock-crawler

Taiwan 股市籌碼雷達：每日抓富邦證券分點 (永豐金-松山 `9A91`) 買賣超，結合 yfinance 收盤價寫入 Google Sheet，再透過 LINE 推播告警與 Streamlit 儀表板分析。

---

## 功能模組

| 檔案 | 說明 |
|---|---|
| `main.py` | 每日爬 Fubon + yfinance，覆寫 Google Sheet 當日資料 (GitHub Actions 排程) |
| `history.py` | 手動補抓過去 30 天歷史資料，逐日寫入 Sheet |
| `update_history.py` | 透過 HiStock 分點明細重算「真實主力成本」，支援 `.progress.json` 中斷續跑 |
| `notify.py` | 讀 Sheet 當日資料，比對 Watchlist + 執行告警規則，LINE 推播 |
| `app.py` | Streamlit 儀表板：篩選 / 個股分析 / ⭐ Watchlist 管理 |
| `get_id.py` | 一次性工具：Flask + ngrok + LINE Webhook 取得 User/Group ID |

---

## 資料流

```
Fubon HTML ──┐
             ├──► main.py ──► Google Sheet (Stock_Data)
yfinance ────┘                      │
                                    ├──► notify.py ──► LINE
HiStock HTML ──► update_history.py ─┤
                                    └──► app.py (Streamlit)
```

---

## 設定檔

### `config/watchlist.yaml`
統一的關注股票清單，`main.py` / `notify.py` / `app.py` 皆讀取此檔。

```yaml
stocks:
  - id: "3035"
    name: 智原
    category: AI/高速傳輸
category_emojis:
  AI/高速傳輸: 🚀
  車用/工控: 🚗
  消費電子: 💻
  上游材料: ⚙️
```

可直接在 Streamlit 介面透過 ⭐ 按鈕新增 / 移除股票，寫回 YAML。

### `config/alerts.yaml`
告警規則引擎。一般規則用 `when:` DSL，排行榜規則使用 `kind: ranking`。

```yaml
alerts:
  - name: 高集中度買盤
    when: concentration >= 5 and net_sheets > 0
    emoji: 🔥
  - name: 連續買超 ≥3 日
    when: consecutive_buy_days >= 3
    emoji: ⚡
  - name: 近3日買超前3大
    kind: ranking
    window_days: 3
    metric: net_sheets
    direction: buy
    top_n: 3
    emoji: 🏆
```

支援變數：`net_sheets` / `net_amount_k` / `concentration` / `market_price` / `avg_cost` / `consecutive_buy_days` / `consecutive_sell_days`。

### `settings.py`
全專案共用常數 (SHEET_NAME、BROKER_ID、檔案路徑)。

---

## 環境變數 / 密鑰

| 名稱 | 用途 |
|---|---|
| `GCP_CREDENTIALS` | Google Service Account JSON (GitHub Actions 注入) |
| `LINE_ACCESS_TOKEN` | LINE Messaging API channel token |
| `LINE_USER_ID` | LINE 推播目標 user / group ID |
| `LOG_LEVEL` | 可選，預設 `INFO`；除錯時設 `DEBUG` |

本機開發時，可把上述 GCP JSON 存成 `service_account.json`，把 LINE 兩個值存成 `line_secret.json`：

```json
{ "LINE_ACCESS_TOKEN": "...", "LINE_USER_ID": "..." }
```

兩個檔案都已加入 `.gitignore`，不會進入版控。

---

## 執行

```bash
pip install -r requirements.txt

# 當日爬蟲
python main.py

# 歷史補齊 (最近 30 日)
python history.py

# 真實成本重算 (需填 HiStock Cookie)
python update_history.py

# LINE 推播
python notify.py

# Streamlit 儀表板
streamlit run app.py
```

### GitHub Actions 排程
`.github/workflows/main.yml`：週一至週五 UTC 11:30 (台灣 19:30) 依序執行 `main.py` → `notify.py`。

---

## 開發

```bash
pip install -r requirements-dev.txt
pytest -v
ruff check .
```

---

## 專案佈局

```
.
├── main.py              # 每日爬蟲
├── notify.py            # LINE 推播
├── history.py           # 歷史補抓
├── update_history.py    # 真實成本重算
├── app.py               # Streamlit 儀表板
├── settings.py          # 共用常數
├── config/
│   ├── watchlist.yaml   # 關注清單
│   └── alerts.yaml      # 告警規則
├── lib/
│   ├── sheet.py         # Google Sheet 連線 + DataFrame 讀寫
│   ├── logger.py        # 共用 logger (支援 LOG_LEVEL)
│   ├── watchlist.py     # watchlist CRUD
│   └── alerts.py        # 告警規則引擎 (condition + ranking)
└── .github/workflows/
    └── main.yml         # 排程
```
