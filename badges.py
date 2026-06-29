"""
成績の「節目(初めて達成・5刻み)」を検知して、お祝いメッセージを作る。

仕組み:
1. 前回見た時の数値を、解析データ用スプレッドシートの専用タブに保存しておく
2. 今回の数値と比較して、「初めて1に達した」または「5の倍数を超えた」ときに
   お祝いメッセージを作る(1個増えただけでは出さない)
3. 今回の数値を新しい「前回の値」として保存し直す

※ 何か失敗しても、成績ページ自体は止めないように作っています
   (バッジ機能はあくまで「あったら楽しい」機能のため)
"""

import pandas as pd

from save_analysis import load_credentials, read_sheet, write_full_sheet, ensure_sheet_exists

SNAPSHOT_SHEET_BATTING = "成績スナップショット_野手"
SNAPSHOT_SHEET_PITCHING = "成績スナップショット_投手"

# お祝いする項目(増えることが良いことの「カウント系」項目だけを選んでいます。
# 打率・防御率のような「割合系」や、増えると良くない項目は対象外にしています)
WATCHED_COLUMNS_BATTING = ["安打数", "本塁打", "打点", "盗塁", "得点"]
WATCHED_COLUMNS_PITCHING = ["奪三振"]

NAME_COL = "選手名"
MILESTONE_STEP = 5  # 初回以降は、この数おきにお祝いする


def get_milestones_crossed(prev_val: float, curr_val: float) -> list:
    """前回の値から今回の値までの間に超えた「節目」(初回、5刻み)を返す"""
    if pd.isna(prev_val) or pd.isna(curr_val):
        return []
    start = int(prev_val) + 1
    end = int(curr_val)
    milestones = []
    for m in range(start, end + 1):
        if m == 1 or m % MILESTONE_STEP == 0:
            milestones.append(m)
    return milestones


def check_and_show_badges(current_df: pd.DataFrame, tab_choice: str) -> list:
    """現在の成績と、前回保存したスナップショットを比べて、節目を達成していたら
    お祝いメッセージの文字列リストを返す(画面への表示は呼び出し側が行う)"""
    watched_cols = WATCHED_COLUMNS_BATTING if tab_choice == "打者" else WATCHED_COLUMNS_PITCHING
    snapshot_sheet = SNAPSHOT_SHEET_BATTING if tab_choice == "打者" else SNAPSHOT_SHEET_PITCHING

    watched_cols = [c for c in watched_cols if c in current_df.columns]
    if not watched_cols or NAME_COL not in current_df.columns:
        return []

    messages = []

    try:
        creds = load_credentials()
        ensure_sheet_exists(creds, snapshot_sheet)  # タブが無ければ先に作っておく
        previous_df = read_sheet(creds, snapshot_sheet)
    except Exception as e:
        import streamlit as st
        st.warning(f"⚠️ バッジ機能でエラー(読み込み): {e}")
        return []

    current_snapshot = current_df[[NAME_COL] + watched_cols].copy()
    for col in watched_cols:
        current_snapshot[col] = pd.to_numeric(current_snapshot[col], errors="coerce")

    if not previous_df.empty and NAME_COL in previous_df.columns:
        for col in watched_cols:
            if col in previous_df.columns:
                previous_df[col] = pd.to_numeric(previous_df[col], errors="coerce")

        for _, row in current_snapshot.iterrows():
            name = row[NAME_COL]
            prev_rows = previous_df[previous_df[NAME_COL] == name]
            if prev_rows.empty:
                continue
            prev_row = prev_rows.iloc[0]
            for col in watched_cols:
                if col not in prev_row.index:
                    continue
                curr_val = row[col]
                prev_val = prev_row[col]
                for milestone in get_milestones_crossed(prev_val, curr_val):
                    if milestone == 1:
                        text = f"初{col}達成!"
                    else:
                        text = f"{milestone}{col}達成!"
                    messages.append(f"{name}、{text}")

    try:
        write_full_sheet(creds, snapshot_sheet, current_snapshot)
    except Exception as e:
        import streamlit as st
        st.warning(f"⚠️ バッジ機能でエラー(保存): {e}")

    return messages
