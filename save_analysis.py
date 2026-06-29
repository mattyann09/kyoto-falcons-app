"""
動画を解析して、結果をスプレッドシート + Google Driveに保存するスクリプト

事前準備:
    pip install mediapipe opencv-python numpy pandas google-auth-oauthlib google-api-python-client google-auth-httplib2

使い方:
    python save_analysis.py 動画のパス batting 右打者 選手名
    python save_analysis.py 動画のパス pitching 右投げ 選手名

例:
    python save_analysis.py swing1.mp4 batting 右打者 龍野眞佳

※ token.json, credentials.json, analysis_engine.py と同じフォルダで実行してください。
"""

import sys
import os
import datetime

import pandas as pd
import streamlit as st
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from analysis_engine import analyze_batting, analyze_pitching

# =============================================================================
SPREADSHEET_ID = "1hWxYWQ4M91Y3q_RZAugz-wVtDEzqr91MXzmZBseX8mI"
DRIVE_FOLDER_ID = "1-JbTfX6baFAcm-V2j3idslvP5oUN5V5A"

SHEET_NAME_BATTING = "打者用"
SHEET_NAME_PITCHING = "投手用"
# =============================================================================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def load_credentials():
    """
    パソコンで動かしてる時は token.json から読む。
    Streamlit Cloudで公開してる時は、安全な場所(Secrets)から読む。
    """
    try:
        has_secret = "gcp_oauth" in st.secrets
    except Exception:
        has_secret = False

    if has_secret:
        info = {
            "refresh_token": st.secrets["gcp_oauth"]["refresh_token"],
            "client_id": st.secrets["gcp_oauth"]["client_id"],
            "client_secret": st.secrets["gcp_oauth"]["client_secret"],
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        creds = Credentials.from_authorized_user_info(info, SCOPES)
    else:
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def upload_video(creds, video_path: str) -> dict:
    service = build("drive", "v3", credentials=creds)
    file_metadata = {
        "name": os.path.basename(video_path),
        "parents": [DRIVE_FOLDER_ID],
    }
    media = MediaFileUpload(video_path, resumable=True)
    file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id, webViewLink")
        .execute()
    )

    # チーム全員が(リンクを知っていれば)動画を見れるようにする
    service.permissions().create(
        fileId=file["id"],
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return {"id": file["id"], "webViewLink": file["webViewLink"]}


def append_row(creds, sheet_name: str, row: list):
    service = build("sheets", "v4", credentials=creds)
    body = {"values": [row]}
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!A1",
        valueInputOption="RAW",
        body=body,
    ).execute()


def read_sheet(creds, sheet_name: str) -> pd.DataFrame:
    """保存済みのデータを表として読み込む"""
    service = build("sheets", "v4", credentials=creds)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=f"{sheet_name}!A:Z")
        .execute()
    )
    values = result.get("values", [])
    if not values:
        return pd.DataFrame()

    header, *rows = values
    # 空セルがあると行の長さがヘッダーより短くなるので、揃える
    rows = [r + [""] * (len(header) - len(r)) for r in rows]
    return pd.DataFrame(rows, columns=header)


def update_cell(creds, sheet_name: str, cell: str, value: str):
    """1つのセルの値を書き換える(例: cell='B5')"""
    service = build("sheets", "v4", credentials=creds)
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!{cell}",
        valueInputOption="RAW",
        body={"values": [[value]]},
    ).execute()


def _get_sheet_id(service, sheet_name: str) -> int:
    metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in metadata["sheets"]:
        if s["properties"]["title"] == sheet_name:
            return s["properties"]["sheetId"]
    raise ValueError(f"シート '{sheet_name}' が見つかりません")


def delete_row(creds, sheet_name: str, row_number: int):
    """指定した行(1始まり。ヘッダーが1行目)をシートから完全に削除する"""
    service = build("sheets", "v4", credentials=creds)
    sheet_id = _get_sheet_id(service, sheet_name)
    requests = [
        {
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": row_number - 1,  # APIは0始まり
                    "endIndex": row_number,
                }
            }
        }
    ]
    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
    ).execute()


def ensure_sheet_exists(creds, sheet_name: str):
    """指定した名前のタブが無ければ、新しく作る"""
    service = build("sheets", "v4", credentials=creds)
    metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    existing = [s["properties"]["title"] for s in metadata["sheets"]]
    if sheet_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
        ).execute()


def write_full_sheet(creds, sheet_name: str, df: pd.DataFrame):
    """シートの中身を全部、指定したデータで置き換える(無ければタブも自動作成)"""
    ensure_sheet_exists(creds, sheet_name)
    service = build("sheets", "v4", credentials=creds)
    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID, range=f"{sheet_name}!A:Z"
    ).execute()

    def cell_to_str(v):
        # NaN(空っぽの値)が混ざっていると送信時にエラーになるため、空文字に変換する
        if pd.isna(v):
            return ""
        return str(v)

    values = [list(df.columns)]
    for _, row in df.iterrows():
        values.append([cell_to_str(v) for v in row.tolist()])

    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()


def main():
    if len(sys.argv) < 5:
        print("使い方:")
        print("  python save_analysis.py 動画のパス batting 右打者 選手名 身長cm")
        print("  python save_analysis.py 動画のパス pitching 右投げ 選手名")
        sys.exit(1)

    video_path, mode, side, player_name = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

    print("① 動画を解析中...")
    if mode == "batting":
        if len(sys.argv) < 6:
            print("打者の解析には、選手の身長(cm)も指定してください。")
            print("例: python save_analysis.py swing1.mp4 batting 右打者 龍野眞佳 170")
            sys.exit(1)
        height = float(sys.argv[5])
        result, _timeseries = analyze_batting(video_path, side, player_height_cm=height)
        sheet_name = SHEET_NAME_BATTING
    elif mode == "pitching":
        result, _timeseries = analyze_pitching(video_path, side)
        sheet_name = SHEET_NAME_PITCHING
    else:
        print("2番目の引数は batting か pitching にしてください")
        sys.exit(1)

    print("解析結果:")
    for k, v in result.items():
        print(f"  {k}: {v:.3f}")

    print("\n② Googleに接続中...")
    creds = load_credentials()

    print("③ 動画をGoogle Driveにアップロード中...(動画の長さによって時間がかかります)")
    video_info = upload_video(creds, video_path)
    video_link = video_info["webViewLink"]
    print(f"  アップロード完了: {video_link}")

    print("④ スプレッドシートに保存中...")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    row = [timestamp, player_name] + list(result.values()) + [video_link]
    append_row(creds, sheet_name, row)

    print("\n🎉 保存完了!スプレッドシートを確認してみてください。")


if __name__ == "__main__":
    main()
