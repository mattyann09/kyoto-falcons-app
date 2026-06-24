import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="成績を見る - 京都ファルコンズ", page_icon="📊", layout="wide")

# =============================================================================
# ↓↓↓ ここをあなたのスプレッドシートの情報に書き換えてください ↓↓↓
# =============================================================================
SPREADSHEET_ID = "1Ewdh74gSzm0CqpbZAsze18hpDhSd6qIR"  # 2026年度シーズン成績のID(参考用)

# 年度ごとの設定(スプレッドシートID + タブのgid)
# 来年以降「同じファイルの別タブ」でも「全く新しいスプレッドシート」でも、
# どちらでもこの下に1行追加するだけで対応できます
YEAR_SHEET_MAP = {
    2026: {"spreadsheet_id": "1Ewdh74gSzm0CqpbZAsze18hpDhSd6qIR", "gid": "1597079224"},
    # 2027: {"spreadsheet_id": "【2027年のスプレッドシートID】", "gid": "【2027年タブのgid】"},
}
# =============================================================================

NAME_COL = "選手名"


def sheet_url(spreadsheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"


@st.cache_data(ttl=300)  # 5分間キャッシュ
def load_raw_sheet(url: str) -> pd.DataFrame:
    # header=None: 1行目をヘッダーとして決めつけず、シート全体をそのまま読み込む
    # (野手の表・投手の表が同じタブの中で上下に並んでいるため)
    return pd.read_csv(url, header=None)


def extract_table(raw: pd.DataFrame, section_keyword: str):
    """rawの中から section_keyword (例:「野手」「投手」) を含む見出し行を探し、
    その下にある「選手名」のヘッダー行から、空行が出るまでのデータを抜き出す。
    戻り値は (個人成績の表, チーム成績の行 または None) のタプル"""

    section_row = None
    for i in range(len(raw)):
        joined = "".join(str(v) for v in raw.iloc[i].tolist())
        if section_keyword in joined:
            section_row = i
            break
    if section_row is None:
        return pd.DataFrame(), None

    header_row = None
    for i in range(section_row, min(section_row + 6, len(raw))):
        row_values = [str(v) for v in raw.iloc[i].tolist()]
        if NAME_COL in row_values:
            header_row = i
            break
    if header_row is None:
        return pd.DataFrame(), None

    headers = raw.iloc[header_row].tolist()

    data_rows = []
    team_row_values = None
    for i in range(header_row + 1, len(raw)):
        row = raw.iloc[i]
        values = [str(v).strip() for v in row.tolist()]
        if all(v in ("", "nan") for v in values):
            break
        if "チーム成績" in values:
            # 列を絞り込む前のこの時点で検出しておく
            # (結合セルの影響で「選手名」以外の列に文字が入っている場合があるため)
            team_row_values = row.tolist()
            continue
        data_rows.append(row.tolist())

    df = pd.DataFrame(data_rows, columns=headers)
    df = df.loc[:, df.columns.notna()]  # 名前のない列(空列)を除外

    team_row = None
    if team_row_values is not None:
        team_row = pd.Series(team_row_values, index=headers)
        team_row = team_row[team_row.index.notna()]

    return df, team_row


def parse_innings_pitched(value) -> float:
    """投球回の表記('7' '22 1/3' など)を小数(7.0 / 22.33...)に変換する。
    野球で「1/3イニング」「2/3イニング」を表す独特の表記に対応するための専用処理。"""
    if pd.isna(value):
        return np.nan
    s = str(value).strip()
    if s in ("", "nan"):
        return np.nan

    parts = s.split()
    try:
        if len(parts) == 2 and "/" in parts[1]:
            whole = float(parts[0])
            num, den = parts[1].split("/")
            return whole + float(num) / float(den)
        if "/" in s:
            num, den = s.split("/")
            return float(num) / float(den)
        return float(s)
    except (ValueError, ZeroDivisionError):
        return np.nan


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """数値っぽい列は数値に変換する(#DIV/0!はNaNになる)。
    「投球回」は野球独特の '22 1/3' 表記があるため専用パーサーで変換する。"""
    df = df.copy()
    for col in df.columns:
        if col == NAME_COL:
            continue
        if col == "投球回":
            df[col] = df[col].apply(parse_innings_pitched)
            continue
        original_count = df[col].notna().sum()
        converted = pd.to_numeric(df[col], errors="coerce")
        if original_count > 0 and converted.notna().sum() >= original_count * 0.5:
            df[col] = converted
    return df


# -----------------------------------------------------------------------------
# 共通ヘッダー(赤文字タイトル + 青枠3ボタン)
# -----------------------------------------------------------------------------
def render_header():
    st.markdown(
        """
        <style>
        div[data-testid="stPageLink"] {
            border: 2px solid #3b82f6;
            border-radius: 10px;
            padding: 4px 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("### :red[京都ファルコンズ 成績・データ分析管理]")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.page_link("Home.py", label="成績を見る", icon="📊")
    with c2:
        st.page_link("pages/1_データを見る.py", label="データを見る", icon="🎥")
    with c3:
        st.page_link("pages/2_データを分析する.py", label="データを分析する", icon="🧠")
    st.markdown("---")


# -----------------------------------------------------------------------------
# 個人成績(カード形式) ← 選手を選ぶとこの画面に切り替わる
# -----------------------------------------------------------------------------
def render_player_detail(player_name: str, row: pd.Series):
    st.subheader(f"👤 {player_name} 成績")

    stat_items = [
        (col, val) for col, val in row.items()
        if col != NAME_COL and pd.notna(val)
    ]

    cols_per_row = 4
    for i in range(0, len(stat_items), cols_per_row):
        chunk = stat_items[i:i + cols_per_row]
        cols = st.columns(len(chunk))
        for c, (label, value) in zip(cols, chunk):
            c.metric(label, value)

    st.write("")
    if st.button("⬅ 一覧に戻る"):
        st.session_state.selected_player = None
        st.rerun()


# -----------------------------------------------------------------------------
# 個人成績一覧(打者/投手タブ切り替え)
# -----------------------------------------------------------------------------
def render_stats_view():
    st.subheader("個人成績")

    col_a, col_b = st.columns(2)
    with col_a:
        years = sorted(YEAR_SHEET_MAP.keys(), reverse=True)
        selected_year = st.selectbox("年度", years)
    with col_b:
        tab_choice = st.radio("成績の種類", ["打者", "投手"], horizontal=True)

    sheet_info = YEAR_SHEET_MAP[selected_year]

    try:
        raw = load_raw_sheet(sheet_url(sheet_info["spreadsheet_id"], sheet_info["gid"]))
    except Exception as e:
        st.error(
            "スプレッドシートの読み込みに失敗しました。\n"
            "・gidの値が正しいか\n"
            "・共有設定が「リンクを知っている全員(閲覧者)」になっているか\n"
            "を確認してください。"
        )
        st.exception(e)
        return

    section_keyword = "野手" if tab_choice == "打者" else "投手"
    df, team_row = extract_table(raw, section_keyword)

    if df.empty:
        st.warning(
            "データが見つかりませんでした。スプレッドシートの見出し"
            "(「個人成績　(野手)」「個人成績　(投手)」)の表記が変わっていないか確認してください。"
        )
        return

    df = coerce_numeric(df)

    if team_row is not None:
        with st.expander("📋 チーム全体成績(合計)"):
            stat_items = [
                (col, val) for col, val in team_row.items()
                if col != NAME_COL and pd.notna(val)
            ]
            cols_per_row = 4
            for i in range(0, len(stat_items), cols_per_row):
                chunk = stat_items[i:i + cols_per_row]
                cols = st.columns(len(chunk))
                for c, (label, value) in zip(cols, chunk):
                    c.metric(label, value)

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.write("")
    st.caption("👇 選手を選んで個人成績ページを見る")
    col1, col2 = st.columns([3, 1])
    with col1:
        player_names = df[NAME_COL].dropna().unique().tolist()
        picked = st.selectbox("選手を選択", player_names, label_visibility="collapsed")
    with col2:
        if st.button("成績を見る ➡", use_container_width=True):
            row = df[df[NAME_COL] == picked].iloc[0]
            st.session_state.selected_player = picked
            st.session_state.selected_player_row = row.to_dict()
            st.rerun()


# -----------------------------------------------------------------------------
# メイン処理
# -----------------------------------------------------------------------------
render_header()

if "selected_player" not in st.session_state:
    st.session_state.selected_player = None

if st.session_state.selected_player:
    row = pd.Series(st.session_state.selected_player_row)
    render_player_detail(st.session_state.selected_player, row)
else:
    render_stats_view()
