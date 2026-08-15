#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/volume2/library/docker/social-theory-library}"
SOURCE_DIR="${SOURCE_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
EXPECTED_VERSION="2.5.0"
BACKUP_ROOT="${APP_DIR}/storage/backups"
BACKUP_DIR="${BACKUP_ROOT}/pre-upgrade-${EXPECTED_VERSION}-$(date +%Y%m%d-%H%M%S)"
API_BASE_TAG="social-theory-library-api-base:offline-pre-${EXPECTED_VERSION}"
WEB_BASE_TAG="social-theory-library-web-base:offline-pre-${EXPECTED_VERSION}"
OCR_BASE_TAG="social-theory-library-ocr-base:offline-pre-${EXPECTED_VERSION}"
API_TARGET_TAG="social-theory-library-api:${EXPECTED_VERSION}"
WEB_TARGET_TAG="social-theory-library-web:${EXPECTED_VERSION}"
RUNTIME_ARCHIVE="${SOURCE_DIR}/offline/web-runtime-node-modules-2.5.0-linux-x64.tar.gz"
RUNTIME_SHA256="1872872d70aae057822e1cfe607c51274754957520c77ee170d6c3a3be79a4a2"

fail() {
  printf '%s\n' "离线升级停止：$1" >&2
  exit 1
}

wait_for_api() {
  attempt=0
  while [ "$attempt" -lt 60 ]; do
    if docker compose exec -T api curl -fsS http://127.0.0.1:8000/api/ready/ >/dev/null 2>&1; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done
  return 1
}

wait_for_web() {
  attempt=0
  while [ "$attempt" -lt 45 ]; do
    if docker compose exec -T web node -e \
      "fetch('http://127.0.0.1:3000/').then(r => { if (!r.ok) process.exit(1) }).catch(() => process.exit(1))" \
      >/dev/null 2>&1; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done
  return 1
}

wait_for_ocr() {
  attempt=0
  while [ "$attempt" -lt 60 ]; do
    if docker compose --profile ocr exec -T paddleocr python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3)" \
      >/dev/null 2>&1; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done
  return 1
}

[ -d "$APP_DIR" ] || fail "找不到现有项目目录 $APP_DIR"
[ -f "$APP_DIR/.env" ] || fail "现有项目缺少 .env"
[ -f "$APP_DIR/compose.yaml" ] || fail "现有项目缺少 compose.yaml"
[ -f "$SOURCE_DIR/api/config/version.py" ] || fail "离线包缺少 API 版本文件"
[ -f "$SOURCE_DIR/api/accounts/migrations/0003_user_token_version.py" ] \
  || fail "离线包缺少账户会话失效迁移"
[ -f "$SOURCE_DIR/api/catalog/migrations/0014_expand_theory_timeline_event_types.py" ] \
  || fail "离线包缺少理论系统迁移"
[ -f "$SOURCE_DIR/api/tests/test_admin_lifecycle_v250.py" ] \
  || fail "离线包缺少 2.5.0 生命周期回归测试"
[ -f "$SOURCE_DIR/web/package.json" ] || fail "离线包缺少 Web 版本文件"
[ -f "$SOURCE_DIR/web/dist/server/index.js" ] || fail "离线包缺少 Web 生产成品"
[ -f "$SOURCE_DIR/web/dist/client/runtime-config.js" ] || fail "离线包缺少运行时地址配置"
[ -f "$SOURCE_DIR/web/scripts/patch-vinext-static-paths.mjs" ] \
  || fail "离线包缺少 Vinext 静态资源路径修复"
