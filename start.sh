#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir"
if [ -r /etc/ssl/cert.pem ]; then
  export SSL_CERT_FILE="${SSL_CERT_FILE:-/etc/ssl/cert.pem}"
  export PIP_CERT="${PIP_CERT:-/etc/ssl/cert.pem}"
fi
if [ -x .venv/bin/python ]; then
  bootstrap_python=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
  bootstrap_python=python3
else
  printf '%s\n' 'Paper Reader 需要 Python 3.10 或更高版本。请先安装 Python，再重新启动。' 'Python 3.10 or later is required. Install Python and run this launcher again.' >&2
  exit 1
fi
if ! "$bootstrap_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  printf '%s\n' '无法使用当前 Python：需要 Python 3.10 或更高版本。' 'Python 3.10 or later is required. If .venv belongs to an older Python, rename .venv and run again; keep data/ unchanged.' >&2
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  if ! "$bootstrap_python" -m venv .venv; then
    printf '%s\n' '无法创建项目环境。请检查 Python 的 venv/ensurepip 是否可用；部分 Linux 发行版需安装 python3-venv。' 'Could not create .venv. Check Python venv/ensurepip support (python3-venv on some Linux distributions), then retry.' >&2
    exit 1
  fi
fi
if ! .venv/bin/python -c 'from importlib.metadata import version; from pathlib import Path; requirements = [line.strip() for line in Path("requirements.txt").read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]; assert all("==" in item and version(item.split("==", 1)[0]) == item.split("==", 1)[1] for item in requirements)' 2>/dev/null; then
  if ! .venv/bin/python -m pip install -r requirements.txt; then
    printf '%s\n' '依赖安装失败。请检查网络和上方提示后重试；不需要删除 data/。' 'Dependency installation failed. Check the network and the error above, then retry; keep data/ unchanged.' >&2
    exit 1
  fi
fi
.venv/bin/python scripts/setup.py
if [ "${1:-}" = '--prepare-only' ]; then
  exit 0
fi
exec .venv/bin/python server.py "$@"
