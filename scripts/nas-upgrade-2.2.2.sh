#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/volume2/library/docker/social-theory-library}"
SOURCE_DIR="${SOURCE_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
BACKUP_ROOT="${APP_DIR}/storage/backups"
BACKUP_DIR="${BACKUP_ROOT}/pre-2.2.2-$(date +%Y%m%d-%H%M%S)"
EXPECTED_VERSION="2.2.2"

fail() {
  printf '%s\n' "升级停止：$1" >&2
  exit 1
}

[ -d "$APP_DIR" ] || fail "找不到现有项目目录 $APP_DIR"
[ -f "$APP_DIR/.env" ] || fail "现有项目缺少 .env"
[ -f "$APP_DIR/compose.yaml" ] || fail "现有项目缺少 compose.yaml"
[ -f "$SOURCE_DIR/compose.yaml" ] || fail "升级包缺少 compose.yaml"
[ -f "$SOURCE_DIR/api/catalog/migrations/0007_shared_media_paths.py" ] || fail "升级包缺少 2.2.2 数据迁移"
[ -f "$SOURCE_DIR/api/config/version.py" ] || fail "升级包缺少 API 版本文件"
[ -f "$SOURCE_DIR/web/package.json" ] || fail "升级包缺少 Web 版本文件"
[ -f "$SOURCE_DIR/web/components/admin-shell.tsx" ] || fail "升级包缺少后台界面文件"
grep -Fq "APP_VERSION = \"$EXPECTED_VERSION\"" "$SOURCE_DIR/api/config/version.py" \
  || fail "升级包 API 版本不是 $EXPECTED_VERSION"
grep -Fq "\"version\": \"$EXPECTED_VERSION\"" "$SOURCE_DIR/web/package.json" \
  || fail "升级包 Web 版本不是 $EXPECTED_VERSION"
grep -Fq "v$EXPECTED_VERSION 局域网测试版" "$SOURCE_DIR/web/components/admin-shell.tsx" \
  || fail "升级包后台页脚版本不是 $EXPECTED_VERSION"
[ "$APP_DIR" != "$SOURCE_DIR" ] || fail "升级包必须解压到现有项目目录以外"
command -v docker >/dev/null 2>&1 || fail "没有找到 Docker 命令"
docker compose version >/dev/null 2>&1 || fail "Docker Compose 不可用"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
cp "$APP_DIR/.env" "$BACKUP_DIR/app.env"
chmod 600 "$BACKUP_DIR/app.env"

cd "$APP_DIR"
docker compose config --quiet
docker compose exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$BACKUP_DIR/database.sql"

tar \
  --exclude='./storage' \
  --exclude='./data' \
  --exclude='./.env' \
  -czf "$BACKUP_DIR/source-before-upgrade.tar.gz" \
  .

cp -a "$SOURCE_DIR/api/." "$APP_DIR/api/"
cp -a "$SOURCE_DIR/web/." "$APP_DIR/web/"
cp -a "$SOURCE_DIR/ocr_service/." "$APP_DIR/ocr_service/"
cp -a "$SOURCE_DIR/scripts/." "$APP_DIR/scripts/"
cp -a "$SOURCE_DIR/docs/." "$APP_DIR/docs/"
cp "$SOURCE_DIR/compose.yaml" "$APP_DIR/compose.yaml"
cp "$SOURCE_DIR/compose.nas.yaml" "$APP_DIR/compose.nas.yaml"
cp "$SOURCE_DIR/compose.public.yaml" "$APP_DIR/compose.public.yaml"

grep -Fq "APP_VERSION = \"$EXPECTED_VERSION\"" "$APP_DIR/api/config/version.py" \
  || fail "目标目录 API 源码没有更新到 $EXPECTED_VERSION"
grep -Fq "\"version\": \"$EXPECTED_VERSION\"" "$APP_DIR/web/package.json" \
  || fail "目标目录 Web 源码没有更新到 $EXPECTED_VERSION"
grep -Fq "v$EXPECTED_VERSION 局域网测试版" "$APP_DIR/web/components/admin-shell.tsx" \
  || fail "目标目录后台页脚没有更新到 $EXPECTED_VERSION"

cd "$APP_DIR"
docker compose config --quiet
if [ "${FORCE_NO_CACHE:-0}" = "1" ]; then
  docker compose build --no-cache api worker web
else
  docker compose build api worker web
fi
docker compose run --rm api python manage.py migrate --noinput
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

printf '\n%s\n' "2.2.2 升级命令已完成。备份位于：$BACKUP_DIR"
printf '%s\n' "目标源码：API $EXPECTED_VERSION / Web $EXPECTED_VERSION"
printf '%s\n' "运行容器：API $api_version / Worker $worker_version / Web $web_version"
printf '%s\n' "容器内健康检查：$health_json"
printf '%s\n' "请继续执行："
printf '%s\n' "  curl -fsS http://127.0.0.1:18081/api/health/"
printf '%s\n' "  docker compose exec -T api python manage.py showmigrations catalog"
printf '%s\n' "  docker compose ps"
printf '%s\n' "  docker compose logs --tail=200 api worker web"
