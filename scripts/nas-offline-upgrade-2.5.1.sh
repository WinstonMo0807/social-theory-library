#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/volume2/library/docker/social-theory-library}"
SOURCE_DIR="${SOURCE_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
EXPECTED_VERSION="${EXPECTED_VERSION:-2.5.1}"
PREWARM_SEMANTIC_MODEL="${PREWARM_SEMANTIC_MODEL:-0}"
VERIFY_INGESTION_ITEM_ID="${VERIFY_INGESTION_ITEM_ID:-}"
VERIFY_INGESTION_SOURCE_FILENAME="${VERIFY_INGESTION_SOURCE_FILENAME:-}"
REQUESTED_STACK_MODE="${STACK_MODE:-auto}"
VERIFY_PUBLIC_ENDPOINT="${VERIFY_PUBLIC_ENDPOINT:-1}"
MIGRATE_LEGACY_CLOUDFLARED="${MIGRATE_LEGACY_CLOUDFLARED:-1}"
STOPPED_LEGACY_CLOUDFLARED=""
BACKUP_ROOT="${APP_DIR}/storage/backups"
BACKUP_DIR="${BACKUP_ROOT}/pre-upgrade-${EXPECTED_VERSION}-$(date +%Y%m%d-%H%M%S)"
API_BASE_TAG="social-theory-library-api-base:offline-pre-${EXPECTED_VERSION}"
WEB_BASE_TAG="social-theory-library-web-base:offline-pre-${EXPECTED_VERSION}"
OCR_BASE_TAG="social-theory-library-ocr-base:offline-pre-${EXPECTED_VERSION}"
RUNTIME_ARCHIVE="${SOURCE_DIR}/offline/web-runtime-node-modules-2.5.0-linux-x64.tar.gz"
RUNTIME_SHA256="1872872d70aae057822e1cfe607c51274754957520c77ee170d6c3a3be79a4a2"

fail() {
  printf '%s\n' "离线升级停止：$1" >&2
  if [ -n "$STOPPED_LEGACY_CLOUDFLARED" ] && command -v docker >/dev/null 2>&1; then
    docker start "$STOPPED_LEGACY_CLOUDFLARED" >/dev/null 2>&1 || true
    printf '%s\n' "已尝试恢复升级前的旧 Cloudflare Tunnel 容器。" >&2
  fi
  exit 1
}

read_env_value() {
  env_key="$1"
  env_file="$2"
  awk -v key="$env_key" '
    index($0, key "=") == 1 {
      value = substr($0, length(key) + 2)
      sub(/\r$/, "", value)
      found = value
    }
    END { print found }
  ' "$env_file"
}

normalize_env_file() {
  env_file="$1"
  env_tmp="${BACKUP_DIR}/.env.normalized.tmp"
  awk '
    {
      source[NR] = $0
      key = ""
      if ($0 ~ /^[A-Za-z_][A-Za-z0-9_]*=/) {
        key = substr($0, 1, index($0, "=") - 1)
        line_key[NR] = key
        last[key] = NR
      }
    }
    END {
      for (line_number = 1; line_number <= NR; line_number++) {
        key = line_key[line_number]
        if (key == "" || last[key] == line_number) print source[line_number]
      }
    }
  ' "$env_file" > "$env_tmp"
  cat "$env_tmp" > "$env_file"
  rm -f "$env_tmp"
}

require_secret_env() {
  env_key="$1"
  env_file="$2"
  min_length="${3:-16}"
  env_value="$(read_env_value "$env_key" "$env_file")"
  [ -n "$env_value" ] || fail ".env 缺少 $env_key"
  case "$env_value" in
    replace-*|change-*|example*|library.example.org)
      fail ".env 中的 $env_key 仍是示例值"
      ;;
  esac
  [ "${#env_value}" -ge "$min_length" ] \
    || fail ".env 中的 $env_key 长度不足"
}

image_repository() {
  image_name="$1"
  without_digest="${image_name%@*}"
  last_component="${without_digest##*/}"
  case "$last_component" in
    *:*) printf '%s\n' "${without_digest%:*}" ;;
    *) printf '%s\n' "$without_digest" ;;
  esac
}

upsert_env() {
  env_key="$1"
  env_value="$2"
  env_file="$3"
  env_tmp="${BACKUP_DIR}/.${env_key}.tmp"
  awk -v key="$env_key" -v value="$env_value" '
    BEGIN { found = 0 }
    index($0, key "=") == 1 {
      if (!found) print key "=" value
      found = 1
      next
    }
    { print }
    END { if (!found) print key "=" value }
  ' "$env_file" > "$env_tmp"
  cat "$env_tmp" > "$env_file"
  rm -f "$env_tmp"
}

