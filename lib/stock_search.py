from __future__ import annotations

import pandas as pd

ID_COL = "代號"
NAME_COL = "名稱"
DATE_COL = "日期"


def build_stock_options(df: pd.DataFrame) -> pd.DataFrame:
    """Return one latest name row per stock id for search/autocomplete."""
    required = {ID_COL, NAME_COL, DATE_COL}
    if df.empty or not required.issubset(df.columns):
        return pd.DataFrame(columns=[ID_COL, NAME_COL])

    rows = df[[ID_COL, NAME_COL, DATE_COL]].copy()
    rows[ID_COL] = rows[ID_COL].astype(str).str.strip()
    rows[NAME_COL] = rows[NAME_COL].astype(str).str.strip()
    rows = rows[(rows[ID_COL] != "") & (rows[NAME_COL] != "")]
    if rows.empty:
        return pd.DataFrame(columns=[ID_COL, NAME_COL])

    latest = (
        rows.sort_values(DATE_COL)
        .drop_duplicates(subset=[ID_COL], keep="last")
        [[ID_COL, NAME_COL]]
        .sort_values(ID_COL)
        .reset_index(drop=True)
    )
    return latest


def search_stocks(df: pd.DataFrame, query: str, limit: int = 20) -> pd.DataFrame:
    """Search stocks by id or display name, prioritising exact and prefix matches."""
    options = build_stock_options(df)
    normalized_query = str(query).strip().lower()
    if options.empty or not normalized_query:
        return options.head(0)

    searchable = options.copy()
    id_text = searchable[ID_COL].astype(str).str.lower()
    name_text = searchable[NAME_COL].astype(str).str.lower()
    mask = id_text.str.contains(normalized_query, regex=False) | name_text.str.contains(
        normalized_query,
        regex=False,
    )
    matches = searchable.loc[mask].copy()
    if matches.empty:
        return matches

    match_id = matches[ID_COL].astype(str).str.lower()
    match_name = matches[NAME_COL].astype(str).str.lower()
    matches["_rank"] = 4
    matches.loc[match_name.str.contains(normalized_query, regex=False), "_rank"] = 3
    matches.loc[match_id.str.startswith(normalized_query), "_rank"] = 2
    matches.loc[match_name.str.startswith(normalized_query), "_rank"] = 1
    matches.loc[match_id == normalized_query, "_rank"] = 0

    return (
        matches.sort_values(["_rank", ID_COL])
        .drop(columns=["_rank"])
        .head(limit)
        .reset_index(drop=True)
    )
