"""Compare current Discovery passages and adjacent-evidence reranking locally."""
import json
from pathlib import Path
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import connection
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import SearchEvaluationSet, SemanticIndexVersion
from catalog.discovery_index_models import DiscoveryDocument
from catalog.services.discovery_evaluation import compare_query, report_metadata, score_comparison, verify_comparison_sources
from catalog.services.discovery_sessions import normalize_filters
from catalog.services.discovery_sources import fingerprint
from catalog.services.discovery_inference import inference_health, DiscoveryInferenceError
from catalog.services.discovery_projection import DiscoveryIndexError, meili
from catalog.services.semantic_search_benchmark import read_jsonl, _render_annotation_html
from catalog.services.semantic_search_evaluation_environment import (
    evaluation_write_guard, _require_ignored_bundle_location, _evaluation_shaped_host, EvaluationEnvironmentError,
)


class Command(BaseCommand):
    help = "默认只做本地预检；隔离评测环境中比较Discovery片段与上下文排序，不切换索引。"

    def add_arguments(self, parser):
        parser.add_argument("--evaluation-set", help="已有SearchEvaluationSet名称或UUID")
        parser.add_argument("--index-version", help="隔离Discovery索引UID或UUID")
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--output-dir")
        parser.add_argument("--split", choices=["diagnostic", "dev", "test"], default="dev")
        parser.add_argument("--score-report", help="离线评分已有comparison.json，不访问模型/数据库")
        parser.add_argument("--judgments", help="已核对PDF的人工评分JSONL")

    def handle(self, *args, **options):
        try:
            return self.run(options)
        except (ValueError, OSError, ValidationError, EvaluationEnvironmentError, DiscoveryIndexError, DiscoveryInferenceError) as exc:
            raise CommandError(str(exc)) from exc

    def run(self, options):
        if options["score_report"]:
            if not options["judgments"] or options["execute"]:
                raise CommandError("离线评分需同时提供--judgments，且不能使用--execute。")
            report = json.loads(Path(options["score_report"]).read_text("utf-8"))
            self.stdout.write(json.dumps(score_comparison(report, read_jsonl(options["judgments"])), ensure_ascii=False))
            return
        if options["dry_run"] and options["execute"]:
            raise CommandError("--dry-run和--execute不能同时使用。")
        tables = set(connection.introspection.table_names())
        required = {"catalog_discoverydocument", "catalog_evidencespan", "catalog_semanticindexversion",
                    "catalog_searchevaluationset", "catalog_searchevaluationquery"}
        missing = sorted(required - tables)
        if missing:
            self.stdout.write(json.dumps({"can_execute": False, "missing_tables": missing,
                "external_calls": False, "database_changed": False}, ensure_ascii=False))
            if options["execute"]:
                raise CommandError("缺少当前Discovery/评测schema；未执行迁移或外部请求。")
            return
        def resolve(manager, value, name):
            row = manager.filter(**{name: value}).first() if value else None
            if row is None and value:
                try:
                    row = manager.filter(pk=UUID(value)).first()
                except ValueError:
                    pass
            return row
        dataset = resolve(SearchEvaluationSet.objects, options["evaluation_set"], "name")
        generation = resolve(SemanticIndexVersion.discovery_objects, options["index_version"], "uid")
        blockers = []
        if dataset is None or not dataset.is_active:
            blockers.append("需要有效的已有SearchEvaluationSet；不自动制造问题或gold。")
        queries = list(dataset.queries.order_by("order", "id")[:51]) if dataset else []
        if not 1 <= len(queries) <= 50:
            blockers.append("试验集需要1至50个问题。")
        split = (dataset.metadata or {}).get("discovery_split") if dataset else None
        if split != options["split"]:
            blockers.append("评测集metadata.discovery_split必须与显式选择的split一致。")
        if (generation is None or generation.status not in {"ready", "active"} or
                not generation.uid.startswith("discovery_eval_")):
            blockers.append("需要ready/active的discovery_eval_隔离索引。")
        doc_count = DiscoveryDocument.objects.filter(generation=generation, channel="passages",
            keyword_ready=True, vector_ready=True).count() if generation else 0
        if not doc_count:
            blockers.append("隔离索引没有完成的原文投影。")
        self.stdout.write(json.dumps({"can_execute": not blockers, "blockers": blockers,
            "query_count": len(queries), "passage_count": doc_count, "split": split,
            "external_calls": False, "quality_verified": False}, ensure_ascii=False))
        if not options["execute"]:
            return
        if blockers or not options["output_dir"]:
            raise CommandError("预检未通过或缺少--output-dir。")
        # Reuse established isolation checks before any external service call.
        evaluation_write_guard("discovery")
        if not _evaluation_shaped_host(settings.DISCOVERY_INFERENCE_URL):
            raise CommandError("评测推理地址必须是本机或包含eval的隔离服务。")
        output = Path(options["output_dir"]).resolve()
        _require_ignored_bundle_location(output)
        if output.exists():
            raise CommandError("输出目录已存在，请指定新目录以保留已有标注。")
        dataset_hash = fingerprint([[str(query.pk), query.query_text, query.filters] for query in queries])
        for query in queries:
            if not 2 <= len(query.query_text.strip()) <= 1200:
                raise CommandError("问题长度必须与当前Discovery契约一致。")
            query.filters = normalize_filters(query.filters)
        health = inference_health()
        for role in ("embedding", "reranker"):
            if health.get("models", {}).get(role, {}).get("artifact_id") != generation.config_snapshot.get(f"{role}_artifact"):
                raise CommandError("模型清单与隔离索引不一致。")
        stats = meili("GET", f"/indexes/{generation.uid}/stats")
        index_header = meili("GET", f"/indexes/{generation.uid}")
        if not index_header.get("updatedAt"):
            raise CommandError("索引缺少更新时间，不能冻结此次比较。")
        if stats.get("isIndexing") or stats.get("numberOfDocuments") != DiscoveryDocument.objects.filter(
                generation=generation, keyword_ready=True, vector_ready=True).count():
            raise CommandError("隔离索引未静默或投影数量不一致。")
        report = {**report_metadata(generation), "created_at": timezone.now().isoformat(),
                  "evaluation_set_id": str(dataset.pk), "split": split, "queries": [],
                  "dataset_hash": dataset_hash, "index_updated_at": index_header["updatedAt"]}
        for number, query in enumerate(queries):
            row = compare_query(query, generation, context_first=bool(number % 2))
            row["split"] = split
            report["queries"].append(row)
        for row in report["queries"]:
            verify_comparison_sources(row)
        current_queries = list(dataset.queries.order_by("order", "id"))
        if (fingerprint([[str(query.pk), query.query_text, query.filters] for query in current_queries]) != dataset_hash or
                meili("GET", f"/indexes/{generation.uid}").get("updatedAt") != index_header["updatedAt"] or
                meili("GET", f"/indexes/{generation.uid}/stats").get("isIndexing")):
            raise CommandError("比较期间问题集或外部索引改变；未导出可评分报告。")
        report["report_hash"] = fingerprint(report)
        output.mkdir(parents=True, exist_ok=False)
        (output / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        # Reuse the existing escaped, blind annotation renderer. Keep diagnostics
        # in comparison.json, not in the cards shown to the human reviewer.
        (output / "annotation.html").write_text(_render_annotation_html(report["queries"],
            {"report_hash": report["report_hash"], "schema": report["schema"]}), "utf-8")
        labels = [{"query_id": row["query_id"], "chunk_document_id": item["candidate_id"],
                   "work_id": item["work_id"], "page": item["page"], "relevance_grade": None,
                   "report_hash": report["report_hash"], "locator_verified": False, "reviewer_note": ""}
                  for row in report["queries"] for item in row["candidates"]]
        for label in labels:
            label["material_role"] = ""
        (output / "judgments.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in labels), "utf-8")
        self.stdout.write(json.dumps({"output": str(output), "quality_verified": False,
            "comparison_usable": all(row["comparison_usable"] for row in report["queries"]),
            "instruction": "核对PDF后在judgments.jsonl填写评分、定位确认与说明；未标注不评分。"}, ensure_ascii=False))