dc() {
  if [ "$STACK_MODE" = "public-cloudflare" ]; then
    docker compose --env-file "$APP_DIR/.env" -p "$COMPOSE_PROJECT_NAME" \
      -f "$APP_DIR/compose.public.yaml" \
      -f "$APP_DIR/compose.cloudflare.yaml" "$@"
  else
    docker compose --env-file "$APP_DIR/.env" -p "$COMPOSE_PROJECT_NAME" \
      -f "$APP_DIR/compose.yaml" "$@"
  fi
}

api_curl() {
  if [ "$STACK_MODE" = "public-cloudflare" ]; then
    dc exec -T api curl -fsS -H 'X-Forwarded-Proto: https' "$@"
  else
    dc exec -T api curl -fsS "$@"
  fi
}

wait_for_healthy_service() {
  service_name="$1"
  attempt=0
  while [ "$attempt" -lt 60 ]; do
    container_id="$(dc ps -q "$service_name" 2>/dev/null || true)"
    if [ -n "$container_id" ]; then
      health_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
      case "$health_status" in
        healthy|running) return 0 ;;
      esac
    fi
    attempt=$((attempt + 1))
    sleep 2
  done
  return 1
}

wait_for_api() {
  attempt=0
  while [ "$attempt" -lt 60 ]; do
    if api_curl http://127.0.0.1:8000/api/ready/ >/dev/null 2>&1; then
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
    if dc exec -T web node -e \
      "fetch('http://127.0.0.1:3000/', { signal: AbortSignal.timeout(5000) }).then(r => { if (!r.ok) process.exit(1) }).catch(() => process.exit(1))" \
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
    if dc --profile ocr exec -T paddleocr python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3)" \
      >/dev/null 2>&1; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done
  return 1
}

wait_for_url_version() {
  target_url="$1"
  expected_version="$2"
  attempts="${3:-45}"
  connection_scope="${4:-public}"
  attempt=0
  while [ "$attempt" -lt "$attempts" ]; do
    if [ "$connection_scope" = "lan" ]; then
      response="$(curl --noproxy '*' -fsS --connect-timeout 5 --max-time 20 "$target_url" 2>/dev/null || true)"
    else
      response="$(curl -fsS --connect-timeout 5 --max-time 20 "$target_url" 2>/dev/null || true)"
    fi
    if printf '%s' "$response" | grep -Fq "\"version\":\"$expected_version\"" \
      || printf '%s' "$response" | grep -Fq "\"version\": \"$expected_version\""; then
      printf '%s\n' "$response"
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done
  return 1
}

require_edge_binding() {
  edge_container_id="$1"
  bind_ip="$2"
  bind_port="$3"
  bindings="$(docker port "$edge_container_id" 80/tcp 2>/dev/null || true)"
  printf '%s\n' "$bindings" | grep -Fxq "$bind_ip:$bind_port" \
    || fail "局域网入口没有监听 $bind_ip:$bind_port"
}

require_container_network() {
  container_id="$1"
  network_name="$2"
  networks="$(docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$container_id" 2>/dev/null || true)"
  printf '%s\n' "$networks" | grep -Fxq "$network_name" \
    || fail "容器 $(docker inspect --format '{{.Name}}' "$container_id" 2>/dev/null || true) 未连接 $network_name"
}

[ -d "$APP_DIR" ] || fail "找不到现有项目目录 $APP_DIR"
[ -f "$APP_DIR/.env" ] || fail "现有项目缺少 .env"
[ -f "$APP_DIR/compose.yaml" ] || fail "现有项目缺少 compose.yaml"
[ -f "$SOURCE_DIR/api/config/version.py" ] || fail "离线包缺少 API 版本文件"
[ -f "$SOURCE_DIR/api/accounts/migrations/0003_user_token_version.py" ] \
  || fail "离线包缺少账户会话失效迁移"
[ -f "$SOURCE_DIR/api/ingestion/migrations/0006_uploaditem_dispatch_state.py" ] \
  || fail "离线包缺少持久化任务派发迁移"
[ -f "$SOURCE_DIR/api/ingestion/management/commands/check_library_pipeline.py" ] \
  || fail "离线包缺少后台处理健康检查"
[ -f "$SOURCE_DIR/api/ingestion/management/commands/verify_ingestion_item.py" ] \
  || fail "离线包缺少单份 PDF 入库核验命令"
