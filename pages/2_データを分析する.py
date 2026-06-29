import os
import tempfile
import datetime

import streamlit as st
import matplotlib.pyplot as plt

from analysis_engine import analyze_batting, analyze_pitching
from save_analysis import load_credentials, upload_video, append_row, SHEET_NAME_BATTING, SHEET_NAME_PITCHING
from player_list import get_player_names
from metric_info import get_description, get_ideal_note, get_comparison

st.set_page_config(page_title="データを分析する - 京都ファルコンズ", page_icon="🧠", layout="wide")


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
st.title("🧠 データを分析する")

# -----------------------------------------------------------------------------
# 画面の状態管理(入力 → 結果 → 保存完了 の3段階)
# -----------------------------------------------------------------------------
if "analysis_stage" not in st.session_state:
    st.session_state.analysis_stage = "input"  # input / result / saved


# =============================================================================
# ① 入力画面
# =============================================================================
def render_input_screen():
    st.info(
        "📹 撮影のポイント: **横から、全身(頭から足まで)が映るように**撮影してください。"
        "全身が映っていないと、着地のタイミングなどがうまく判定できません。"
    )

    mode_label = st.radio("分析する種類", ["打者", "投手"], horizontal=True)
    mode = "batting" if mode_label == "打者" else "pitching"

    section_keyword = "野手" if mode == "batting" else "投手"
    player_names = get_player_names(section_keyword)

    if player_names:
        player_name = st.selectbox("選手を選択してください", player_names)
    else:
        st.warning("成績シートから選手名を取得できませんでした。直接入力してください。")
        player_name = st.text_input("選手名を入力してください")

    if mode == "batting":
        side = st.radio("利き手", ["右打者", "左打者"], horizontal=True)
        col_h, col_b = st.columns(2)
        with col_h:
            height_cm = st.number_input(
                "選手の身長(cm) ※バットスピードの計算に必須です",
                min_value=0, max_value=220, value=0, step=1,
            )
        with col_b:
            bat_length_cm = st.number_input("バットの長さ(cm)", min_value=50, max_value=110, value=84, step=1)
    else:
        side = st.radio("利き手", ["右投げ", "左投げ"], horizontal=True)

    uploaded_file = st.file_uploader("動画を貼ろう", type=["mp4", "mov", "avi"])

    if uploaded_file is not None:
        st.video(uploaded_file)

    if st.button("解析を実行する ➡", type="primary", use_container_width=True):
        if not player_name:
            st.error("選手名を入力してください。")
            return
        if uploaded_file is None:
            st.error("動画を選んでください。")
            return
        if mode == "batting" and height_cm <= 0:
            st.error("選手の身長を入力してください(バットスピードの計算に必要です)。")
            return

        # アップロードされた動画を、一旦パソコン上の一時ファイルに保存する
        # (動画を解析するにも、Driveにアップロードするにも、ファイルのパスが必要なため)
        suffix = os.path.splitext(uploaded_file.name)[1] or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getvalue())
            video_path = tmp.name

        with st.spinner("動画を解析中です...(動画の長さによって数十秒〜数分かかります)"):
            try:
                if mode == "batting":
                    result, timeseries = analyze_batting(
                        video_path, side,
                        player_height_cm=height_cm if height_cm > 0 else None,
                        bat_length_cm=bat_length_cm,
                    )
                else:
                    result, timeseries = analyze_pitching(video_path, side)
            except Exception as e:
                st.error("解析に失敗しました。動画の撮影アングルなどを確認してください。")
                st.exception(e)
                return

        st.session_state.analysis_mode = mode
        st.session_state.analysis_player_name = player_name
        st.session_state.analysis_side = side
        st.session_state.analysis_video_path = video_path
        st.session_state.analysis_result = result
        st.session_state.analysis_timeseries = timeseries
        st.session_state.analysis_stage = "result"
        st.rerun()


# =============================================================================
# ② 結果画面
# =============================================================================
def render_result_screen():
    result = st.session_state.analysis_result

    st.subheader(f"📊 {st.session_state.analysis_player_name} さんの分析結果")
    st.video(st.session_state.analysis_video_path)

    cols = st.columns(len(result))
    for col, (label, value) in zip(cols, result.items()):
        col.metric(label, f"{value:.2f}", help=get_description(label))
        comparison = get_comparison(label, value)
        if comparison:
            col.caption(comparison)
        else:
            col.caption("📌 自己ベストと比較しよう")

    with st.expander("ℹ️ 各指標の詳しい説明を見る"):
        for label in result.keys():
            st.markdown(f"**{label}**")
            st.write(get_description(label))
            note = get_ideal_note(label)
            if note:
                st.caption(note)
            st.write("")

    st.write("")
    st.subheader("📈 動きの推移")
    timeseries = st.session_state.analysis_timeseries
    graph_cols = [c for c in timeseries.columns if c != "time_s"]
    chart_cols = st.columns(len(graph_cols))

    def ylabel_for(column_name: str) -> str:
        # ラベルは日本語フォントが無い環境でも表示が崩れないよう英語表記にしています
        if "度" in column_name:
            return "Angle (degrees)"
        if "身長比" in column_name:
            return "Ratio (vs body height)"
        return "Value"

    for col, label in zip(chart_cols, graph_cols):
        with col:
            st.caption(label)
            fig, ax = plt.subplots(figsize=(3, 2.5))
            ax.plot(timeseries["time_s"], timeseries[label])
            ax.set_xlabel("Time (seconds)")
            ax.set_ylabel(ylabel_for(label))
            ax.grid(alpha=0.3)
            st.pyplot(fig)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅ 保存せずに戻る", use_container_width=True):
            st.session_state.analysis_stage = "input"
            st.rerun()
    with col2:
        save_label = f"{st.session_state.analysis_player_name} としてデータを保存する ➡"
        if st.button(save_label, type="primary", use_container_width=True):
            with st.spinner("保存中です...(動画のアップロードに時間がかかることがあります)"):
                try:
                    creds = load_credentials()
                    video_info = upload_video(creds, st.session_state.analysis_video_path)
                    video_link = video_info["webViewLink"]

                    sheet_name = (
                        SHEET_NAME_BATTING
                        if st.session_state.analysis_mode == "batting"
                        else SHEET_NAME_PITCHING
                    )
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    row = (
                        [timestamp, st.session_state.analysis_player_name]
                        + list(result.values())
                        + [video_link]
                    )
                    append_row(creds, sheet_name, row)
                except Exception as e:
                    st.error("保存に失敗しました。")
                    st.exception(e)
                    return

            st.session_state.analysis_stage = "saved"
            st.rerun()


# =============================================================================
# ③ 保存完了画面
# =============================================================================
def render_saved_screen():
    st.success("データ保存完了!!")
    st.write("続けてデータ分析しますか?")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("はい", use_container_width=True):
            st.session_state.analysis_stage = "input"
            st.rerun()
    with col2:
        if st.button("いいえ(メニューに戻る)", use_container_width=True):
            st.session_state.analysis_stage = "input"
            st.switch_page("Home.py")


# -----------------------------------------------------------------------------
# メイン処理
# -----------------------------------------------------------------------------
if st.session_state.analysis_stage == "input":
    render_input_screen()
elif st.session_state.analysis_stage == "result":
    render_result_screen()
elif st.session_state.analysis_stage == "saved":
    render_saved_screen()
