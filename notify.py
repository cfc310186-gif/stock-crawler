import datetime
import json
import os
import warnings

import pandas as pd
import yfinance as yf
from linebot import LineBotApi
from linebot.models import TextSendMessage

from lib.alerts import (
    AlertHit,
    evaluate_conditions,
    evaluate_rankings,
    load_alerts,
)
from lib.logger import get_logger
from lib.sheet import SheetNotReady, load_dataframe
from lib.watchlist import load_watchlist
from settings import LINE_SECRET_FILE

warnings.filterwarnings("ignore", category=UserWarning)

log = get_logger(__name__)


LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

if (not LINE_ACCESS_TOKEN or not LINE_USER_ID) and os.path.exists(LINE_SECRET_FILE):
    try:
        with open(LINE_SECRET_FILE, encoding="utf-8") as f:
            secrets = json.load(f)
            LINE_ACCESS_TOKEN = secrets.get("LINE_ACCESS_TOKEN")
            LINE_USER_ID = secrets.get("LINE_USER_ID")
        log.info("💻 偵測到本機密碼檔，已載入 LINE 設定。")
    except (OSError, json.JSONDecodeError) as e:
        log.warning(f"⚠️ 讀取 {LINE_SECRET_FILE} 失敗: {e}")


def get_market_data(stock_id, target_date_str):
    """取得當日收盤價、漲跌幅、總成交量。失敗回傳 None，代表 yfinance 無資料。"""
    try:
        stock = yf.Ticker(f"{stock_id}.TW")
        hist = stock.history(period="1mo")
    except Exception as e:  # yfinance 內部例外類型多變
        log.warning(f"⚠️ yfinance 失敗 ({stock_id}): {e}")
        return None

    if hist.empty:
        return None
    hist.index = hist.index.strftime("%Y-%m-%d")

    if target_date_str not in hist.index:
        return None

    target_idx = hist.index.get_loc(target_date_str)
    total_vol = int(hist.iloc[target_idx]["Volume"] / 1000)
    close_price = float(hist.iloc[target_idx]["Close"])

    if target_idx > 0:
        prev_close = float(hist.iloc[target_idx - 1]["Close"])
        pct_change = round(((close_price - prev_close) / prev_close) * 100, 2)
    else:
        pct_change = 0.0

    return close_price, pct_change, total_vol


def _format_number_signed(value):
    return f"+{value:,}" if value > 0 else f"{value:,}"


def _format_ranking_block(rule_name, payload):
    """將 ranking 規則結果格式化成一段訊息"""
    emoji = payload["emoji"]
    records = payload["records"]
    metric = payload["metric"]
    unit = "張" if metric == "net_sheets" else "千"

    lines = [f"{emoji} {rule_name}"]
    for i, rec in enumerate(records, 1):
        stock_id = str(rec["代號"])
        stock_name = rec["名稱"]
        total = int(rec["total"])
        lines.append(f"  {i}. {stock_name} ({stock_id})  {_format_number_signed(total)} {unit}")
    return "\n".join(lines)


def _format_condition_group(hits_by_rule):
    """把 condition 命中按規則名稱分組後的結果格式化"""
    blocks = []
    for rule_name, hits in hits_by_rule.items():
        emoji = hits[0].emoji
        lines = [f"{emoji} {rule_name}"]
        for h in hits:
            detail_bits = []
            conc = h.extra.get("concentration", 0)
            if conc:
                detail_bits.append(f"集中 {conc}%")
            streak_b = h.extra.get("consecutive_buy_days", 0)
            streak_s = h.extra.get("consecutive_sell_days", 0)
            if streak_b >= 2:
                detail_bits.append(f"連買 {streak_b} 日")
            if streak_s >= 2:
                detail_bits.append(f"連賣 {streak_s} 日")
            mp = h.extra.get("market_price", 0)
            ac = h.extra.get("avg_cost", 0)
            if mp and ac:
                detail_bits.append(f"市價 {mp} / 成本 {ac}")
            detail = " | ".join(detail_bits) if detail_bits else ""
            suffix = f"  ({detail})" if detail else ""
            lines.append(f"  {h.stock_name} ({h.stock_id}){suffix}")
        blocks.append("\n".join(lines))
    return blocks