[ -f "$SOURCE_DIR/scripts/verify_public_lan_item.py" ] \
  || fail "离线包缺少公网与内网一致性验收脚本"
[ -f "$SOURCE_DIR/api/catalog/management/commands/prewarm_semantic_model.py" ] \
  || fail "离线包缺少语义模型预热命令"
[ -f "$SOURCE_DIR/api/catalog/migrations/0014_expand_theory_timeline_event_types.py" ] \
  || fail "离线包缺少理论系统迁移"
[ -f "$SOURCE_DIR/api/tests/test_admin_lifecycle_v250.py" ] \
  || fail "离线包缺少后台生命周期回归测试"
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
command -v curl >/dev/null 2>&1 || fail "NAS 缺少 curl"
tar -tzf "$RUNTIME_ARCHIVE" >/dev/null 2>&1 || fail "Linux Web 运行依赖归档损坏"
runtime_sha256="$(sha256sum "$RUNTIME_ARCHIVE" | awk '{print $1}')"

# Keep the untouched environment before removing duplicate keys. Compose uses
# the last duplicate, while previous upgrade scripts read the first one.
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
cp "$APP_DIR/.env" "$BACKUP_DIR/app.env.original"
chmod 600 "$BACKUP_DIR/app.env.original"
normalize_env_file "$APP_DIR/.env"
[ "$runtime_sha256" = "$RUNTIME_SHA256" ] || fail "Linux Web 运行依赖校验失败"

cd "$APP_DIR"

# 先从正在运行的 API 容器读取 Compose 项目，避免升级时创建第二套数据库和服务。
api_container=""
fallback_api_container=""
api_candidate_count=0
for candidate in $(docker ps -aq --filter label=com.docker.compose.service=api); do
  api_candidate_count=$((api_candidate_count + 1))
  fallback_api_container="$candidate"
  candidate_dir="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$candidate" 2>/dev/null || true)"
  if [ "$candidate_dir" = "$APP_DIR" ]; then
    api_container="$candidate"
    break
  fi
done
if [ -z "$api_container" ] && [ "$api_candidate_count" -eq 1 ]; then
  api_container="$fallback_api_container"
fi
[ "$api_candidate_count" -le 1 ] || [ -n "$api_container" ] \
  || fail "发现多个 API 容器，但没有一个属于 $APP_DIR，请先确认实际项目目录"
[ -n "$api_container" ] || fail "没有找到现有 API 容器"

COMPOSE_PROJECT_NAME="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$api_container")"
[ -n "$COMPOSE_PROJECT_NAME" ] || fail "无法读取现有 Compose 项目名"

case "$REQUESTED_STACK_MODE" in
  auto|lan|public-cloudflare) ;;
  *) fail "STACK_MODE 只能是 auto、lan 或 public-cloudflare" ;;
esac

STACK_MODE="$REQUESTED_STACK_MODE"
if [ "$STACK_MODE" = "auto" ]; then
  STACK_MODE="lan"
  for candidate in $(docker ps -aq --filter label=com.docker.compose.service=cloudflared); do
    candidate_project="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$candidate" 2>/dev/null || true)"
    if [ "$candidate_project" = "$COMPOSE_PROJECT_NAME" ]; then
      STACK_MODE="public-cloudflare"
      break
    fi
  done
  if [ "$STACK_MODE" = "lan" ]; then
    for candidate in $(docker ps -aq --filter name=cloudflared-library); do
      candidate_name="$(docker inspect --format '{{.Name}}' "$candidate" 2>/dev/null || true)"
      if [ "$candidate_name" = "/cloudflared-library" ]; then
        STACK_MODE="public-cloudflare"
        break
      fi
    done
  fi
  if [ "$STACK_MODE" = "lan" ]; then
    configured_tunnel_token="$(read_env_value CLOUDFLARE_TUNNEL_TOKEN "$APP_DIR/.env")"
    case "$configured_tunnel_token" in
      ""|replace-*|change-*|example*) ;;
      *) STACK_MODE="public-cloudflare" ;;
    esac
  fi
fi

