#!/usr/bin/env bash
# inbox-dispatcher.sh — Obsidian inbox の .md を読み取り、
# Claude CLI で重要度・担当・期限を判定して active.md に追記する。
# 処理済みは _processed/YYYY-MM-DD/ に移動する。
#
# Usage:
#   inbox-dispatcher.sh                         # 通常実行
#   inbox-dispatcher.sh --dry-run               # 移動はせず、追記内容だけ表示
#   inbox-dispatcher.sh --inbox /path/to/dir    # 別の inbox ディレクトリを指定
#
# 想定スケジュール: morning briefing(7:30) の直前 7:25 に launchd か APScheduler で起動。
# 失敗時はエラー出力するが exit 0 で抜ける（朝のブリーフィングを止めないため）。

set -uo pipefail  # -e は意図的に外す。1ノートの失敗で全体停止しないため。

INBOX="${INBOX_DIR:-/Users/Mac_air/Obsidian/inbox}"
ACTIVE_MD="${ACTIVE_MD:-/Users/Mac_air/Claude-Workspace/.company/secretary/todos/active.md}"
TODAY="$(date +%Y-%m-%d)"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --inbox)   INBOX="$2"; shift 2 ;;
    *) echo "[err] unknown arg: $1" >&2; exit 0 ;;
  esac
done

if [[ ! -d "$INBOX" ]]; then
  echo "[skip] inbox not found: $INBOX"
  exit 0
fi
if [[ ! -f "$ACTIVE_MD" ]]; then
  echo "[err] active.md not found: $ACTIVE_MD" >&2
  exit 0
fi

PROCESSED_DIR="$INBOX/_processed/$TODAY"
COUNT=0

shopt -s nullglob
for note in "$INBOX"/*.md; do
  base="$(basename "$note")"
  case "$base" in
    _template.md|*.tmp) continue ;;
  esac

  echo "[note] $base"
  content="$(cat "$note")"
  if [[ -z "${content// /}" ]]; then
    echo "  [skip] empty"
    continue
  fi

  prompt='以下のメモから1〜複数のタスクを抽出してください。返却はJSON配列のみ（説明文・コードブロックなし）。タスクなしなら []。

各オブジェクトは以下フィールド:
- title: 簡潔なタスク名（30字以内）
- assignee: Jack(運営) / Larry(開発) / Mark(マーケ) / Warren(経理) / Elon(リサーチ) / Reid(経営企画) / Steve(秘書) / 社長 のいずれか
- priority: 緊急 / 高優先度 / 通常 のいずれか（明確に時間制約あれば緊急、戦略的重要なら高優先度、それ以外は通常）
- deadline: YYYY-MM-DD または なし

メモ内容:
'"$content"

  raw="$(printf '%s' "$prompt" | claude -p --output-format text 2>/dev/null || echo '[]')"
  json="$(echo "$raw" | sed -n '/^\[/,/^\]/p')"
  [[ -z "$json" ]] && json="$raw"

  if ! echo "$json" | jq -e '. | type == "array"' >/dev/null 2>&1; then
    echo "  [warn] non-JSON response, skip note"
    continue
  fi

  n="$(echo "$json" | jq 'length')"
  if [[ "$n" -eq 0 ]]; then
    echo "  [info] no tasks extracted"
    if [[ "$DRY_RUN" -eq 0 ]]; then
      mkdir -p "$PROCESSED_DIR"
      mv "$note" "$PROCESSED_DIR/"
    fi
    continue
  fi

  for i in $(seq 0 $((n-1))); do
    title="$(echo "$json" | jq -r ".[$i].title // empty")"
    assignee="$(echo "$json" | jq -r ".[$i].assignee // \"Steve\"")"
    priority="$(echo "$json" | jq -r ".[$i].priority // \"通常\"")"
    deadline="$(echo "$json" | jq -r ".[$i].deadline // \"なし\"")"
    [[ -z "$title" ]] && continue

    entry="- [UN] $title | 担当: $assignee | 期限: $deadline | 追加: $TODAY"
    case "$priority" in
      "緊急")     section="## 緊急" ;;
      "高優先度") section="## 高優先度" ;;
      *)          section="## 通常" ;;
    esac

    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "  [dry] $section <- $entry"
      continue
    fi

    if grep -qF "$section" "$ACTIVE_MD"; then
      awk -v marker="$section" -v entry="$entry" '
        BEGIN { inserted=0 }
        $0 == marker && !inserted { print; print entry; inserted=1; next }
        { print }
      ' "$ACTIVE_MD" > "$ACTIVE_MD.tmp" && mv "$ACTIVE_MD.tmp" "$ACTIVE_MD"
    else
      printf '\n%s\n%s\n' "$section" "$entry" >> "$ACTIVE_MD"
    fi
    echo "  [+] $entry"
    COUNT=$((COUNT+1))
  done

  if [[ "$DRY_RUN" -eq 0 ]]; then
    mkdir -p "$PROCESSED_DIR"
    mv "$note" "$PROCESSED_DIR/"
  fi
done

echo "[done] dispatched $COUNT task(s) at $(date +%H:%M)"
