# Claude Code で AI秘書スキルを使うためのセットアップ

Claude Code（Cursor含む）でこのスキルのフル機能を使うには、Gmail と Google カレンダーの MCP サーバーを設定する必要があります。

## 推奨: Google Workspace MCP（Gmail + カレンダー一括対応）

最も手軽な方法は、Gmail と Google カレンダーの両方に対応した MCP サーバーを使うことです。

### オプションA: mcp-gsuite（おすすめ）

GitHub: https://github.com/MarkusPfundstein/mcp-gsuite

```bash
# リポジトリをクローン
git clone https://github.com/MarkusPfundstein/mcp-gsuite.git
cd mcp-gsuite
npm install
npm run build
```

### オプションB: google-workspace-mcp-server

GitHub: https://github.com/epaproditus/google-workspace-mcp-server

Gmail検索・カレンダーイベント管理に対応しています。

### オプションC: 個別に設定

**Google カレンダー:**
```bash
npm install -g @cocal/google-calendar-mcp
```

**Gmail:**
GitHub: https://github.com/GongRzhe/Gmail-MCP-Server

---

## Google Cloud の事前準備

どのMCPサーバーを使う場合でも、Google Cloud の OAuth 認証情報が必要です。

### ステップ1: Google Cloud プロジェクト作成

1. https://console.cloud.google.com/ にアクセス
2. 新しいプロジェクトを作成（例: `ai-secretary-mcp`）

### ステップ2: API を有効化

Google Cloud Console で以下の API を有効にします:

- **Gmail API**
- **Google Calendar API**

「APIとサービス」→「ライブラリ」から検索して有効化してください。

### ステップ3: OAuth 同意画面の設定

1. 「APIとサービス」→「OAuth 同意画面」
2. ユーザータイプ: **外部** を選択
3. アプリ名、サポートメール、デベロッパー連絡先を入力
4. スコープに以下を追加:
   - `https://mail.google.com/`
   - `https://www.googleapis.com/auth/calendar`
   - `https://www.googleapis.com/auth/userinfo.email`
5. テストユーザーに自分のメールアドレスを追加

### ステップ4: OAuth クライアント ID の作成

1. 「APIとサービス」→「認証情報」→「認証情報を作成」
2. **OAuth クライアント ID** を選択
3. アプリケーションの種類: **デスクトップアプリ**
4. 作成後、JSONファイルをダウンロード
5. ダウンロードしたファイルを安全な場所に保存（例: `~/.config/gcp-oauth.keys.json`）

---

## Claude Code への MCP サーバー設定

### 設定ファイルの場所

- **プロジェクト単位**: `.mcp.json`（プロジェクトルートに配置）
- **ユーザー単位**: `~/.claude/.mcp.json`

### 設定例（mcp-gsuite の場合）

`~/.claude/.mcp.json` に以下を追加:

```json
{
  "mcpServers": {
    "gsuite": {
      "type": "stdio",
      "command": "node",
      "args": ["/path/to/mcp-gsuite/dist/index.js"],
      "env": {
        "GOOGLE_OAUTH_CREDENTIALS": "/path/to/gcp-oauth.keys.json"
      }
    }
  }
}
```

### 設定例（個別サーバーの場合）

```json
{
  "mcpServers": {
    "google-calendar": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@cocal/google-calendar-mcp"],
      "env": {
        "GOOGLE_OAUTH_CREDENTIALS": "/path/to/gcp-oauth.keys.json"
      }
    },
    "gmail": {
      "type": "stdio",
      "command": "node",
      "args": ["/path/to/gmail-mcp-server/dist/index.js"],
      "env": {
        "GOOGLE_OAUTH_CREDENTIALS": "/path/to/gcp-oauth.keys.json"
      }
    }
  }
}
```

### CLIコマンドで追加する場合

```bash
# Claude Code の CLI で追加
claude mcp add gsuite --scope user -- node /path/to/mcp-gsuite/dist/index.js
```

---

## 初回認証

MCP サーバーを設定後、初めて使用する際にブラウザが開いて Google アカウントの認証を求められます。認証が完了すると、トークンが保存され、以降は自動的に接続されます。

---

## スキルのインストール

### Cursor の場合

1. `.skill` ファイルをダウンロード
2. プロジェクトルートに `.claude/skills/` ディレクトリを作成
3. スキルの SKILL.md をそこに配置

```bash
mkdir -p .claude/skills/ai-secretary
cp /path/to/ai-secretary/SKILL.md .claude/skills/ai-secretary/
cp -r /path/to/ai-secretary/references .claude/skills/ai-secretary/
```

### Claude Code（ターミナル）の場合

同様にホームディレクトリまたはプロジェクトディレクトリにスキルファイルを配置します。

---

## トラブルシューティング

**「MCP サーバーに接続できない」場合:**
- Node.js がインストールされているか確認
- パスが正しいか確認
- `npm install` が完了しているか確認

**「認証エラー」の場合:**
- OAuth 同意画面でテストユーザーに自分のメールが追加されているか確認
- API が有効化されているか確認
- 認証情報のJSONファイルのパスが正しいか確認

**「スコープが不足」の場合:**
- OAuth 同意画面のスコープに Gmail API と Calendar API の両方が追加されているか確認