if [ "$STACK_MODE" = "public-cloudflare" ]; then
  [ -f "$APP_DIR/compose.public.yaml" ] || fail "公网项目缺少 compose.public.yaml"
  [ -f "$APP_DIR/compose.cloudflare.yaml" ] || fail "公网项目缺少 compose.cloudflare.yaml"
  require_secret_env LIBRARY_DOMAIN "$APP_DIR/.env" 4
  require_secret_env CLOUDFLARE_TUNNEL_TOKEN "$APP_DIR/.env" 20
  require_secret_env LAN_PROXY_TOKEN "$APP_DIR/.env" 32
  require_secret_env INTERNAL_API_TOKEN "$APP_DIR/.env" 32
  require_secret_env DJANGO_SECRET_KEY "$APP_DIR/.env" 32
  require_secret_env POSTGRES_PASSWORD "$APP_DIR/.env" 16
  require_secret_env REDIS_PASSWORD "$APP_DIR/.env" 16
  require_secret_env MEILISEARCH_MASTER_KEY "$APP_DIR/.env" 16
  library_domain="$(read_env_value LIBRARY_DOMAIN "$APP_DIR/.env")"
  case "$library_domain" in
    http://*|https://*|*/*|*:*|localhost|127.*)
      fail ".env 中的 LIBRARY_DOMAIN 只能填写公网域名，不能包含协议、路径或端口"
      ;;
  esac
  edge_bind_ip="$(read_env_value EDGE_BIND_IP "$APP_DIR/.env")"
  lan_host="$(read_env_value LAN_HOST "$APP_DIR/.env")"
  [ -n "$edge_bind_ip" ] || fail ".env 缺少 EDGE_BIND_IP"
  [ -n "$lan_host" ] || fail ".env 缺少 LAN_HOST"
  case "$edge_bind_ip" in
    0.0.0.0|::|"[::]") fail "公网模式不允许把局域网管理入口绑定到所有网卡" ;;
  esac
  [ "$edge_bind_ip" = "$lan_host" ] \
    || fail "EDGE_BIND_IP 与 LAN_HOST 不一致，局域网登录标记将无法可靠生效"
fi

dc config --quiet
configured_services="$(dc config --services)"
for required_service in postgres redis meilisearch api worker beat web edge; do
  printf '%s\n' "$configured_services" | grep -Fxq "$required_service" \
    || fail "当前运行模式缺少 $required_service 服务"
done
if [ "$STACK_MODE" = "public-cloudflare" ]; then
  printf '%s\n' "$configured_services" | grep -Fxq cloudflared \
    || fail "公网运行模式缺少 cloudflared 服务"
fi
api_container="$(dc ps -aq api)"
web_container="$(dc ps -aq web)"
[ -n "$api_container" ] || fail "当前 Compose 项目没有 API 容器"
[ -n "$web_container" ] || fail "当前 Compose 项目没有 Web 容器"

api_base_image="$(docker inspect --format '{{.Image}}' "$api_container")"
web_base_image="$(docker inspect --format '{{.Image}}' "$web_container")"
api_configured_image="$(docker inspect --format '{{.Config.Image}}' "$api_container")"
web_configured_image="$(docker inspect --format '{{.Config.Image}}' "$web_container")"
[ -n "$api_base_image" ] || fail "无法读取 API 容器镜像"
[ -n "$web_base_image" ] || fail "无法读取 Web 容器镜像"
[ -n "$api_configured_image" ] || fail "无法读取 API 镜像名称"
[ -n "$web_configured_image" ] || fail "无法读取 Web 镜像名称"
case "$api_configured_image" in sha256:*) fail "API 容器没有可复用的镜像仓库名" ;; esac
case "$web_configured_image" in sha256:*) fail "Web 容器没有可复用的镜像仓库名" ;; esac
docker image inspect "$api_base_image" >/dev/null 2>&1 || fail "API 基础镜像不在 NAS 本地"
docker image inspect "$web_base_image" >/dev/null 2>&1 || fail "Web 基础镜像不在 NAS 本地"

API_TARGET_TAG="$(image_repository "$api_configured_image"):${EXPECTED_VERSION}"
WEB_TARGET_TAG="$(image_repository "$web_configured_image"):${EXPECTED_VERSION}"
docker image tag "$api_base_image" "$API_BASE_TAG"
docker image tag "$web_base_image" "$WEB_BASE_TAG"

ocr_container="$(dc --profile ocr ps -aq paddleocr 2>/dev/null || true)"
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

