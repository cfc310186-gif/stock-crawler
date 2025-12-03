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

# --- 1. 頁面設定 (手機優先 + 文青風格設定) ---
st.set_page_config(
    page_title="永豐松山籌碼雷達", 
    layout="wide", 
    page_icon="📈",
    initial_sidebar_state="auto"
)

# --- CSS 全域美化 (文青風 + 標題防換行) ---
custom_css = """
    <style>
        /* 1. 整體背景色 - 柔和米白 */
        .stApp {
            background-color: #F9F9F7;
        }
        
        /* 2. 標題優化 - 永豐松山籌碼雷達 */
        h1 {
            color: #4A4A4A !important;
            font-family: 'Helvetica Neue', 'PingFang TC', 'Microsoft JhengHei', sans-serif;
            font-weight: 400 !important;
            font-size: 1.6rem !important; /* 調整字體大小適配手機 */
            white-space: nowrap !important; /* 強制不換行 */
            overflow: hidden;
            text-overflow: ellipsis;
            padding-top: 0px !important;
        }
        
        /* 3. 隱藏預設選單與 footer */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;} /* 隱藏上方紅線條 */
        
        /* 4. 分頁籤樣式 (Tabs) */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 40px;
            white-space: pre-wrap;
            background-color: #F0F0F0;
            border-radius: 5px 5px 0px 0px;
            color: #4A4A4A;
            font-size: 14px;
        }
        .stTabs [aria-selected="true"] {
            background-color: #FFFFFF;
            color: #EF553B;
            font-weight: bold;
        }

        /* 5. 調整 Metric 指標樣式 */
        [data-testid="stMetricLabel"] {
            font-size: 14px !important;
            color: #888888 !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 18px !important;
            color: #333333 !important;
        }
    </style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# 顯示標題
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

# --- 3. 載入資料與防呆 ---
try:
    df_raw = load_data()
    if df_raw.empty:
        st.warning("⚠️ 目前無資料，請確認爬蟲是否執行成功。")
        st.stop()
    min_db_date = df_raw["日期"].min().date()
    max_db_date = df_raw["日期"].max().date()
except Exception as e:
    st.error(f"連線錯誤: {e}")
    st.stop()

# --- 4. 側邊欄：篩選條件 ---
st.sidebar.header("🔍 篩選條件")
filter_side = st.sidebar.radio("方向", ["買超 (主力進)", "賣超 (主力出)"])
is_buy = True if "買超" in filter_side else False

filter_days_option = st.sidebar.selectbox("時間範圍", ["近 3 天", "近 5 天", "近 10 天", "近 20 天", "自訂"])
end_date = max_db_date

# 計算起始日
if filter_days_option == "自訂":
    date_range = st.sidebar.date_input("區間", [min_db_date, max_db_date])
    start_date = date_range[0] if len(date_range) > 0 else min_db_date
    if len(date_range) == 2: end_date = date_range[1]
else:
    days_back = int(filter_days_option.split(" ")[1])
    start_date = end_date - timedelta(days=days_back)

# 計算篩選的天數長度 (用於決定圖表 X 軸)
selected_days_count = (end_date - start_date).days

min_appear_days = st.sidebar.slider("出現天數", 1, 20, 1)
amount_threshold = st.sidebar.number_input("累計金額(千)", value=1000, step=500)

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

# Session State 初始化
if 'selected_stock_id' not in st.session_state:
    st.session_state.selected_stock_id = None
if 'selected_stock_name' not in st.session_state:
    st.session_state.selected_stock_name = None

with tab1:
    st.caption(f"📅 篩選區間：{start_date} ~ {end_date} (共 {selected_days_count} 天)")
    if final_list.empty:
        st.info("💡 無符合條件的股票，請嘗試放寬篩選條件。")
    else:
        st.markdown(f"**共 {len(final_list)} 檔** (請點擊選取)")
        event = st.dataframe(
            final_list, 
            on_select="rerun", 
            selection_mode="single-row", 
            use_container_width=True, 
            hide_index=True,
            height=450
        )
        if len(event.selection.rows) > 0:
            row = final_list.iloc[event.selection.rows[0]]
            st.session_state.selected_stock_id = row["代號"]
            st.session_state.selected_stock_name = row["名稱"]
            st.toast(f"已選擇：{row['名稱']}，請切換至「個股分析」", icon="👉")

with tab2:
    stock_id = st.session_state.selected_stock_id
    stock_name = st.session_state.selected_stock_name
    
    if stock_id:
        st.markdown(f"### {stock_name} <span style='font-size:16px;color:#888'>({stock_id})</span>", unsafe_allow_html=True)
        
        # --- A. 圖表時間軸邏輯 ---
        # 規則：如果篩選天數 < 30 天，圖表強制顯示 30 天；如果 >= 30 天，則依據實際篩選天數顯示
        if selected_days_count < 30:
            chart_start_date = end_date - timedelta(days=29)
        else:
            chart_start_date = start_date
            
        mask_chart = (df_raw["代號"] == stock_id) & \
                     (df_raw["日期"].dt.date >= chart_start_date) & \
                     (df_raw["日期"].dt.date <= end_date)
        df_chart = df_raw.loc[mask_chart].sort_values(by="日期").copy()
        
        if df_chart.empty:
            st.info("此區間無交易資料")
        else:
            # --- B. 計算「區間平均成本」 ---
            # 關鍵：這裡的平均成本必須依據「篩選區間 (start_date ~ end_date)」計算，而不是圖表顯示的區間
            # 這樣才符合使用者的篩選邏輯 (例如：這 5 天買超的成本是多少)
            mask_stat = (df_raw["代號"] == stock_id) & \
                        (df_raw["日期"].dt.date >= start_date) & \
                        (df_raw["日期"].dt.date <= end_date)
            df_stat = df_raw.loc[mask_stat]
            
            total_amt = df_stat["買賣超金額(千)"].sum()
            total_sheets = df_stat["估算張數"].sum()
            current_price = df_chart.iloc[-1]['收盤價']
            
            # 避免除以零
            if total_sheets != 0:
                avg_cost = round(total_amt / total_sheets, 2)
            else:
                avg_cost = 0
            
            # --- C. 呈現關鍵指標 ---
            col_m1, col_m2, col_m3 = st.columns(3)
            
            with col_m1:
                st.metric("篩選區間累積", f"{int(total_sheets)} 張")
            
            with col_m2:
                # 成本紅綠燈：若現價 > 成本 = 賺錢(紅)，反之賠錢(綠)
                # 若為賣超(張數為負)，邏輯相反：賣得比現價高 = 賺錢
                delta_color = "off"
                if avg_cost > 0:
                    diff = current_price - avg_cost
                    # 若是買超狀態 (張數>0)
                    if total_sheets > 0:
                        delta_color = "normal" if diff > 0 else "inverse"
                    # 若是賣超狀態 (張數<0)
                    elif total_sheets < 0:
                         delta_color = "inverse" if diff > 0 else "normal"
                         
                st.metric("區間平均成本", f"{avg_cost}", delta=round(current_price - avg_cost, 1), delta_color=delta_color)
            
            with col_m3:
                st.metric("最新收盤價", f"{current_price}")

            # --- D. 繪製圖表 (文青配色) ---
            # 累積張數計算 (基於圖表區間)
            df_chart["累積張數"] = df_chart["估算張數"].cumsum()
            
            # 配色：買超用柔和紅 (#E67F75)，賣超用柔和綠 (#6CB097)
            df_chart["顏色"] = df_chart["估算張數"].apply(lambda x: "#E67F75" if x > 0 else "#6CB097")

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # 1. 柱狀圖 (每日)
            fig.add_trace(
                go.Bar(
                    x=df_chart["日期"], 
                    y=df_chart["估算張數"], 
                    name="每日買賣(張)", 
                    marker_color=df_chart["顏色"],
                    opacity=0.8
                ), 
                secondary_y=False
            )
            
            # 2. 折線圖 (累積庫存) - 使用深藍色 (#2C3E50)
            fig.add_trace(
                go.Scatter(
                    x=df_chart["日期"], 
                    y=df_chart["累積張數"], 
                    name="累積庫存", 
                    line=dict(color='#2C3E50', width=2.5),
                    mode='lines' # 文青風通常不顯示圓點，只顯示線條
                ), 
                secondary_y=True
            )

            # 圖表美化
            fig.update_layout(
                title=dict(text="籌碼分佈趨勢", font=dict(size=14, color="#555")),
                legend=dict(orientation="h", y=1.15, x=0, font=dict(color="#555")),
                height=380,
                margin=dict(l=10, r=10, t=50, b=10),
                plot_bgcolor='rgba(0,0,0,0)', # 透明背景
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, tickfont=dict(color="#666")),
                yaxis=dict(showgrid=True, gridcolor="#E0E0E0", tickfont=dict(color="#666")), # 只留 Y 軸格線
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # 詳細表格
            with st.expander("📄 查看每日詳細數據"):
                st.dataframe(
                    df_chart[["日期", "收盤價", "估算張數", "累積張數"]].style.format({
                        "收盤價": "{:.2f}", 
                        "估算張數": "{:.0f}", 
                        "累積張數": "{:.0f}"
                    }), 
                    use_container_width=True,
                    hide_index=True
                )
    else:
        st.info("👈 請先點選「選股清單」分頁，選擇一檔股票。")