[ -s "$RUNTIME_ARCHIVE" ] || fail "离线包缺少 Linux Web 运行依赖"
[ -f "$SOURCE_DIR/offline/api.Dockerfile" ] || fail "离线包缺少 API 叠加镜像定义"
[ -f "$SOURCE_DIR/offline/web.Dockerfile" ] || fail "离线包缺少 Web 叠加镜像定义"
[ -f "$SOURCE_DIR/offline/ocr.Dockerfile" ] || fail "离线包缺少 OCR 叠加镜像定义"
[ "$APP_DIR" != "$SOURCE_DIR" ] || fail "离线包必须解压到现有项目目录以外"
grep -Fq "APP_VERSION = \"$EXPECTED_VERSION\"" "$SOURCE_DIR/api/config/version.py" \
  || fail "离线包 API 版本不是 $EXPECTED_VERSION"
grep -Fq "\"version\": \"$EXPECTED_VERSION\"" "$SOURCE_DIR/web/package.json" \
  || fail "离线包 Web 版本不是 $EXPECTED_VERSION"
command -v docker >/dev/null 2>&1 || fail "没有找到 Docker 命令"
docker compose version >/dev/null 2>&1 || fail "Docker Compose 不可用"
command -v sha256sum >/dev/null 2>&1 || fail "NAS 缺少 sha256sum"
tar -tzf "$RUNTIME_ARCHIVE" >/dev/null 2>&1 || fail "Linux Web 运行依赖归档损坏"
runtime_sha256="$(sha256sum "$RUNTIME_ARCHIVE" | awk '{print $1}')"
[ "$runtime_sha256" = "$RUNTIME_SHA256" ] || fail "Linux Web 运行依赖校验失败"

cd "$APP_DIR"
docker compose config --quiet

api_container="$(docker compose ps -aq api)"
web_container="$(docker compose ps -aq web)"
[ -n "$api_container" ] || fail "没有找到现有 API 容器"
[ -n "$web_container" ] || fail "没有找到现有 Web 容器"

api_base_image="$(docker inspect --format '{{.Image}}' "$api_container")"
web_base_image="$(docker inspect --format '{{.Image}}' "$web_container")"
[ -n "$api_base_image" ] || fail "无法读取 API 容器镜像"
[ -n "$web_base_image" ] || fail "无法读取 Web 容器镜像"
docker image inspect "$api_base_image" >/dev/null 2>&1 || fail "API 基础镜像不在 NAS 本地"
docker image inspect "$web_base_image" >/dev/null 2>&1 || fail "Web 基础镜像不在 NAS 本地"
docker image tag "$api_base_image" "$API_BASE_TAG"
docker image tag "$web_base_image" "$WEB_BASE_TAG"

ocr_container="$(docker compose --profile ocr ps -aq paddleocr 2>/dev/null || true)"
ocr_target_image=""
ocr_base_image=""
if [ -n "$ocr_container" ]; then
  ocr_base_image="$(docker inspect --format '{{.Image}}' "$ocr_container")"
  ocr_target_image="$(docker inspect --format '{{.Config.Image}}' "$ocr_container")"
  [ -n "$ocr_base_image" ] || fail "无法读取 OCR 容器镜像"
  [ -n "$ocr_target_image" ] || fail "无法读取 OCR 镜像名称"
  docker image inspect "$ocr_base_image" >/dev/null 2>&1 || fail "OCR 基础镜像不在 NAS 本地"
  docker image tag "$ocr_base_image" "$OCR_BASE_TAG"
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
cp "$APP_DIR/.env" "$BACKUP_DIR/app.env"
chmod 600 "$BACKUP_DIR/app.env"
cat >"$BACKUP_DIR/images.env" <<EOF
API_IMAGE_ID=$api_base_image
WEB_IMAGE_ID=$web_base_image
OCR_IMAGE_ID=$ocr_base_image
API_ROLLBACK_TAG=$API_BASE_TAG
WEB_ROLLBACK_TAG=$WEB_BASE_TAG
OCR_ROLLBACK_TAG=$OCR_BASE_TAG
EOF
chmod 600 "$BACKUP_DIR/images.env"

docker compose exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$BACKUP_DIR/database.sql"
[ -s "$BACKUP_DIR/database.sql" ] || fail "数据库备份为空"

