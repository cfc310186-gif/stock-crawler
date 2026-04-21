import os
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from lib.sheet import (
    SheetNotReady,
    load_credentials_from_json_string,
    load_dataframe,
)
from lib.watchlist import (
    add_stock,
    get_categories,
    load_watchlist,
    remove_stock,
)
from settings import JSON_FILE_NAME

# --- 1. 頁面設定 ---
st.set_page_config(
    page_title="永豐松山籌碼雷達",
    layout="wide",
    page_icon="📈",
)

# --- CSS 全域美化 (維持之前的修復設定) ---
custom_css = """
    <style>
        :root {
            color-scheme: light;
            --primaryColor: #E67F75;
            --backgroundColor: #F9F9F7;
            --secondaryBackgroundColor: #FFFFFF;
            --textColor: #333333;
            --font: "sans-serif";
        }

        .stApp { background-color: #F9F9F7; }

        h1 {
            color: #333333 !important;
            font-family: 'Helvetica Neue', 'PingFang TC', 'Microsoft JhengHei', sans-serif;
            font-weight: 600 !important;
            font-size: 1.25rem !important;
            white-space: nowrap !important;
            padding-top: 10px !important;
            padding-bottom: 5px !important;
        }
        h2, h3, p, div, span, label { color: #333333 !important; }

        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div {
            background-color: #FFFFFF !important;
            border-color: #CCCCCC !important;
            color: #333333 !important;
        }
        input, .stSelectbox span, .stNumberInput input {
            color: #333333 !important;
            -webkit-text-fill-color: #333333 !important;
            caret-color: #333333 !important;
            font-weight: 500 !important;
        }

        div[data-baseweb="popover"] {
            background-color: #FFFFFF !important;
            border: 1px solid #E0E0E0 !important;
        }
        div[data-baseweb="popover"] * {
            background-color: #FFFFFF !important;
            color: #333333 !important;
        }
        div[data-baseweb="popover"] li[aria-selected="true"],
        div[data-baseweb="popover"] li:hover {
            background-color: #E67F75 !important;
        }
        div[data-baseweb="popover"] li[aria-selected="true"] *,
        div[data-baseweb="popover"] li:hover * {
            background-color: #E67F75 !important;
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }

        div[data-baseweb="radio"] div { color: #333333 !important; }
        div[role="radiogroup"] label { color: #333333 !important; }
        .streamlit-expanderHeader {
            background-color: #FFFFFF;
            color: #333333 !important;
            border: 1px solid #E0E0E0;
        }
        .streamlit-expanderHeader p { color: #222222 !important; }
        .streamlit-expanderContent { background-color: #F9F9F7; color: #333333 !important; }
        div[data-baseweb="slider"] div[role="slider"] { color: #333333 !important; }

        [data-testid="stMetricLabel"] { color: #444444 !important; }
        [data-testid="stMetricValue"] { color: #222222 !important; }

        /* Sidebar 樣式 */
        section[data-testid="stSidebar"] { background-color: #FFFFFF !important; }
        section[data-testid="stSidebar"] * { color: #333333 !important; }

        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
    </style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

st.title("📱 永豐松山籌碼雷達")


# --- 2. 資料讀取 ---
def _prepare_credentials() -> None:
    """如果 Streamlit Secrets 中有 GCP_CREDENTIALS，先寫出到本機檔案，讓 lib.sheet 取用。"""
    if os.path.exists(JSON_FILE_NAME):
        return
    if "GCP_CREDENTIALS" in st.secrets:
        load_credentials_from_json_string(st.secrets["GCP_CREDENTIALS"])


@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    _prepare_credentials()
    df = load_dataframe()
    return df if df is not None else pd.DataFrame()


@st.cache_data(ttl=10)
def load_watchlist_cached() -> dict[str, dict]:
    return load_watchlist()


# --- 3. 載入資料 ---
try:
    df_raw = load_data()
except SheetNotReady as e:
    st.error(f"連線設定錯誤: {e}")
    st.stop()
except Exception as e:
    st.error(f"連線錯誤: {e}")
    st.stop()

if df_raw.empty:
    st.warning("⚠️ 目前無資料")
    st.stop()

min_db_date = df_raw["日期"].min().date()
max_db_date = df_raw["日期"].max().date()
watchlist = load_watchlist_cached()
watchlist_ids = set(watchlist.keys())


# --- 4. 篩選條件 (Sidebar) ---
with st.sidebar:
    st.markdown("### 🔍 篩選條件")

    filter_side = st.radio(
        "尋找方向 (淨流量)",
        ["買超 (主力囤貨)", "賣超 (主力出貨)"],
        horizontal=False,
    )
    is_buy = "買超" in filter_side

    filter_days_option = st.selectbox(
        "時間範圍",
        ["近 3 天", "近 5 天", "近 10 天", "近 20 天", "自訂"],
    )

    amount_threshold = st.number_input(
        "累計淨金額大於(千)",
        value=1000,
        step=500,
    )

    with st.expander("進階條件", expanded=False):
        min_appear_days = st.slider("至少出現天數 (該方向)", 1, 20, 1)
        custom_range = None
        if filter_days_option == "自訂":
            custom_range = st.date_input(
                "選擇區間",
                [min_db_date, max_db_date],
                min_value=min_db_date,
                max_value=max_db_date,
            )

    if filter_days_option == "自訂" and custom_range:
        start_date = custom_range[0] if len(custom_range) > 0 else min_db_date
        end_date = custom_range[1] if len(custom_range) == 2 else max_db_date
    else:
        end_date = max_db_date
        days_back = int(filter_days_option.split(" ")[1])
        start_date = end_date - timedelta(days=days_back)

    selected_days_count = (end_date - start_date).days

    st.markdown("---")
    st.caption(f"⭐ Watchlist：{len(watchlist)} 檔")
    if st.button("🔄 重新載入", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# --- 5. 資料篩選邏輯 ---
mask_date = (df_raw["日期"].dt.date >= start_date) & (df_raw["日期"].dt.date <= end_date)
df_period = df_raw.loc[mask_date].copy()

df_period["is_buy_day"] = df_period["估算張數"] > 0
df_period["is_sell_day"] = df_period["估算張數"] < 0

stats = df_period.groupby(["代號", "名稱"]).agg(
    累計金額=("買賣超金額(千)", "sum"),
    累計張數=("估算張數", "sum"),
    買超天數=("is_buy_day", "sum"),
    賣超天數=("is_sell_day", "sum"),
).reset_index()

if is_buy:
    final_list = stats[stats["累計張數"] > 0].copy()
    final_list = final_list[final_list["買超天數"] >= min_appear_days]
    final_list["顯示天數"] = final_list["買超天數"]
else:
    final_list = stats[stats["累計張數"] < 0].copy()
    final_list = final_list[final_list["賣超天數"] >= min_appear_days]
    final_list["顯示天數"] = final_list["賣超天數"]

final_list = final_list[final_list["累計金額"].abs() >= amount_threshold]
final_list["金額絕對值"] = final_list["累計金額"].abs()
final_list = final_list.sort_values(by="金額絕對值", ascending=False)


# --- 6. Session state ---
if "selected_stock_id" not in st.session_state:
    st.session_state.selected_stock_id = None
if "selected_stock_name" not in st.session_state:
    st.session_state.selected_stock_name = None


# --- 7. 清單 ---
st.markdown("#### 📋 選股清單")
st.caption(
    f"📅 區間：{start_date} ~ {end_date} ({selected_days_count}天)  |  "
    f"門檻：{amount_threshold}千"
)

if final_list.empty:
    st.info("💡 無符合條件股票，請於左側調整條件。")
else:
    st.markdown(f"**共 {len(final_list)} 檔** (點擊查看詳情)")

    display_df = final_list[
        ["代號", "名稱", "顯示天數", "累計金額", "累計張數"]
    ].copy()
    display_df["累計張數"] = display_df["累計張數"].astype(int)
    display_df.insert(
        0,
        "⭐",
        display_df["代號"].apply(lambda sid: "⭐" if str(sid) in watchlist_ids else ""),
    )
    display_df.columns = ["⭐", "代號", "名稱", "出現天數", "淨買賣超(千)", "淨張數"]

    event = st.dataframe(
        display_df,
        on_select="rerun",
        selection_mode="single-row",
        use_container_width=True,
        hide_index=True,
        height=380,
    )
    if len(event.selection.rows) > 0:
        row = display_df.iloc[event.selection.rows[0]]
        st.session_state.selected_stock_id = row["代號"]
        st.session_state.selected_stock_name = row["名稱"]


# --- 8. 個股分析 (同頁下方) ---
st.markdown("---")
st.markdown("#### 📊 個股分析")

stock_id = st.session_state.selected_stock_id
stock_name = st.session_state.selected_stock_name

if not stock_id:
    st.info("👆 請先在「選股清單」選擇股票")
    st.stop()

in_watchlist = stock_id in watchlist_ids
star_icon = "⭐" if in_watchlist else "☆"

header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.markdown(
        f"### {star_icon} {stock_name} "
        f"<span style='font-size:16px;color:#555'>({stock_id})</span>",
        unsafe_allow_html=True,
    )
with header_col2:
    if in_watchlist:
        if st.button("🗑️ 從 Watchlist 移除", use_container_width=True, key="remove_btn"):
            if remove_stock(stock_id):
                st.cache_data.clear()
                st.success(f"已移除 {stock_name}")
                st.rerun()
    else:
        with st.popover("➕ 加入 Watchlist", use_container_width=True):
            categories = get_categories() or [
                "AI/高速傳輸", "車用/工控", "消費電子", "上游材料"
            ]
            new_category = st.selectbox(
                "選擇分類", categories, key="add_cat_select"
            )
            custom_category = st.text_input(
                "或輸入新分類", key="add_cat_custom"
            )
            final_cat = custom_category.strip() or new_category
            if st.button("確認加入", key="confirm_add"):
                if add_stock(stock_id, stock_name, final_cat):
                    st.cache_data.clear()
                    st.success(f"已將 {stock_name} 加入「{final_cat}」")
                    st.rerun()
                else:
                    st.warning("已存在，已更新分類")
                    st.cache_data.clear()
                    st.rerun()


if selected_days_count < 30:
    chart_start_date = end_date - timedelta(days=29)
else:
    chart_start_date = start_date

mask_chart = (
    (df_raw["代號"] == stock_id)
    & (df_raw["日期"].dt.date >= chart_start_date)
    & (df_raw["日期"].dt.date <= end_date)
)
df_chart = df_raw.loc[mask_chart].sort_values(by="日期").copy()

if df_chart.empty:
    st.info("此區間無資料")
    st.stop()

mask_stat = (
    (df_raw["代號"] == stock_id)
    & (df_raw["日期"].dt.date >= start_date)
    & (df_raw["日期"].dt.date <= end_date)
)
df_stat = df_raw.loc[mask_stat]

total_amt = df_stat["買賣超金額(千)"].sum()
total_sheets = df_stat["估算張數"].sum()
current_price = df_chart.iloc[-1]["收盤價"]
avg_cost = round(total_amt / total_sheets, 2) if total_sheets != 0 else 0

col_m1, col_m2, col_m3 = st.columns(3)
with col_m1:
    st.metric("區間淨張數", f"{int(total_sheets)} 張")
with col_m2:
    delta_color = "off"
    if avg_cost > 0:
        diff = current_price - avg_cost
        if total_sheets > 0:
            delta_color = "normal" if diff > 0 else "inverse"
        elif total_sheets < 0:
            delta_color = "inverse" if diff > 0 else "normal"
    st.metric(
        "平均成本",
        f"{avg_cost}",
        delta=round(current_price - avg_cost, 1),
        delta_color=delta_color,
        help="= 區間累計金額(千) / 區間累計張數，反映主力的成本區。",
    )
with col_m3:
    st.metric("收盤價", f"{current_price}")

df_chart["累積張數"] = df_chart["估算張數"].cumsum()
df_chart["顏色"] = df_chart["估算張數"].apply(
    lambda x: "#E67F75" if x > 0 else "#6CB097"
)

fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_trace(
    go.Bar(
        x=df_chart["日期"],
        y=df_chart["估算張數"],
        name="每日",
        marker_color=df_chart["顏色"],
        opacity=0.8,
    ),
    secondary_y=False,
)
fig.add_trace(
    go.Scatter(
        x=df_chart["日期"],
        y=df_chart["累積張數"],
        name="庫存",
        line=dict(color="#2C3E50", width=2),
        mode="lines",
    ),
    secondary_y=True,
)

fig.update_layout(
    title=dict(text="籌碼分佈趨勢", font=dict(color="#333333", size=16)),
    plot_bgcolor="#FFFFFF",
    paper_bgcolor="#FFFFFF",
    font=dict(color="#333333"),
    legend=dict(orientation="h", y=1.1, x=0, font=dict(color="#333333")),
    height=350,
    margin=dict(l=15, r=15, t=50, b=10),
    xaxis=dict(
        showgrid=False,
        tickfont=dict(color="#333333", size=12),
        title_font=dict(color="#333333"),
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="#F0F0F0",
        tickfont=dict(color="#333333", size=12),
    ),
)

st.plotly_chart(
    fig,
    use_container_width=True,
    config={"displayModeBar": False, "staticPlot": False, "scrollZoom": False},
)

with st.expander("📄 詳細數據"):
    st.dataframe(
        df_chart[["日期", "收盤價", "估算張數", "累積張數"]],
        use_container_width=True,
        hide_index=True,
    )
