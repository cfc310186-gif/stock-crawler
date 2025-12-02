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

# --- 1. 頁面設定 (手機優先模式) ---
st.set_page_config(
    page_title="籌碼雷達", 
    layout="wide", 
    page_icon="📱",
    initial_sidebar_state="auto" # 手機上預設收合側邊欄
)

# --- CSS 優化 (隱藏預設選單，讓介面更像 App) ---
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            .stApp {padding-top: 10px;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.title("📱 松山分點籌碼雷達")

# --- 2. 讀取資料函式 ---
@st.cache_data(ttl=60)
def load_data():
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
    
    # 雲端部署關鍵：優先讀取 Secrets
    if "GCP_CREDENTIALS" in st.secrets:
        key_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    elif os.path.exists("service_account.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    else:
        return pd.DataFrame() # 防呆

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
        st.warning("目前無資料")
        st.stop()
    min_db_date = df_raw["日期"].min().date()
    max_db_date = df_raw["日期"].max().date()
except Exception as e:
    st.error(f"連線錯誤: {e}")
    st.stop()

# --- 4. 側邊欄：篩選 (手機按左上角 > 展開) ---
st.sidebar.header("🔍 篩選條件")
filter_side = st.sidebar.radio("方向", ["買超 (主力進)", "賣超 (主力出)"])
is_buy = True if "買超" in filter_side else False

filter_days_option = st.sidebar.selectbox("時間範圍", ["近 3 天", "近 5 天", "近 10 天", "近 20 天", "自訂"])
end_date = max_db_date

if filter_days_option == "自訂":
    date_range = st.sidebar.date_input("區間", [min_db_date, max_db_date])
    start_date = date_range[0] if len(date_range) > 0 else min_db_date
    if len(date_range) == 2: end_date = date_range[1]
else:
    days_back = int(filter_days_option.split(" ")[1])
    start_date = end_date - timedelta(days=days_back)

min_appear_days = st.sidebar.slider("出現天數", 1, 20, 1)
amount_threshold = st.sidebar.number_input("累計金額(千)", value=1000, step=500)

# --- 5. 邏輯計算 ---
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

# --- 6. 手機版分頁介面 (Tabs) ---
tab1, tab2 = st.tabs(["📋 選股清單", "📊 個股分析"])

# 全域變數初始化
if 'selected_stock_id' not in st.session_state:
    st.session_state.selected_stock_id = None
if 'selected_stock_name' not in st.session_state:
    st.session_state.selected_stock_name = None

with tab1:
    st.caption(f"篩選區間：{start_date} ~ {end_date}")
    if final_list.empty:
        st.warning("無符合條件股票")
    else:
        st.write(f"共找到 **{len(final_list)}** 檔股票 (點擊查看詳情)")
        
        # 使用 Streamlit 的選取事件
        event = st.dataframe(
            final_list, 
            on_select="rerun", 
            selection_mode="single-row", 
            use_container_width=True, 
            hide_index=True,
            height=400 # 固定高度方便手機滑動
        )
        
        # 捕捉選取事件
        if len(event.selection.rows) > 0:
            row = final_list.iloc[event.selection.rows[0]]
            st.session_state.selected_stock_id = row["代號"]
            st.session_state.selected_stock_name = row["名稱"]
            st.toast(f"已選擇：{row['名稱']}，請切換至「個股分析」分頁", icon="✅")

with tab2:
    stock_id = st.session_state.selected_stock_id
    stock_name = st.session_state.selected_stock_name
    
    if stock_id:
        st.subheader(f"{stock_name} ({stock_id})")
        
        # 繪圖資料準備 (30天)
        chart_start_date = end_date - timedelta(days=29)
        mask_chart = (df_raw["代號"] == stock_id) & \
                     (df_raw["日期"].dt.date >= chart_start_date) & \
                     (df_raw["日期"].dt.date <= end_date)
        df_chart = df_raw.loc[mask_chart].sort_values(by="日期").copy()
        
        if df_chart.empty:
            st.info("此區間無資料")
        else:
            # 計算平均成本
            mask_stat = (df_raw["代號"] == stock_id) & \
                        (df_raw["日期"].dt.date >= start_date) & \
                        (df_raw["日期"].dt.date <= end_date)
            df_stat = df_raw.loc[mask_stat]
            
            total_amt = df_stat["買賣超金額(千)"].sum()
            total_sheets = df_stat["估算張數"].sum()
            avg_cost = round(total_amt / total_sheets, 2) if total_sheets != 0 else 0
            
            # 手機版數據指標 (並排顯示)
            c1, c2 = st.columns(2)
            c1.metric("區間平均成本", f"{avg_cost}", delta_color="off")
            c2.metric("最新收盤價", f"{df_chart.iloc[-1]['收盤價']}")

            # 繪圖
            df_chart["累積張數"] = df_chart["估算張數"].cumsum()
            df_chart["顏色"] = df_chart["估算張數"].apply(lambda x: "#EF553B" if x > 0 else "#00CC96")

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=df_chart["日期"], y=df_chart["估算張數"], name="每日", marker_color=df_chart["顏色"]), secondary_y=False)
            fig.add_trace(go.Scatter(x=df_chart["日期"], y=df_chart["累積張數"], name="庫存", line=dict(color='blue', width=2)), secondary_y=True)

            fig.update_layout(
                title=dict(text="近30日籌碼趨勢", font=dict(size=14)),
                legend=dict(orientation="h", y=1.1),
                height=350, # 縮小高度適配手機
                margin=dict(l=10, r=10, t=40, b=10) # 減少邊框留白
            )
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("📄 詳細數據明細"):
                st.dataframe(df_chart[["日期", "收盤價", "估算張數", "累積張數"]], hide_index=True)
    else:
        st.info("👈 請先在「選股清單」選擇一檔股票")