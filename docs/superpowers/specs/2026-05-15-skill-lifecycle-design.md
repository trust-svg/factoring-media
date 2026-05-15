# スキルライフサイクルシステム — Design Spec

**Date**: 2026-05-15
**Author**: Hiro + Claude
**Status**: Approved
**Origin**: Hermes Agent Masterclass (x.com/akshay_pachaar/status/2054564519280804028) の Curator / スキル自律生成を Claude Code スーパーパワーズに移植

---

## 1. 目的

51スキル（683MB）が増え続ける中、使用されていないスキルを自動で整理し、再利用可能なパターンをスキルとして自動提案する仕組みを構築する。

### 解決する課題

- どのスキルが使われているか把握できない
- 使われなくなったスキルが放置されてトークンと注意を消費する
- 手動での `monthly-cleanup` は精度が低い（使用頻度データがない）
- 複雑なタスクを解決しても、そのパターンがスキルとして定着しない

### 非目標

- GEPA / SQLite セッション検索（別フェーズで検討）
- 自然言語 cron（別フェーズで検討）
- スキルの品質評価（Curator は使用頻度のみで判定）
- VPS 側のスキル管理

---

## 2. アーキテクチャ概要

```
[PreToolUse Hook]
  Skill ツール呼び出しを検知
       ↓
  ~/.claude/skill-usage.json を更新（JST日付）

[SessionEnd Hook]
  Curator スクリプト起動（7日に1回のみ実行）
       ↓
  ① skill-usage.json 読み込み
  ② 未追跡スキルを last_used = 今日 で初期化（保護）
  ③ 各スキルの日数判定
     ├─ 30〜89日未使用 → skill-status.json に stale: true
     └─ 90日以上未使用 → .archive/ へ退避（バックアップ後）
  ④ 変化があった場合のみ Telegram 通知

[CLAUDE.md 追記]
  複雑タスク完了後に skill-creator 提案基準を明記
```

---

## 3. ファイル構成

```
~/.claude/
  ├── skill-usage.json          # 使用履歴 { "skill-name": "YYYY-MM-DD" }
  ├── skill-status.json         # stale 状態 { "skill-name": { "stale": true, ... } }
  ├── scripts/
  │   ├── track-skill-usage.sh  # PreToolUse hook スクリプト
  │   ├── curator.sh            # SessionEnd hook スクリプト（7日チェック + 起動）
  │   └── curator_logic.py     # Curator コアロジック（Python）
  └── skills/
      └── .archive/
          └── backups/
              └── YYYYMMDD/     # アーカイブ前のバックアップ
```

---

## 4. Phase 1: 使用履歴トラッキング

### 4.1 settings.json への追加

```json
"PreToolUse": [
  {
    "matcher": "Skill",
    "hooks": [{
      "type": "command",
      "command": "~/.claude/scripts/track-skill-usage.sh"
    }]
  }
]
```

### 4.2 track-skill-usage.sh

```bash
#!/bin/bash
# PreToolUse hook: Skill ツール呼び出し時に使用日を記録

USAGE_FILE="$HOME/.claude/skill-usage.json"
TODAY=$(TZ=Asia/Tokyo date +%Y-%m-%d)

# 標準入力から skill 名を取得
SKILL_NAME=$(python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input', {}).get('skill', ''))
except:
    print('')
")

[ -z "$SKILL_NAME" ] && exit 0
[ -f "$USAGE_FILE" ] || echo '{}' > "$USAGE_FILE"

# ファイルロック付きで書き込み
python3 -c "
import json, fcntl, os
path = os.path.expanduser('~/.claude/skill-usage.json')
with open(path, 'r+') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    d = json.load(f)
    d['$SKILL_NAME'] = '$TODAY'
    f.seek(0)
    json.dump(d, f, indent=2)
    f.truncate()
    fcntl.flock(f, fcntl.LOCK_UN)
"
```

### 4.3 skill-usage.json のイメージ

