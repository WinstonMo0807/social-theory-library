#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/volume2/library/docker/social-theory-library}"
SOURCE_DIR="${SOURCE_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
EXPECTED_VERSION="2.2.2"
BACKUP_ROOT="${APP_DIR}/storage/backups"
BACKUP_DIR="${BACKUP_ROOT}/pre-offline-2.2.2-$(date +%Y%m%d-%H%M%S)"
API_BASE_TAG="social-theory-library-api-base:offline-2.2.1"
WEB_BASE_TAG="social-theory-library-web-base:offline-2.2.1"
API_TARGET_TAG="social-theory-library-api:${EXPECTED_VERSION}"
WEB_TARGET_TAG="social-theory-library-web:${EXPECTED_VERSION}"

fail() {
  printf '%s\n' "离线升级停止：$1" >&2
  exit 1
}

[ -d "$APP_DIR" ] || fail "找不到现有项目目录 $APP_DIR"
[ -f "$APP_DIR/.env" ] || fail "现有项目缺少 .env"
[ -f "$APP_DIR/compose.yaml" ] || fail "现有项目缺少 compose.yaml"
[ -f "$SOURCE_DIR/api/config/version.py" ] || fail "离线包缺少 API 版本文件"
[ -f "$SOURCE_DIR/web/package.json" ] || fail "离线包缺少 Web 版本文件"
[ -f "$SOURCE_DIR/web/dist/server/index.js" ] || fail "离线包缺少 Web 生产成品"
[ -f "$SOURCE_DIR/offline/api.Dockerfile" ] || fail "离线包缺少 API 叠加镜像定义"
[ -f "$SOURCE_DIR/offline/web.Dockerfile" ] || fail "离线包缺少 Web 叠加镜像定义"
[ "$APP_DIR" != "$SOURCE_DIR" ] || fail "离线包必须解压到现有项目目录以外"
grep -Fq "APP_VERSION = \"$EXPECTED_VERSION\"" "$SOURCE_DIR/api/config/version.py" \
  || fail "离线包 API 版本不是 $EXPECTED_VERSION"
grep -Fq "\"version\": \"$EXPECTED_VERSION\"" "$SOURCE_DIR/web/package.json" \
  || fail "离线包 Web 版本不是 $EXPECTED_VERSION"
command -v docker >/dev/null 2>&1 || fail "没有找到 Docker 命令"
docker compose version >/dev/null 2>&1 || fail "Docker Compose 不可用"

cd "$APP_DIR"
docker compose config --quiet

api_container="$(docker compose ps -q api)"
web_container="$(docker compose ps -q web)"
[ -n "$api_container" ] || fail "没有找到正在运行的 API 容器"
[ -n "$web_container" ] || fail "没有找到正在运行的 Web 容器"

api_base_image="$(docker inspect --format '{{.Image}}' "$api_container")"
web_base_image="$(docker inspect --format '{{.Image}}' "$web_container")"
[ -n "$api_base_image" ] || fail "无法读取 API 容器镜像"
[ -n "$web_base_image" ] || fail "无法读取 Web 容器镜像"
docker image inspect "$api_base_image" >/dev/null 2>&1 \
  || fail "API 基础镜像不在 NAS 本地"
docker image inspect "$web_base_image" >/dev/null 2>&1 \
  || fail "Web 基础镜像不在 NAS 本地"

docker image tag "$api_base_image" "$API_BASE_TAG"
docker image tag "$web_base_image" "$WEB_BASE_TAG"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
cp "$APP_DIR/.env" "$BACKUP_DIR/app.env"
chmod 600 "$BACKUP_DIR/app.env"

docker compose exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$BACKUP_DIR/database.sql"

tar \
  --exclude='./storage' \
  --exclude='./data' \
  --exclude='./.env' \
  -czf "$BACKUP_DIR/source-before-offline-upgrade.tar.gz" \
  .

