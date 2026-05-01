#!/usr/bin/env bash
# Alembic マイグレーションのラッパースクリプト。
# 必ずこのスクリプト経由でマイグレーションを実行する（直接 alembic コマンドを叩かない）。
set -euo pipefail

# .env が無いと alembic コマンドが KeyError でクラッシュする (env.py が config.py 経由で env vars を必須とするため)
if [ ! -f "$(dirname "$0")/../.env" ]; then
  echo "❌ .env not found at $(dirname "$0")/../.env"
  echo "   Required env vars: GEMINI_API_KEY ATLAS_CLOUD_API_KEY TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID"
  exit 1
fi

cd "$(dirname "$0")/.."

case "${1:-help}" in
  backup)
    if [ ! -f video_ad.db ]; then
      echo "ℹ️  video_ad.db が存在しません — バックアップをスキップ"
    else
      ts=$(date +%Y%m%d_%H%M%S)
      cp video_ad.db "video_ad.db.bak.${ts}"
      echo "✓ バックアップ作成: video_ad.db.bak.${ts}"
    fi
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
    # 注意: これは alembic_version テーブルを含む完全なファイル復元。スキーマだけを戻したい場合は `downgrade` を使う。
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
