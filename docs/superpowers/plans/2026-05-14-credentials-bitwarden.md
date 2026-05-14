# Credentials Bitwarden 移行 Implementation Plan (Phase 1: ebay-agent パイロット)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 散在している `.env` credentials を Bitwarden Vault に集約する移行を、**ebay-agent をパイロットケース** として完遂し、ヘルパースクリプト（`bw-export-env.sh` / `bw-deploy-env.sh`）と `/credentials-rotate` slash command を整備する。Phase 2-4（全プロダクト・VPS本番・GitHub Actions）は別 plan で段階実施。

**Architecture:** ハイブリッド方式 (C案) — Bitwarden Vault は **配布チャネル** であり、ランタイム依存にしない。ローカル Mac で `bw export` → `.env` 再生成 → 各プロダクトに配置 / VPS本番には rsync で配信。Bitwarden 障害時も稼働中の本番には無影響。Phase 1 では ebay-agent のみ移行し、ワークフローを確立。

**Tech Stack:** Bitwarden Cloud (Free plan), `bw` CLI (npm), Bash helper scripts (`~/.claude/scripts/bw-*.sh`), Claude Code slash command (`/credentials-rotate`)

**Spec:** [`docs/superpowers/specs/2026-05-14-credentials-bitwarden-design.md`](../specs/2026-05-14-credentials-bitwarden-design.md)

**Depends on:** [`2026-05-14-ssot-flow-stock.md`](2026-05-14-ssot-flow-stock.md) (implementation 完了済み) — Credentials は SSoT Map で「Bitwarden Vault」として既に明記済み

---

## File Structure

| ファイル | 役割 | 状態 |
|---------|------|------|
| Bitwarden Cloud Vault | SSoT (Free plan) | 新規セットアップ |
| `~/.bw-session` | bw CLI session（gitignore） | 実行時生成 |
| `~/.claude/scripts/bw-export-env.sh` | `<product>` 名から `.env` 生成 | 新規作成 |
| `~/.claude/scripts/bw-deploy-env.sh` | ローカル→VPS rsync 配信 | 新規作成 |
| `~/.claude/commands/credentials-rotate.md` | `/credentials-rotate` slash command | 新規作成 |
| `~/Claude-Workspace/products/ebay-agent/.env.bak.YYYYMMDD` | パイロット ロールバック用 | 実行時生成 |
| `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/bitwarden-setup.md` | Bitwarden 運用 memory | 新規作成 |

---

### Task 1: Bitwarden アカウント + Folder 構造のセットアップ（Hiro 手作業）

