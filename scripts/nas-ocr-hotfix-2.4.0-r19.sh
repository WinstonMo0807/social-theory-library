#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/volume2/library/docker/social-theory-library}"
SOURCE_DIR="${SOURCE_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
EXPECTED_VERSION="2.4.0"
BASE_TAG="social-theory-library-ocr-base:offline-pre-${EXPECTED_VERSION}-r19"

fail() {
  printf '%s\n' "OCR 修复停止：$1" >&2
  exit 1
}

[ -d "$APP_DIR" ] || fail "找不到项目目录 $APP_DIR"
[ -f "$APP_DIR/compose.yaml" ] || fail "项目缺少 compose.yaml"
[ -f "$SOURCE_DIR/ocr_service/docker-entrypoint.sh" ] || fail "修补包缺少 OCR 启动脚本"
[ -f "$SOURCE_DIR/offline/ocr.Dockerfile" ] || fail "修补包缺少 OCR 叠加镜像定义"
command -v docker >/dev/null 2>&1 || fail "没有找到 Docker 命令"

cd "$APP_DIR"
docker compose --profile ocr config --quiet

ocr_container="$(docker compose --profile ocr ps -aq paddleocr 2>/dev/null || true)"
[ -n "$ocr_container" ] || fail "没有找到现有 OCR 容器"
ocr_base_image="$(docker inspect --format '{{.Image}}' "$ocr_container")"
ocr_target_image="$(docker inspect --format '{{.Config.Image}}' "$ocr_container")"
[ -n "$ocr_base_image" ] || fail "无法读取 OCR 基础镜像"
[ -n "$ocr_target_image" ] || fail "无法读取 OCR 镜像名称"
docker image inspect "$ocr_base_image" >/dev/null 2>&1 || fail "OCR 基础镜像不在 NAS 本地"

backup_dir="$APP_DIR/storage/backups/ocr-hotfix-r19-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
if [ -f "$APP_DIR/ocr_service/docker-entrypoint.sh" ]; then
  cp "$APP_DIR/ocr_service/docker-entrypoint.sh" "$backup_dir/docker-entrypoint.sh"
fi

mkdir -p "$APP_DIR/ocr_service" "$APP_DIR/offline"
cp "$SOURCE_DIR/ocr_service/docker-entrypoint.sh" "$APP_DIR/ocr_service/docker-entrypoint.sh"
cp "$SOURCE_DIR/offline/ocr.Dockerfile" "$APP_DIR/offline/ocr.Dockerfile"
chmod 0755 "$APP_DIR/ocr_service/docker-entrypoint.sh"

docker image tag "$ocr_base_image" "$BASE_TAG"
docker build \
  --pull=false \
  --network=none \
  --build-arg "BASE_IMAGE=$BASE_TAG" \
  -f "$SOURCE_DIR/offline/ocr.Dockerfile" \
  -t "$ocr_target_image" \
  "$SOURCE_DIR"

cd "$APP_DIR"
docker compose --profile ocr up -d --no-deps --force-recreate paddleocr

attempt=0
while [ "$attempt" -lt 60 ]; do
  if docker compose --profile ocr exec -T paddleocr python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3)" \
    >/dev/null 2>&1; then
    model_home="$(docker compose --profile ocr exec -T paddleocr sh -c 'printf %s "$PADDLE_HOME"' | tr -d '\r\n')"
    paddlex_cache="$(docker compose --profile ocr exec -T paddleocr sh -c 'printf %s "$PADDLE_PDX_CACHE_HOME"' | tr -d '\r\n')"
    printf '%s\n' "OCR 修复完成。"
    printf '%s\n' "Paddle 模型目录：$model_home"
    printf '%s\n' "PaddleX 缓存目录：$paddlex_cache"
    printf '%s\n' "修复前启动脚本备份：$backup_dir"
    docker compose --profile ocr ps paddleocr
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 2
done

docker compose --profile ocr logs --no-color --tail=100 paddleocr >&2 || true
fail "OCR 在 120 秒内没有通过健康检查，请保留上方日志"
