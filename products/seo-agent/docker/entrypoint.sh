#!/usr/bin/env bash
set -euo pipefail

# Export env vars for cron (cron strips environment)
printenv | grep -E '^(TELEGRAM_|GSC_|FACCEL_|SAIMU_|REPORTS_DIR|DB_PATH|MIN_IMPRESSIONS|POSITION_|LOOKBACK_)' \
    > /etc/environment || true

# If args passed, run them directly (e.g., dry-run)
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

mkdir -p /app/reports /app/data
touch /app/reports/cron.log

# Initial schema bootstrap
python -c "from core import db; db.init_schema()" || true

echo "[entrypoint] starting cron, weekly job Mon 08:00 JST"
exec cron -f
