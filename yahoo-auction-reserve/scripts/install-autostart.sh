#!/usr/bin/env bash
#
# ログイン時に自動で起動するようにする(ターミナルを開かなくてよくなる)。
#
#   scripts/install-autostart.sh            登録して即起動
#   scripts/install-autostart.sh uninstall  登録解除(アプリは止めない)
#   scripts/install-autostart.sh status     今どうなっているか
#
# ⚠️ 登録すると Mac は **スリープしなくなる**(caffeinate 常駐)。
#    入札の実行に必要な代償。蓋を閉じても止まらないので、電源とバッテリーに注意。
#    一時的に止めたいときは uninstall ではなく `launchctl kill TERM ...` で足りる
#    (下の status に出るコマンドを使う)。
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.trustlink.yar-autostart"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$APP_DIR/tmp/autostart"
DOMAIN="gui/$(id -u)"

case "${1:-install}" in
  status)
    echo "plist: $PLIST"
    if launchctl print "${DOMAIN}/${LABEL}" >/dev/null 2>&1; then
      launchctl print "${DOMAIN}/${LABEL}" | grep -E "state|last exit code|pid" || true
      echo
      echo "ログ: tail -f $LOG_DIR/autostart.log"
      echo "再起動: launchctl kickstart -k ${DOMAIN}/${LABEL}"
      echo "一時停止: launchctl kill TERM ${DOMAIN}/${LABEL}"
    else
      echo "未登録"
    fi
    exit 0
    ;;
  uninstall)
    launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
    rm -f "$PLIST"
    echo "自動起動を解除しました(コンテナは動いたままです)"
    echo "コンテナも止めるなら: cd $APP_DIR && docker compose down"
    exit 0
    ;;
  install) ;;
  *) echo "使い方: $0 [install|uninstall|status]" >&2; exit 1 ;;
esac

# 1度もビルドしていない状態で登録すると、autostart.sh は --build しないので
# 永久に立ち上がらない。先に人間が1回 remote-serve.sh を通しておくこと。
if ! docker image ls --format '{{.Repository}}' 2>/dev/null | grep -q "yahoo-auction-reserve"; then
  cat >&2 <<MSG
⚠️ イメージがまだビルドされていないようです。
   自動起動はビルドをしない(ログイン時に数分かかるため)ので、先に一度:

     cd $APP_DIR && scripts/remote-serve.sh

   を通してから、もう一度この登録を実行してください。
MSG
  exit 1
fi

mkdir -p "$LOG_DIR" "$(dirname "$PLIST")"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${APP_DIR}/scripts/autostart.sh</string>
  </array>
  <key>WorkingDirectory</key><string>${APP_DIR}</string>
  <key>RunAtLoad</key><true/>
  <!-- 落ちたら起こし直す。Docker がまだ上がっていない等で exit 1 した場合の再試行もこれ。 -->
  <key>KeepAlive</key><true/>
  <!-- 起動失敗を繰り返すときに秒間ループにならないよう間隔を空ける -->
  <key>ThrottleInterval</key><integer>60</integer>
  <key>StandardOutPath</key><string>${LOG_DIR}/autostart.log</string>
  <key>StandardErrorPath</key><string>${LOG_DIR}/autostart.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
PLIST_EOF

launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl enable "${DOMAIN}/${LABEL}"

echo "登録しました: $PLIST"
echo
echo "  ログ    : tail -f $LOG_DIR/autostart.log"
echo "  状態    : $0 status"
echo "  解除    : $0 uninstall"
echo
echo "⚠️ この登録中、Mac はスリープしません(入札の実行に必要)。"