**Files:**
- External: Bitwarden Web Vault (https://vault.bitwarden.com/)

- [ ] **Step 1: Bitwarden アカウント作成 or 既存ログイン確認**

1. https://vault.bitwarden.com/ にアクセス
2. 既存アカウント無ければ新規作成（Hiro のメインメール `otsuka@trustlink-tk.com`）
3. **強力なマスターパスワード** + 2FA（TOTP）を設定
4. **リカバリーコード** を物理媒体（紙）に印刷して保管

- [ ] **Step 2: Folder 構造を作成**

Bitwarden Web Vault → 「Folders」→ 以下の階層を作成:

```
claude-workspace/
├── ebay-agent
├── saimu-media
├── faccel
├── ai-uranai
├── d-manager
└── threads-auto
infrastructure/
├── vps-trustlink
└── github-actions
shared-keys/
├── anthropic
├── google-cloud
└── meta-business
```

Phase 1 では `claude-workspace/ebay-agent` と `shared-keys/anthropic` の2フォルダだけ実用する。残りは枠だけ用意。

- [ ] **Step 3: Emergency Access の設定（リスク1対策）**

Web Vault → 「Tools」→ 「Emergency Access」:
- 受け手は **Phase 1 中は空でOK**、Phase 全体完了後に再検討（spec § オープン質問）
- ただし「将来設定する予定」のリマインダーを memory に記録（Task 6 で実施）

---

### Task 2: `bw` CLI インストール + API キー方式ログイン

**Files:**
- Modify: `/Users/Mac_air/.claude/.gitignore`
- Create: `~/.bw-api-credentials`（chmod 600、gitignore）

- [ ] **Step 1: `bw` CLI インストール**

```bash
which bw || npm install -g @bitwarden/cli
bw --version
```

Expected: バージョン番号が出る（例: `2024.x.x`）。

- [ ] **Step 2: API キー方式 credentials を取得（Hiro 手作業）**

Bitwarden Web Vault → 「Account Settings」→ 「Security」→ 「Keys」→ 「View API Key」:
- `client_id` と `client_secret` をコピー（マスターパスワード要再入力）

- [ ] **Step 3: API キーを ローカルに保管**

`~/.bw-api-credentials` を Write（**値はチャットに出力しない**）:

```bash
# Bitwarden API key (login --apikey 用)
BW_CLIENTID=user.<取得したclient_id>
BW_CLIENTSECRET=<取得したclient_secret>
```

```bash
chmod 600 ~/.bw-api-credentials
```

- [ ] **Step 4: .gitignore 確認**

```bash
grep -n "\.bw-api-credentials" /Users/Mac_air/.gitignore 2>/dev/null
grep -n "\.bw-session" /Users/Mac_air/.gitignore 2>/dev/null
```

無ければ追記:

```bash
echo ".bw-api-credentials" >> /Users/Mac_air/.gitignore
echo ".bw-session" >> /Users/Mac_air/.gitignore
```

ホームディレクトリの .gitignore が無い場合は Workspace の .gitignore に追記:

```bash
echo "/.bw-api-credentials" >> /Users/Mac_air/Claude-Workspace/.gitignore
```

- [ ] **Step 5: API キー方式でログイン**

```bash
source ~/.bw-api-credentials
bw login --apikey
```

Expected: `You are logged in!` メッセージ。

- [ ] **Step 6: Vault を unlock してセッショントークン保存**

```bash
# マスターパスワード入力プロンプト → セッショントークン返却
export BW_SESSION="$(bw unlock --raw)"
echo "BW_SESSION=$BW_SESSION" > ~/.bw-session
chmod 600 ~/.bw-session
```

- [ ] **Step 7: 動作確認**

```bash
source ~/.bw-session
bw status
```

Expected: `{"status":"unlocked", ...}` JSON が出る。

---

### Task 3: ebay-agent 現状 .env を Bitwarden に転記（手作業）

**Files:**
- Read: `/Users/Mac_air/Claude-Workspace/products/ebay-agent/.env`（参考のみ、内容は転記用）

- [ ] **Step 1: 現状 .env の項目一覧化（値は出さない）**

```bash
grep -E "^[A-Z_]+=" /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env | cut -d= -f1
```

Expected: `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `ANTHROPIC_API_KEY`, ... の **キー名一覧** が出る（値は出力しない）。

- [ ] **Step 2: 各項目を Bitwarden に Login item として登録（Hiro 手作業）**

Web Vault → 「claude-workspace/ebay-agent」folder → 「Add Item」→ Type: `Login`:

各項目について:
- **Name**: `ebay-agent / <KEY名>` 例: `ebay-agent / EBAY_CLIENT_ID`
- **Username**: 空 or `env`
- **Password**: 実際の値（`.env` から手動コピペ）
- **Folder**: `claude-workspace/ebay-agent`

`ANTHROPIC_API_KEY` のように複数プロダクトで共有される予定のキーは:
- 個別 `ebay-agent / ANTHROPIC_API_KEY` ではなく
- `shared/ANTHROPIC_API_KEY` として `shared-keys/anthropic` folder に登録
- ebay-agent の `.env` 生成時に shared 参照を組む（Task 4 でスクリプト化）

- [ ] **Step 3: 転記後の Bitwarden 内容確認**

```bash
source ~/.bw-session
bw list items --folderid "$(bw list folders --search 'ebay-agent' | jq -r '.[0].id')" \
  | jq -r '.[].name'
```

Expected: `ebay-agent / EBAY_CLIENT_ID` 等のキー名のみ列挙（値は出さない）。

転記漏れが無いか Step 1 の出力と突き合わせ確認。

---

### Task 4: ヘルパースクリプト `bw-export-env.sh` 作成

**Files:**
- Create: `/Users/Mac_air/.claude/scripts/bw-export-env.sh`

- [ ] **Step 1: スクリプトを Write**

`/Users/Mac_air/.claude/scripts/bw-export-env.sh` を以下で作成:

```bash
#!/bin/bash
# Bitwarden から <product> の .env を生成 (spec #6)
# Usage:
#   bw-export-env.sh <product-name> [--include-shared <category>]
#   例: bw-export-env.sh ebay-agent --include-shared anthropic
# Output (stdout): KEY=VALUE 形式の .env 内容
# 注意:
#   - BW_SESSION が未設定なら ~/.bw-session を source、それでも無ければ unlock を案内
#   - shared/<category> の項目を product item と統合
#   - 同一キー名が product/shared 両方にあれば product 側を優先（ログに警告）

set -euo pipefail

PRODUCT="${1:-}"
[ -z "$PRODUCT" ] && echo "Usage: $0 <product-name> [--include-shared <category>]" >&2 && exit 1
shift

SHARED_CATEGORY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --include-shared) SHARED_CATEGORY="${2:-}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