tar \
  --exclude='./storage' \
  --exclude='./data' \
  --exclude='./.env' \
  --exclude='./web/node_modules' \
  --exclude='./web/dist' \
  -czf "$BACKUP_DIR/source-before-${EXPECTED_VERSION}.tar.gz" \
  .

cp -a "$SOURCE_DIR/api/." "$APP_DIR/api/"
cp -a "$SOURCE_DIR/web/." "$APP_DIR/web/"
cp -a "$SOURCE_DIR/ocr_service/." "$APP_DIR/ocr_service/"
cp -a "$SOURCE_DIR/scripts/." "$APP_DIR/scripts/"
cp -a "$SOURCE_DIR/docs/." "$APP_DIR/docs/"
mkdir -p "$APP_DIR/deploy" "$APP_DIR/offline"
cp -a "$SOURCE_DIR/deploy/." "$APP_DIR/deploy/"
cp -a "$SOURCE_DIR/offline/." "$APP_DIR/offline/"
cp "$SOURCE_DIR/compose.yaml" "$APP_DIR/compose.yaml"
cp "$SOURCE_DIR/compose.nas.yaml" "$APP_DIR/compose.nas.yaml"
cp "$SOURCE_DIR/compose.public.yaml" "$APP_DIR/compose.public.yaml"
for sample in .env.example .env.lan.example .env.nas.example .env.nas-192.168.5.6.example .env.production.example; do
  if [ -f "$SOURCE_DIR/$sample" ]; then
    cp "$SOURCE_DIR/$sample" "$APP_DIR/$sample"
  fi
done

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

if [ -n "$ocr_target_image" ]; then
  docker build \
    --pull=false \
    --network=none \
    --build-arg "BASE_IMAGE=$OCR_BASE_TAG" \
    -f "$SOURCE_DIR/offline/ocr.Dockerfile" \
    -t "$ocr_target_image" \
    "$SOURCE_DIR"
fi

cd "$APP_DIR"
docker compose config --quiet
docker compose run --rm --no-deps api python manage.py migrate --noinput
docker compose up -d --no-deps --force-recreate api worker beat web
edge_container="$(docker compose ps -aq edge 2>/dev/null || true)"
if [ -n "$edge_container" ]; then
  docker compose up -d --no-deps --force-recreate edge
fi
if [ -n "$ocr_target_image" ]; then
  docker compose --profile ocr up -d --no-deps --force-recreate paddleocr
fi

wait_for_api || fail "API 在 120 秒内没有通过数据库和迁移就绪检查"
if ! wait_for_web; then
  docker compose logs --no-color --tail=100 web >&2 || true
  fail "Web 在 90 秒内没有启动，请查看上方日志"
fi
if [ -n "$ocr_target_image" ] && ! wait_for_ocr; then
  docker compose --profile ocr logs --no-color --tail=100 paddleocr >&2 || true
  fail "OCR 在 120 秒内没有启动，请查看上方日志"
fi

api_version="$(docker compose exec -T api python -c 'from config.version import APP_VERSION; print(APP_VERSION)' | tr -d '\r\n ')"
worker_version="$(docker compose exec -T worker python -c 'from config.version import APP_VERSION; print(APP_VERSION)' | tr -d '\r\n ')"
web_version="$(docker compose exec -T web node -p "require('./package.json').version" | tr -d '\r\n ')"
next_version="$(docker compose exec -T web node -p "require('./node_modules/next/package.json').version" | tr -d '\r\n ')"
react_version="$(docker compose exec -T web node -p "require('./node_modules/react/package.json').version" | tr -d '\r\n ')"
[ "$api_version" = "$EXPECTED_VERSION" ] || fail "API 容器仍为 $api_version"
[ "$worker_version" = "$EXPECTED_VERSION" ] || fail "Worker 容器仍为 $worker_version"
[ "$web_version" = "$EXPECTED_VERSION" ] || fail "Web 容器仍为 $web_version"
[ "$next_version" = "16.2.12" ] || fail "Web 容器 Next 版本不正确：$next_version"
[ "$react_version" = "19.2.8" ] || fail "Web 容器 React 版本不正确：$react_version"
docker compose exec -T web node_modules/@esbuild/linux-x64/bin/esbuild --version >/dev/null \
  || fail "Web 容器的 Linux 原生运行依赖不可执行"

