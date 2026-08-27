#!/usr/bin/env bash
#
# ログイン時に launchd から呼ばれる常駐スクリプト(対話なし)。
# 手で叩くときは scripts/remote-serve.sh を使うこと。こちらは
# 「ターミナルを開かずに同じ状態にする」ための無人版。
#
# やること: Docker の起動待ち → compose up -d → tailnet 公開の確認 → caffeinate 常駐
#
# ⚠️ 無人で走るので、**失敗したら黙って続けず必ず exit 1 する**。
#    launchd の KeepAlive が再試行してくれる。ここで「まあ動くだろう」と
#    先に進むと、画面だけ開けて入札だけ動かない状態がいちばん長く続く。
#
set -euo pipefail

cd "$(dirname "$0")/.."
PORT="${PORT:-3000}"
LOG_TAG="[yar-autostart]"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG $*"; }

# launchd の PATH は /usr/bin:/bin:/usr/sbin:/sbin しかない。
# docker も tailscale もここには居ないので、実体を明示的に探す。
find_bin() {
  local name="$1"; shift
  local p
  p="$(command -v "$name" 2>/dev/null || true)"
  if [ -n "$p" ]; then echo "$p"; return 0; fi
  for p in "$@"; do
    if [ -x "$p" ]; then echo "$p"; return 0; fi
  done
  return 1
}

DOCKER="$(find_bin docker \
  /usr/local/bin/docker \
  /opt/homebrew/bin/docker \
  "$HOME/.docker/bin/docker" \
  /Applications/Docker.app/Contents/Resources/bin/docker)" || {
  log "docker が見つからない"; exit 1;
}
TS="$(find_bin tailscale \
  /usr/local/bin/tailscale \
  /opt/homebrew/bin/tailscale \
  /Applications/Tailscale.app/Contents/MacOS/Tailscale)" || {
  log "tailscale が見つからない"; exit 1;
}

# --- 1. Docker デーモンの起動待ち ---
# ログイン直後は Docker Desktop がまだ上がっていない。
# ⚠️ ここを待たずに compose を叩くと「起動できなかった」ではなく
#    「起動した気になって終了」になり、KeepAlive も再試行しない。
if ! "$DOCKER" info >/dev/null 2>&1; then
  log "Docker がまだ起動していない。起動を試みる"
  open -a Docker >/dev/null 2>&1 || true
  for i in $(seq 1 90); do
    if "$DOCKER" info >/dev/null 2>&1; then break; fi
    if [ "$i" = 90 ]; then log "Docker が3分待っても起動しない"; exit 1; fi
    sleep 2
  done
fi
log "Docker OK"

# --- 2. コンテナ起動 ---
# ⚠️ ここで --build しない。ログイン時に数分かかるうえ、ネットワークが
#    まだ繋がっていない時間帯に当たると失敗する。イメージのビルドは
#    コードを変えた人間が scripts/remote-serve.sh で明示的にやること。
if ! "$DOCKER" compose up -d; then
  log "docker compose up -d に失敗"
  exit 1
fi

# --- 3. アプリの応答待ち ---
for i in $(seq 1 90); do
  if curl -fsS -o /dev/null "http://localhost:${PORT}/login"; then
    log "アプリ応答 OK (${i}回目)"
    break
  fi
  if [ "$i" = 90 ]; then
    log "localhost:${PORT} が3分待っても応答しない"
    exit 1
  fi
  sleep 2
done

# --- 4. tailnet 公開 ---
# serve の設定は tailscaled 側に永続化されるので再起動しても残る。
# 残っていない場合だけ張り直す(毎回叩いても害はないが、ログが読みやすい)。
if "$TS" serve status 2>/dev/null | grep -q "127.0.0.1:${PORT}"; then
  log "tailnet 公開は既に有効"
elif "$TS" serve --bg "$PORT" >/dev/null 2>&1; then
  log "tailnet に公開した"
else
  # ⚠️ ここは exit しない。公開できなくても **入札は動く**。
  #    外から見えないだけなので、止めると被害が大きくなる方に倒れる。
  log "⚠️ tailnet 公開に失敗(入札は動く。外部からの閲覧だけできない)"
fi

# --- 5. スリープ抑止 ---
# スリープすると入札が実行されない。caffeinate をフォアグラウンドで抱えて
# launchd に「このジョブは生きている」と見せる。落ちたら KeepAlive が復活させる。
log "スリープ抑止に入る (caffeinate)"
exec caffeinate -dimsu