```json
{
  "brainstorming": "2026-05-15",
  "skill-creator": "2026-05-10",
  "monthly-cleanup": "2026-04-01",
  "ads-google": "2026-02-20"
}
```

### 4.4 Phase 1 の完了基準

- 1週間以上 skill-usage.json にデータが蓄積されていること
- 実際に呼び出したスキルが正しく記録されていること

---

## 5. Phase 2: Curator（自動アーカイブ）

### 5.1 settings.json への追加

```json
"SessionEnd": [
  {
    "hooks": [{
      "type": "command",
      "command": "~/.claude/scripts/curator.sh"
    }]
  }
]
```

### 5.2 curator.sh の動作フロー

```bash
#!/bin/bash
# SessionEnd hook: スキルのライフサイクル管理

SKILLS_DIR="$HOME/.claude/skills"
USAGE_FILE="$HOME/.claude/skill-usage.json"
STATUS_FILE="$HOME/.claude/skill-status.json"
LAST_RUN_FILE="$HOME/.claude/.curator-last-run"
ARCHIVE_DIR="$SKILLS_DIR/.archive"
BACKUP_BASE="$ARCHIVE_DIR/backups"
TODAY=$(TZ=Asia/Tokyo date +%Y-%m-%d)
TODAY_STAMP=$(TZ=Asia/Tokyo date +%Y%m%d)

# ① 7日以内に実行済みなら終了
if [ -f "$LAST_RUN_FILE" ]; then
    LAST=$(cat "$LAST_RUN_FILE")
    DAYS=$(python3 -c "from datetime import date; print((date.fromisoformat('$TODAY') - date.fromisoformat('$LAST')).days)")
    [ "$DAYS" -lt 7 ] && exit 0
fi

# ② Curator ロジックを Python で実行（ファイルロック込み）
python3 ~/.claude/scripts/curator_logic.py

echo "$TODAY" > "$LAST_RUN_FILE"
```

### 5.3 curator_logic.py の処理

```python
import json, os, shutil, fcntl
from datetime import date, timedelta

SKILLS_DIR  = os.path.expanduser("~/.claude/skills")
USAGE_FILE  = os.path.expanduser("~/.claude/skill-usage.json")
STATUS_FILE = os.path.expanduser("~/.claude/skill-status.json")
ARCHIVE_DIR = os.path.join(SKILLS_DIR, ".archive")
BACKUP_BASE = os.path.join(ARCHIVE_DIR, "backups")
from datetime import timezone, timedelta
JST   = timezone(timedelta(hours=9))
TODAY = date.today()  # ホスト TZ が Asia/Tokyo のため date.today() は JST

# ファイル読み込み
usage  = json.load(open(USAGE_FILE)) if os.path.exists(USAGE_FILE) else {}
status = json.load(open(STATUS_FILE)) if os.path.exists(STATUS_FILE) else {}

archived = []
staled   = []

for skill_dir in os.scandir(SKILLS_DIR):
    if not skill_dir.is_dir(): continue
    if skill_dir.name.startswith("."): continue  # .archive/ 等を除外
    if not os.path.exists(os.path.join(skill_dir.path, "SKILL.md")): continue

    name = skill_dir.name

    # ② 未追跡スキルを today で初期化（保護）
    if name not in usage:
        usage[name] = str(TODAY)
        continue

    days = (TODAY - date.fromisoformat(usage[name])).days

    if days >= 90:
        # アーカイブ処理
        backup_path = os.path.join(BACKUP_BASE, str(TODAY), name)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copytree(skill_dir.path, backup_path)
        shutil.rmtree(skill_dir.path)
        archived.append(name)

    elif days >= 30:
        # stale マーク
        status[name] = {"stale": True, "stale_since": str(TODAY), "days_unused": days}
        staled.append(name)

    else:
        # 正常使用中 → stale 解除
        if name in status:
            status[name]["stale"] = False

# ファイル書き込み（ロック付き）
for path, data in [(USAGE_FILE, usage), (STATUS_FILE, status)]:
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(data, f, indent=2, ensure_ascii=False)
        fcntl.flock(f, fcntl.LOCK_UN)

# Telegram 通知（変化がある場合のみ）
if archived or staled:
    import subprocess
    env_file = os.path.expanduser("~/.claude/.telegram-meta-bot.env")
    env = {}
    for line in open(env_file):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v.strip("'\"")

    lines = ["🗂 Curator 実行完了"]
    if archived: lines.append(f"アーカイブ: {', '.join(archived)}")
    if staled:   lines.append(f"Stale マーク: {len(staled)}件")
    lines.append(f"ロールバック: ~/.claude/skills/.archive/backups/{TODAY}/")

    subprocess.run([
        "curl", "-s",
        f"https://api.telegram.org/bot{env['TELEGRAM_META_BOT_TOKEN']}/sendMessage",
        "--data-urlencode", f"chat_id={env['TELEGRAM_META_BOT_CHAT_ID']}",
        "--data-urlencode", f"text={chr(10).join(lines)}"
    ], capture_output=True)
```

