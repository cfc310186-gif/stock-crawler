"""專案共用常數設定"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SHEET_NAME = "Stock_Data"
WATCHLIST_SHEET_TAB = "Watchlist"  # 存放 watchlist 的第二分頁
JSON_FILE_NAME = "service_account.json"
LINE_SECRET_FILE = "line_secret.json"

BROKER_ID = "9A91"  # 永豐金-松山

# 舊的 YAML 路徑保留作為 migration 用 (一次性搬進 Sheet 後可刪除)
WATCHLIST_FILE = BASE_DIR / "config" / "watchlist.yaml"
ALERTS_FILE = BASE_DIR / "config" / "alerts.yaml"
PROGRESS_FILE = BASE_DIR / ".progress.json"
