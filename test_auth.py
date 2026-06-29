"""
認証(token.json)が正しく機能するかを確認するテストスクリプト

スプレッドシートに1行書き込み、Driveに1つファイルをアップロードしてみて、
両方成功するか確認します。

事前準備:
    pip install google-auth-oauthlib google-api-python-client google-auth-httplib2

使い方:
    python test_auth.py

※ token.json と同じフォルダで実行してください。
"""

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SPREADSHEET_ID = "1hWxYWQ4M91Y3q_RZAugz-wVtDEzqr91MXzmZBseX8mI"
DRIVE_FOLDER_ID = "1-JbTfX6baFAcm-V2j3idslvP5oUN5V5A"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def load_credentials():
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def test_sheets(creds):
    service = build("sheets", "v4", credentials=creds)
    body = {"values": [["テスト行", "認証テスト成功", "🎉"]]}
    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=SPREADSHEET_ID,
            range="A1",
            valueInputOption="RAW",
            body=body,
        )
        .execute()
    )
    print("✅ スプレッドシートへの書き込み成功:", result.get("updates"))


def test_drive(creds):
    service = build("drive", "v3", credentials=creds)

    with open("test_upload.txt", "w", encoding="utf-8") as f:
        f.write("認証テスト用ファイルです。確認後は削除してOKです。")

    file_metadata = {"name": "認証テスト.txt", "parents": [DRIVE_FOLDER_ID]}
    media = MediaFileUpload("test_upload.txt")
    file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id, webViewLink")
        .execute()
    )
    print("✅ Driveへのアップロード成功:", file.get("webViewLink"))


if __name__ == "__main__":
    creds = load_credentials()
    test_sheets(creds)
    test_drive(creds)
    print("\n🎉 すべてのテストが成功しました!")