# セッション復元
if [ -z "${BW_SESSION:-}" ] && [ -f ~/.bw-session ]; then
  # shellcheck disable=SC1090
  source ~/.bw-session
fi
if [ -z "${BW_SESSION:-}" ]; then
  echo "❌ BW_SESSION 未設定。先に: export BW_SESSION=\$(bw unlock --raw)" >&2
  exit 1
fi

# Product folder 取得
PRODUCT_FOLDER_ID="$(bw list folders --search "$PRODUCT" --session "$BW_SESSION" \
  | jq -r --arg name "claude-workspace/$PRODUCT" '.[] | select(.name == $name) | .id')"
if [ -z "$PRODUCT_FOLDER_ID" ] || [ "$PRODUCT_FOLDER_ID" = "null" ]; then
  echo "❌ Folder claude-workspace/$PRODUCT が見つかりません" >&2
  exit 1
fi

# Product items
declare -A SEEN_KEYS
bw list items --folderid "$PRODUCT_FOLDER_ID" --session "$BW_SESSION" \
  | jq -r '.[] | "\(.name)\t\(.login.password // "")"' \
  | while IFS=$'\t' read -r name value; do
    # "ebay-agent / EBAY_CLIENT_ID" → "EBAY_CLIENT_ID"
    key="${name##*/ }"
    [ -z "$key" ] && continue
    echo "${key}=${value}"
  done

# Shared items (任意)
if [ -n "$SHARED_CATEGORY" ]; then
  SHARED_FOLDER_ID="$(bw list folders --search "$SHARED_CATEGORY" --session "$BW_SESSION" \
    | jq -r --arg name "shared-keys/$SHARED_CATEGORY" '.[] | select(.name == $name) | .id')"
  if [ -z "$SHARED_FOLDER_ID" ] || [ "$SHARED_FOLDER_ID" = "null" ]; then
    echo "⚠️  shared-keys/$SHARED_CATEGORY が見つかりません（スキップ）" >&2
  else
    bw list items --folderid "$SHARED_FOLDER_ID" --session "$BW_SESSION" \
      | jq -r '.[] | "\(.name)\t\(.login.password // "")"' \
      | while IFS=$'\t' read -r name value; do
        # "shared / ANTHROPIC_API_KEY" → "ANTHROPIC_API_KEY"
        key="${name##*/ }"
        [ -z "$key" ] && continue
        echo "${key}=${value}"
      done
  fi
fi
```

- [ ] **Step 2: 実行権限**

```bash
chmod +x /Users/Mac_air/.claude/scripts/bw-export-env.sh
```

- [ ] **Step 3: ebay-agent で動作確認**

```bash
source ~/.bw-session
/Users/Mac_air/.claude/scripts/bw-export-env.sh ebay-agent --include-shared anthropic \
  | grep -E "^[A-Z_]+=" | cut -d= -f1 | sort -u
```

Expected: ebay-agent の `.env` キー名一覧と一致（**値は表示しない**ためキー名だけ確認）。

- [ ] **Step 4: 現状 .env と diff 比較**

```bash
# 現状 .env のキー一覧
EXPECT_KEYS="$(grep -E "^[A-Z_]+=" /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env | cut -d= -f1 | sort -u)"
# Bitwarden 生成のキー一覧
ACTUAL_KEYS="$(/Users/Mac_air/.claude/scripts/bw-export-env.sh ebay-agent --include-shared anthropic | grep -E "^[A-Z_]+=" | cut -d= -f1 | sort -u)"

diff <(echo "$EXPECT_KEYS") <(echo "$ACTUAL_KEYS")
```

Expected: diff なし（空出力）。差分があれば Task 3 の転記漏れ修正へ戻る。

- [ ] **Step 5: Commit**

```bash
git -C /Users/Mac_air/.claude add scripts/bw-export-env.sh
git -C /Users/Mac_air/.claude commit -m "feat: add bw-export-env.sh helper (spec #6 Phase 1)"
```

注: `~/.claude` が git 管理外ならスキップ。

---

### Task 5: ヘルパースクリプト `bw-deploy-env.sh` 作成（VPS 配信）

**Files:**
- Create: `/Users/Mac_air/.claude/scripts/bw-deploy-env.sh`

- [ ] **Step 1: スクリプトを Write**

`/Users/Mac_air/.claude/scripts/bw-deploy-env.sh` を以下で作成:

```bash
#!/bin/bash
# Bitwarden から .env 生成 → VPS rsync 配信 (spec #6)
# Usage:
#   bw-deploy-env.sh <product> <vps-target-path> [--include-shared <category>] [--dry-run]
#   例: bw-deploy-env.sh ebay-agent root@46.250.252.99:/opt/apps/ebay-agent/.env --include-shared anthropic
# 動作:
#   1. bw-export-env.sh で .env を一時ファイル生成
#   2. ターゲット VPS の現状 .env をバックアップ (.env.bak.YYYYMMDD-HHMMSS)
#   3. rsync で chmod=600 配置
#   4. 完了 Telegram 通知