### 5.4 ロールバック方法

```bash
# 誤アーカイブ時の復元（1コマンド）
cp -r ~/.claude/skills/.archive/backups/20260515/skill-name \
       ~/.claude/skills/skill-name
```

### 5.5 stale の可視化

`monthly-cleanup` スキルのレポートに以下を追加する（Phase 2 実装時に monthly-cleanup を更新）：

```
⚠️ Stale スキル（30日以上未使用）:
  - ads-google: 45日未使用
  - nano-banana-pro: 38日未使用
```

---

## 6. Phase 3: スキル自律生成基準（CLAUDE.md 追記）

```markdown
## スキル自律生成の判断基準

以下が 2つ以上揃ったタスクが完了したとき、skill-creator の使用を提案する：

1. ツールコールが 5 回以上あった
2. エラーや行き詰まりを経て解決した
3. 同じパターンを複数プロダクトで使った
4. ユーザーが手順を訂正した

提案文の例:
「このタスクはスキル化できそうです。/skill-creator で手順を保存しますか？」

制約:
- 1セッションにつき最大 1 回
- 短い質問・単純な修正タスクは対象外
- ユーザーが断った場合はそれ以上提案しない
```

---

## 7. 実装スケジュール

| Phase | 内容 | 期間 |
|-------|------|------|
| Phase 1 | track-skill-usage.sh + PreToolUse hook | Day 1 |
| (観察) | 1週間データを貯める | Day 1〜7 |
| Phase 2 | curator.sh + SessionEnd hook | Day 8 |
| Phase 3 | CLAUDE.md 自律生成基準追記 | Day 8（同時） |

---

## 8. リスクと対策

| リスク | 対策 |
|--------|------|
| 並行セッションのファイル競合 | Python `fcntl` ロック |
| 初回 Curator で全スキルアーカイブ | 未追跡スキルは last_used = 今日で保護 |
| .archive/ が誤ってスキル探索される | bash glob は `.` 始まりを自動除外（Phase 2 テスト時確認） |
| 90日閾値が実態に合わない | Phase 1 の観察データを見て調整してから Phase 2 投入 |
| stale スキルに気づかない | monthly-cleanup レポートに統合 |

---

## 9. 検証方法

**Phase 1:**
```bash
# 任意のスキルを呼び出した後に確認
cat ~/.claude/skill-usage.json
```

**Phase 2:**
```bash
# テスト用に last_used を古い日付に書き換えて Curator を手動実行
# .curator-last-run を削除（または古い日付に書き換え）して curator.sh を直接実行
rm ~/.claude/.curator-last-run
~/.claude/scripts/curator.sh
```

**Phase 3:**
- 5回以上ツールコールしたセッション終了後、提案が出るか目視確認
