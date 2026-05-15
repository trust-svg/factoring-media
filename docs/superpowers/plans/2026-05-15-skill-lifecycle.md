# スキルライフサイクルシステム Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** スキルの使用履歴を自動記録し、90日未使用スキルを自動アーカイブする Curator を構築する。

**Architecture:** PreToolUse フックで使用日を `skill-usage.json` に記録。SessionEnd フックで Curator を週1回起動し、30日未使用を stale、90日未使用を自動アーカイブ（バックアップ付き）。CLAUDE.md に自律スキル生成の提案基準を追記。

**Tech Stack:** bash, Python 3.11+（fcntl, json, shutil, subprocess）, Claude Code settings.json hooks

---

> ⚠️ **Phase 分割注意:** Task 1〜4 を完了したら **1週間データを貯めてから** Task 5 以降を実行する。
> Phase 1 完了後すぐに Phase 2 を入れると、全スキルが「未使用」判定される。

---

## Task 1: ディレクトリとファイルのスキャフォールド

**Files:**
- Create: `~/.claude/scripts/` (ディレクトリ)
- Create: `~/.claude/skills/.archive/backups/` (ディレクトリ)
- Create: `~/.claude/skill-usage.json`
- Create: `~/.claude/skill-status.json`

- [ ] **Step 1: ディレクトリを作成する**

```bash
mkdir -p ~/.claude/scripts
mkdir -p ~/.claude/skills/.archive/backups
```

- [ ] **Step 2: JSON ファイルを初期化する**

```bash
echo '{}' > ~/.claude/skill-usage.json
echo '{}' > ~/.claude/skill-status.json
```

- [ ] **Step 3: 作成を確認する**

```bash
ls ~/.claude/scripts/
ls ~/.claude/skills/.archive/
cat ~/.claude/skill-usage.json
```

期待出力:
```
{}
```

- [ ] **Step 4: コミットする**

```bash
cd ~/Claude-Workspace
git add -A
git commit -m "feat(skill-lifecycle): Phase1 ディレクトリスキャフォールド"
```

---

## Task 2: track-skill-usage.sh 実装

**Files:**
- Create: `~/.claude/scripts/track-skill-usage.sh`

- [ ] **Step 1: スクリプトを作成する**

```bash
cat > ~/.claude/scripts/track-skill-usage.sh << 'SCRIPT'
#!/bin/bash
# PreToolUse hook: Skill ツール呼び出し時に使用日を skill-usage.json に記録

USAGE_FILE="$HOME/.claude/skill-usage.json"
TODAY=$(TZ=Asia/Tokyo date +%Y-%m-%d)

# 標準入力から skill 名を取得（Claude Code が JSON で渡す）
INPUT=$(cat)
SKILL_NAME=$(python3 -c "
import sys, json
try:
    d = json.loads('''$INPUT'''.replace(\"'\", '\"'))
    print(d.get('tool_input', {}).get('skill', ''))
except Exception as e:
    print('')
" 2>/dev/null)

# skill 名が空の場合はスキップ
[ -z "$SKILL_NAME" ] && exit 0

# ファイルが存在しない場合は初期化
[ -f "$USAGE_FILE" ] || echo '{}' > "$USAGE_FILE"

# ファイルロック付きで使用日を書き込む
python3 - <<PYEOF
import json, fcntl, os, sys
from pathlib import Path

path = Path(os.path.expanduser("~/.claude/skill-usage.json"))
skill = "$SKILL_NAME"
today = "$TODAY"

# 存在しない場合は作成
if not path.exists():
    path.write_text("{}")

with open(path, "r+") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    try:
        d = json.load(f)
    except json.JSONDecodeError:
        d = {}
    d[skill] = today
    f.seek(0)
    json.dump(d, f, indent=2)
    f.truncate()
    fcntl.flock(f, fcntl.LOCK_UN)
PYEOF
SCRIPT

chmod +x ~/.claude/scripts/track-skill-usage.sh
```

- [ ] **Step 2: モック入力でテストする**

```bash
echo '{"tool_name":"Skill","tool_input":{"skill":"brainstorming","args":""}}' \
  | ~/.claude/scripts/track-skill-usage.sh

cat ~/.claude/skill-usage.json
```

期待出力（今日の日付が入る）:
```json
{
  "brainstorming": "2026-05-15"
}
```

- [ ] **Step 3: 並行実行でロック競合が起きないことを確認する**

