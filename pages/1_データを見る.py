import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from save_analysis import (
    load_credentials,
    read_sheet,
    update_cell,
    delete_row,
    SHEET_NAME_BATTING,
    SHEET_NAME_PITCHING,
)
from player_list import get_player_names
from metric_info import get_description, get_comparison, METRIC_INFO

st.set_page_config(page_title="データを見る - 京都ファルコンズ", page_icon="🎥", layout="wide")


# -----------------------------------------------------------------------------
# 共通ヘッダー
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


render_header()
st.title("🎥 データを見る")


def ylabel_for(column_name: str) -> str:
    if "度" in column_name:
        return "Angle (degrees)"
    if "身長比" in column_name:
        return "Ratio (vs body height)"
    return "Value"


def video_embed_url(web_view_link: str) -> str:
    """webViewLinkから、画面に埋め込んで再生できるURLを作る"""
    try:
        file_id = web_view_link.split("/d/")[1].split("/")[0]
        return f"https://drive.google.com/file/d/{file_id}/preview"
    except (IndexError, AttributeError):
        return ""


mode_label = st.radio("見る種類", ["打者", "投手"], horizontal=True)
sheet_name = SHEET_NAME_BATTING if mode_label == "打者" else SHEET_NAME_PITCHING

with st.spinner("読み込み中..."):
    try:
        creds = load_credentials()
        df = read_sheet(creds, sheet_name)
    except Exception as e:
        st.error("データの読み込みに失敗しました。")
        st.exception(e)
        st.stop()

if df.empty:
    st.info("データはまだありません。")
    st.stop()

DATE_COL = df.columns[0]
NAME_COL = df.columns[1]
VIDEO_COL = df.columns[-1]
metric_cols = list(df.columns[2:-1])

# 数値の列はちゃんと数値に変換しておく(グラフ描画のため)
for col in metric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# スプレッドシート上の実際の行番号(1始まり、ヘッダーが1行目)を記録しておく
# (このあとの編集・削除機能で、どの行を直すか指定するのに使う)
df["_sheet_row"] = df.index + 2

players = df[NAME_COL].dropna().unique().tolist()
if not players:
    st.info("データはまだありません。")
    st.stop()

selected_player = st.selectbox("選手を選択", players)
player_df = df[df[NAME_COL] == selected_player].reset_index(drop=True)

tab_list, tab_growth = st.tabs(["📋 一覧", "📈 成長を見る"])

# =============================================================================
# 一覧タブ
# =============================================================================
with tab_list:
    if player_df.empty:
        st.info("データはまだありません。")
    else:
        st.dataframe(player_df, use_container_width=True, hide_index=True)

        st.write("")
        st.caption("👇 動画を見たいデータを選んでください")
        picked_label = st.selectbox(
            "日時を選択", player_df[DATE_COL].tolist(), label_visibility="collapsed"
        )
        picked_row = player_df[player_df[DATE_COL] == picked_label].iloc[0]

        embed_url = video_embed_url(picked_row[VIDEO_COL])
        if embed_url:
            st.components.v1.iframe(embed_url, height=400)
        else:
            st.warning("動画のリンクが見つかりませんでした。")

        cols = st.columns(len(metric_cols))
        for c, mcol in zip(cols, metric_cols):
            val = picked_row[mcol]
            c.metric(mcol, f"{val:.2f}" if pd.notna(val) else "—", help=get_description(mcol))
            if pd.notna(val):
                comparison = get_comparison(mcol, val)
                if comparison:
                    c.caption(comparison)

        st.write("")
        with st.expander("✏️ このデータを編集・削除する"):
            all_player_names = get_player_names("野手" if mode_label == "打者" else "投手")
            if not all_player_names:
                all_player_names = players

            current_name = picked_row[NAME_COL]
            options = all_player_names if current_name in all_player_names else [current_name] + all_player_names
            new_name = st.selectbox(
                "選手名を変更する", options, index=options.index(current_name)
            )

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("💾 選手名を保存する", use_container_width=True):
                    sheet_row = int(picked_row["_sheet_row"])
                    update_cell(creds, sheet_name, f"B{sheet_row}", new_name)
                    st.success("更新しました")
                    st.rerun()
            with col_b:
                delete_key = f"confirm_delete_{sheet_name}_{int(picked_row['_sheet_row'])}"
                if not st.session_state.get(delete_key, False):
                    if st.button("🗑️ このデータを削除する", use_container_width=True):
                        st.session_state[delete_key] = True
                        st.rerun()
                else:
                    st.warning("本当に削除しますか?この操作は元に戻せません。")
                    yes_col, no_col = st.columns(2)
                    with yes_col:
                        if st.button("はい、削除する", type="primary", use_container_width=True):
                            sheet_row = int(picked_row["_sheet_row"])
                            delete_row(creds, sheet_name, sheet_row)
                            st.session_state[delete_key] = False
                            st.success("削除しました")
                            st.rerun()
                    with no_col:
                        if st.button("キャンセル", use_container_width=True):
                            st.session_state[delete_key] = False
                            st.rerun()

# =============================================================================
# 成長を見るタブ
# =============================================================================
with tab_growth:
    if len(player_df) < 2:
        st.info("成長グラフを表示するには、2件以上のデータが必要です。")
    else:
        chart_cols = st.columns(2)
        for i, mcol in enumerate(metric_cols):
            with chart_cols[i % 2]:
                st.caption(mcol)
                fig, ax = plt.subplots(figsize=(5, 2.5))
                ax.plot(range(len(player_df)), player_df[mcol], marker="o")

                info = METRIC_INFO.get(mcol)
                if info and info.get("ideal_range"):
                    low, high = info["ideal_range"]
                    ax.axhspan(low, high, color="green", alpha=0.1, label="Ideal range")
                    ax.legend(fontsize=7, loc="upper right")

                ax.set_xticks(range(len(player_df)))
                ax.set_xticklabels(player_df[DATE_COL], rotation=45, ha="right", fontsize=7)
                ax.set_ylabel(ylabel_for(mcol))
                ax.grid(alpha=0.3)
                fig.tight_layout()
                st.pyplot(fig)
