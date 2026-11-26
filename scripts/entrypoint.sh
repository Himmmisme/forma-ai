#!/bin/sh
set -eu
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
python -m app.manage migrate
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers --no-access-log
