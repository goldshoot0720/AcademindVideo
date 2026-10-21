#!/bin/zsh
# 終端機入口 —— 與 start.command 完全相同，僅檔名不同
# 用法：./serve.sh [port]

cd "$(dirname "$0")" || exit 1
exec ./start.command "$@"