```bash
for i in {1..5}; do
  echo '{"tool_name":"Skill","tool_input":{"skill":"test-skill-'$i'","args":""}}' \
    | ~/.claude/scripts/track-skill-usage.sh &
done
wait
cat ~/.claude/skill-usage.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d), 'entries')"
```

期待出力: `6 entries`（brainstorming + test-skill-1〜5）

- [ ] **Step 4: コミットする**

```bash
git add -A
git commit -m "feat(skill-lifecycle): track-skill-usage.sh 実装"
```

---

## Task 3: PreToolUse hook を settings.json に追加

**Files:**
- Modify: `~/.claude/settings.json`

- [ ] **Step 1: 現在の settings.json を確認する**

```bash
cat ~/.claude/settings.json | python3 -m json.tool | head -30
```

- [ ] **Step 2: PreToolUse セクションを追加する**

`~/.claude/settings.json` の `"hooks"` オブジェクトに以下を追加する。
既存の `"SessionStart"`, `"PreCompact"`, `"UserPromptSubmit"` はそのまま残す。

```json
"PreToolUse": [
  {
    "matcher": "Skill",
    "hooks": [
      {
        "type": "command",
        "command": "/Users/Mac_air/.claude/scripts/track-skill-usage.sh"
      }
    ]
  }
]
```

> ⚠️ `~` ではなく絶対パス `/Users/Mac_air/` を使うこと（フックは環境変数展開が不安定）

- [ ] **Step 3: JSON 構文を検証する**

```bash
python3 -m json.tool ~/.claude/settings.json > /dev/null && echo "JSON OK" || echo "JSON ERROR"
```

期待出力: `JSON OK`

- [ ] **Step 4: コミットする**

```bash
git add -A
git commit -m "feat(skill-lifecycle): PreToolUse hook 追加（Skill 使用記録）"
```

---

## Task 4: Phase 1 動作確認

- [ ] **Step 1: 新しいセッションで任意のスキルを呼び出す**

Claude Code を再起動し、`/brainstorming` などスキルを実際に呼び出す。

- [ ] **Step 2: skill-usage.json に記録されたか確認する**

```bash
cat ~/.claude/skill-usage.json
```

期待出力（呼び出したスキル名と今日の日付が入っている）:
```json
{
  "brainstorming": "2026-05-15"
}
```

- [ ] **Step 3: 1週間後に Phase 2 へ進む**

> **⏸ ここで 7日間待つ。データが蓄積されてから Phase 2 を開始する。**
> Phase 2 開始前に `cat ~/.claude/skill-usage.json` でデータを確認すること。

---

## Task 5: curator_logic.py 実装（Phase 2 開始 — Day 8 以降）

**Files:**
- Create: `~/.claude/scripts/curator_logic.py`

- [ ] **Step 1: curator_logic.py を作成する**

```python
# ファイル: ~/.claude/scripts/curator_logic.py
#!/usr/bin/env python3
"""Curator: スキルの stale 判定と自動アーカイブ"""
import json, os, shutil, fcntl, subprocess
from datetime import date, timezone, timedelta
from pathlib import Path

JST         = timezone(timedelta(hours=9))
TODAY       = date.today()  # ホスト TZ=Asia/Tokyo なので JST
TODAY_STR   = str(TODAY)
SKILLS_DIR  = Path.home() / ".claude" / "skills"
USAGE_FILE  = Path.home() / ".claude" / "skill-usage.json"
STATUS_FILE = Path.home() / ".claude" / "skill-status.json"
ARCHIVE_DIR = SKILLS_DIR / ".archive"
BACKUP_BASE = ARCHIVE_DIR / "backups"
ENV_FILE    = Path.home() / ".claude" / ".telegram-meta-bot.env"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(data, f, indent=2, ensure_ascii=False)
        fcntl.flock(f, fcntl.LOCK_UN)


def load_telegram_env() -> dict:
    env: dict = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v.strip("'\"")
    return env


def send_telegram(text: str) -> None:
    env = load_telegram_env()
    token = env.get("TELEGRAM_META_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_META_BOT_CHAT_ID", "")
    if not token or not chat_id:
        return
    subprocess.run(
        [
            "curl", "-s",
            f"https://api.telegram.org/bot{token}/sendMessage",
            "--data-urlencode", f"chat_id={chat_id}",
            "--data-urlencode", f"text={text}",
        ],
        capture_output=True,
    )


def main() -> None:
    usage  = load_json(USAGE_FILE)
    status = load_json(STATUS_FILE)
    archived: list[str] = []
    staled: list[str]   = []

    for entry in os.scandir(SKILLS_DIR):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):   # .archive/ 等を除外
            continue
        if not os.path.exists(os.path.join(entry.path, "SKILL.md")):
            continue

        name = entry.name

        # 未追跡スキル: today で初期化して保護（アーカイブしない）
        if name not in usage:
            usage[name] = TODAY_STR
            continue

        days = (TODAY - date.fromisoformat(usage[name])).days

        if days >= 90:
            backup_path = BACKUP_BASE / TODAY_STR / name
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(entry.path, backup_path)
            shutil.rmtree(entry.path)
            archived.append(name)

        elif days >= 30:
            status[name] = {
                "stale": True,
                "stale_since": TODAY_STR,
                "days_unused": days,
            }
            staled.append(name)

        else:
            # 正常使用中: stale フラグを解除
            if name in status:
                status[name]["stale"] = False

    save_json(USAGE_FILE, usage)
    save_json(STATUS_FILE, status)

    if archived or staled:
        lines = ["🗂 Curator 実行完了"]
        if archived:
            lines.append(f"アーカイブ: {', '.join(archived)}")
        if staled:
            lines.append(f"Stale マーク: {len(staled)}件")
        lines.append(
            f"ロールバック先: ~/.claude/skills/.archive/backups/{TODAY_STR}/"
        )
        send_telegram("\n".join(lines))


if __name__ == "__main__":
    main()
```