ready_json="$(docker compose exec -T api curl -fsS http://127.0.0.1:8000/api/ready/)" \
  || fail "就绪接口不可用"
health_json="$(docker compose exec -T api curl -fsS http://127.0.0.1:8000/api/health/)" \
  || fail "健康接口不可用"
printf '%s' "$health_json" | grep -Eq '"version"[[:space:]]*:[[:space:]]*"2\.5\.0"' \
  || fail "健康接口版本不正确：$health_json"

pending_migrations="$(docker compose exec -T api python manage.py showmigrations --plan | grep '\[ \]' || true)"
[ -z "$pending_migrations" ] || fail "仍有未执行迁移：$pending_migrations"

overview_json="$(docker compose exec -T api curl -fsS http://127.0.0.1:8000/api/catalog/theory-system/overview/)" \
  || fail "理论系统公开接口不可用"
printf '%s' "$overview_json" | grep -Fq 'disciplines' || fail "理论系统首页接口缺少学科数据"

docker compose exec -T web sh -c 'test -s /app/dist/client/runtime-config.js' \
  || fail "Web 容器没有运行时 API 地址配置"
docker compose exec -T web sh -c 'test -w /app/dist/client' \
  || fail "Web 运行用户不能写入运行时配置目录"
for forbidden in 'http://localhost:8000/api' '192.168.5.6' 'postgres:5432' 'redis:6379' 'meilisearch:7700'; do
  if docker compose exec -T web sh -c "grep -R -F '$forbidden' /app/dist/client/assets >/dev/null 2>&1"; then
    fail "浏览器脚本包含不应公开的地址：$forbidden"
  fi
done

public_asset_id="$(docker compose exec -T api python -c \
  'import os; os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings"); import django; django.setup(); from catalog.models import Asset, PublicationState; print(Asset.objects.filter(kind=Asset.Kind.NORMALIZED, status=Asset.Status.READY, edition__state=PublicationState.PUBLISHED, is_current=True).values_list("id", flat=True).first() or "")' \
  | tr -d '\r\n ')"
if [ -n "$public_asset_id" ]; then
  access_json="$(docker compose exec -T api curl -fsS "http://127.0.0.1:8000/api/distribution/assets/$public_asset_id/access/")" \
    || fail "公开 PDF 授权接口不可用"
  printf '%s' "$access_json" | grep -Fq '"url"' || fail "公开 PDF 授权接口没有返回阅读地址"
fi

printf '\n%s\n' "2.5.0 离线升级完成。"
printf '%s\n' "运行版本：API $api_version / Worker $worker_version / Web $web_version"
printf '%s\n' "Web 依赖：Next $next_version / React $react_version"
printf '%s\n' "就绪检查：$ready_json"
if [ -n "$ocr_target_image" ]; then
  ocr_model_home="$(docker compose --profile ocr exec -T paddleocr sh -c 'printf %s "$PADDLE_HOME"' | tr -d '\r\n')"
  printf '%s\n' "OCR 模型目录：$ocr_model_home"
fi
printf '%s\n' "升级前备份：$BACKUP_DIR"
printf '%s\n' "回退镜像标签：$API_BASE_TAG / $WEB_BASE_TAG / $OCR_BASE_TAG"
printf '%s\n' "本次构建没有访问 Docker Hub、npm、pip 或 Hugging Face。"
printf '%s\n' "请按 docs/nas-offline-upgrade-2.5.0.md 完成局域网验收。公网开放仍须另行完成域名、证书和外部访问验收。"
