"""一次性搬運：把 config/watchlist.yaml 寫入 Google Sheet 的 Watchlist 分頁。

使用方式：
    python scripts/migrate_watchlist_to_sheet.py

執行成功後，Sheet 的 Watchlist 分頁即為新的單一資料來源。
可刪除 config/watchlist.yaml（或保留作為備份）。
"""
from __future__ import annotations

import sys

print(f"[boot] python = {sys.executable}", flush=True)
print(f"[boot] version = {sys.version}", flush=True)
print(f"[boot] __name__ = {__name__}", flush=True)
print("[boot] importing deps...", flush=True)

from pathlib import Path  # noqa: E402

# 讓 `python scripts/xxx.py` 能直接 import 專案 lib/settings
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from lib.logger import get_logger  # noqa: E402
from lib.sheet import SheetNotReady  # noqa: E402
from lib.watchlist import _get_worksheet, _save_rows  # noqa: E402
from settings import WATCHLIST_FILE  # noqa: E402

print("[boot] imports done", flush=True)
log = get_logger(__name__)


def main() -> int:
    print(f"[debug] ROOT = {ROOT}", flush=True)
    print(f"[debug] WATCHLIST_FILE = {WATCHLIST_FILE}", flush=True)
    print(f"[debug] exists = {WATCHLIST_FILE.exists()}", flush=True)

    if not WATCHLIST_FILE.exists():
        log.error(f"❌ 找不到 {WATCHLIST_FILE}，無資料可搬運。")
        return 1

    with WATCHLIST_FILE.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    stocks = raw.get("stocks", [])
    print(f"[debug] 讀到 stocks 數量 = {len(stocks)}", flush=True)
    if not stocks:
        log.error("❌ YAML 中沒有 stocks 條目。")
        return 1

    rows: list[dict[str, str]] = []
    for item in stocks:
        rows.append({
            "id": str(item["id"]),
            "name": str(item.get("name", item["id"])),
            "category": str(item.get("category", "其他")),
        })

    log.info(f"📤 即將寫入 {len(rows)} 筆 watchlist 到 Sheet...")

    try:
        ws = _get_worksheet()
    except SheetNotReady as e:
        log.error(f"❌ Sheet 連線失敗: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        log.error(f"❌ 開 Sheet 失敗 ({type(e).__name__}): {e}")
        return 1

    print(f"[debug] 已取得 worksheet: {getattr(ws, 'title', ws)}", flush=True)
    _save_rows(rows, ws)
    log.info("✅ 搬運完成。Sheet 的 Watchlist 分頁已更新。")
    return 0


print(f"[boot] __name__ at bottom = {__name__}", flush=True)

if __name__ == "__main__":
    print("[boot] entering main()...", flush=True)
    raise SystemExit(main())
else:
    print("[boot] NOT entering main() because __name__ != __main__", flush=True)
