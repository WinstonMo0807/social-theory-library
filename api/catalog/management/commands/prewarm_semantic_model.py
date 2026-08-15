from __future__ import annotations

import httpx
import uuid
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.services.semantic_indexing import ensure_semantic_index
from catalog.services.semantic_search import current_semantic_runtime, semantic_model_health
from ingestion.services.indexing import _headers, _wait_task


class Command(BaseCommand):
    help = "预先下载并验证 Meilisearch 使用的本地语义模型。"

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=1800)
        parser.add_argument("--index-uid", default="")

    def handle(self, *args, **options):
        runtime = current_semantic_runtime()
        if not runtime["enabled"] or runtime["engine"] != "meilisearch_hybrid":
            self.stdout.write("语义混合检索未启用，无需预缓存模型。")
            return
        if runtime["provider"] != "huggingFace":
            self.stdout.write(f"当前提供方为 {runtime['provider']}，不需要下载 Hugging Face 模型。")
            return

        model_health = semantic_model_health(runtime)
        if runtime.get("offline_mode") and not model_health.get("available"):
            raise CommandError(model_health.get("reason") or "本地语义模型不完整。")

        timeout = max(60, min(options["timeout"], 7200))
        base_url = settings.MEILISEARCH_URL.rstrip("/")
        requested_index_uid = str(options.get("index_uid") or "").strip()
        temporary_index = not bool(requested_index_uid)
        index_uid = requested_index_uid or f"semantic_model_probe_{uuid.uuid4().hex[:12]}"
        probe_id = "__library_model_prewarm__"
        try:
            ensure_semantic_index(runtime, index_uid=index_uid)
            response = httpx.post(
                f"{base_url}/indexes/{index_uid}/documents",
                headers=_headers(),
                json=[{
                    "id": probe_id,
                    "title": "语义模型预热检查",
                    "authors": ["系统"],
                    "chapter_title": "",
                    "section_title": "",
                    "original_text": "社会科学文献检索模型本地缓存与向量生成检查。",
                    "normalized_text": "社会科学文献检索模型本地缓存与向量生成检查",
                    "is_public": False,
                }],
                timeout=30,
            )
            response.raise_for_status()
            _wait_task(response.json(), timeout=timeout)
            self.stdout.write(
                self.style.SUCCESS(
                    f"语义模型已通过隔离索引探针：{runtime['model']} ({index_uid})"
                )
            )
        except Exception as exc:
            raise CommandError(f"语义模型预缓存失败：{exc}") from exc
        finally:
            try:
                target = (
                    f"{base_url}/indexes/{index_uid}"
                    if temporary_index
                    else f"{base_url}/indexes/{index_uid}/documents/{probe_id}"
                )
                response = httpx.delete(target, headers=_headers(), timeout=15)
                if response.status_code < 400:
                    _wait_task(response.json(), timeout=60)
            except Exception:
                pass
