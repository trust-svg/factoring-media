#!/usr/bin/env bash
# Alembic マイグレーションのラッパースクリプト。
# 必ずこのスクリプト経由でマイグレーションを実行する（直接 alembic コマンドを叩かない）。
set -euo pipefail

cd "$(dirname "$0")/.."

case "${1:-help}" in
  backup)
    ts=$(date +%Y%m%d_%H%M%S)
    cp video_ad.db "video_ad.db.bak.${ts}"
    echo "✓ バックアップ作成: video_ad.db.bak.${ts}"
    ;;
  migrate)
    "$0" backup
    alembic upgrade head
    echo "✓ マイグレーション完了"
    ;;
  rollback)
    if [ -z "${2:-}" ]; then
      echo "Usage: $0 rollback <backup_filename>"
      ls -t video_ad.db.bak.* 2>/dev/null | head -5
      exit 1
    fi
    if [ ! -f "$2" ]; then
      echo "❌ バックアップファイルが見つかりません: $2"
      exit 1
    fi
    cp "$2" video_ad.db
    echo "✓ ロールバック完了: $2 → video_ad.db"
    ;;
  downgrade)
    "$0" backup
    alembic downgrade -1
    echo "✓ Alembic 1段階ダウングレード完了"
    ;;
  *)
    echo "Usage: $0 {backup|migrate|rollback <file>|downgrade}"
    exit 1
    ;;
esac