LEGACY_CLOUDFLARED_CONTAINER=""
if [ "$STACK_MODE" = "public-cloudflare" ]; then
  for candidate in $(docker ps -q --filter name=cloudflared-library); do
    candidate_name="$(docker inspect --format '{{.Name}}' "$candidate" 2>/dev/null || true)"
    candidate_project="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$candidate" 2>/dev/null || true)"
    if [ "$candidate_name" = "/cloudflared-library" ] && [ "$candidate_project" != "$COMPOSE_PROJECT_NAME" ]; then
      LEGACY_CLOUDFLARED_CONTAINER="$candidate"
      break
    fi
  done
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
cp "$APP_DIR/.env" "$BACKUP_DIR/app.env"
chmod 600 "$BACKUP_DIR/app.env"
cat >"$BACKUP_DIR/images.env" <<EOF
STACK_MODE=$STACK_MODE
COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME
API_IMAGE_ID=$api_base_image
WEB_IMAGE_ID=$web_base_image
OCR_IMAGE_ID=$ocr_base_image
API_CONFIGURED_IMAGE=$api_configured_image
WEB_CONFIGURED_IMAGE=$web_configured_image
API_TARGET_TAG=$API_TARGET_TAG
WEB_TARGET_TAG=$WEB_TARGET_TAG
API_ROLLBACK_TAG=$API_BASE_TAG
WEB_ROLLBACK_TAG=$WEB_BASE_TAG
OCR_ROLLBACK_TAG=$OCR_BASE_TAG
LEGACY_CLOUDFLARED_CONTAINER=$LEGACY_CLOUDFLARED_CONTAINER
EOF
chmod 600 "$BACKUP_DIR/images.env"

dc exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
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
cp "$SOURCE_DIR/compose.cloudflare.yaml" "$APP_DIR/compose.cloudflare.yaml"
for sample in .env.example .env.lan.example .env.nas.example .env.nas-192.168.5.6.example .env.production.example; do
  if [ -f "$SOURCE_DIR/$sample" ]; then
    cp "$SOURCE_DIR/$sample" "$APP_DIR/$sample"
  fi
done

# 固定新镜像名称，保证以后重启不会因默认值或历史仓库名切回旧版本。
upsert_env LIBRARY_API_IMAGE "$API_TARGET_TAG" "$APP_DIR/.env"
upsert_env LIBRARY_WEB_IMAGE "$WEB_TARGET_TAG" "$APP_DIR/.env"
upsert_env CELERY_RESULT_BACKEND "" "$APP_DIR/.env"
upsert_env CELERY_TASK_IGNORE_RESULT "true" "$APP_DIR/.env"
upsert_env CELERY_TASK_STORE_ERRORS_EVEN_IF_IGNORED "false" "$APP_DIR/.env"
upsert_env CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP "true" "$APP_DIR/.env"
upsert_env PROCESS_INGESTION_INLINE "false" "$APP_DIR/.env"
upsert_env POSTGRES_IMAGE "postgres:16-alpine" "$APP_DIR/.env"
if [ "$STACK_MODE" = "public-cloudflare" ]; then
  postgres_user="$(read_env_value POSTGRES_USER "$APP_DIR/.env")"
  postgres_db="$(read_env_value POSTGRES_DB "$APP_DIR/.env")"
  postgres_password="$(read_env_value POSTGRES_PASSWORD "$APP_DIR/.env")"
  redis_password="$(read_env_value REDIS_PASSWORD "$APP_DIR/.env")"
  [ -n "$postgres_user" ] || postgres_user=library
  [ -n "$postgres_db" ] || postgres_db=library
  case "$postgres_password" in
    *[!A-Za-z0-9._~-]*) fail "POSTGRES_PASSWORD must use URL-safe characters: letters, numbers, dot, underscore, tilde or hyphen" ;;
  esac
  case "$redis_password" in
    *[!A-Za-z0-9._~-]*) fail "REDIS_PASSWORD must use URL-safe characters: letters, numbers, dot, underscore, tilde or hyphen" ;;
  esac
  upsert_env DATABASE_URL "postgresql://${postgres_user}:${postgres_password}@postgres:5432/${postgres_db}" "$APP_DIR/.env"
  upsert_env REDIS_URL "redis://:${redis_password}@redis:6379/0" "$APP_DIR/.env"
  upsert_env CACHE_URL "redis://:${redis_password}@redis:6379/1" "$APP_DIR/.env"
  upsert_env CELERY_BROKER_URL "redis://:${redis_password}@redis:6379/2" "$APP_DIR/.env"
fi
export LIBRARY_API_IMAGE="$API_TARGET_TAG"
export LIBRARY_WEB_IMAGE="$WEB_TARGET_TAG"

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
dc config --quiet
if [ -n "$LEGACY_CLOUDFLARED_CONTAINER" ]; then
  [ "$MIGRATE_LEGACY_CLOUDFLARED" = "1" ] \
    || fail "检测到旧 cloudflared-library 容器。请设置 MIGRATE_LEGACY_CLOUDFLARED=1 由升级脚本接管，或先人工确认"
  docker stop "$LEGACY_CLOUDFLARED_CONTAINER" >/dev/null \
    || fail "无法停止旧 Cloudflare Tunnel 容器"
  STOPPED_LEGACY_CLOUDFLARED="$LEGACY_CLOUDFLARED_CONTAINER"
