#!/bin/sh
set -eu

MEILISEARCH_IMAGE="${MEILISEARCH_IMAGE:?请提供现有 Meilisearch 镜像或镜像 ID}"
MODEL_ROOT="${MODEL_ROOT:?请提供 Hugging Face 缓存主机目录}"
MODEL_REPO="${MODEL_REPO:-sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2}"
MODEL_REVISION="${MODEL_REVISION:?请提供固定模型 revision}"
MODEL_POOLING="${MODEL_POOLING:-useModel}"
CONTAINER_NAME="${CONTAINER_NAME:-library-hf-offline-probe-$$}"
MASTER_KEY="library-offline-model-probe-$$-only"
INDEX_UID="semantic_offline_probe_$$"

case "$MODEL_ROOT" in
  /*) ;;
  *) printf '%s\n' "MODEL_ROOT 必须是绝对路径" >&2; exit 1 ;;
esac
[ "$MODEL_ROOT" != "/" ] || {
  printf '%s\n' "拒绝把根目录作为模型目录" >&2
  exit 1
}
[ -d "$MODEL_ROOT" ] || {
  printf '%s\n' "模型目录不存在：$MODEL_ROOT" >&2
  exit 1
}
docker image inspect "$MEILISEARCH_IMAGE" >/dev/null
if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  printf '%s\n' "临时探针容器已存在：$CONTAINER_NAME" >&2
  exit 1
fi

cleanup() {
  code=$?
  if [ "$code" -ne 0 ]; then
    docker logs --tail 120 "$CONTAINER_NAME" >&2 2>/dev/null || true
  fi
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

extract_task_uid() {
  sed -n 's/.*"taskUid":\([0-9][0-9]*\).*/\1/p'
}

wait_for_task() {
  task_uid="$1"
  attempts="${2:-360}"
  attempt=0
  while [ "$attempt" -lt "$attempts" ]; do
    task_body="$(docker exec "$CONTAINER_NAME" curl -fsS \
      -H "Authorization: Bearer $MASTER_KEY" \
      "http://127.0.0.1:7700/tasks/$task_uid")"
    case "$task_body" in
      *'"status":"succeeded"'*) return 0 ;;
      *'"status":"failed"'*) printf '%s\n' "$task_body" >&2; return 1 ;;
    esac
    attempt=$((attempt + 1))
    sleep 5
  done
  printf '%s\n' "等待 Meilisearch task $task_uid 超时" >&2
  return 1
}

docker run -d \
  --name "$CONTAINER_NAME" \
  --network none \
  --cpus 2 \
  --memory 3g \
  --env MEILI_ENV=production \
  --env "MEILI_MASTER_KEY=$MASTER_KEY" \
  --env MEILI_NO_ANALYTICS=true \
  --env HF_HOME=/meili_data/models \
  --env HF_HUB_OFFLINE=1 \
  --env TRANSFORMERS_OFFLINE=1 \
  --env HF_ENDPOINT=https://offline.invalid \
  --volume "$MODEL_ROOT:/meili_data/models:ro" \
  "$MEILISEARCH_IMAGE" >/dev/null

attempt=0
until docker exec "$CONTAINER_NAME" curl -fsS http://127.0.0.1:7700/health >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  [ "$attempt" -lt 60 ] || {
    printf '%s\n' "离线 Meilisearch 探针未就绪" >&2
    exit 1
  }
  sleep 2
done

response="$(docker exec "$CONTAINER_NAME" curl -fsS \
  -X POST \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H 'Content-Type: application/json' \
  --data "{\"uid\":\"$INDEX_UID\",\"primaryKey\":\"id\"}" \
  http://127.0.0.1:7700/indexes)"
task_uid="$(printf '%s' "$response" | extract_task_uid)"
[ -n "$task_uid" ]
wait_for_task "$task_uid" 120

settings_json="$(printf '%s' "$MODEL_REPO" | sed 's/["\\]/\\&/g')"
response="$(docker exec "$CONTAINER_NAME" curl -fsS \
  -X PATCH \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H 'Content-Type: application/json' \
  --data "{\"default\":{\"source\":\"huggingFace\",\"model\":\"$settings_json\",\"revision\":\"$MODEL_REVISION\",\"pooling\":\"$MODEL_POOLING\",\"documentTemplate\":\"{{doc.title}}\\n{{doc.original_text}}\"}}" \
  "http://127.0.0.1:7700/indexes/$INDEX_UID/settings/embedders")"
task_uid="$(printf '%s' "$response" | extract_task_uid)"
[ -n "$task_uid" ]
wait_for_task "$task_uid" 360

response="$(docker exec "$CONTAINER_NAME" curl -fsS \
  -X POST \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H 'Content-Type: application/json' \
  --data '[{"id":"probe-1","title":"社会理论与实践","original_text":"社会理论帮助研究者解释制度与行动之间的关系。"},{"id":"probe-2","title":"自然科学导论","original_text":"这是一段用于区分候选结果的自然科学文本。"}]' \
  "http://127.0.0.1:7700/indexes/$INDEX_UID/documents")"
task_uid="$(printf '%s' "$response" | extract_task_uid)"
[ -n "$task_uid" ]
wait_for_task "$task_uid" 360

search_response="$(docker exec "$CONTAINER_NAME" curl -fsS \
  -X POST \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"q":"制度与人的行动","hybrid":{"embedder":"default","semanticRatio":1.0},"limit":2}' \
  "http://127.0.0.1:7700/indexes/$INDEX_UID/search")"
printf '%s' "$search_response" | grep -Fq 'probe-1'

printf '%s\n' "HF_OFFLINE_PROBE_SUCCEEDED image=$MEILISEARCH_IMAGE revision=$MODEL_REVISION"
