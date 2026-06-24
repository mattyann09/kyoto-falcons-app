import streamlit as st

st.set_page_config(page_title="データを分析する - 京都ファルコンズ", page_icon="🧠", layout="wide")

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

st.title("🧠 データを分析する")
st.info(
    "🚧 準備中です。\n\n"
    "今後ここに、バッティング動作解析・ピッチング動作解析の機能を追加していきます。"
)
