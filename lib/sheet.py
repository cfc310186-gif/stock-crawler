"""Google Sheet 共用連線與讀寫工具"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable

import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

from settings import JSON_FILE_NAME, SHEET_NAME

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

DEFAULT_NUMERIC_COLS = ("買賣超金額(千)", "收盤價", "估算張數")
DEFAULT_DATE_COL = "日期"
DEFAULT_ID_COL = "代號"


class SheetNotReady(RuntimeError):
    """找不到 service_account.json 或 GCP_CREDENTIALS 環境變數"""


def _ensure_keyfile() -> str:
    """確保本機有 service_account.json；若無則嘗試從 GCP_CREDENTIALS 環境變數寫出。"""
    if os.path.exists(JSON_FILE_NAME):
        return JSON_FILE_NAME
    env_value = os.environ.get("GCP_CREDENTIALS")
    if not env_value:
        raise SheetNotReady(
            f"找不到 {JSON_FILE_NAME}，且環境變數 GCP_CREDENTIALS 也未設定"
        )
    with open(JSON_FILE_NAME, "w", encoding="utf-8") as f:
        f.write(env_value)
    return JSON_FILE_NAME


def get_client() -> gspread.Client:
    keyfile = _ensure_keyfile()
    creds = ServiceAccountCredentials.from_json_keyfile_name(keyfile, SCOPE)
    return gspread.authorize(creds)


def open_sheet(sheet_name: str = SHEET_NAME):
    """打開試算表並回傳第一頁 worksheet"""
    client = get_client()
    return client.open(sheet_name).sheet1


def load_dataframe(
    sheet_name: str = SHEET_NAME,
    numeric_cols: Iterable[str] = DEFAULT_NUMERIC_COLS,
    date_col: str = DEFAULT_DATE_COL,
    id_col: str = DEFAULT_ID_COL,
) -> pd.DataFrame | None:
    """讀取 sheet 並回傳預處理過的 DataFrame。Sheet 空時回傳 None。"""
    sheet = open_sheet(sheet_name)
    data = sheet.get_all_values()
    if not data:
        return None

    headers = data[0]
    rows = data[1:]
    df = pd.DataFrame(rows, columns=headers)

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", ""), errors="coerce"
            ).fillna(0)

    if date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col])
    if id_col in df.columns:
        df[id_col] = df[id_col].astype(str)

    return df


def overwrite_sheet(sheet, dataframe: pd.DataFrame) -> None:
    """以 DataFrame 全量覆寫 sheet (含 header)"""
    payload = [dataframe.columns.values.tolist()] + dataframe.values.tolist()
    sheet.clear()
    sheet.update(payload)


def load_credentials_from_json_string(json_str: str) -> None:
    """Streamlit 專用：把 st.secrets['GCP_CREDENTIALS'] 寫到本機以便 get_client 取用。"""
    data = json.loads(json_str) if isinstance(json_str, str) else json_str
    with open(JSON_FILE_NAME, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
