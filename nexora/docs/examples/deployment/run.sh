#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec .venv/bin/nex run app.nex --allow-read config/app.conf -- "$@"
