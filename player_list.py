"""
既存の「成績」スプレッドシート(読み取り専用)から、選手名の一覧だけを取得する。

※ 来年タブが増えたら、Home.py の YEAR_SHEET_MAP と同様に
   STATS_GID もその年のものに更新してください。
"""

import pandas as pd

STATS_SPREADSHEET_ID = "1Ewdh74gSzm0CqpbZAsze18hpDhSd6qIR"
STATS_GID = "1597079224"  # 2026年度シーズン成績のタブ


def get_player_names(section_keyword: str) -> list:
    """成績シートから、野手または投手の選手名一覧を取得する
    section_keyword: "野手" または "投手"
    """
    url = (
        f"https://docs.google.com/spreadsheets/d/{STATS_SPREADSHEET_ID}"
        f"/export?format=csv&gid={STATS_GID}"
    )
    try:
        raw = pd.read_csv(url, header=None)
    except Exception:
        return []

    section_row = None
    for i in range(len(raw)):
        joined = "".join(str(v) for v in raw.iloc[i].tolist())
        if section_keyword in joined:
            section_row = i
            break
    if section_row is None:
        return []

    header_row = None
    name_col_idx = None
    for i in range(section_row, min(section_row + 6, len(raw))):
        row_values = [str(v) for v in raw.iloc[i].tolist()]
        if "選手名" in row_values:
            header_row = i
            name_col_idx = row_values.index("選手名")
            break
    if header_row is None:
        return []

    names = []
    for i in range(header_row + 1, len(raw)):
        values = [str(v).strip() for v in raw.iloc[i].tolist()]
        if all(v in ("", "nan") for v in values):
            break
        name = values[name_col_idx]
        if name and name not in ("nan", "チーム成績"):
            names.append(name)
    return names
