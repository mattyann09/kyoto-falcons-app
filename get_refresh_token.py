"""
初回だけ実行する認証スクリプト

これを実行すると、ブラウザが開いて
「kyotofalcons.appdata@gmail.com」でログイン・許可を求められます。
許可すると token.json というファイルが作られます。
これがあれば、今後アプリは自動でスプレッドシートへの書き込み・
Google Driveへの動画保存ができるようになります。

事前準備:
    pip install google-auth-oauthlib google-api-python-client google-auth-httplib2

使い方:
    python get_refresh_token.py

※ credentials.json と同じフォルダで実行してください。
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def main():
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)

    with open("token.json", "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print("\n✅ 認証完了!token.json が作られました。")
    print("このファイルの中身は、後でStreamlit Cloudの設定(Secrets)に登録します。")


if __name__ == "__main__":
    main()
