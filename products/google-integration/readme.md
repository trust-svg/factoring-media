# Google連携 AIエージェント

Gmail・Googleカレンダー・GoogleドライブをAIで操作するCLIエージェント。

## できること

| 機能 | 例 |
|------|-----|
| **スケジュール自動登録** | 「このメール見てカレンダーに登録して」 |
| **メール返信文生成** | 「このメールに返信文を作って」→確認→送信 |
| **Driveファイル参照・編集** | 「議事録.docxを探して内容を教えて」 |

---

## セットアップ

### ステップ 1: Google Cloud Console でプロジェクトを作成する

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセスしてGoogleアカウントでログイン

2. 画面上部の「プロジェクトを選択」→「新しいプロジェクト」をクリック

3. プロジェクト名に「google-agent」と入力して「作成」

---

### ステップ 2: Google APIを有効化する

1. 左メニュー「APIとサービス」→「ライブラリ」をクリック

2. 以下の3つを検索して、それぞれ「有効にする」をクリック：
   - **Google Calendar API**
   - **Gmail API**
   - **Google Drive API**

---

### ステップ 3: OAuth 2.0 クライアントIDを作成する

1. 左メニュー「APIとサービス」→「認証情報」をクリック

2. 「+ 認証情報を作成」→「OAuth クライアントID」をクリック

3. 「同意画面を構成」が表示されたら：
   - 「外部」を選択して「作成」
   - アプリ名（例: google-agent）を入力
   - メールアドレスを入力
   - 下部の「保存して次へ」を何度かクリックして完了

4. 再び「認証情報」→「+ 認証情報を作成」→「OAuth クライアントID」

5. アプリケーションの種類：**「デスクトップアプリ」** を選択

6. 名前は任意（例: google-agent-desktop）→「作成」

7. 「JSONをダウンロード」をクリックして `credentials.json` を取得

8. ダウンロードした `credentials.json` を **このフォルダ（Google連携/）** に置く

---

### ステップ 4: Anthropic APIキーを設定する

1. [Anthropic Console](https://console.anthropic.com/) でAPIキーを取得

2. `.env.example` をコピーして `.env` を作成：

```bash
cp .env.example .env
```

3. `.env` を開いて `ANTHROPIC_API_KEY` に取得したキーを貼り付け：

```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx
```

---

### ステップ 5: ライブラリをインストールする

```bash
cd /Users/Mac_air/Desktop/Cursor/Google連携
pip install -r requirements.txt
```

---

### ステップ 6: 起動する

```bash
python main.py
```

初回起動時：
- ブラウザが自動で開きます
- Googleアカウントでログインして「許可」をクリック
- `token.json` が自動生成されて認証完了

次回以降は `token.json` が使われるのでブラウザは開きません。

---

## 使い方の例

```
あなた: 最新のメールを5件見せて
AI: 以下のメールが届いています...

あなた: 一番上のメールに返信して「来週の月曜日に伺います」と書いて
AI: 以下の返信文を作成しました：
    ----
    〇〇様
    来週の月曜日に伺います。
    ----
    送信しますか？

あなた: OK
AI: 送信しました！

あなた: 来週月曜の14時から1時間、会議をカレンダーに登録して
AI: 「会議」2025-03-10 14:00〜15:00 で登録しますか？

あなた: はい
AI: 登録しました！

あなた: 議事録というファイルをDriveで探して
AI: 以下のファイルが見つかりました...
```

---

## ファイル構成

```
Google連携/
├── main.py              # メインの対話ループ
├── agent.py             # Claude AI + ツール統合
├── auth.py              # Google OAuth 2.0認証
├── calendar_tool.py     # カレンダー操作
├── gmail_tool.py        # Gmail操作
├── drive_tool.py        # Drive操作
├── config.py            # 設定読み込み
├── requirements.txt     # 依存パッケージ
├── .env                 # APIキー（要作成）
├── credentials.json     # Google認証情報（要配置）
└── token.json           # 認証トークン（自動生成）
```

---

## トラブルシューティング

**`credentials.json が見つかりません` と表示される**
→ ステップ 3 の手順で credentials.json をダウンロードしてこのフォルダに置いてください。

**`ANTHROPIC_API_KEY が設定されていません` と表示される**
→ `.env` ファイルを作成して API キーを設定してください（ステップ 4）。

**ブラウザが開かない（認証できない）**
→ `token.json` を削除して `python main.py` を再実行してください。

**`403 Access denied` エラーが出る**
→ Google Cloud Console で該当APIが有効になっているか確認してください（ステップ 2）。
