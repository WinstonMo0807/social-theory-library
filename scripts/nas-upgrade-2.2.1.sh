#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/volume2/library/social-theory-library}"
SOURCE_DIR="${SOURCE_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
BACKUP_ROOT="${APP_DIR}/storage/backups"
BACKUP_DIR="${BACKUP_ROOT}/pre-2.2.1-$(date +%Y%m%d-%H%M%S)"

fail() {
  printf '%s\n' "升级停止：$1" >&2
  exit 1
}

[ -d "$APP_DIR" ] || fail "找不到现有项目目录 $APP_DIR"
[ -f "$APP_DIR/.env" ] || fail "现有项目缺少 .env"
[ -f "$APP_DIR/compose.yaml" ] || fail "现有项目缺少 compose.yaml"
[ -f "$SOURCE_DIR/compose.yaml" ] || fail "升级包缺少 compose.yaml"
[ -f "$SOURCE_DIR/api/catalog/migrations/0006_covercandidate.py" ] || fail "升级包缺少 2.2.1 数据迁移"
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

cd "$APP_DIR"
docker compose config --quiet
docker compose build api worker web
docker compose run --rm api python manage.py migrate --noinput
docker compose up -d --no-deps api worker web

printf '\n%s\n' "升级命令已完成。备份位于：$BACKUP_DIR"
printf '%s\n' "请继续执行："
printf '%s\n' "  curl http://127.0.0.1:18081/api/health/"
printf '%s\n' "  docker compose exec -T api python manage.py showmigrations catalog"
printf '%s\n' "  docker compose ps"
printf '%s\n' "  docker compose logs --tail=200 api worker web"