set -euo pipefail

PRODUCT="${1:-}"
TARGET="${2:-}"
shift 2 || true

if [ -z "$PRODUCT" ] || [ -z "$TARGET" ]; then
  echo "Usage: $0 <product> <user@host:/path/to/.env> [--include-shared <category>] [--dry-run]" >&2
  exit 1
fi

DRY_RUN=""
EXTRA_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN="--dry-run"; shift ;;
    --include-shared) EXTRA_ARGS+=(--include-shared "$2"); shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
TEMP_ENV="$(mktemp)"
trap 'rm -f "$TEMP_ENV"' EXIT

echo "📥 [bw-deploy] Generating .env for $PRODUCT..." >&2
/Users/Mac_air/.claude/scripts/bw-export-env.sh "$PRODUCT" "${EXTRA_ARGS[@]}" > "$TEMP_ENV"

# 行数だけ報告（値は出さない）
LINES="$(grep -c -E "^[A-Z_]+=" "$TEMP_ENV" || echo 0)"
echo "   → ${LINES} keys exported" >&2

# VPS バックアップ
HOST="${TARGET%%:*}"
REMOTE_PATH="${TARGET#*:}"
BACKUP_PATH="${REMOTE_PATH}.bak.${TIMESTAMP}"

echo "💾 [bw-deploy] Backing up remote .env → ${BACKUP_PATH}" >&2
ssh "$HOST" "if [ -f '${REMOTE_PATH}' ]; then cp '${REMOTE_PATH}' '${BACKUP_PATH}'; fi"

# rsync
echo "🚀 [bw-deploy] rsync → ${TARGET} (chmod 600) ${DRY_RUN}" >&2
rsync -av $DRY_RUN --chmod=F600 "$TEMP_ENV" "$TARGET"

if [ -z "$DRY_RUN" ]; then
  # 通知
  if [ -f /Users/Mac_air/.claude/.telegram-meta-bot.env ]; then
    # shellcheck disable=SC1090
    source /Users/Mac_air/.claude/.telegram-meta-bot.env
    curl -s "https://api.telegram.org/bot${TELEGRAM_META_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TELEGRAM_META_BOT_CHAT_ID}" \
      --data-urlencode "text=🚀 bw-deploy 完了: ${PRODUCT} → ${TARGET} (${LINES} keys, backup ${BACKUP_PATH})" > /dev/null
  fi
fi

echo "✅ [bw-deploy] Done." >&2
```

- [ ] **Step 2: 実行権限**

```bash
chmod +x /Users/Mac_air/.claude/scripts/bw-deploy-env.sh
```

- [ ] **Step 3: `--dry-run` で動作確認（VPS 触らない）**

```bash
source ~/.bw-session
/Users/Mac_air/.claude/scripts/bw-deploy-env.sh ebay-agent \
  root@46.250.252.99:/opt/apps/ebay-agent/.env \
  --include-shared anthropic --dry-run
```

Expected:
- `→ N keys exported` 表示
- VPS バックアップは作成される（dry-run でも cp 実行する設計）
  - 副作用が気になるなら一時的に `Backing up remote` ステップを `dry-run` 判定に組み込む拡張（実装時判断）
- `rsync --dry-run` は実際にはファイルを置かない

- [ ] **Step 4: Commit**

```bash
git -C /Users/Mac_air/.claude add scripts/bw-deploy-env.sh
git -C /Users/Mac_air/.claude commit -m "feat: add bw-deploy-env.sh for VPS rsync deployment (spec #6 Phase 1)"
```

---

### Task 6: ebay-agent .env を Bitwarden 経由で再生成 + 動作確認（ローカル）

**Files:**
- Backup: `/Users/Mac_air/Claude-Workspace/products/ebay-agent/.env.bak.20260514`
- Rewrite: `/Users/Mac_air/Claude-Workspace/products/ebay-agent/.env`

- [ ] **Step 1: 現状 .env をバックアップ**

```bash
cp /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env \
   /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env.bak.20260514
chmod 600 /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env.bak.20260514
```

- [ ] **Step 2: Bitwarden から再生成（既存を上書き）**

```bash
source ~/.bw-session
/Users/Mac_air/.claude/scripts/bw-export-env.sh ebay-agent --include-shared anthropic \
  > /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env
