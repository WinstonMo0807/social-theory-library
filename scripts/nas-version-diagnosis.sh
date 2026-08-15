#!/bin/sh
set -u

APP_DIR="${APP_DIR:-/volume2/library/docker/social-theory-library}"
EXPECTED_VERSION="${EXPECTED_VERSION:-2.3.1}"

printf '%s\n' "社会理论书库版本诊断"
printf '%s\n' "项目目录：$APP_DIR"
printf '%s\n' "期望版本：$EXPECTED_VERSION"

if [ ! -d "$APP_DIR" ]; then
  printf '%s\n' "错误：项目目录不存在" >&2
  exit 1
fi

cd "$APP_DIR" || exit 1

printf '\n%s\n' "一、目标目录源码"
if [ -f api/config/version.py ]; then
  sed -n '1,3p' api/config/version.py
else
  printf '%s\n' "缺少 api/config/version.py"
fi
if [ -f web/package.json ]; then
  grep -m 1 '"version"' web/package.json || true
else
  printf '%s\n' "缺少 web/package.json"
fi
if [ -f web/components/admin-shell.tsx ]; then
  grep -m 1 '局域网测试版' web/components/admin-shell.tsx || true
else
  printf '%s\n' "缺少 web/components/admin-shell.tsx"
fi

printf '\n%s\n' "二、Compose 容器"
docker compose ps

printf '\n%s\n' "三、容器内版本"
printf '%s' "API："
docker compose exec -T api \
  python -c 'from config.version import APP_VERSION; print(APP_VERSION)' \
  2>&1 || true
printf '%s' "Worker："
docker compose exec -T worker \
  python -c 'from config.version import APP_VERSION; print(APP_VERSION)' \
  2>&1 || true
printf '%s' "Web："
docker compose exec -T web \
  node -p "require('./package.json').version" \
  2>&1 || true

printf '\n%s\n' "四、容器内健康接口"
docker compose exec -T api \
  curl -fsS http://127.0.0.1:8000/api/health/ \
  2>&1 || true
printf '\n'

printf '\n%s\n' "五、宿主机健康接口"
curl -fsS http://127.0.0.1:18081/api/health/ 2>&1 || true
printf '\n'

source_api_version="$(
  sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' api/config/version.py 2>/dev/null \
    | tr -d '\r\n '
)"
runtime_api_version="$(
  docker compose exec -T api \
    python -c 'from config.version import APP_VERSION; print(APP_VERSION)' \
    2>/dev/null \
    | tr -d '\r\n '
)"
runtime_web_version="$(
  docker compose exec -T web \
    node -p "require('./package.json').version" \
    2>/dev/null \
    | tr -d '\r\n '
)"

if [ "$source_api_version" = "$EXPECTED_VERSION" ] \
  && [ "$runtime_api_version" = "$EXPECTED_VERSION" ] \
  && [ "$runtime_web_version" = "$EXPECTED_VERSION" ]; then
  printf '\n%s\n' "结论：源码、API 容器和 Web 容器均为 $EXPECTED_VERSION。"
  exit 0
fi

printf '\n%s\n' "结论：版本没有全部切换到 $EXPECTED_VERSION。"
printf '%s\n' "源码 API=$source_api_version，容器 API=$runtime_api_version，容器 Web=$runtime_web_version"
exit 2
