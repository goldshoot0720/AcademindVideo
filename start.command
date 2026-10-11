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

exec python3 scripts/serve.py --port "$PORT" --open
