#!/bin/sh
# Injects the API_BASE env var into index.html's __API_BASE__ placeholder
# before nginx starts. Runs automatically: the official nginx image's
# entrypoint executes every executable script under /docker-entrypoint.d/.
set -eu

: "${API_BASE:=http://127.0.0.1:8000}"

sed -i "s|__API_BASE__|${API_BASE}|g" /usr/share/nginx/html/index.html
