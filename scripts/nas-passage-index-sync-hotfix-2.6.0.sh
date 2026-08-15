#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/volume2/library/docker/social-theory-library}"
PROJECT_NAME="${PROJECT_NAME:-social-science-library}"
PAYLOAD_DIR="${PAYLOAD_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}"
EXPECTED_INDEXING_SHA="04b5790ce9b8b20446a1e634aadffd7e7f66cbfbf919a121d93d8976d6979641"
EXPECTED_TEST_SHA="de56ba106c678823719da98b01353a270e3ce9aa72e06005475380351b64bf37"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$APP_DIR/storage/backups/pre-passage-index-sync-hotfix-2.6.0-$STAMP"
PREVIOUS_IMAGE_TAG="social-theory-library-api:pre-r39-$STAMP"
NEW_IMAGE_TAG="social-theory-library-api:r39-$STAMP"
PATCH_CONTAINER="library-api-r39-build-$STAMP"
ROLLBACK_READY=0
COMPLETED=0

dc() {
  sudo -n docker compose \
    --env-file "$APP_DIR/.env" \
    -p "$PROJECT_NAME" \
    -f "$APP_DIR/compose.public.yaml" \
    -f "$APP_DIR/compose.cloudflare.yaml" \
    "$@"
}

rollback_on_error() {
  status="$?"
  trap - EXIT HUP INT TERM
  if [ -n "$PATCH_CONTAINER" ]; then
    sudo -n docker rm -f "$PATCH_CONTAINER" >/dev/null 2>&1 || true
  fi
  if [ "$status" -ne 0 ] && [ "$ROLLBACK_READY" -eq 1 ] && [ "$COMPLETED" -eq 0 ]; then
    printf '%s\n' "全文索引同步热修复失败，正在恢复旧源码和旧 API 镜像。" >&2
    sudo -n cp -a "$BACKUP_DIR/indexing.py" "$APP_DIR/api/ingestion/services/indexing.py" || true
    sudo -n docker tag "$PREVIOUS_IMAGE_TAG" "$previous_image_ref" || true
    dc up -d --no-build --pull never --no-deps --force-recreate api || true
  fi
  exit "$status"
}
trap rollback_on_error EXIT HUP INT TERM

test -d "$APP_DIR"
test -f "$APP_DIR/.env"
test -f "$APP_DIR/compose.public.yaml"
test -f "$APP_DIR/compose.cloudflare.yaml"
test -f "$APP_DIR/api/ingestion/services/indexing.py"
test -f "$PAYLOAD_DIR/api/ingestion/services/indexing.py"
test -f "$PAYLOAD_DIR/api/tests/test_passage_index_synchronization.py"

printf '%s  %s\n' "$EXPECTED_INDEXING_SHA" "$PAYLOAD_DIR/api/ingestion/services/indexing.py" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_TEST_SHA" "$PAYLOAD_DIR/api/tests/test_passage_index_synchronization.py" | sha256sum -c -

api_container_id="$(dc ps -q api)"
test -n "$api_container_id"
previous_image_id="$(sudo -n docker inspect --format '{{.Image}}' "$api_container_id")"
previous_image_ref="$(sudo -n docker inspect --format '{{.Config.Image}}' "$api_container_id")"
test -n "$previous_image_id"
test -n "$previous_image_ref"
case "$previous_image_ref" in *@*) printf '%s\n' "API 镜像使用 digest，无法安全覆盖标签。" >&2; exit 1;; esac

sudo -n mkdir -p "$BACKUP_DIR"
sudo -n cp -a "$APP_DIR/api/ingestion/services/indexing.py" "$BACKUP_DIR/indexing.py"
printf '%s\n' "$previous_image_id" | sudo -n tee "$BACKUP_DIR/api-image-id.txt" >/dev/null
printf '%s\n' "$previous_image_ref" | sudo -n tee "$BACKUP_DIR/api-image-ref.txt" >/dev/null
printf '%s\n' "$PREVIOUS_IMAGE_TAG" | sudo -n tee "$BACKUP_DIR/api-image-rollback-tag.txt" >/dev/null
sudo -n docker tag "$previous_image_id" "$PREVIOUS_IMAGE_TAG"
ROLLBACK_READY=1

sudo -n install -m 0644 "$PAYLOAD_DIR/api/ingestion/services/indexing.py" "$APP_DIR/api/ingestion/services/indexing.py"

sudo -n docker create --name "$PATCH_CONTAINER" "$previous_image_id" >/dev/null
sudo -n docker cp "$PAYLOAD_DIR/api/ingestion/services/indexing.py" "$PATCH_CONTAINER:/app/ingestion/services/indexing.py"
sudo -n docker cp "$PAYLOAD_DIR/api/tests/test_passage_index_synchronization.py" "$PATCH_CONTAINER:/app/tests/test_passage_index_synchronization.py"
new_image_id="$(sudo -n docker commit --pause=true "$PATCH_CONTAINER" "$NEW_IMAGE_TAG")"
test -n "$new_image_id"
sudo -n docker rm "$PATCH_CONTAINER" >/dev/null
PATCH_CONTAINER=""
sudo -n docker tag "$new_image_id" "$previous_image_ref"

sudo -n docker run --rm "$NEW_IMAGE_TAG" \
  python -m py_compile \
  ingestion/services/indexing.py \
  tests/test_passage_index_synchronization.py
sudo -n docker run --rm "$NEW_IMAGE_TAG" \
  python -m pytest tests/test_passage_index_synchronization.py -q

dc up -d --no-build --pull never --no-deps --force-recreate api
attempt=0
state=""
while [ "$attempt" -lt 60 ]; do
  attempt=$((attempt + 1))
  api_container_id="$(dc ps -q api)"
  state="$(sudo -n docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$api_container_id" 2>/dev/null || true)"
  [ "$state" = "healthy" ] && break
  sleep 2
done
[ "$state" = "healthy" ]
dc exec -T api python manage.py check
dc exec -T api python manage.py makemigrations --check --dry-run

COMPLETED=1
printf '%s\n' "全文索引同步热修复已完成。"
printf '%s\n' "备份目录：$BACKUP_DIR"
printf '%s\n' "旧镜像标签：$PREVIOUS_IMAGE_TAG"
printf '%s\n' "新镜像标签：$NEW_IMAGE_TAG"
printf '%s\n' "API 容器：$(dc ps -q api)"
