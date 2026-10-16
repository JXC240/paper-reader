#!/bin/sh
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir" || exit 1
printf '%s\n' '将安装当前用户的Paper Reader后台服务：登录启动、退出后自动重启。' '不需要管理员权限，不改变休眠设置，只允许本机访问。'
if ./start.sh --prepare-only && .venv/bin/python scripts/background_service.py install && .venv/bin/python scripts/wait_for_reader.py; then
  open 'http://127.0.0.1:8877'
  printf '%s\n' '后台服务已安装，可以关闭此窗口。按回车结束。'
  read -r unused
  exit 0
fi
printf '%s\n' '安装未完成。若8877端口已有前台阅读器，请先在它的启动窗口按Control+C，再重试。' '不会自动关闭其他程序。按回车结束。'
read -r unused
exit 1
