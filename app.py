import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os
import json

# --- 1. 頁面設定 ---
st.set_page_config(
    page_title="永豐松山籌碼雷達", 
    layout="wide", 
    page_icon="📈"
)

# --- CSS 全域美化 (修正深色模式文字消失問題) ---
custom_css = """
    <style>
        /* 1. 背景色 */
        .stApp {
            background-color: #F9F9F7;
        }
        
        /* 2. 標題優化 */
        h1 {
            color: #4A4A4A !important;
            font-family: 'Helvetica Neue', 'PingFang TC', 'Microsoft JhengHei', sans-serif;
            font-weight: 400 !important;
            font-size: 1.5rem !important;
            white-space: nowrap !important;
            padding-top: 10px !important;
            padding-bottom: 10px !important;
        }
        
        /* 3. 調整 Expander (篩選區塊) 的外觀 */
        .streamlit-expanderHeader {
            background-color: #FFFFFF;
            border-radius: 5px;
            color: #4A4A4A !important; /* 強制標題深色 */
            font-weight: 500;
        }
        
        /* 4. 隱藏 footer 但保留 header */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* 5. 分頁籤優化 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 40px;
            background-color: #EFEFEF;
            border-radius: 5px;
            color: #666;
            font-size: 14px;
            padding: 0px 16px;
        }
        .stTabs [aria-selected="true"] {
            background-color: #FFFFFF;
            color: #E67F75;
            box-shadow: 0px 2px 5px rgba(0,0,0,0.05);
        }
        
        /* 6. 指標優化 */
        [data-testid="stMetricLabel"] { font-size: 13px !important; color: #888 !important; }
        [data-testid="stMetricValue"] { font-size: 18px !important; color: #333 !important; }

        /* --- 7. (新) 強制修正深色模式下的文字顏色 --- */
        /* 這段代碼會強制所有標籤文字變成深灰，避免在手機暗模式下變成白色 */
        
        /* 一般文字與 Markdown */
        .stMarkdown, .stMarkdown p {
            color: #4A4A4A !important;
        }
        
        /* Widget 的標題 Label (如：尋找方向、時間範圍...) */
        .stRadio label, .stSelectbox label, .stSlider label, .stNumberInput label, .stDateInput label {
            color: #4A4A4A !important;
        }
        
        /* Radio 按鈕選項的文字 */
        div[role="radiogroup"] label div p {
            color: #4A4A4A !important;
        }
        
        /* 讓 Input 輸入框在暗模式下保持可讀 (白字黑底或適應) */
        /* 這裡不強制改 Input 內部，讓它隨系統變換，確保對比度 */
        
    </style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

st.title("📱 永豐松山籌碼雷達")

# --- 2. 讀取資料函式 ---
@st.cache_data(ttl=60)
def load_data():
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
    
    if "GCP_CREDENTIALS" in st.secrets:
        key_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    elif os.path.exists("service_account.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    else:
        return pd.DataFrame()

    client = gspread.authorize(creds)
    sheet = client.open("Stock_Data").sheet1
    
    data = sheet.get_all_values()
    if not data: return pd.DataFrame()

    headers = data[0]
    rows = data[1:]
    df = pd.DataFrame(rows, columns=headers)
    
    numeric_cols = ["買賣超金額(千)", "收盤價", "估算張數"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"])
        
    return df

# --- 3. 載入資料 ---
try:
    df_raw = load_data()
    if df_raw.empty:
        st.warning("⚠️ 目前無資料")
        st.stop()
    min_db_date = df_raw["日期"].min().date()
    max_db_date = df_raw["日期"].max().date()
except Exception as e:
    st.error(f"連線錯誤: {e}")
    st.stop()

# --- 4. 篩選條件 (Expander) ---
with st.expander("🔍 點擊設定篩選條件 (方向、天數、金額)", expanded=True):
    f_col1, f_col2 = st.columns(2)
    
    with f_col1:
        # 這裡的 Label 已經被 CSS 強制改為深色
        filter_side = st.radio("尋找方向", ["買超 (主力進)", "賣超 (主力出)"], horizontal=True)
        is_buy = True if "買超" in filter_side else False
        
        min_appear_days = st.slider("至少出現天數", 1, 20, 1)

    with f_col2:
        filter_days_option = st.selectbox("時間範圍", ["近 3 天", "近 5 天", "近 10 天", "近 20 天", "自訂"])
        amount_threshold = st.number_input("累計金額大於(千)", value=1000, step=500)

    # 自訂日期邏輯
    end_date = max_db_date
    if filter_days_option == "自訂":
        date_range = st.date_input("選擇區間", [min_db_date, max_db_date])
        start_date = date_range[0] if len(date_range) > 0 else min_db_date
        if len(date_range) == 2: end_date = date_range[1]
    else:
        days_back = int(filter_days_option.split(" ")[1])
        start_date = end_date - timedelta(days=days_back)
    
    selected_days_count = (end_date - start_date).days

# --- 5. 資料篩選邏輯 ---
mask_date = (df_raw["日期"].dt.date >= start_date) & (df_raw["日期"].dt.date <= end_date)
df_period = df_raw.loc[mask_date].copy()

if is_buy:
    df_direction = df_period[df_period["買賣超金額(千)"] > 0].copy()
else:
    df_direction = df_period[df_period["買賣超金額(千)"] < 0].copy()

stats = df_direction.groupby(["代號", "名稱"]).agg(
    出現天數=("日期", "count"),
    累計金額=("買賣超金額(千)", "sum")
).reset_index()

if not is_buy: stats["累計金額"] = stats["累計金額"].abs()

final_list = stats[
    (stats["出現天數"] >= min_appear_days) & 
    (stats["累計金額"] >= amount_threshold)
].sort_values(by="累計金額", ascending=False)

# --- 6. 介面呈現 (Tabs) ---
tab1, tab2 = st.tabs(["📋 選股清單", "📊 個股分析"])

if 'selected_stock_id' not in st.session_state:
    st.session_state.selected_stock_id = None
if 'selected_stock_name' not in st.session_state:
    st.session_state.selected_stock_name = None

with tab1:
    st.caption(f"📅 區間：{start_date} ~ {end_date} ({selected_days_count}天) | 門檻：{amount_threshold}千")
    
    if final_list.empty:
        st.info("💡 無符合條件股票，請點擊上方「🔍」放寬條件。")
    else:
        st.markdown(f"**共 {len(final_list)} 檔** (點擊查看)")
        event = st.dataframe(
            final_list, 
            on_select="rerun", 
            selection_mode="single-row", 
            use_container_width=True, 
            hide_index=True,
            height=400
        )
        if len(event.selection.rows) > 0:
            row = final_list.iloc[event.selection.rows[0]]
            st.session_state.selected_stock_id = row["代號"]
            st.session_state.selected_stock_name = row["名稱"]
            st.toast(f"已選擇：{row['名稱']}，請切換分頁", icon="👉")

with tab2:
    stock_id = st.session_state.selected_stock_id
    stock_name = st.session_state.selected_stock_name
    
    if stock_id:
        st.markdown(f"### {stock_name} <span style='font-size:16px;color:#888'>({stock_id})</span>", unsafe_allow_html=True)
        
        # 圖表邏輯
        if selected_days_count < 30:
            chart_start_date = end_date - timedelta(days=29)
        else:
            chart_start_date = start_date
            
        mask_chart = (df_raw["代號"] == stock_id) & \
                     (df_raw["日期"].dt.date >= chart_start_date) & \
                     (df_raw["日期"].dt.date <= end_date)
        df_chart = df_raw.loc[mask_chart].sort_values(by="日期").copy()
        
        if df_chart.empty:
            st.info("此區間無資料")
        else:
            mask_stat = (df_raw["代號"] == stock_id) & \
                        (df_raw["日期"].dt.date >= start_date) & \
                        (df_raw["日期"].dt.date <= end_date)
            df_stat = df_raw.loc[mask_stat]
            
            total_amt = df_stat["買賣超金額(千)"].sum()
            total_sheets = df_stat["估算張數"].sum()
            current_price = df_chart.iloc[-1]['收盤價']
            avg_cost = round(total_amt / total_sheets, 2) if total_sheets != 0 else 0
            
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1: st.metric("區間累積", f"{int(total_sheets)} 張")
            with col_m2:
                delta_color = "off"
                if avg_cost > 0:
                    diff = current_price - avg_cost
                    if total_sheets > 0: delta_color = "normal" if diff > 0 else "inverse"
                    elif total_sheets < 0: delta_color = "inverse" if diff > 0 else "normal"
                st.metric("平均成本", f"{avg_cost}", delta=round(current_price-avg_cost, 1), delta_color=delta_color)
            with col_m3: st.metric("收盤價", f"{current_price}")

            # 繪圖
            df_chart["累積張數"] = df_chart["估算張數"].cumsum()
            df_chart["顏色"] = df_chart["估算張數"].apply(lambda x: "#E67F75" if x > 0 else "#6CB097")

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=df_chart["日期"], y=df_chart["估算張數"], name="每日", marker_color=df_chart["顏色"], opacity=0.8), secondary_y=False)
            fig.add_trace(go.Scatter(x=df_chart["日期"], y=df_chart["累積張數"], name="庫存", line=dict(color='#2C3E50', width=2), mode='lines'), secondary_y=True)

            fig.update_layout(
                legend=dict(orientation="h", y=1.1, x=0),
                height=350,
                margin=dict(l=10, r=10, t=40, b=10),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor="#EEE")
            )
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("📄 詳細數據"):
                st.dataframe(df_chart[["日期", "收盤價", "估算張數", "累積張數"]], use_container_width=True, hide_index=True)
    else:
        st.info("👈 請先在「選股清單」選擇股票")