fi
# Recreate infrastructure first. This joins every service to the current
# backend network and applies Redis authentication before workers reconnect.
# All startup commands forbid remote image pulls.
dc up -d --no-build --pull never --force-recreate postgres redis meilisearch
for infrastructure_service in postgres redis meilisearch; do
  wait_for_healthy_service "$infrastructure_service" \
    || fail "$infrastructure_service did not become healthy during the offline upgrade"
done
# Older Docker Compose releases on UGOS support `up --pull never` but reject
# the same flag on `run`. The target API image was built and tagged locally
# immediately above, so `run` can use it without contacting a registry.
dc run --rm --no-deps api python manage.py migrate --noinput
dc up -d --no-build --pull never --no-deps --force-recreate api worker beat web
dc up -d --no-build --pull never --no-deps --force-recreate edge
if [ -n "$ocr_target_image" ]; then
  dc --profile ocr up -d --no-build --pull never --no-deps --force-recreate paddleocr
fi
if [ "$STACK_MODE" = "public-cloudflare" ]; then
  dc up -d --no-build --pull never --no-deps --force-recreate cloudflared
fi

wait_for_api || fail "API 在 120 秒内没有通过数据库和迁移就绪检查"
if ! wait_for_web; then
  dc logs --no-color --tail=100 web >&2 || true
  fail "Web 在 90 秒内没有启动，请查看上方日志"
fi
if [ -n "$ocr_target_image" ] && ! wait_for_ocr; then
  dc --profile ocr logs --no-color --tail=100 paddleocr >&2 || true
  fail "OCR 在 120 秒内没有启动，请查看上方日志"
fi

api_version="$(dc exec -T api python -c 'from config.version import APP_VERSION; print(APP_VERSION)' | tr -d '\r\n ')"
worker_version="$(dc exec -T worker python -c 'from config.version import APP_VERSION; print(APP_VERSION)' | tr -d '\r\n ')"
web_version="$(dc exec -T web node -p "require('./package.json').version" | tr -d '\r\n ')"
next_version="$(dc exec -T web node -p "require('./node_modules/next/package.json').version" | tr -d '\r\n ')"
react_version="$(dc exec -T web node -p "require('./node_modules/react/package.json').version" | tr -d '\r\n ')"
[ "$api_version" = "$EXPECTED_VERSION" ] || fail "API 容器仍为 $api_version"
[ "$worker_version" = "$EXPECTED_VERSION" ] || fail "Worker 容器仍为 $worker_version"
[ "$web_version" = "$EXPECTED_VERSION" ] || fail "Web 容器仍为 $web_version"
[ "$next_version" = "16.2.12" ] || fail "Web 容器 Next 版本不正确：$next_version"
[ "$react_version" = "19.2.8" ] || fail "Web 容器 React 版本不正确：$react_version"
dc exec -T web node_modules/@esbuild/linux-x64/bin/esbuild --version >/dev/null \
  || fail "Web 容器的 Linux 原生运行依赖不可执行"

ready_json="$(api_curl http://127.0.0.1:8000/api/ready/)" \
  || fail "就绪接口不可用"
health_json="$(api_curl http://127.0.0.1:8000/api/health/)" \
  || fail "健康接口不可用"
if ! printf '%s' "$health_json" | grep -Fq "\"version\":\"$EXPECTED_VERSION\"" \
  && ! printf '%s' "$health_json" | grep -Fq "\"version\": \"$EXPECTED_VERSION\""; then
  fail "健康接口版本不正确：$health_json"
fi

pending_migrations="$(dc exec -T api python manage.py showmigrations --plan | grep '\[ \]' || true)"
[ -z "$pending_migrations" ] || fail "仍有未执行迁移：$pending_migrations"

overview_json="$(api_curl http://127.0.0.1:8000/api/catalog/theory-system/overview/)" \
  || fail "理论系统公开接口不可用"
printf '%s' "$overview_json" | grep -Fq 'disciplines' || fail "理论系统首页接口缺少学科数据"

