#!/bin/sh
set -eu

runtime_file="/app/dist/client/runtime-config.js"
api_base="${BROWSER_API_BASE_URL:-${NEXT_PUBLIC_API_URL:-}}"

if [ -n "$api_base" ] && [ "$api_base" != "/api" ]; then
  if ! printf '%s' "$api_base" \
    | LC_ALL=C grep -Eq '^https?://(\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.-]+)(:[0-9]{1,5})?/api$'; then
    printf '%s\n' "Web 启动失败：BROWSER_API_BASE_URL 必须为空、/api 或有效的 http(s) API 地址。" >&2
    exit 1
  fi
fi

if [ -d "$(dirname "$runtime_file")" ]; then
  temporary_file="${runtime_file}.tmp"
  printf 'window.__SOCIAL_THEORY_LIBRARY_CONFIG__ = Object.freeze({ apiBase: "%s" });\n' "$api_base" > "$temporary_file"
  mv "$temporary_file" "$runtime_file"
fi

exec "$@"