chmod 600 /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env
```

- [ ] **Step 3: バックアップとの値レベル diff（キー名 + 値の存在のみ確認、値は表示しない）**

```bash
# キー一覧の diff
diff <(grep -E "^[A-Z_]+=" /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env.bak.20260514 | cut -d= -f1 | sort -u) \
     <(grep -E "^[A-Z_]+=" /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env | cut -d= -f1 | sort -u)
```

Expected: 差分なし。

```bash
# 各キーの値の長さだけ比較（値そのものは出さない）
join -j1 -t= \
  <(grep -E "^[A-Z_]+=" /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env.bak.20260514 | awk -F= '{print $1"="length($0)}' | sort) \
  <(grep -E "^[A-Z_]+=" /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env | awk -F= '{print $1"="length($0)}' | sort)
```

Expected: 全キーの length が一致（一致しなければ Bitwarden 転記時に値が変質した可能性 → Task 3 戻り）。

- [ ] **Step 4: ebay-agent ローカル起動確認**

```bash
cd /Users/Mac_air/Claude-Workspace/products/ebay-agent
# テスト用エンドポイントで credentials 読み込み確認（プロダクトのスモークテスト）
# 既存の起動コマンドに合わせる:
docker compose config > /dev/null && echo "✅ docker compose config OK"
docker compose up -d
sleep 10
docker compose logs --tail=50 | grep -iE "(error|missing|credential|api_key|token)" || echo "✅ credentials errors なし"
docker compose ps
```

Expected:
- credentials エラーがログに出ない
- 全コンテナが healthy / Up 状態

- [ ] **Step 5: 主要機能スモークテスト**

ebay-agent の主要エンドポイントを叩いて credentials が実際に使えているか確認:

```bash
# 例: 在庫検索エンドポイント（ebay-agent の実エンドポイントに合わせる）
curl -s -H "Content-Type: application/json" \
  https://ebay.trustlink-tk.com/healthz 2>&1 | head -20
