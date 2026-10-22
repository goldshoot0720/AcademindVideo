#!/bin/zsh
# 啟動本地測試伺服器 —— Academind 中英雙語動態字幕課程庫
#
# 用法：
#   雙擊本檔（Finder）         → 自動開瀏覽器
#   終端機：./start.command    → 同上
#   ./start.command 9000       → 指定埠號
#
# 停止：在此視窗按 Ctrl-C，或執行  pkill -f scripts/serve.py

cd "$(dirname "$0")" || exit 1

PORT="${1:-8788}"
URL="http://localhost:${PORT}/"

# Finder 雙擊時 PATH 很精簡，逐一找出可用的 python3
PY=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3 \
         "$HOME/.workbuddy-ai/binaries/python/versions/3.13.12/bin/python3"; do
  if [ -x "$c" ]; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  echo "✗ 找不到 python3，請先安裝（或安裝 Xcode Command Line Tools）"
  echo "  按任意鍵關閉…"
  read -k 1
  exit 1
fi

# 自動提交常駐：launchd 在這台機器被擋（bootstrap 一律 EIO），
# 所以改由每次啟動本檔時把 autopush 拉起來。autopush 自己有單實例鎖，
# 重複呼叫是安全的；_drive/ 不存在（別台機器）就跳過。
if [ -f _drive/launch_autopush.py ] && ! pgrep -f "_drive/autopush.py" >/dev/null 2>&1; then
  env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
      "$PY" _drive/launch_autopush.py >/dev/null 2>&1
fi

# 若同埠已有服務，直接開啟不重複啟動
# 注意：--noproxy '*' 繞過系統/環境代理，否則代理會對任何埠都回應成功
CODE=$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --max-time 2 "$URL" 2>/dev/null)
if [ "$CODE" = "200" ]; then
  echo "✓ 本地伺服器已在運行：$URL"
  open "$URL"
  exit 0
fi

echo "→ 啟動本地伺服器：$URL"
echo "  （按 Ctrl-C 可停止）"
echo

exec "$PY" scripts/serve.py --port "$PORT" --open