def build_message(df_full, target_date, watchlist, alert_rules):
    """組出完整通知訊息。若今日沒有任何可發內容回傳 None。"""
    target_date_str = target_date.strftime('%Y-%m-%d')
    target_ts = pd.Timestamp(target_date)

    daily_df = df_full[df_full["日期"] == target_ts]
    if daily_df.empty:
        return None

    # --- (A) 組 watchlist 每檔的基本資料 + condition 規則命中 ---
    hits_per_stock = []
    condition_hits_grouped: dict[str, list[AlertHit]] = {}

    for _, row in daily_df.iterrows():
        stock_id = str(row['代號'])
        if stock_id not in watchlist:
            continue

        net_amt = int(row['買賣超金額(千)'])
        est_sheets = int(row['估算張數'])
        sheet_cost_val = float(row['收盤價'])
        info = watchlist[stock_id]

        market_tuple = get_market_data(stock_id, target_date_str)
        if market_tuple is None:
            market_price = 0.0
            pct_change = 0.0
            total_vol = 0
            price_display = "⚠️ 無法取得股價"
        else:
            market_price, pct_change, total_vol = market_tuple
            if pct_change != 0:
                pct_str = f"+{pct_change}%" if pct_change > 0 else f"{pct_change}%"
                price_display = f"{market_price} ({pct_str})"
            else:
                price_display = f"{market_price}"

        concentration = 0.0
        if total_vol > 0:
            concentration = round((est_sheets / total_vol) * 100, 1)

        trend_icon = "🔴" if net_amt > 0 else "🟢"

        hits_per_stock.append({
            'id': stock_id,
            'name': info['name'],
            'category': info['category'],
            'category_display': info['category_display'],
            'price_display': price_display,
            'trend': trend_icon,
            'sheets': est_sheets,
            'amount': net_amt,
            'concentration': concentration,
            'cost': sheet_cost_val,
        })

        # 跑 condition 規則
        cond_hits = evaluate_conditions(
            df_full=df_full,
            stock_id=stock_id,
            stock_name=info['name'],
            target_date=target_ts,
            market_price=market_price,
            concentration=concentration,
            rules=alert_rules,
        )
        for h in cond_hits:
            condition_hits_grouped.setdefault(h.rule_name, []).append(h)

    if not hits_per_stock:
        return None

    hits_per_stock.sort(key=lambda x: abs(x['amount']), reverse=True)

    # --- (B) 跑 ranking 規則 (對全 Sheet，不限 watchlist) ---
    ranking_results = evaluate_rankings(
        df_full=df_full,
        target_date=target_ts,
        rules=alert_rules,
    )

    # --- (C) 組訊息 ---
    SEP = "----------------------"
    HEADER = "======================"

    parts = ["【連接器供應鏈】主力動向", f"📅 {target_date_str}"]

    if ranking_results or condition_hits_grouped:
        parts.append(HEADER)
        parts.append("🔥 重點告警")
        parts.append(HEADER)

        for rule_name, payload in ranking_results.items():
            parts.append(_format_ranking_block(rule_name, payload))
            parts.append(SEP)

        for block in _format_condition_group(condition_hits_grouped):
            parts.append(block)
            parts.append(SEP)

    parts.append(HEADER)
    parts.append("📋 一般動向")
    parts.append(HEADER)

    for h in hits_per_stock:
        sheet_str = _format_number_signed(h['sheets'])
        parts.append(h['category_display'])
        parts.append(f"{h['trend']} {h['name']} ({h['id']})")
        parts.append(f"張數: {sheet_str} 張")
        parts.append(f"集中: {h['concentration']}%")
        parts.append(f"成本: {h['cost']}")
        parts.append(f"金額: {h['amount']:,} 千")
        parts.append(f"股價: {h['price_display']}")
        parts.append(SEP)

    parts.append("詳細分析請看 App")
    return "\n".join(parts)


def send_line_notify():
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        log.error("❌ 錯誤：找不到 LINE 金鑰。")
        return

    watchlist = load_watchlist()
    if not watchlist:
        log.warning("⚠️ Watchlist 為空，請檢查 config/watchlist.yaml")
        return

    alert_rules = load_alerts()

    try:
        df = load_dataframe()
    except SheetNotReady as e:
        log.error(f"❌ Sheet 連線失敗: {e}")
        return
    if df is None:
        log.warning("⚠️ 試算表無資料")
        return

    today_date = datetime.date.today()
    today_ts = pd.Timestamp(today_date)

    if not df[df["日期"] == today_ts].empty:
        target_date = today_date
    else:
        target_date = df["日期"].max().date()
        log.warning(f"⚠️ 今日無資料，改用最新日期: {target_date}")

    log.info(f"🔍 開始分析 {target_date} 資料 (讀取 Sheet 成本)...")

    message = build_message(df, target_date, watchlist, alert_rules)
    if not message:
        log.info("✅ 今日無供應鏈股票動態，不發送。")
        return

    try:
        line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
        line_bot_api.push_message(LINE_USER_ID, TextSendMessage(text=message))
        log.info("🎉 LINE 通知發送成功！")
    except Exception as e:  # line-bot-sdk 例外類型多樣
        log.error(f"❌ 發送失敗: {e}")


if __name__ == "__main__":
    send_line_notify()
