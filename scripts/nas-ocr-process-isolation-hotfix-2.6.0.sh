#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/volume2/library/docker/social-theory-library}"
PROJECT_NAME="${PROJECT_NAME:-social-science-library}"
PAYLOAD_DIR="${PAYLOAD_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}"
EXPECTED_APP_SHA="c8e786a4b8e2e6ffe687068555c772f9b2b3672c05c55141ac6cbf32129243a6"
EXPECTED_MODEL_PROBE_SHA="40e4fbd2334f6ec08d49b90b481683c6484b27d0c338fa62405fe49fd2d136fd"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$APP_DIR/storage/backups/pre-ocr-process-hotfix-2.6.0-$STAMP"
COMPOSE_IMAGE="${PROJECT_NAME}-paddleocr"
PREVIOUS_IMAGE_TAG="$COMPOSE_IMAGE:pre-r37-$STAMP"
NEW_IMAGE_TAG="$COMPOSE_IMAGE:r37-$STAMP"
PATCH_CONTAINER="library-ocr-r37-build-$STAMP"
ROLLBACK_READY=0
COMPLETED=0

dc() {
  sudo -n docker compose \
    --env-file "$APP_DIR/.env" \
    -p "$PROJECT_NAME" \
    -f "$APP_DIR/compose.public.yaml" \
    -f "$APP_DIR/compose.cloudflare.yaml" \
    --profile ocr \
    "$@"
}

rollback_on_error() {
  status="$?"
  trap - EXIT HUP INT TERM
  if [ -n "$PATCH_CONTAINER" ]; then
    sudo -n docker rm -f "$PATCH_CONTAINER" >/dev/null 2>&1 || true
  fi
  if [ "$status" -ne 0 ] && [ "$ROLLBACK_READY" -eq 1 ] && [ "$COMPLETED" -eq 0 ]; then
    printf '%s\n' "OCR 热修复失败，正在恢复旧源码和旧镜像。" >&2
    sudo -n cp -a "$BACKUP_DIR/app.py" "$APP_DIR/ocr_service/app.py" || true
    sudo -n cp -a "$BACKUP_DIR/model_probe.py" "$APP_DIR/ocr_service/model_probe.py" || true
    sudo -n docker tag "$PREVIOUS_IMAGE_TAG" "$COMPOSE_IMAGE" || true
    dc up -d --no-build --pull never --no-deps --force-recreate paddleocr || true
  fi
  exit "$status"
}
trap rollback_on_error EXIT HUP INT TERM

test -d "$APP_DIR"
test -f "$APP_DIR/.env"
test -f "$APP_DIR/compose.public.yaml"
test -f "$APP_DIR/compose.cloudflare.yaml"
test -f "$APP_DIR/ocr_service/app.py"
test -f "$APP_DIR/ocr_service/model_probe.py"
test -f "$PAYLOAD_DIR/ocr_service/app.py"
test -f "$PAYLOAD_DIR/ocr_service/model_probe.py"
test -f "$PAYLOAD_DIR/ocr_service/tests/test_app.py"

printf '%s  %s\n' "$EXPECTED_APP_SHA" "$PAYLOAD_DIR/ocr_service/app.py" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_MODEL_PROBE_SHA" "$PAYLOAD_DIR/ocr_service/model_probe.py" | sha256sum -c -

container_id="$(dc ps -q paddleocr)"
test -n "$container_id"
previous_image_id="$(sudo -n docker inspect --format '{{.Image}}' "$container_id")"
test -n "$previous_image_id"

sudo -n mkdir -p "$BACKUP_DIR"
sudo -n cp -a "$APP_DIR/ocr_service/app.py" "$BACKUP_DIR/app.py"
sudo -n cp -a "$APP_DIR/ocr_service/model_probe.py" "$BACKUP_DIR/model_probe.py"
sudo -n cp -a "$APP_DIR/ocr_service/Dockerfile" "$BACKUP_DIR/Dockerfile"
printf '%s\n' "$previous_image_id" | sudo -n tee "$BACKUP_DIR/paddleocr-image-id.txt" >/dev/null
printf '%s\n' "$PREVIOUS_IMAGE_TAG" | sudo -n tee "$BACKUP_DIR/paddleocr-image-tag.txt" >/dev/null
sudo -n docker tag "$previous_image_id" "$PREVIOUS_IMAGE_TAG"
ROLLBACK_READY=1

sudo -n install -m 0644 "$PAYLOAD_DIR/ocr_service/app.py" "$APP_DIR/ocr_service/app.py"
sudo -n install -m 0644 "$PAYLOAD_DIR/ocr_service/model_probe.py" "$APP_DIR/ocr_service/model_probe.py"

# The production OCR image may have been loaded from an offline release, so
# BuildKit dependency layers are not guaranteed to exist. Create one new image
# layer from the verified running image instead of invoking apt or pip again.
sudo -n docker create --name "$PATCH_CONTAINER" "$previous_image_id" >/dev/null
sudo -n docker cp "$PAYLOAD_DIR/ocr_service/app.py" "$PATCH_CONTAINER:/app/app.py"
sudo -n docker cp "$PAYLOAD_DIR/ocr_service/model_probe.py" "$PATCH_CONTAINER:/app/model_probe.py"
new_image_id="$(sudo -n docker commit --pause=true "$PATCH_CONTAINER" "$NEW_IMAGE_TAG")"
test -n "$new_image_id"
sudo -n docker rm "$PATCH_CONTAINER" >/dev/null
PATCH_CONTAINER=""
sudo -n docker tag "$new_image_id" "$COMPOSE_IMAGE"

sudo -n docker run --rm \
  -v "$PAYLOAD_DIR/ocr_service/tests:/app/tests:ro" \
  "$NEW_IMAGE_TAG" \
  python -m unittest discover -s /app/tests -v

dc up -d --no-build --pull never --no-deps --force-recreate paddleocr

attempt=0
while [ "$attempt" -lt 30 ]; do
  attempt=$((attempt + 1))
  container_id="$(dc ps -q paddleocr)"
  state="$(sudo -n docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
  [ "$state" = "healthy" ] && break
  sleep 2
done
[ "$state" = "healthy" ]

ready_json="$(
  dc exec -T paddleocr python -c \
    "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8010/ready?deep=true', timeout=180).read().decode('utf-8'))"
)"
printf '%s' "$ready_json" | grep -Fq '"available":true'

COMPLETED=1
printf '%s\n' "OCR 进程隔离热修复已完成。"
printf '%s\n' "备份目录：$BACKUP_DIR"
printf '%s\n' "旧镜像标签：$PREVIOUS_IMAGE_TAG"
printf '%s\n' "新镜像标签：$NEW_IMAGE_TAG"
printf '%s\n' "新容器：$(dc ps -q paddleocr)"
