#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir"
if [ -r /etc/ssl/cert.pem ]; then
  export SSL_CERT_FILE="${SSL_CERT_FILE:-/etc/ssl/cert.pem}"
  export PIP_CERT="${PIP_CERT:-/etc/ssl/cert.pem}"
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'from importlib.metadata import version; assert version("pypdf") == "6.10.0"' 2>/dev/null; then
  .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python scripts/setup.py
if [ "${1:-}" = '--prepare-only' ]; then
  exit 0
fi
exec .venv/bin/python server.py "$@"