# 任务状态以数据库为准。服务重启后先恢复历史滞留任务，再验证 Redis、
# Celery worker、OCR 和搜索服务确实可用，避免只通过 API 健康检查。
dc exec -T api python manage.py recover_library_pipeline --limit 500 \
  || fail "无法恢复滞留的入库或语义索引任务"
dc exec -T api python manage.py check_library_pipeline --wait 180 --strict \
  || {
    dc logs --no-color --tail=160 api worker beat >&2 || true
    if [ -n "$ocr_target_image" ]; then
      dc --profile ocr logs --no-color --tail=120 paddleocr >&2 || true
    fi
    fail "后台处理服务没有共同就绪，请查看上方日志"
  }

# 可选地对管理员指定的真实上传记录做数据库和存储核验。这里只读取既有
# 记录，不会自动发布，也不会改动管理员已确认的元数据。
if [ -n "$VERIFY_INGESTION_ITEM_ID" ]; then
  dc exec -T api python manage.py verify_ingestion_item \
    --item-id "$VERIFY_INGESTION_ITEM_ID" --strict \
    || fail "指定 PDF 没有完成可复核或已发布的入库流程"
elif [ -n "$VERIFY_INGESTION_SOURCE_FILENAME" ]; then
  dc exec -T api python manage.py verify_ingestion_item \
    --source-filename "$VERIFY_INGESTION_SOURCE_FILENAME" --strict \
    || fail "指定 PDF 没有完成可复核或已发布的入库流程"
fi

if [ "$PREWARM_SEMANTIC_MODEL" = "1" ]; then
  dc exec -T api python manage.py prewarm_semantic_model --timeout 900 \
    || fail "语义模型预热失败。请检查 NAS 容器代理、HF_ENDPOINT 和 Meilisearch 日志"
fi

dc exec -T web sh -c 'test -s /app/dist/client/runtime-config.js' \
  || fail "Web 容器没有运行时 API 地址配置"
dc exec -T web sh -c 'test -w /app/dist/client' \
  || fail "Web 运行用户不能写入运行时配置目录"
for forbidden in 'http://localhost:8000/api' '192.168.5.6:8000' 'postgres:5432' 'redis:6379' 'meilisearch:7700'; do
  if dc exec -T web sh -c "grep -R -F '$forbidden' /app/dist/client/assets >/dev/null 2>&1"; then
    fail "浏览器脚本包含不应公开的地址：$forbidden"
  fi
done

public_asset_id="$(dc exec -T api python -c \
  'import os; os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings"); import django; django.setup(); from catalog.models import Asset, PublicationState; print(Asset.objects.filter(kind=Asset.Kind.NORMALIZED, status=Asset.Status.READY, edition__state=PublicationState.PUBLISHED, is_current=True).values_list("id", flat=True).first() or "")' \
  | tr -d '\r\n ')"
if [ -n "$public_asset_id" ]; then
  access_json="$(api_curl "http://127.0.0.1:8000/api/distribution/assets/$public_asset_id/access/")" \
    || fail "公开 PDF 授权接口不可用"
  printf '%s' "$access_json" | grep -Fq '"url"' || fail "公开 PDF 授权接口没有返回阅读地址"
fi

edge_container="$(dc ps -q edge)"
[ -n "$edge_container" ] || fail "没有找到统一入口 edge 容器"

