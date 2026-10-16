#!/bin/sh
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir" || exit 1
if [ -x .venv/bin/python ] && [ -f scripts/background_service.py ]; then
  .venv/bin/python scripts/background_service.py is-installed
  installed=$?
  if [ "$installed" -eq 0 ]; then
    if .venv/bin/python scripts/background_service.py start && .venv/bin/python scripts/wait_for_reader.py; then
      open 'http://127.0.0.1:8877'
      exit 0
    fi
    printf '%s\n' '后台服务启动未完成，请查看上方提示。不会另起一个冲突的服务。按回车关闭。'
    read -r unused
    exit 1
  elif [ "$installed" -ne 1 ]; then
    printf '%s\n' '检测到其他项目的后台配置，未修改。请查看使用说明或联系维护者。按回车关闭。'
    read -r unused
    exit 1
  fi
fi
if [ -x .venv/bin/python ] && .venv/bin/python -c 'import urllib.request; r=urllib.request.urlopen("http://127.0.0.1:8877/api/session", timeout=2); assert r.headers.get("Server", "").startswith("PaperReader/")' 2>/dev/null; then
  open 'http://127.0.0.1:8877'
  exit 0
fi
printf '%s\n' 'Paper Reader 正在启动。页面地址：http://127.0.0.1:8877' '当前为前台模式：请保留这个窗口，按 Control+C 可以停止。' '希望登录后自动运行，可关闭本窗口后双击「安装后台服务.command」（仅macOS）。'
./start.sh --open-browser
result=$?
if [ "$result" -ne 0 ]; then
  printf '%s\n' '启动未完成，请查看上方提示。按回车关闭。'
  read -r unused
fi
exit "$result"
