#!/bin/sh
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir" || exit 1
if [ ! -x .venv/bin/python ]; then
  printf '%s\n' '未找到项目Python环境，未执行停止。按回车结束。'
  read -r unused
  exit 1
fi
printf '%s\n' '请先在阅读页面等待「已保存到本机」。停止后网页将无法连接。'
.venv/bin/python scripts/background_service.py stop
result=$?
printf '%s\n' '再次双击「启动阅读器.command」可重新启用后台服务。按回车结束。'
read -r unused
exit "$result"