実際の書き込みコマンド:

```bash
cat > ~/.claude/scripts/curator_logic.py << 'PYEOF'
[上記 Python コードをそのまま貼り付ける]
PYEOF
chmod +x ~/.claude/scripts/curator_logic.py
```

- [ ] **Step 2: テスト用ダミースキルを作成する**

```bash
mkdir -p ~/.claude/skills/curator-test-dummy
cat > ~/.claude/skills/curator-test-dummy/SKILL.md << 'EOF'
---
name: curator-test-dummy
description: Curator 動作確認用ダミースキル（テスト後に削除）
---
# Test
EOF
```

- [ ] **Step 3: ダミースキルを 91 日前として skill-usage.json に登録する**

```bash
python3 -c "
import json
from datetime import date, timedelta
from pathlib import Path

path = Path.home() / '.claude' / 'skill-usage.json'
d = json.loads(path.read_text())
old_date = str(date.today() - timedelta(days=91))
d['curator-test-dummy'] = old_date
path.write_text(json.dumps(d, indent=2))
print(f'curator-test-dummy を {old_date} (91日前) として登録しました')
"
```

- [ ] **Step 4: curator_logic.py を単体実行してアーカイブされるか確認する**

```bash
python3 ~/.claude/scripts/curator_logic.py
```

- [ ] **Step 5: アーカイブ結果を確認する**

```bash
# ダミースキルが .archive に移動している
ls ~/.claude/skills/.archive/backups/
# .archive/backups/YYYY-MM-DD/curator-test-dummy/ が存在する

# skills/ 本体からは消えている
ls ~/.claude/skills/ | grep curator-test-dummy && echo "ERROR: まだある" || echo "OK: 消えた"
```

- [ ] **Step 6: コミットする**

```bash
git add -A
git commit -m "feat(skill-lifecycle): curator_logic.py 実装"
```

---

## Task 6: curator.sh 実装（SessionEnd ラッパー）

**Files:**
- Create: `~/.claude/scripts/curator.sh`

- [ ] **Step 1: curator.sh を作成する**

```bash
cat > ~/.claude/scripts/curator.sh << 'SCRIPT'
#!/bin/bash
# SessionEnd hook: 週 1 回 Curator を起動する

LAST_RUN_FILE="$HOME/.claude/.curator-last-run"
TODAY=$(TZ=Asia/Tokyo date +%Y-%m-%d)

# 前回実行から 7 日未満なら終了（セッションごとの重複実行を防ぐ）
if [ -f "$LAST_RUN_FILE" ]; then
    LAST=$(cat "$LAST_RUN_FILE")
    DAYS=$(python3 -c "
from datetime import date
print((date.fromisoformat('$TODAY') - date.fromisoformat('$LAST')).days)
" 2>/dev/null || echo 0)
    if [ "$DAYS" -lt 7 ]; then
        exit 0
    fi
fi

# Curator ロジックを実行
python3 "$HOME/.claude/scripts/curator_logic.py"

# 実行日を記録
echo "$TODAY" > "$LAST_RUN_FILE"
SCRIPT

chmod +x ~/.claude/scripts/curator.sh
```