cp -a "$SOURCE_DIR/api/." "$APP_DIR/api/"
cp -a "$SOURCE_DIR/web/." "$APP_DIR/web/"
cp -a "$SOURCE_DIR/scripts/." "$APP_DIR/scripts/"
cp -a "$SOURCE_DIR/docs/." "$APP_DIR/docs/"
mkdir -p "$APP_DIR/offline"
cp -a "$SOURCE_DIR/offline/." "$APP_DIR/offline/"
cp "$SOURCE_DIR/compose.yaml" "$APP_DIR/compose.yaml"
cp "$SOURCE_DIR/compose.nas.yaml" "$APP_DIR/compose.nas.yaml"
cp "$SOURCE_DIR/compose.public.yaml" "$APP_DIR/compose.public.yaml"

grep -Fq "APP_VERSION = \"$EXPECTED_VERSION\"" "$APP_DIR/api/config/version.py" \
  || fail "目标目录 API 源码没有更新到 $EXPECTED_VERSION"
grep -Fq "\"version\": \"$EXPECTED_VERSION\"" "$APP_DIR/web/package.json" \
  || fail "目标目录 Web 源码没有更新到 $EXPECTED_VERSION"

docker build \
  --pull=false \
  --network=none \
  --build-arg "BASE_IMAGE=$API_BASE_TAG" \
  -f "$SOURCE_DIR/offline/api.Dockerfile" \
  -t "$API_TARGET_TAG" \
  "$SOURCE_DIR"

docker build \
  --pull=false \
  --network=none \
  --build-arg "BASE_IMAGE=$WEB_BASE_TAG" \
  -f "$SOURCE_DIR/offline/web.Dockerfile" \
  -t "$WEB_TARGET_TAG" \
  "$SOURCE_DIR"

cd "$APP_DIR"
docker compose config --quiet
docker compose run --rm --no-deps api python manage.py migrate --noinput
docker compose up -d --no-deps --force-recreate api worker web

api_version="$(
  docker compose exec -T api \
    python -c 'from config.version import APP_VERSION; print(APP_VERSION)' \
    | tr -d '\r\n '
)"
worker_version="$(
  docker compose exec -T worker \
    python -c 'from config.version import APP_VERSION; print(APP_VERSION)' \
    | tr -d '\r\n '
)"
web_version="$(
  docker compose exec -T web \
    node -p "require('./package.json').version" \
    | tr -d '\r\n '
)"

[ "$api_version" = "$EXPECTED_VERSION" ] \
  || fail "API 容器仍为 $api_version，期望 $EXPECTED_VERSION"
[ "$worker_version" = "$EXPECTED_VERSION" ] \
  || fail "Worker 容器仍为 $worker_version，期望 $EXPECTED_VERSION"
[ "$web_version" = "$EXPECTED_VERSION" ] \
  || fail "Web 容器仍为 $web_version，期望 $EXPECTED_VERSION"

health_json=""
health_attempt=0
while [ "$health_attempt" -lt 30 ]; do
  if health_json="$(
    docker compose exec -T api \
      curl -fsS http://127.0.0.1:8000/api/health/ 2>/dev/null
  )"; then
    break
  fi
  health_attempt=$((health_attempt + 1))
  sleep 2
done

[ -n "$health_json" ] || fail "API 在 60 秒内没有通过健康检查"
printf '%s' "$health_json" \
  | grep -Eq '"version"[[:space:]]*:[[:space:]]*"2\.2\.2"' \
  || fail "健康接口没有返回版本 $EXPECTED_VERSION：$health_json"

printf '\n%s\n' "SCP 离线升级完成。"
printf '%s\n' "运行容器：API $api_version / Worker $worker_version / Web $web_version"
printf '%s\n' "容器内健康检查：$health_json"
printf '%s\n' "升级前备份：$BACKUP_DIR"
printf '%s\n' "本次没有访问 Docker Hub、npm 或 pip。"