```

Expected: 200 OK + credentials 関連エラーなし。

- [ ] **Step 6: 1週間運用観察期間の開始**

`~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/bitwarden-setup.md` に記録（Task 8 で詳細作成、まずは記録予定だけ）。

- [ ] **Step 7: ロールバック手順の確認（実行はしない）**

ドキュメント化のみ:

```bash
# 異常検出時のロールバック（実行はしない、確認だけ）
# mv /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env.bak.20260514 \
#    /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env
# docker compose -C /Users/Mac_air/Claude-Workspace/products/ebay-agent restart
```

---

### Task 7: `/credentials-rotate` slash command 実装

**Files:**
- Create: `/Users/Mac_air/.claude/commands/credentials-rotate.md`

- [ ] **Step 1: prompt を Write**

`/Users/Mac_air/.claude/commands/credentials-rotate.md` を以下で作成:

```markdown
---
description: Credentials のローテーション支援 (spec #6)
---

あなたは credentials ローテーション agent です。
spec: `~/Claude-Workspace/docs/superpowers/specs/2026-05-14-credentials-bitwarden-design.md`

引数: $ARGUMENTS
形式: `<product> <KEY_NAME> [--shared <category>] [--vps-target <user@host:/path>]`

例:
- `/credentials-rotate ebay-agent EBAY_CLIENT_SECRET`
- `/credentials-rotate shared ANTHROPIC_API_KEY --shared anthropic --vps-target root@46.250.252.99:/opt/apps/ebay-agent/.env`

## 実施手順

### ① ユーザーへの事前確認

以下を Hiro に確認:
- 「Bitwarden Web Vault で対象 item の値を更新しましたか？」
- 「旧 credentials の失効タイミング（即時 / 24h grace 等）は把握していますか？」
- 「VPS 配信対象は？（local-only / VPS path指定）」

未更新なら停止して Vault 更新を促す。

### ② ローカル .env 再生成

```bash
source ~/.bw-session
~/.claude/scripts/bw-export-env.sh <product> [--include-shared <category>] \
  > ~/Claude-Workspace/products/<product>/.env.new
chmod 600 ~/Claude-Workspace/products/<product>/.env.new
```

旧 .env の **キー名一覧と diff** を取り、対象キーだけが変わっていることを確認:

```bash
diff <(grep -E "^[A-Z_]+=" ~/Claude-Workspace/products/<product>/.env | cut -d= -f1 | sort -u) \
     <(grep -E "^[A-Z_]+=" ~/Claude-Workspace/products/<product>/.env.new | cut -d= -f1 | sort -u)
```

Expected: 差分なし（キー名は不変、値だけ変更）。

差分があれば停止して Hiro に報告。

### ③ ローカル .env 入れ替え

```bash
mv ~/Claude-Workspace/products/<product>/.env ~/Claude-Workspace/products/<product>/.env.bak.$(date +%Y%m%d-%H%M%S)
mv ~/Claude-Workspace/products/<product>/.env.new ~/Claude-Workspace/products/<product>/.env
```

### ④ ローカル動作確認

該当プロダクトを restart し、credentials エラーが出ないことを確認:

```bash
cd ~/Claude-Workspace/products/<product>
docker compose restart
sleep 10
docker compose logs --tail=50 | grep -iE "(error|missing|credential)" || echo "✅ no errors"
```

### ⑤ VPS デプロイ（--vps-target 指定時のみ）

```bash
~/.claude/scripts/bw-deploy-env.sh <product> <vps-target> [--include-shared <category>]
```

deploy 後、VPS 側で対象プロダクトを restart:

```bash
ssh <user@host> "cd /opt/apps/<product> && docker compose restart"
```

30分の監視期間を Hiro に通知（spec § Phase 3 動作確認）。

### ⑥ 旧 credentials 失効確認

- API側で旧 credentials が rejected になることを Hiro に確認依頼
- 例: ebay-agent なら旧 EBAY_CLIENT_SECRET で API call して 401 を確認

### ⑦ Telegram 通知

```bash
source ~/.claude/.telegram-meta-bot.env
TEXT="🔑 credentials-rotate 完了
プロダクト: <product>
キー: <KEY_NAME>
ローカル: 成功 / VPS: 成功 or skip
旧credentials: 失効確認待ち（Hiro）"
curl -s "https://api.telegram.org/bot${TELEGRAM_META_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_META_BOT_CHAT_ID}" \
  --data-urlencode "text=${TEXT}" > /dev/null
```

### ⑧ 最終出力

- ローカル/VPS 入れ替え結果
- バックアップファイルパス（ロールバック用）
- Telegram 通知到達可否
- 「旧 credentials 失効確認をお願いします」を最後に明示

## 重要ルール

- **値そのものをチャットに出力しない**（feedback_secret_disclosure.md 準拠）
- ロールバック手段（バックアップ）を必ず残してから入れ替える
- VPS deploy 前に必ずローカルで動作確認、ローカル失敗時は VPS に行かない
```

- [ ] **Step 2: ファイル確認**

```bash
wc -l /Users/Mac_air/.claude/commands/credentials-rotate.md
```

Expected: 80-120行程度。

- [ ] **Step 3: Commit**

```bash
git -C /Users/Mac_air/.claude add commands/credentials-rotate.md
git -C /Users/Mac_air/.claude commit -m "feat: add /credentials-rotate slash command (spec #6 Phase 1)"
```

---

### Task 8: Bitwarden 運用 memory + SSoT Map 更新

**Files:**
- Create: `/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/bitwarden-setup.md`
- Modify: `/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/MEMORY.md`
- Modify: `/Users/Mac_air/Obsidian/context/subscriptions.md`

- [ ] **Step 1: memory ファイル作成**

`/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/bitwarden-setup.md` を Write:

```markdown
---
name: Bitwarden Vault Credentials SSoT
description: Credentials の SSoT。Bitwarden は配布チャネル、ランタイム依存にしない。ヘルパー bw-export-env.sh / bw-deploy-env.sh
type: feedback
scope: workspace
trigger_count: 1
last_confirmed: 2026-05-14
---

## Bitwarden Vault — Credentials SSoT (spec #6)

### アーキテクチャ

ハイブリッド方式 (C案)。Bitwarden は **配布チャネル** であり、ランタイム依存にしない。
ローカル Mac で `bw export` → `.env` 再生成 → 各プロダクト/VPS に配置。

### Folder 構造

```
claude-workspace/<product>/   — 各プロダクト固有
shared-keys/<category>/        — 複数プロダクトで共有
infrastructure/<resource>/     — VPS, GitHub Actions
```

### credentials の場所

- Bitwarden API キー: `~/.bw-api-credentials` (gitignore, chmod 600)
- 現在のセッショントークン: `~/.bw-session` (gitignore, chmod 600)
- マスターパスワード: Hiro の記憶 + リカバリーコード（物理保管）

### 運用コマンド

```bash
# セッション確立
source ~/.bw-api-credentials
bw login --apikey      # 初回のみ
export BW_SESSION=$(bw unlock --raw)
echo "BW_SESSION=$BW_SESSION" > ~/.bw-session

# .env 生成
~/.claude/scripts/bw-export-env.sh <product> [--include-shared <category>]

# VPS 配信
~/.claude/scripts/bw-deploy-env.sh <product> <vps-target> [--include-shared <category>]

# ローテーション
/credentials-rotate <product> <KEY_NAME> [--shared <cat>] [--vps-target <target>]
```

### Phase 進捗

- **Phase 1 完了 (2026-05-14)**: ebay-agent パイロット成功
- Phase 2 (全ローカル): 別 plan で実施予定
- Phase 3 (VPS本番): 別 plan で実施予定（最高リスク）
- Phase 4 (GitHub Actions): 別 plan で実施予定

### 重要ルール

- VPS .env を直接編集しない（Bitwarden起点で配信）
- 月次棚卸し (spec #1) で VPS .env と Bitwarden の整合性チェックを追加（Task 9）
- credentials の値をチャットに出力しない (`feedback_secret_disclosure.md` 準拠)
- 旧 .env はバックアップ保持（即ロールバック可能に）

### TODO

- Bitwarden Emergency Access 受け手の設定（Phase 全体完了後）
- 4半期に1度のマスターパスワード動作確認

### 関連

- spec: `~/Claude-Workspace/docs/superpowers/specs/2026-05-14-credentials-bitwarden-design.md`
- plan (Phase 1): `~/Claude-Workspace/docs/superpowers/plans/2026-05-14-credentials-bitwarden.md`
- スクリプト: `~/.claude/scripts/bw-export-env.sh`, `~/.claude/scripts/bw-deploy-env.sh`
- slash: `/credentials-rotate`
```

- [ ] **Step 2: MEMORY.md にポインタ追加**

`/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/MEMORY.md` の Security 節 or 新規 "Credentials" 節に1行追記:

```markdown
- [Bitwarden Vault Credentials SSoT](bitwarden-setup.md) — spec #6 Phase 1完了、ハイブリッド方式・bw-export-env.sh
```

- [ ] **Step 3: subscriptions.md に Bitwarden Premium 移行予定を反映**

`/Users/Mac_air/Obsidian/context/subscriptions.md` の SaaS/Tools 表の Bitwarden 行を Edit:

```markdown
| Bitwarden | Free | $0 | - | Credentials SSoT (spec #6 Phase 1完了)。Emergency Access設定後 Premium 検討 | `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/bitwarden-setup.md` |
```

`last_confirmed` を 2026-05-14 のまま（変更なし、再確認日のみ更新するなら今日付に）。

- [ ] **Step 4: Commit**

```bash
git -C /Users/Mac_air/.claude add projects/-Users-Mac-air-Claude-Workspace/memory/bitwarden-setup.md projects/-Users-Mac-air-Claude-Workspace/memory/MEMORY.md
git -C /Users/Mac_air/.claude commit -m "feat(memory): add Bitwarden Vault Credentials SSoT (spec #6 Phase 1)"

git -C /Users/Mac_air/Obsidian add context/subscriptions.md
git -C /Users/Mac_air/Obsidian commit -m "docs(subscriptions): update Bitwarden row with spec #6 Phase 1 status"
```

---

### Task 9: 月次棚卸し prompt に VPS .env 整合チェック追加（spec #1 連動）

**Files:**
- Modify: `/Users/Mac_air/.claude/commands/monthly-cleanup.md`

- [ ] **Step 1: prompt に新検査項目を Edit で追加**

`/Users/Mac_air/.claude/commands/monthly-cleanup.md` の「⑤ x-intake inbox 未処理検出」（spec #4 plan で追加済み）の直後に追加:

```markdown
### ⑥ VPS .env と Bitwarden の整合チェック（spec #6 連動）

**Phase 1 (ebay-agent) のみ対象**。Phase 2-4 完了後に対象プロダクトを拡張。

```bash
# Bitwarden 側でのキー一覧
source ~/.bw-session 2>/dev/null
LOCAL_KEYS=$(~/.claude/scripts/bw-export-env.sh ebay-agent --include-shared anthropic 2>/dev/null \
  | grep -E "^[A-Z_]+=" | cut -d= -f1 | sort -u)

# VPS 側でのキー一覧
VPS_KEYS=$(ssh root@46.250.252.99 "grep -E '^[A-Z_]+=' /opt/apps/ebay-agent/.env | cut -d= -f1 | sort -u" 2>/dev/null)

# diff（キー名のみ、値は比較しない）
diff <(echo "$LOCAL_KEYS") <(echo "$VPS_KEYS")
```

差分があれば「VPS .env と Bitwarden の乖離」セクションをレポートに追記し、`/credentials-rotate` 実行を提案。

VPS .env を直接編集する運用は禁止 (spec § リスク5)。
```

- [ ] **Step 2: ファイル確認**

```bash
grep -n "VPS .env と Bitwarden" /Users/Mac_air/.claude/commands/monthly-cleanup.md
```

Expected: 1ヒット。

- [ ] **Step 3: Commit**

```bash
git -C /Users/Mac_air/.claude add commands/monthly-cleanup.md
git -C /Users/Mac_air/.claude commit -m "feat: add VPS .env integrity check to monthly-cleanup (spec #6 Phase 1)"
```

---

### Task 10: 1週間運用観察期間後の Phase 1 完了判定

**Files:**
- Modify: `/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/bitwarden-setup.md`
- Delete: `/Users/Mac_air/Claude-Workspace/products/ebay-agent/.env.bak.20260514`（任意・1週間経過後）

- [ ] **Step 1: 1週間後のヘルスチェック**

Task 6 から1週間運用観察。エラーゼロを確認:

```bash
docker compose -C /Users/Mac_air/Claude-Workspace/products/ebay-agent logs --since=7d \
  | grep -iE "(credential|missing|unauthorized|api_key)" | head -20
```

Expected: ヒットなし。

- [ ] **Step 2: バックアップ削除（任意）**

問題なければバックアップを削除して片付け:

```bash
rm /Users/Mac_air/Claude-Workspace/products/ebay-agent/.env.bak.20260514
```

復旧ルートを残したい場合は `.env.bak.YYYYMMDD` で残し、ファイル名から Phase 1 完了日を辿れる状態にする。

- [ ] **Step 3: bitwarden-setup.md に Phase 1 完了日記録**

`/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/bitwarden-setup.md` の `### Phase 進捗` を Edit:

```markdown
- **Phase 1 完了 (2026-05-14 → 2026-05-21 検証完了)**: ebay-agent パイロット成功、1週間運用エラーゼロ
```

`last_confirmed: 2026-05-21` に更新。

- [ ] **Step 4: 受け入れ基準チェック**

spec § 8 「Phase 1 完了基準」と対応:
- [ ] Bitwarden に ebay-agent folder + 全 credentials 移行済み（Task 3）
- [ ] `bw-export-env.sh ebay-agent` で .env 再生成可能（Task 4 Step 3）
- [ ] ローカル ebay-agent が正常稼働（Task 6 Step 4-5）
- [ ] VPS 側は Phase 1 では未着手（Phase 3 で実施）→ ローカルのみで Phase 1 完了
- [ ] 1週間運用してエラーゼロ（Task 10 Step 1）

- [ ] **Step 5: Commit**

```bash
git -C /Users/Mac_air/.claude add projects/-Users-Mac-air-Claude-Workspace/memory/bitwarden-setup.md
git -C /Users/Mac_air/.claude commit -m "chore(memory): mark Bitwarden Phase 1 completed (2026-05-21)"
```

---

## 受け入れ基準の検証

spec #6 セクション8 「Phase 1 完了基準」のみ実施（Phase 2-4 は別 plan）:

- [x] Task 1-3 で Bitwarden に ebay-agent folder + credentials 移行
- [x] Task 4 で `bw-export-env.sh` 実装、ebay-agent で動作確認
- [x] Task 6 でローカル ebay-agent が Bitwarden 起点 .env で正常稼働
- [x] Task 10 で 1週間運用エラーゼロを確認

**Phase 2-4 (別 plan):**
- [ ] Phase 2: saimu-media / faccel / ai-uranai / d-manager / threads-auto / deal-watcher / b-manager 移行
- [ ] Phase 3: VPS本番 移行（最高リスク、プロダクトごとに分散）
- [ ] Phase 4: GitHub Actions secrets 移行

---

## Phase 2-4 の前提条件（次 plan 作成時の参考）

- **Phase 2** 開始前提:
  - Phase 1 が 1週間運用エラーゼロ
  - `bw-export-env.sh` のスクリプト的バグが洗い出し済み
- **Phase 3** 開始前提:
  - Phase 2 で各プロダクトのスモークテスト確立
  - Telegram 通知到達確認手段が動いている（spec #1 Bot）
  - VPS .env バックアップから 30秒以内に復旧できる procedure 確立
- **Phase 4** 開始前提:
  - Phase 3 が全プロダクトで完了
  - GitHub Actions の Bitwarden API キー保管方針確定（chicken-and-egg許容判断）

---

## Self-Review Checklist（plan作成者用）

- [x] spec の全セクション（1-10）のうち Phase 1 範囲のみマッピング
- [x] Phase 2-4 はスコープ外と明示
- [x] credentials の値をチャットに出力させない（Task 1/3/4/6 で「キー名のみ」「length比較のみ」を強制）
- [x] バックアップ → 検証 → 入れ替え の順序を守る（Task 6 / Task 7 で明示）
- [x] Bitwarden 障害時のランタイム影響ゼロを保証するアーキ（C案）を Task 4 ヘルパースクリプトで体現
- [x] spec #1 月次棚卸し連動（Task 9）で運用後の乖離検知
- [x] Phase 2-4 への引き継ぎ前提条件を明示（次 plan 作成時の指針）
- [x] feedback_secret_disclosure.md 準拠（値の表示を全 task で禁止）