- [ ] **Step 2: 手動実行でエラーがないか確認する（.curator-last-run を削除してから）**

```bash
rm -f ~/.claude/.curator-last-run
~/.claude/scripts/curator.sh
echo "Exit code: $?"
```

期待出力: `Exit code: 0`（エラーなし）

- [ ] **Step 3: 2 回目の実行がスキップされるか確認する（7 日以内制御）**

```bash
~/.claude/scripts/curator.sh
echo "Exit code: $?"
# .curator-last-run が今日の日付になっているので即終了するはず
cat ~/.claude/.curator-last-run
```

- [ ] **Step 4: コミットする**

```bash
git add -A
git commit -m "feat(skill-lifecycle): curator.sh SessionEnd ラッパー実装"
```

---

## Task 7: SessionEnd hook を settings.json に追加

**Files:**
- Modify: `~/.claude/settings.json`

- [ ] **Step 1: settings.json の `"hooks"` に SessionEnd を追加する**

```json
"SessionEnd": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "/Users/Mac_air/.claude/scripts/curator.sh"
      }
    ]
  }
]
```

> ⚠️ 絶対パスを使うこと。`~` は不可。

- [ ] **Step 2: JSON 構文を検証する**

```bash
python3 -m json.tool ~/.claude/settings.json > /dev/null && echo "JSON OK" || echo "JSON ERROR"
```

期待出力: `JSON OK`

- [ ] **Step 3: コミットする**

```bash
git add -A
git commit -m "feat(skill-lifecycle): SessionEnd hook 追加（Curator 週次起動）"
```

---

## Task 8: Phase 2 エンドツーエンド動作確認

- [ ] **Step 1: skill-usage.json に 31 日前のスキルを登録して stale を確認する**

```bash
python3 -c "
import json
from datetime import date, timedelta
from pathlib import Path

path = Path.home() / '.claude' / 'skill-usage.json'
d = json.loads(path.read_text())
stale_date = str(date.today() - timedelta(days=31))
d['ads-microsoft'] = stale_date   # 例: 実際に存在するスキルに変更する
path.write_text(json.dumps(d, indent=2))
print(f'ads-microsoft を {stale_date} (31日前) として登録')
"
```

- [ ] **Step 2: .curator-last-run を削除して Curator を強制実行する**

```bash
rm -f ~/.claude/.curator-last-run
~/.claude/scripts/curator.sh
```

- [ ] **Step 3: skill-status.json に stale エントリが追加されたか確認する**

```bash
cat ~/.claude/skill-status.json | python3 -m json.tool
```

期待出力（stale: true のエントリが存在する）:
```json
{
  "ads-microsoft": {
    "stale": true,
    "stale_since": "2026-05-15",
    "days_unused": 31
  }
}
```

- [ ] **Step 4: Telegram に通知が届いたか確認する**

Telegram の `@bmanager_trustlink_bot` で「🗂 Curator 実行完了」メッセージを確認する。

- [ ] **Step 5: stale テスト用エントリを元の日付に戻す（本番スキルを誤アーカイブしないため）**

```bash
python3 -c "
import json
from datetime import date
from pathlib import Path

path = Path.home() / '.claude' / 'skill-usage.json'
d = json.loads(path.read_text())
d['ads-microsoft'] = str(date.today())   # 今日に戻す
path.write_text(json.dumps(d, indent=2))
print('ads-microsoft の日付をリセットしました')
"
```

- [ ] **Step 6: コミットする**

```bash
git add -A
git commit -m "feat(skill-lifecycle): Phase2 動作確認完了"
```

---

## Task 9: monthly-cleanup スキルに stale 可視化を追加

**Files:**
- Modify: `~/.claude/skills/monthly-cleanup/SKILL.md`

- [ ] **Step 1: 現在の monthly-cleanup スキルの内容を確認する**

```bash
cat ~/.claude/skills/monthly-cleanup/SKILL.md | head -80
```

- [ ] **Step 2: 「① 未使用スキル検出」セクションに stale 表示を追記する**

monthly-cleanup スキルの未使用スキル検出セクションに以下のコードブロックを追加する（既存の bash コマンドの後ろに追記）:

```bash
# skill-status.json から stale スキルを一覧表示する
STALE_FILE="$HOME/.claude/skill-status.json"
if [ -f "$STALE_FILE" ]; then
    python3 - << 'PYEOF'
import json
from pathlib import Path

status_file = Path.home() / ".claude" / "skill-status.json"
usage_file  = Path.home() / ".claude" / "skill-usage.json"

status = json.loads(status_file.read_text()) if status_file.exists() else {}
usage  = json.loads(usage_file.read_text())  if usage_file.exists()  else {}

stale_skills = [
    (name, data)
    for name, data in status.items()
    if data.get("stale")
]

if stale_skills:
    print("\n⚠️  Stale スキル（30日以上未使用）:")
    for name, data in sorted(stale_skills, key=lambda x: x[1].get("days_unused", 0), reverse=True):
        days = data.get("days_unused", "?")
        since = data.get("stale_since", "?")
        print(f"  - {name}: {days}日未使用（stale_since: {since}）")
else:
    print("\n✅ Stale スキルなし（全スキルが30日以内に使用済み）")

# skill-usage.json に記録がないスキル（追跡対象外）も表示
import os
skills_dir = Path.home() / ".claude" / "skills"
all_skills = {
    e.name for e in os.scandir(skills_dir)
    if e.is_dir() and not e.name.startswith(".") and
    os.path.exists(os.path.join(e.path, "SKILL.md"))
}
untracked = all_skills - set(usage.keys())
if untracked:
    print(f"\n📋 未追跡スキル（Curator に登録されていない）: {len(untracked)}件")
    for name in sorted(untracked):
        print(f"  - {name}")
PYEOF
fi
```

- [ ] **Step 3: monthly-cleanup を手動実行して stale セクションが表示されるか確認する**

Claude Code で `/monthly-cleanup` を実行し、Stale スキルセクションが出力されることを確認する。

- [ ] **Step 4: コミットする**

```bash
git add ~/.claude/skills/monthly-cleanup/SKILL.md
git commit -m "feat(skill-lifecycle): monthly-cleanup に Curator stale 可視化を追加"
```

---

## Task 10: CLAUDE.md にスキル自律生成基準を追記（Phase 3）

**Files:**
- Modify: `~/.claude/CLAUDE.md`

- [ ] **Step 1: ~/.claude/CLAUDE.md の末尾に追記する**

```bash
cat >> ~/.claude/CLAUDE.md << 'EOF'

## スキル自律生成の判断基準

以下が **2つ以上**揃ったタスクが完了したとき、`skill-creator` の使用を提案する:

1. ツールコールが 5 回以上あった
2. エラーや行き詰まりを経て解決した
3. 同じパターンを複数プロダクトで使った
4. ユーザーが手順を訂正した

**提案文の例:**
「このタスクはスキル化できそうです。`/skill-creator` で手順を保存しますか？」

**制約:**
- 1セッションにつき最大 1 回提案する
- 短い質問・単純な修正タスクは対象外
- ユーザーが断った場合はそのセッションでは再提案しない
EOF
```

- [ ] **Step 2: 追記内容を確認する**

```bash
tail -20 ~/.claude/CLAUDE.md
```

期待出力（上記のスキル自律生成基準セクションが表示される）

- [ ] **Step 3: コミットする**

```bash
git add -A
git commit -m "feat(skill-lifecycle): CLAUDE.md にスキル自律生成基準を追記"
```

---

## セルフレビュー

### スペックカバレッジ確認

| スペック要件 | 実装タスク |
|------------|-----------|
| PreToolUse hook → skill-usage.json | Task 2, 3 |
| SessionEnd hook → Curator 週1回 | Task 6, 7 |
| 30日 stale マーク | Task 5 (curator_logic.py) |
| 90日 自動アーカイブ | Task 5 (curator_logic.py) |
| バックアップ（ロールバック） | Task 5 (.archive/backups/) |
| 並行セッション競合対策（fcntl） | Task 2, 5 |
| 未追跡スキルの保護（初期化） | Task 5 |
| Telegram 通知 | Task 5 |
| monthly-cleanup stale 可視化 | Task 9 |
| CLAUDE.md 自律生成基準 | Task 10 |

### 型・関数名の整合性確認

- `load_json(path: Path) -> dict` — Task 5 で定義、Task 5 内のみで使用 ✓
- `save_json(path: Path, data: dict) -> None` — Task 5 で定義、Task 5 内のみで使用 ✓
- `USAGE_FILE`, `STATUS_FILE` — Task 2 (sh) と Task 5 (py) でパスが一致: `~/.claude/skill-usage.json` / `~/.claude/skill-status.json` ✓
- ロールバックパス: `~/.claude/skills/.archive/backups/YYYY-MM-DD/skill-name` — Task 1 で作成、Task 5 で使用 ✓
