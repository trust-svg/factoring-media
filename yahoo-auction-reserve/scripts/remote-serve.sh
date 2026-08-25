#!/usr/bin/env bash
#
# 外出先から自分の端末だけに公開する(Tailscale)。
# 公開URLは作られない。tailnet(自分のアカウントの端末)からしか到達できない。
#
#   scripts/remote-serve.sh        起動して公開し、スリープを抑止したまま常駐
#   scripts/remote-serve.sh off    公開だけ取り下げる(アプリは止めない)
#
# ⚠️ このアプリは Mac でしか動かせない。ヤフオクはデータセンター IP を 403 で
#    弾くので、VPS に載せると画面は開くのに入札だけ落ちる(設計 §4)。
#
set -euo pipefail

cd "$(dirname "$0")/.."
PORT="${PORT:-3000}"

# App Store 版・cask 版どちらでも CLI の位置が違う。PATH に無ければ app 内を見る。
TS="$(command -v tailscale || true)"
if [ -z "$TS" ] && [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]; then
  TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
fi
if [ -z "$TS" ]; then
  cat <<'MSG' >&2
tailscale が見つかりません。先に入れてください。

  brew install --cask tailscale
  open -a Tailscale     # ログイン。iPhone 側にも同じアカウントで入れておく

MSG
  exit 1
fi

if [ "${1:-}" = "off" ]; then
  "$TS" serve reset
  echo "公開を取り下げました(アプリと worker は動いたままです)"
  exit 0
fi

echo "==> アプリを起動 (docker compose)"
docker compose up -d --build

echo "==> localhost:${PORT} の応答を待つ"
for i in $(seq 1 60); do
  if curl -fsS -o /dev/null "http://localhost:${PORT}/login"; then
    echo "    OK (${i}回目)"
    break
  fi
  if [ "$i" = 60 ]; then
    echo "    応答がありません。docker compose logs web で確認してください" >&2
    exit 1
  fi
  sleep 2
done

echo "==> tailnet に公開"
"$TS" serve --bg "$PORT"
"$TS" serve status

cat <<'MSG'

上の https://... を iPhone の Safari で開き、共有 > ホーム画面に追加 で PWA になる。
(iPhone 側の Tailscale が接続されている必要がある)

⚠️ この窓を閉じる / Ctrl-C を押すとスリープ抑止が解除される。
   Mac がスリープすると入札は実行されない(画面だけは外から開けてしまう)。
   止まっているかどうかは、外出先でも画面上部の赤い警告で分かる。

MSG

echo "==> スリープ抑止 (caffeinate)。終了するには Ctrl-C"
exec caffeinate -dimsu
