#!/bin/sh
set -eu

requested_model_dir="${PADDLE_HOME:-/models}"
fallback_model_dir="${OCR_FALLBACK_MODEL_DIR:-/tmp/ocr/models}"
runtime_dir="${OCR_RUNTIME_DIR:-/tmp/ocr}"
require_persistent_models="${OCR_REQUIRE_PERSISTENT_MODELS:-false}"

model_dir_is_writable() {
  directory="$1"
  mkdir -p "$directory" 2>/dev/null || return 1
  probe="$directory/.library-write-probe-$$"
  : > "$probe" 2>/dev/null || return 1
  rm -f "$probe"
}

if model_dir_is_writable "$requested_model_dir"; then
  cache_root="$requested_model_dir"
else
  case "$(printf '%s' "$require_persistent_models" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)
      printf '%s\n' "OCR 错误：模型持久化目录 $requested_model_dir 不可写。已按生产配置拒绝退回容器临时目录。" >&2
      exit 78
      ;;
  esac
  mkdir -p "$fallback_model_dir"
  cache_root="$fallback_model_dir"
  printf '%s\n' "OCR 提示：模型持久化目录 $requested_model_dir 不可写，当前改用 $fallback_model_dir。请修复 NAS 目录权限后重建容器。" >&2
fi

mkdir -p \
  "$cache_root/.paddlex" \
  "$cache_root/.cache" \
  "$runtime_dir/tmp"

export HOME="$cache_root"
export PADDLE_HOME="$cache_root"
export PADDLE_PDX_CACHE_HOME="$cache_root/.paddlex"
export XDG_CACHE_HOME="$cache_root/.cache"
export TMPDIR="$runtime_dir/tmp"
export LIBRARY_OCR_EFFECTIVE_MODEL_ROOT="$cache_root"

exec "$@"
