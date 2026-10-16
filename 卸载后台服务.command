#!/bin/sh
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir" || exit 1
if [ ! -x .venv/bin/python ]; then
  printf '%s\n' '未找到项目Python环境，未执行卸载。按回车结束。'
  read -r unused
  exit 1
fi
printf '%s\n' '请先在阅读页面等待「已保存到本机」。将移除本项目的登录后台项，保留论文、标注和日志。'
.venv/bin/python scripts/background_service.py uninstall
result=$?
printf '%s\n' '按回车结束。'
read -r unused
exit "$result"
