"""Add publication filter fields without recreating indexes or embeddings."""

import json

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.models import SemanticIndexVersion
from catalog.services.claims.indexing import claim_index_uid
from catalog.services.semantic_indexing import SEMANTIC_INDEX_UID
from ingestion.services.indexing import _headers, _wait_task


def _add_attributes(current, required):
    values = list(current or [])
    if "*" in values:
        return values
    return [*values, *(name for name in required if name not in values)]


class Command(BaseCommand):
    help = (
        "Plan the additive 3.0.4 publication filters for existing search indexes. "
        "Use --apply after backup; no documents, vectors or embedder settings are changed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--wait-seconds", type=int, default=45)

    def handle(self, *args, **options):
        wait_seconds = options["wait_seconds"]
        if not 1 <= wait_seconds <= 60:
            raise CommandError("等待时间必须在 1 至 60 秒之间。")
        active_uids = list(SemanticIndexVersion.objects.filter(
            status=SemanticIndexVersion.Status.ACTIVE,
        ).values_list("uid", flat=True)[:2])
        if len(active_uids) > 1:
            raise CommandError("存在多个活动语义索引，先明确当前索引，不能自动选择。")
        targets = [
            ("passages", ["catalog_revision_id"], ["passage_id", "catalog_revision_id"]),
            (active_uids[0] if active_uids else SEMANTIC_INDEX_UID,
             ["catalog_revision_id"], ["chunk_id", "catalog_revision_id"]),
            (claim_index_uid(), ["catalog_revision_id", "document_revision_id"], ["claim_id", "catalog_revision_id"]),
        ]
        base_url = settings.MEILISEARCH_URL.rstrip("/")
        plans = []
        try:
            # Inspect every target before changing anything. Reports deliberately
            # omit embedder/API settings, which may contain credentials.
            for uid, filterable, displayed in targets:
                response = httpx.get(
                    f"{base_url}/indexes/{uid}/settings", headers=_headers(), timeout=5,
                )
                if response.status_code == 404:
                    plans.append({"index_uid": uid, "status": "missing_no_change"})
                    continue
                response.raise_for_status()
                current = response.json()
                before = {
                    "filterableAttributes": current.get("filterableAttributes", []),
                    "displayedAttributes": current.get("displayedAttributes", ["*"]),
                }
                desired = {
                    "filterableAttributes": _add_attributes(before["filterableAttributes"], filterable),
                    "displayedAttributes": _add_attributes(before["displayedAttributes"], displayed),
                }
                patch = {name: value for name, value in desired.items() if before[name] != value}
                plans.append({
                    "index_uid": uid, "status": "pending" if patch else "unchanged",
                    "before": before, "patch": patch,
                })
            self.stdout.write(json.dumps({"apply": options["apply"], "plans": plans}, ensure_ascii=False, indent=2))
            self.stdout.flush()
            if not options["apply"]:
                return
            for plan in plans:
                if not plan.get("patch"):
                    continue
                response = httpx.patch(
                    f"{base_url}/indexes/{plan['index_uid']}/settings",
                    headers=_headers(), json=plan["patch"], timeout=5,
                )
                response.raise_for_status()
                task = response.json()
                self.stdout.write(json.dumps({"index_uid": plan["index_uid"], "submitted_task": task}, ensure_ascii=False))
                self.stdout.flush()
                result = _wait_task(task, timeout=wait_seconds)
                self.stdout.write(json.dumps({"index_uid": plan["index_uid"], "status": result.get("status", "succeeded")}, ensure_ascii=False))
        except (httpx.HTTPError, ValueError, RuntimeError, TimeoutError) as exc:
            # A timeout leaves the reported Meilisearch task intact. Inspect
            # that task before rerunning; do not delete or rebuild the index.
            raise CommandError(f"索引字段准备未完成，请保留报告并检查已提交任务。{exc}") from exc