if [ "$STACK_MODE" = "public-cloudflare" ]; then
  # 公网与局域网必须共用这一组 API、数据库、文件目录和后台任务。
  # Web 与 API 不能再单独映射主机端口，否则浏览器会绕过同源入口，
  # 重新出现登录后跳回登录页和公网、内网状态不一致的问题。
  [ -z "$(docker port "$api_container" 2>/dev/null || true)" ] \
    || fail "公网模式下 API 仍直接暴露主机端口"
  [ -z "$(docker port "$web_container" 2>/dev/null || true)" ] \
    || fail "公网模式下 Web 仍直接暴露主机端口"

  edge_bind_ip="$(read_env_value EDGE_BIND_IP "$APP_DIR/.env")"
  lan_admin_port="$(read_env_value LAN_ADMIN_PORT "$APP_DIR/.env")"
  lan_legacy_port="$(read_env_value LAN_LEGACY_PORT "$APP_DIR/.env")"
  edge_port="$(read_env_value EDGE_PORT "$APP_DIR/.env")"
  [ -n "$lan_admin_port" ] || lan_admin_port=3000
  [ -n "$lan_legacy_port" ] || lan_legacy_port=18080
  [ -n "$edge_port" ] || edge_port=18082

  require_edge_binding "$edge_container" "$edge_bind_ip" "$lan_admin_port"
  require_edge_binding "$edge_container" "$edge_bind_ip" "$lan_legacy_port"
  require_edge_binding "$edge_container" "$edge_bind_ip" "$edge_port"

  for lan_port in "$lan_admin_port" "$lan_legacy_port" "$edge_port"; do
    lan_health="$(wait_for_url_version "http://${edge_bind_ip}:${lan_port}/api/health/" "$EXPECTED_VERSION" 30 lan || true)"
    [ -n "$lan_health" ] \
      || fail "局域网入口 http://${edge_bind_ip}:${lan_port} 没有返回 $EXPECTED_VERSION"
  done

  cloudflared_container="$(dc ps --status running -q cloudflared)"
  [ -n "$cloudflared_container" ] || {
    dc logs --no-color --tail=160 cloudflared >&2 || true
    fail "Cloudflare Tunnel 容器没有保持运行"
  }
  public_front_network="$(docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$edge_container" 2>/dev/null | grep '_public_front$' | head -n 1 || true)"
  [ -n "$public_front_network" ] || fail "统一入口没有连接 public_front 网络"
  require_container_network "$cloudflared_container" "$public_front_network"

  if [ "$VERIFY_PUBLIC_ENDPOINT" = "1" ]; then
    public_health="$(wait_for_url_version "https://${library_domain}/api/health/" "$EXPECTED_VERSION" 60 public || true)"
    if [ -z "$public_health" ]; then
      dc logs --no-color --tail=160 cloudflared edge >&2 || true
      fail "公网域名 https://${library_domain} 没有返回 $EXPECTED_VERSION"
    fi
  fi
fi

# 到达这里说明新 Tunnel 已通过局域网、网络归属和可选公网域名检查。
# 不再让失败处理函数重新启动旧容器，避免两个 Tunnel 同时争用同一域名。
STOPPED_LEGACY_CLOUDFLARED=""

printf '\n%s\n' "$EXPECTED_VERSION 离线升级完成。"
printf '%s\n' "运行模式：$STACK_MODE"
printf '%s\n' "Compose 项目：$COMPOSE_PROJECT_NAME"
printf '%s\n' "运行版本：API $api_version / Worker $worker_version / Web $web_version"
printf '%s\n' "目标镜像：$API_TARGET_TAG / $WEB_TARGET_TAG"
printf '%s\n' "Web 依赖：Next $next_version / React $react_version"
printf '%s\n' "就绪检查：$ready_json"
if [ -n "$ocr_target_image" ]; then
  ocr_model_home="$(dc --profile ocr exec -T paddleocr sh -c 'printf %s "$PADDLE_HOME"' | tr -d '\r\n')"
  printf '%s\n' "OCR 模型目录：$ocr_model_home"
fi
printf '%s\n' "升级前备份：$BACKUP_DIR"
printf '%s\n' "回退镜像标签：$API_BASE_TAG / $WEB_BASE_TAG / $OCR_BASE_TAG"
if [ "$STACK_MODE" = "public-cloudflare" ]; then
  printf '%s\n' "局域网入口：http://${edge_bind_ip}:${lan_admin_port}、:${lan_legacy_port}、:${edge_port}"
  if [ "$VERIFY_PUBLIC_ENDPOINT" = "1" ]; then
    printf '%s\n' "公网入口：https://${library_domain} 已返回 $EXPECTED_VERSION"
  else
    printf '%s\n' "公网域名检查已按 VERIFY_PUBLIC_ENDPOINT=0 跳过。"
  fi
fi
printf '%s\n' "本次构建没有访问 Docker Hub、npm、pip 或 Hugging Face。"
if [ "$PREWARM_SEMANTIC_MODEL" = "1" ]; then
  printf '%s\n' "语义模型已经完成预热。"
else
  printf '%s\n' "语义模型未在本次升级中联网预热。如需预热，请设置 PREWARM_SEMANTIC_MODEL=1 后重新运行。"
fi
if [ -n "$VERIFY_INGESTION_ITEM_ID" ] || [ -n "$VERIFY_INGESTION_SOURCE_FILENAME" ]; then
  printf '%s\n' "指定的真实 PDF 已通过数据库、文件、页文本和检索段落核验。"
else
  printf '%s\n' "本次未指定真实 PDF。上传后请运行 verify_ingestion_item 和 verify_public_lan_item.py。"
fi
printf '%s\n' "请按 docs/nas-offline-upgrade-${EXPECTED_VERSION}.md 完成局域网、域名、PDF Range 和真实上传验收。"
