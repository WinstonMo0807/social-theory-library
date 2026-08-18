from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid5

import httpx
from django.apps import apps
from django.conf import settings
from django.db import connection, models, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Exists, F, OuterRef, Q
from django.utils import timezone

from catalog.models import (
    Asset,
    Contribution,
    LegacyKnowledgeMapping,
    Page,
    Person,
    QueryLexiconChangeEvent,
    QueryLexiconEntry,
    QueryLexiconGeneration,
    QueryLexiconState,
    SemanticChunk,
    SemanticIndexVersion,
    Work,
    WorkKnowledgeRelation,
)
from catalog.services.query_lexicon.sync import (
    dry_run_reconciliation,
    rebuild_query_lexicon,
)
from catalog.services.query_lexicon.normalization import detect_language, normalize_term
from catalog.services.semantic_chunks import CHUNK_VERSION, PARSER_VERSION
from catalog.services.semantic_indexing import (
    ensure_semantic_index,
    semantic_documents,
    semantic_index_document_count,
    semantic_index_version_runtime,
)
from catalog.services.semantic_search_benchmark import (
    audit_historical_chunk_languages,
    audit_query_lexicon_coverage,
    content_hash,
    run_shadow_query_pool,
)
from catalog.services.semantic_search_v2_config import search_v2_config_snapshot
from ingestion.services.indexing import _headers, _wait_task


EVALUATION_BUNDLE_SCHEMA = "stl-semantic-search-evaluation-bundle-v1"
EVALUATION_MANIFEST_SCHEMA = "stl-semantic-search-evaluation-manifest-v1"
EVALUATION_EXPORT_VERSION = "task2b0.5-search-only-export-v1"
EVALUATION_INDEX_PREFIX = "semantic_passages_eval_"
EVALUATION_VERSION_NAMESPACE = UUID("f708a5d0-3ce8-4c7e-b2b1-80b8472926d1")
SNAPSHOT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
DEFAULT_EVALUATION_DOCUMENT_BATCH_SIZE = 128
MAX_EVALUATION_DOCUMENT_BATCH_SIZE = 1000


class EvaluationEnvironmentError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExportSpec:
    label: str
    filename: str


# The order is also the import order. QueryLexicon derived tables, task state,
# accounts, sessions, reading data and user activity are intentionally absent.
EXPORT_SPECS = (
    ExportSpec("catalog.discipline", "catalog.discipline.jsonl"),
    ExportSpec("catalog.theoryschool", "catalog.theoryschool.jsonl"),
    ExportSpec("catalog.topic", "catalog.topic.jsonl"),
    ExportSpec("catalog.concept", "catalog.concept.jsonl"),
    ExportSpec("catalog.subdiscipline", "catalog.subdiscipline.jsonl"),
    ExportSpec("catalog.person", "catalog.person.jsonl"),
    ExportSpec("catalog.personnamevariant", "catalog.personnamevariant.jsonl"),
    ExportSpec("catalog.knowledgenode", "catalog.knowledgenode.jsonl"),
    ExportSpec("catalog.knowledgenodealias", "catalog.knowledgenodealias.jsonl"),
    ExportSpec("catalog.legacyknowledgemapping", "catalog.legacyknowledgemapping.jsonl"),
    ExportSpec("catalog.work", "catalog.work.jsonl"),
    ExportSpec("catalog.edition", "catalog.edition.jsonl"),
    ExportSpec("catalog.asset", "catalog.asset.jsonl"),
    ExportSpec("catalog.page", "catalog.page.jsonl"),
    ExportSpec("catalog.contribution", "catalog.contribution.jsonl"),
    ExportSpec("catalog.workknowledgerelation", "catalog.workknowledgerelation.jsonl"),
    ExportSpec("catalog.semanticchunk", "catalog.semanticchunk.jsonl"),
)

MIGRATION_SEEDED_AUTHORITY_LABELS = frozenset(
    {
        "catalog.discipline",
        "catalog.theoryschool",
        "catalog.topic",
        "catalog.concept",
        "catalog.subdiscipline",
        "catalog.knowledgenode",
        "catalog.knowledgenodealias",
        "catalog.legacyknowledgemapping",
    }
)


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def validate_snapshot_id(snapshot_id: str) -> str:
    value = str(snapshot_id or "").strip().casefold()
    if not SNAPSHOT_ID_PATTERN.fullmatch(value):
        raise EvaluationEnvironmentError(
            "snapshot id 只能使用小写字母、数字、下划线和连字符，长度为 3 至 64。"
        )
    return value


def evaluation_index_uid(snapshot_id: str) -> str:
    return f"{EVALUATION_INDEX_PREFIX}{validate_snapshot_id(snapshot_id).replace('-', '_')}"


def _normalized_service_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if not parsed.scheme or not parsed.hostname:
        return ""
    host = parsed.hostname.casefold()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host
    if parsed.port is not None:
        netloc = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme.casefold(), netloc, parsed.path.rstrip("/"), "", ""))


def _evaluation_shaped_host(value: str) -> bool:
    host = (urlsplit(value).hostname or "").casefold()
    return host in {"localhost", "127.0.0.1", "::1"} or "eval" in host


def evaluation_write_guard(snapshot_id: str) -> dict:
    """Refuse evaluation writes unless every namespace is explicitly isolated."""

    snapshot_id = validate_snapshot_id(snapshot_id)
    if not getattr(settings, "SEMANTIC_SEARCH_EVALUATION_MODE", False):
        raise EvaluationEnvironmentError(
            "SEMANTIC_SEARCH_EVALUATION_MODE 未开启，拒绝评测环境写入。"
        )
    if connection.vendor != "postgresql":
        raise EvaluationEnvironmentError("正式评测环境必须使用 PostgreSQL。")

    actual_name = str(connection.settings_dict.get("NAME") or "")
    confirmed_name = str(
        getattr(settings, "SEMANTIC_SEARCH_EVALUATION_DATABASE_NAME", "") or ""
    )
    database_host = str(connection.settings_dict.get("HOST") or "localhost").casefold()
    if not confirmed_name or actual_name != confirmed_name:
        raise EvaluationEnvironmentError("评测数据库名称确认值与当前连接不一致。")
    if "eval" not in actual_name.casefold():
        raise EvaluationEnvironmentError("评测数据库名称必须明确包含 eval。")
    if database_host not in {"", "localhost", "127.0.0.1", "::1"} and "eval" not in database_host:
        raise EvaluationEnvironmentError("评测 PostgreSQL host 未体现隔离命名。")

    actual_meili = _normalized_service_url(settings.MEILISEARCH_URL)
    confirmed_meili = _normalized_service_url(
        getattr(settings, "SEMANTIC_SEARCH_EVALUATION_MEILISEARCH_URL", "")
    )
    if not confirmed_meili or actual_meili != confirmed_meili:
        raise EvaluationEnvironmentError("评测 Meilisearch URL 确认值与当前设置不一致。")
    if not _evaluation_shaped_host(actual_meili):
        raise EvaluationEnvironmentError("评测 Meilisearch host 必须是本机或包含 eval。")
    if getattr(settings, "SEMANTIC_SEARCH_V2_ENABLED", False):
        raise EvaluationEnvironmentError("评测环境不得开启公开 V2 feature flag。")

    expected_uid = evaluation_index_uid(snapshot_id)
    with connection.cursor() as cursor:
        cursor.execute("SHOW server_version")
        server_version = str(cursor.fetchone()[0])
    return {
        "snapshot_id": snapshot_id,
        "database_vendor": connection.vendor,
        "database_name": actual_name,
        "database_host": database_host or "local-socket",
        "postgresql_version": server_version,
        "meilisearch_url": actual_meili,
        "evaluation_index_uid": expected_uid,
        "public_v2_enabled": False,
    }


def _migration_state() -> dict:
    loader = MigrationLoader(connection, ignore_no_migrations=True)
    heads = sorted(f"{app}.{name}" for app, name in loader.graph.leaf_nodes())
    applied = MigrationRecorder(connection).applied_migrations()
    missing = sorted(
        head
        for head in heads
        if tuple(head.split(".", 1)) not in applied
    )
    return {
        "heads": heads,
        "applied_count": len(applied),
        "missing_heads": missing,
        "current": not missing,
        "catalog_head": next(
            (head for head in heads if head.startswith("catalog.")),
            None,
        ),
    }


def _database_fingerprint() -> str:
    settings_dict = connection.settings_dict
    value = {
        "engine": settings_dict.get("ENGINE"),
        "name": settings_dict.get("NAME"),
        "host": settings_dict.get("HOST"),
        "port": settings_dict.get("PORT"),
    }
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_ignored_bundle_location(path: Path) -> None:
    repository_root = Path(settings.BASE_DIR).resolve().parent
    try:
        path.relative_to(repository_root)
    except ValueError:
        return
    allowed_roots = [
        repository_root / "data",
        repository_root / "output",
        repository_root / "tmp",
    ]
    if not any(root == path or root in path.parents for root in allowed_roots):
        raise EvaluationEnvironmentError(
            "evaluation bundle 含馆藏文本。仓库内输出只能放在已忽略的 data、output 或 tmp。"
        )


def _secret_free_index_snapshot(version: SemanticIndexVersion) -> dict:
    raw = dict(version.config_snapshot) if isinstance(version.config_snapshot, dict) else {}
    allowed = {
        "enabled",
        "engine",
        "provider",
        "embedder_name",
        "model",
        "model_repo_id",
        "model_local_path",
        "model_revision",
        "dimensions",
        "pooling",
        "offline_mode",
        "semantic_ratio",
        "reranker",
        "query_rewrite_enabled",
        "max_results_per_work",
        "api_key_configured",
        "external_text_warning",
        "saved_configuration_version",
        "protocol_version",
        "parser_version",
        "chunk_version",
        "language_detector",
        "document_template",
    }
    snapshot = {key: raw.get(key) for key in allowed if key in raw}
    viewpoint_v2 = raw.get("viewpoint_v2")
    if isinstance(viewpoint_v2, dict):
        allowed_v2 = {
            "enabled",
            "profile",
            "dense_top_k",
            "sparse_top_k",
            "fusion_top_k",
            "rerank_top_k",
            "final_top_k",
            "query_expansion_enabled",
            "query_expansion_max",
            "rerank_provider",
            "rerank_model",
            "rerank_service_configured",
        }
        snapshot["viewpoint_v2"] = {
            key: viewpoint_v2.get(key)
            for key in allowed_v2
            if key in viewpoint_v2
        }
    for key in ("service_url", "endpoint"):
        value = _normalized_service_url(str(raw.get(key) or ""))
        if value:
            snapshot[key] = value
    snapshot["model_local_path"] = ""
    return {
        "source_id": str(version.id),
        "source_uid": version.uid,
        "source_status": version.status,
        "source_created_at": version.created_at.isoformat(),
        "provider": version.provider,
        "model_repo_id": version.model_repo_id,
        "model_revision": version.model_revision,
        "dimensions": version.dimensions,
        "pooling": version.pooling,
        "document_template": version.document_template,
        "config_snapshot": snapshot,
        "config_hash": content_hash(snapshot),
        "document_count": version.document_count,
        "expected_document_count": version.expected_document_count,
    }


def _resolve_index_version(value: str) -> SemanticIndexVersion:
    version = SemanticIndexVersion.objects.filter(uid=str(value)).first()
    if version is None:
        try:
            version = SemanticIndexVersion.objects.filter(pk=UUID(str(value))).first()
        except (TypeError, ValueError, AttributeError):
            version = None
    if version is None:
        raise EvaluationEnvironmentError(f"找不到 SemanticIndexVersion：{value}")
    if version.status not in {
        SemanticIndexVersion.Status.READY,
        SemanticIndexVersion.Status.ACTIVE,
        SemanticIndexVersion.Status.RETIRED,
    }:
        raise EvaluationEnvironmentError("只能从 ready、active 或 retired 语义索引导出。")
    if not semantic_index_version_runtime(version):
        raise EvaluationEnvironmentError("SemanticIndexVersion 缺少冻结 config_snapshot。")
    return version


def _snapshot_querysets(version: SemanticIndexVersion) -> tuple[dict[str, models.QuerySet], dict]:
    runtime = semantic_index_version_runtime(version) or {}
    parser_version = str(runtime.get("parser_version") or PARSER_VERSION)
    chunk_version = str(runtime.get("chunk_version") or CHUNK_VERSION)
    model_name = str(
        version.model_repo_id
        or runtime.get("model_repo_id")
        or runtime.get("model")
        or ""
    )
    chunks = SemanticChunk._base_manager.filter(
        parser_version=parser_version,
        chunk_version=chunk_version,
        embedding_model=model_name,
        index_status=SemanticChunk.IndexStatus.READY,
        asset__kind=Asset.Kind.NORMALIZED,
        asset__status=Asset.Status.READY,
        asset__is_current=True,
    ).order_by("pk")
    chunk_count = chunks.count()
    frozen_count = int(version.document_count or version.expected_document_count or 0)
    if chunk_count < 1:
        raise EvaluationEnvironmentError("源数据库没有可导出的真实 SemanticChunk。")
    if frozen_count < 1:
        raise EvaluationEnvironmentError("SemanticIndexVersion 没有冻结文档数。")
    if chunk_count != frozen_count:
        raise EvaluationEnvironmentError(
            f"按冻结 parser、chunk 和 model 解析得到 {chunk_count} 个 chunk，"
            f"SemanticIndexVersion 记录为 {frozen_count}。必须先在隔离副本中核对差异。"
        )

    asset_ids = list(chunks.values_list("asset_id", flat=True).distinct())
    assets = Asset._base_manager.filter(pk__in=asset_ids).order_by("pk")
    edition_ids = list(assets.values_list("edition_id", flat=True).distinct())
    editions = apps.get_model("catalog", "Edition")._base_manager.filter(
        pk__in=edition_ids
    ).order_by("pk")
    work_ids = list(editions.values_list("work_id", flat=True).distinct())
    works = Work._base_manager.filter(pk__in=work_ids).order_by("pk")
    selected = {
        "work_ids": {str(value) for value in work_ids},
        "asset_ids": {str(value) for value in asset_ids},
    }
    querysets = {
        "catalog.discipline": apps.get_model("catalog", "Discipline")._base_manager.all().order_by("pk"),
        "catalog.theoryschool": apps.get_model("catalog", "TheorySchool")._base_manager.all().order_by("pk"),
        "catalog.topic": apps.get_model("catalog", "Topic")._base_manager.all().order_by("pk"),
        "catalog.concept": apps.get_model("catalog", "Concept")._base_manager.all().order_by("pk"),
        "catalog.subdiscipline": apps.get_model("catalog", "Subdiscipline")._base_manager.all().order_by("pk"),
        "catalog.person": Person._base_manager.all().order_by("pk"),
        "catalog.personnamevariant": apps.get_model("catalog", "PersonNameVariant")._base_manager.all().order_by("pk"),
        "catalog.knowledgenode": apps.get_model("catalog", "KnowledgeNode")._base_manager.all().order_by("pk"),
        "catalog.knowledgenodealias": apps.get_model("catalog", "KnowledgeNodeAlias")._base_manager.all().order_by("pk"),
        "catalog.legacyknowledgemapping": LegacyKnowledgeMapping._base_manager.all().order_by("pk"),
        "catalog.work": works,
        "catalog.edition": editions,
        "catalog.asset": assets,
        "catalog.page": Page._base_manager.filter(asset_id__in=asset_ids).order_by("pk"),
        "catalog.contribution": Contribution._base_manager.filter(edition_id__in=edition_ids).order_by("pk"),
        "catalog.workknowledgerelation": WorkKnowledgeRelation._base_manager.filter(work_id__in=work_ids).order_by("pk"),
        "catalog.semanticchunk": chunks,
    }
    return querysets, selected


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def _serialize_instance(instance, selected: dict) -> dict:
    label = instance._meta.label_lower
    fields: dict[str, object] = {}
    for field in instance._meta.concrete_fields:
        value = getattr(instance, field.attname)
        related_model = getattr(getattr(field, "remote_field", None), "model", None)
        if related_model is not None and related_model._meta.label_lower == settings.AUTH_USER_MODEL.casefold():
            value = None
        if isinstance(field, models.ImageField):
            value = ""
        if label == "catalog.work" and field.attname in {"cover", "recommendation_image"}:
            value = ""
        if label == "catalog.work" and field.attname == "translation_of_id":
            value = value if str(value or "") in selected["work_ids"] else None
        if label == "catalog.edition" and field.attname == "publisher_authority_id":
            value = None
        if label == "catalog.edition" and field.attname == "citation_data":
            value = {}
        if label == "catalog.asset":
            if field.attname == "file":
                value = f"evaluation/assets/{instance.pk}.pdf"
            elif field.attname == "original_filename":
                value = ""
            elif field.attname == "sha256":
                value = sha256(f"evaluation-asset:{instance.pk}".encode("utf-8")).hexdigest()
            elif field.attname == "byte_size":
                value = 0
            elif field.attname == "source_asset_id":
                value = None
            elif field.attname == "rights_note":
                value = ""
            elif field.attname == "validation_details":
                value = {}
        if label == "catalog.workknowledgerelation":
            if field.attname == "evidence_asset_id":
                value = value if str(value or "") in selected["asset_ids"] else None
            elif field.attname in {
                "source",
                "evidence_printed_label",
                "evidence_text",
            }:
                value = ""
            elif field.attname == "reviewed_at":
                value = None
        if label == "catalog.contribution" and field.attname == "source":
            value = ""
        if label == "catalog.semanticchunk" and field.attname == "index_error":
            value = ""
        fields[field.attname] = _json_value(value)
    return {"model": label, "pk": str(instance.pk), "fields": fields}


def _write_queryset(path: Path, queryset, selected: dict, *, batch_size: int) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for instance in queryset.iterator(chunk_size=max(100, int(batch_size))):
            handle.write(
                json.dumps(
                    _serialize_instance(instance, selected),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
            count += 1
    return count


def _source_lexicon_snapshot() -> dict:
    state = QueryLexiconState.objects.select_related("active_generation").filter(
        key="default"
    ).first()
    if state is None:
        return {"available": False, "revision": None, "generation": None}
    return {
        "available": True,
        "revision": state.revision,
        "generation": str(state.active_generation_id),
        "entry_count": state.active_generation.entry_count,
        "content_hash": state.active_generation.effective_content_hash,
    }


def export_evaluation_bundle(
    *,
    output_dir: str | Path,
    snapshot_id: str,
    index_version_value: str,
    source_kind: str,
    batch_size: int = 1000,
) -> dict:
    """Create a search-only bundle inside one PostgreSQL read-only snapshot."""

    snapshot_id = validate_snapshot_id(snapshot_id)
    if connection.vendor != "postgresql":
        raise EvaluationEnvironmentError("正式评测快照只能从 PostgreSQL 导出。")
    if source_kind not in {"backup_restore", "read_replica", "production_readonly"}:
        raise EvaluationEnvironmentError("source kind 必须明确标记数据来源。")
    output = Path(output_dir).resolve()
    _require_ignored_bundle_location(output)
    if output.exists():
        raise EvaluationEnvironmentError("输出目录已经存在。请为每个 snapshot 使用新目录。")
    output.parent.mkdir(parents=True, exist_ok=True)

    temporary_root = Path(
        tempfile.mkdtemp(prefix=f"{snapshot_id}-", dir=str(output.parent))
    )
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                cursor.execute("SHOW transaction_read_only")
                read_only = str(cursor.fetchone()[0]).casefold() == "on"
                cursor.execute("SHOW transaction_isolation")
                isolation = str(cursor.fetchone()[0])
                cursor.execute("SHOW server_version")
                server_version = str(cursor.fetchone()[0])
            if not read_only:
                raise EvaluationEnvironmentError("无法确认导出事务为 read only。")
            migrations = _migration_state()
            if not migrations["current"]:
                raise EvaluationEnvironmentError(
                    f"源副本 schema 未到当前 migration head：{migrations['missing_heads']}"
                )
            version = _resolve_index_version(index_version_value)
            querysets, selected = _snapshot_querysets(version)
            counts: dict[str, int] = {}
            files: list[dict] = []
            for spec in EXPORT_SPECS:
                path = temporary_root / spec.filename
                row_count = _write_queryset(
                    path,
                    querysets[spec.label],
                    selected,
                    batch_size=batch_size,
                )
                counts[spec.label] = row_count
                files.append(
                    {
                        "path": spec.filename,
                        "model": spec.label,
                        "rows": row_count,
                        "bytes": path.stat().st_size,
                        "sha256": file_sha256(path),
                    }
                )
            index_snapshot = _secret_free_index_snapshot(version)
            manifest = {
                "schema": EVALUATION_BUNDLE_SCHEMA,
                "export_version": EVALUATION_EXPORT_VERSION,
                "snapshot_id": snapshot_id,
                "created_at": timezone.now().isoformat(),
                "source": {
                    "kind": source_kind,
                    "database_fingerprint": _database_fingerprint(),
                    "postgresql_version": server_version,
                    "transaction_read_only": read_only,
                    "transaction_isolation": isolation,
                },
                "migrations": migrations,
                "counts": counts,
                "work_count": counts.get("catalog.work", 0),
                "page_count": counts.get("catalog.page", 0),
                "semantic_chunk_count": counts.get("catalog.semanticchunk", 0),
                "source_query_lexicon": _source_lexicon_snapshot(),
                "source_semantic_index_version": index_snapshot,
                "evaluation_index_uid": evaluation_index_uid(snapshot_id),
                "will_rebuild_query_lexicon": True,
                "will_reembed_evaluation_index": True,
                "contains_authentication_data": False,
                "contains_reader_private_data": False,
                "contains_original_files": False,
                "files": files,
            }
            manifest["config_hash"] = content_hash(
                {
                    "export_version": EVALUATION_EXPORT_VERSION,
                    "migrations": migrations["heads"],
                    "semantic_index": index_snapshot,
                    "files": [
                        {"path": row["path"], "sha256": row["sha256"]}
                        for row in files
                    ],
                }
            )
            (temporary_root / "bundle-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
        os.replace(temporary_root, output)
        return manifest
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise


def load_bundle_manifest(bundle_dir: str | Path) -> tuple[Path, dict]:
    root = Path(bundle_dir).resolve()
    manifest_path = root / "bundle-manifest.json"
    if not manifest_path.is_file():
        raise EvaluationEnvironmentError("bundle-manifest.json 不存在。")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationEnvironmentError(f"无法读取 bundle manifest：{exc}") from exc
    if manifest.get("schema") != EVALUATION_BUNDLE_SCHEMA:
        raise EvaluationEnvironmentError("evaluation bundle schema 不兼容。")
    for row in manifest.get("files") or []:
        relative = Path(str(row.get("path") or ""))
        path = (root / relative).resolve()
        if root != path.parent and root not in path.parents:
            raise EvaluationEnvironmentError("bundle file 路径越界。")
        if not path.is_file():
            raise EvaluationEnvironmentError(f"bundle file 缺失：{relative}")
        if file_sha256(path) != row.get("sha256"):
            raise EvaluationEnvironmentError(f"bundle file checksum 不一致：{relative}")
    return root, manifest


def _field_value(field, value):
    if value is None:
        return None
    if isinstance(field, models.ForeignKey):
        return field.target_field.to_python(value)
    return field.to_python(value)


def _load_model_file(root: Path, spec: ExportSpec, *, batch_size: int) -> int:
    model = apps.get_model(spec.label)
    field_map = {field.attname: field for field in model._meta.concrete_fields}
    objects = []
    loaded = 0
    path = root / spec.filename
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise EvaluationEnvironmentError(
                    f"{spec.filename} 第 {line_number} 行无效：{exc.msg}"
                ) from exc
            if record.get("model") != spec.label:
                raise EvaluationEnvironmentError(
                    f"{spec.filename} 第 {line_number} 行 model 不匹配。"
                )
            source_fields = record.get("fields")
            if not isinstance(source_fields, dict):
                raise EvaluationEnvironmentError(
                    f"{spec.filename} 第 {line_number} 行缺少 fields。"
                )
            values = {
                name: _field_value(field_map[name], value)
                for name, value in source_fields.items()
                if name in field_map
            }
            values[model._meta.pk.attname] = model._meta.pk.to_python(record["pk"])
            objects.append(model(**values))
            if len(objects) >= batch_size:
                model._base_manager.bulk_create(objects, batch_size=batch_size)
                loaded += len(objects)
                objects.clear()
    if objects:
        model._base_manager.bulk_create(objects, batch_size=batch_size)
        loaded += len(objects)
    return loaded


def _assert_fresh_evaluation_database() -> None:
    occupied = []
    for spec in EXPORT_SPECS:
        if spec.label in MIGRATION_SEEDED_AUTHORITY_LABELS:
            continue
        model = apps.get_model(spec.label)
        if model._base_manager.exists():
            occupied.append(spec.label)
    if SemanticIndexVersion._base_manager.exists():
        occupied.append("catalog.semanticindexversion")
    state = QueryLexiconState.objects.select_related("active_generation").filter(
        key="default"
    ).first()
    if (
        state is None
        or state.revision != 0
        or state.active_generation.entry_count != 0
        or QueryLexiconGeneration.objects.count() != 1
        or QueryLexiconEntry.objects.exists()
        or QueryLexiconChangeEvent.objects.exists()
    ):
        occupied.append("catalog.querylexicon-derived-state")
    if occupied:
        raise EvaluationEnvironmentError(
            "评测数据库不是空的。请删除并重建 evaluation PostgreSQL volume："
            + ", ".join(occupied[:8])
        )

    private_counts = _private_data_counts()
    nonzero_private = [label for label, count in private_counts.items() if count]
    if nonzero_private:
        raise EvaluationEnvironmentError(
            "评测数据库含有账户、session 或读者私有数据："
            + ", ".join(nonzero_private[:8])
        )


def _private_data_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for app_label in ("accounts", "reading", "sessions", "token_blacklist"):
        app_config = apps.get_app_config(app_label)
        for model in app_config.get_models():
            counts[model._meta.label_lower] = model._base_manager.count()
    return counts


def _clear_migration_seed_authorities() -> dict[str, int]:
    """Remove only deterministic catalog seeds before loading source authority.

    Migration 0013 creates authority rows in every fresh database. They are not
    user data, and keeping them would make a source snapshot collide on unique
    names and slugs. The evaluation write guard is checked before this helper is
    called.
    """

    cleared: dict[str, int] = {}
    for label in (
        "catalog.legacyknowledgemapping",
        "catalog.knowledgenodealias",
        "catalog.knowledgenode",
        "catalog.subdiscipline",
        "catalog.concept",
        "catalog.topic",
        "catalog.theoryschool",
        "catalog.discipline",
    ):
        model = apps.get_model(label)
        deleted, _details = model._base_manager.all().delete()
        cleared[label] = int(deleted)
    return cleared


def import_evaluation_bundle(
    *,
    bundle_dir: str | Path,
    snapshot_id: str,
    batch_size: int = 1000,
) -> dict:
    guard = evaluation_write_guard(snapshot_id)
    root, manifest = load_bundle_manifest(bundle_dir)
    if manifest.get("snapshot_id") != guard["snapshot_id"]:
        raise EvaluationEnvironmentError("bundle snapshot id 与当前评测环境不一致。")
    if manifest.get("evaluation_index_uid") != guard["evaluation_index_uid"]:
        raise EvaluationEnvironmentError("bundle evaluation index UID 不一致。")
    migrations = _migration_state()
    if not migrations["current"]:
        raise EvaluationEnvironmentError("evaluation DB 尚未应用全部 migrations。")
    if migrations["heads"] != (manifest.get("migrations") or {}).get("heads"):
        raise EvaluationEnvironmentError("bundle 与 evaluation DB 的 migration heads 不一致。")
    _assert_fresh_evaluation_database()

    imported: dict[str, int] = {}
    with transaction.atomic():
        cleared_migration_seeds = _clear_migration_seed_authorities()
        with connection.constraint_checks_disabled():
            for spec in EXPORT_SPECS:
                imported[spec.label] = _load_model_file(
                    root,
                    spec,
                    batch_size=max(100, int(batch_size)),
                )
        connection.check_constraints()
        for label, expected in (manifest.get("counts") or {}).items():
            if imported.get(label) != int(expected):
                raise EvaluationEnvironmentError(
                    f"{label} 导入数量为 {imported.get(label)}，预期为 {expected}。"
                )

        dry_run = dry_run_reconciliation()
        lexicon = rebuild_query_lexicon()
        source_version = manifest["source_semantic_index_version"]
        runtime = dict(source_version.get("config_snapshot") or {})
        version = SemanticIndexVersion._base_manager.create(
            id=uuid5(EVALUATION_VERSION_NAMESPACE, guard["snapshot_id"]),
            uid=guard["evaluation_index_uid"],
            provider=str(source_version.get("provider") or runtime.get("provider") or ""),
            model_repo_id=str(source_version.get("model_repo_id") or runtime.get("model_repo_id") or ""),
            model_local_path="",
            model_revision=str(source_version.get("model_revision") or runtime.get("model_revision") or ""),
            dimensions=source_version.get("dimensions"),
            pooling=str(source_version.get("pooling") or runtime.get("pooling") or ""),
            document_template=str(source_version.get("document_template") or runtime.get("document_template") or ""),
            config_snapshot=runtime,
            document_count=0,
            expected_document_count=int(manifest["semantic_chunk_count"]),
            validation_details={
                "snapshot_id": guard["snapshot_id"],
                "source_version_id": source_version.get("source_id"),
                "source_version_uid": source_version.get("source_uid"),
                "build_mode": "evaluation_reembed",
                "production_activation_allowed": False,
                "historical_language_metadata_preserved": True,
            },
            status=SemanticIndexVersion.Status.BUILDING,
        )
    state = QueryLexiconState.objects.select_related("active_generation").get(key="default")
    return {
        "guard": guard,
        "snapshot_id": guard["snapshot_id"],
        "imported": imported,
        "cleared_migration_seeds": cleared_migration_seeds,
        "query_lexicon_dry_run": dry_run,
        "query_lexicon_rebuild": lexicon,
        "query_lexicon_revision": state.revision,
        "query_lexicon_generation": str(state.active_generation_id),
        "semantic_index_version": {
            "id": str(version.id),
            "uid": version.uid,
            "status": version.status,
            "expected_document_count": version.expected_document_count,
        },
    }


def _meili_index_stats(index_uid: str) -> dict | None:
    response = httpx.get(
        f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{index_uid}/stats",
        headers=_headers(),
        timeout=15,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _index_evaluation_asset_in_batches(
    asset: Asset,
    *,
    version: SemanticIndexVersion,
    runtime: dict,
    document_batch_size: int,
) -> dict:
    """Idempotently upsert one asset without mutating frozen chunk metadata."""

    documents = semantic_documents(asset, runtime_config=runtime)
    if not documents:
        raise EvaluationEnvironmentError(
            f"asset {asset.id} 没有可写入 evaluation index 的 SemanticChunk。"
        )
    batch_size = min(
        MAX_EVALUATION_DOCUMENT_BATCH_SIZE,
        max(1, int(document_batch_size)),
    )
    batches = 0
    for offset in range(0, len(documents), batch_size):
        batch = documents[offset : offset + batch_size]
        response = httpx.post(
            f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{version.uid}/documents",
            headers=_headers(),
            json=batch,
            timeout=max(30, settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        _wait_task(
            response.json(),
            timeout=settings.SEMANTIC_INDEX_TASK_TIMEOUT_SECONDS,
        )
        batches += 1
    return {
        "backend": "meilisearch",
        "index_uid": version.uid,
        "documents": len(documents),
        "batches": batches,
        "document_batch_size": batch_size,
    }


def build_evaluation_meilisearch_index(
    *,
    snapshot_id: str,
    resume: bool = False,
    document_batch_size: int = DEFAULT_EVALUATION_DOCUMENT_BATCH_SIZE,
) -> dict:
    guard = evaluation_write_guard(snapshot_id)
    version = SemanticIndexVersion.objects.filter(uid=guard["evaluation_index_uid"]).first()
    if version is None:
        raise EvaluationEnvironmentError("evaluation SemanticIndexVersion 不存在。")
    if version.status not in {
        SemanticIndexVersion.Status.BUILDING,
        SemanticIndexVersion.Status.FAILED,
    }:
        raise EvaluationEnvironmentError("只有 building 或 failed evaluation index 可以建立。")
    runtime = semantic_index_version_runtime(version)
    if not runtime:
        raise EvaluationEnvironmentError("evaluation SemanticIndexVersion 缺少 runtime snapshot。")
    before = _meili_index_stats(version.uid)
    before_count = int((before or {}).get("numberOfDocuments") or 0)
    if before_count and not resume:
        raise EvaluationEnvironmentError(
            "evaluation Meilisearch index 已有文档。使用全新 volume，或确认后使用 --resume。"
        )

    parser_version = str(runtime.get("parser_version") or PARSER_VERSION)
    chunk_version = str(runtime.get("chunk_version") or CHUNK_VERSION)
    model_name = str(
        version.model_repo_id
        or runtime.get("model_repo_id")
        or runtime.get("model")
        or ""
    )
    assets = Asset.objects.filter(
        semantic_chunks__parser_version=parser_version,
        semantic_chunks__chunk_version=chunk_version,
        semantic_chunks__embedding_model=model_name,
        kind=Asset.Kind.NORMALIZED,
        status=Asset.Status.READY,
        is_current=True,
    ).select_related("edition__work").distinct().order_by("pk")
    expected = SemanticChunk.objects.filter(
        asset__in=assets,
        parser_version=parser_version,
        chunk_version=chunk_version,
        embedding_model=model_name,
    ).count()
    if expected != version.expected_document_count or expected < 1:
        raise EvaluationEnvironmentError(
            f"evaluation DB 可建立 {expected} 个文档，版本预期为 {version.expected_document_count}。"
        )

    ensure_semantic_index(runtime, index_uid=version.uid)
    indexed = 0
    asset_count = 0
    batch_count = 0
    try:
        for asset in assets.iterator(chunk_size=50):
            result = _index_evaluation_asset_in_batches(
                asset,
                version=version,
                runtime=runtime,
                document_batch_size=document_batch_size,
            )
            if result.get("backend") != "meilisearch":
                raise EvaluationEnvironmentError(
                    f"asset {asset.id} 未写入 evaluation Meilisearch：{result.get('warning') or result}"
                )
            indexed += int(result.get("documents") or 0)
            batch_count += int(result.get("batches") or 0)
            asset_count += 1
        actual = semantic_index_document_count(version.uid)
        if actual != expected:
            raise EvaluationEnvironmentError(
                f"evaluation Meilisearch 文档数为 {actual}，预期为 {expected}。"
            )
        details = {
            **(version.validation_details or {}),
            "built_at": timezone.now().isoformat(),
            "actual_document_count": actual,
            "asset_count": asset_count,
            "batch_count": batch_count,
            "document_batch_size": min(
                MAX_EVALUATION_DOCUMENT_BATCH_SIZE,
                max(1, int(document_batch_size)),
            ),
            "reembedding_performed": True,
            "production_index_modified": False,
        }
        SemanticIndexVersion.objects.filter(pk=version.pk).update(
            status=SemanticIndexVersion.Status.READY,
            document_count=actual,
            validation_details=details,
            error_message="",
            updated_at=timezone.now(),
        )
        return {
            "guard": guard,
            "index_uid": version.uid,
            "asset_count": asset_count,
            "batch_count": batch_count,
            "document_batch_size": min(
                MAX_EVALUATION_DOCUMENT_BATCH_SIZE,
                max(1, int(document_batch_size)),
            ),
            "documents_written_this_run": indexed,
            "document_count": actual,
            "reembedding_performed": True,
            "semantic_index_activated": False,
            "production_index_modified": False,
        }
    except Exception as exc:
        SemanticIndexVersion.objects.filter(pk=version.pk).update(
            status=SemanticIndexVersion.Status.FAILED,
            error_message=str(exc)[:4000],
            updated_at=timezone.now(),
        )
        raise


def _chunk_location_audit() -> dict:
    chunks = SemanticChunk.objects.annotate(
        start_page_exists=Exists(
            Page.objects.filter(asset_id=OuterRef("asset_id"), index=OuterRef("page_start"))
        ),
        end_page_exists=Exists(
            Page.objects.filter(asset_id=OuterRef("asset_id"), index=OuterRef("page_end"))
        ),
    )
    total = chunks.count()
    return {
        "total": total,
        "missing_document_id": chunks.filter(document_id="").count(),
        "work_asset_mismatch": chunks.exclude(work_id=F("asset__edition__work_id")).count(),
        "invalid_page_range": chunks.filter(page_start__gt=F("page_end")).count(),
        "missing_start_page": chunks.filter(start_page_exists=False).count(),
        "missing_end_page": chunks.filter(end_page_exists=False).count(),
    }


def _smoke_record(query: str, query_language: str) -> dict:
    language = str(query_language or "").casefold()
    if language not in {"zh", "en", "mixed"}:
        raise EvaluationEnvironmentError("smoke query language 必须是 zh、en 或 mixed。")
    direction = "mixed" if language == "mixed" else f"{language}_to_{language}"
    return {
        "query_id": "evaluation-smoke-query",
        "query": str(query).strip(),
        "query_language": language,
        "direction": direction,
        "query_type": "conceptual",
        "expected_entities": [],
        "gold_judgments": [],
        "notes": "只验证四路 retrieval，不生成 gold。",
        "split": "diagnostic",
        "filters": {},
    }


def audit_evaluation_environment(
    *,
    snapshot_id: str,
    bundle_dir: str | Path | None = None,
    smoke_query: str | None = None,
    smoke_query_language: str = "zh",
) -> dict:
    guard = evaluation_write_guard(snapshot_id)
    migrations = _migration_state()
    version = SemanticIndexVersion.objects.filter(uid=guard["evaluation_index_uid"]).first()
    state = QueryLexiconState.objects.select_related("active_generation").filter(
        key="default"
    ).first()
    stats = _meili_index_stats(guard["evaluation_index_uid"])
    counts = {
        "works": Work.objects.count(),
        "pages": Page.objects.count(),
        "semantic_chunks": SemanticChunk.objects.count(),
    }
    private_counts = _private_data_counts()
    location = _chunk_location_audit()
    smoke = None
    if smoke_query:
        if version is None:
            raise EvaluationEnvironmentError("无法执行 smoke query，索引版本不存在。")
        smoke_pool = run_shadow_query_pool(
            _smoke_record(smoke_query, smoke_query_language),
            version,
            pool_top_k=5,
        )
        smoke = {
            "query": smoke_query,
            "systems": {
                name: {
                    "result_count": values.get("result_count"),
                    "fallback_used": values.get("fallback_used"),
                    "fallback_reason": values.get("fallback_reason"),
                }
                for name, values in smoke_pool["systems"].items()
            },
            "unique_candidate_count": smoke_pool["candidate_count"],
        }
    bundle = None
    if bundle_dir:
        _root, bundle = load_bundle_manifest(bundle_dir)
    meili_count = int((stats or {}).get("numberOfDocuments") or 0)
    ready = bool(
        migrations["current"]
        and counts["semantic_chunks"] > 0
        and version is not None
        and version.status == SemanticIndexVersion.Status.READY
        and state is not None
        and stats is not None
        and meili_count == counts["semantic_chunks"]
        and not any(private_counts.values())
        and all(value == 0 for key, value in location.items() if key != "total")
        and smoke is not None
        and all(
            int(values.get("result_count") or 0) > 0
            and (name == "lexical" or not values.get("fallback_used"))
            for name, values in smoke["systems"].items()
        )
    )
    return {
        "schema": EVALUATION_MANIFEST_SCHEMA,
        "created_at": timezone.now().isoformat(),
        "snapshot_id": guard["snapshot_id"],
        "ready_for_pilot": ready,
        "guard": guard,
        "migrations": migrations,
        "counts": counts,
        "private_data": {
            "counts": private_counts,
            "all_zero": not any(private_counts.values()),
        },
        "chunk_location_integrity": location,
        "query_lexicon": {
            "available": state is not None,
            "revision": state.revision if state else None,
            "generation": str(state.active_generation_id) if state else None,
            "entry_count": state.active_generation.entry_count if state else None,
            "coverage": audit_query_lexicon_coverage(),
        },
        "semantic_index_version": (
            {
                "id": str(version.id),
                "uid": version.uid,
                "status": version.status,
                "created_at": version.created_at.isoformat(),
                "provider": version.provider,
                "model_repo_id": version.model_repo_id,
                "model_revision": version.model_revision,
                "dimensions": version.dimensions,
                "document_count": version.document_count,
                "expected_document_count": version.expected_document_count,
                "config_hash": content_hash(version.config_snapshot or {}),
            }
            if version
            else None
        ),
        "meilisearch": {
            "available": stats is not None,
            "index_uid": guard["evaluation_index_uid"],
            "document_count": meili_count if stats is not None else None,
        },
        "historical_language": audit_historical_chunk_languages(),
        "smoke_retrieval": smoke,
        "bundle": (
            {
                "schema": bundle.get("schema"),
                "config_hash": bundle.get("config_hash"),
                "files": bundle.get("files"),
            }
            if bundle
            else None
        ),
        "baseline_v2a": search_v2_config_snapshot(),
        "baseline_language_metadata_modified": False,
        "semantic_index_activated": False,
        "production_write_performed": False,
    }


def write_evaluation_manifest(report: dict, output_path: str | Path) -> Path:
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _language_family(value: object) -> str:
    language = str(value or "").strip().casefold()
    if language.startswith("zh"):
        return "zh"
    if language.startswith("en"):
        return "en"
    if language == "mixed":
        return "mixed"
    return "unknown"


def _term_priority(row: dict) -> tuple:
    term_order = {
        QueryLexiconEntry.TermType.CANONICAL: 0,
        QueryLexiconEntry.TermType.TRANSLATION: 1,
        QueryLexiconEntry.TermType.ALIAS: 2,
        QueryLexiconEntry.TermType.TRANSLITERATION: 3,
        QueryLexiconEntry.TermType.ABBREVIATION: 4,
    }
    trust_order = {
        QueryLexiconEntry.TrustLevel.AUTHORITATIVE: 0,
        QueryLexiconEntry.TrustLevel.VERIFIED: 1,
    }
    return (
        term_order.get(row["term_type"], 9),
        trust_order.get(row["trust_level"], 9),
        len(row["term"]),
        row["normalized_term"],
    )


def _target_language_query(family: str):
    if family == "zh":
        return Q(language__istartswith="zh") | Q(language="mixed")
    if family == "en":
        return Q(language__istartswith="en") | Q(language="mixed")
    return Q(language="mixed")


def prepare_pilot_query_candidates(
    *,
    snapshot_id: str,
    output_path: str | Path,
    limit: int = 60,
    per_direction_minimum: int = 5,
) -> dict:
    """Propose data-backed pilot queries without assigning entities or qrels as gold."""

    guard = evaluation_write_guard(snapshot_id)
    state = QueryLexiconState.objects.select_related("active_generation").filter(
        key="default"
    ).first()
    if state is None or SemanticChunk.objects.count() < 1:
        raise EvaluationEnvironmentError("需要可用 QueryLexicon 和真实 SemanticChunk 才能生成 pilot 候选。")
    version = SemanticIndexVersion.objects.filter(uid=guard["evaluation_index_uid"]).first()
    if version is None or version.status != SemanticIndexVersion.Status.READY:
        raise EvaluationEnvironmentError("evaluation SemanticIndexVersion 尚未 ready。")

    target = Path(output_path).resolve()
    if target.exists():
        raise EvaluationEnvironmentError("pilot candidate 输出文件已经存在。")
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = list(
        QueryLexiconEntry.objects.filter(
            generation_id=state.active_generation_id,
            public_active=True,
            trust_level__in=[
                QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
                QueryLexiconEntry.TrustLevel.VERIFIED,
            ],
            term_type__in=[
                QueryLexiconEntry.TermType.CANONICAL,
                QueryLexiconEntry.TermType.TRANSLATION,
                QueryLexiconEntry.TermType.ALIAS,
                QueryLexiconEntry.TermType.TRANSLITERATION,
                QueryLexiconEntry.TermType.ABBREVIATION,
            ],
        ).values(
            "entity_type",
            "entity_id",
            "term",
            "normalized_term",
            "language",
            "term_type",
            "trust_level",
        )
    )
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        family = _language_family(row["language"])
        if family == "unknown":
            family = _language_family(detect_language(row["term"]))
        if family in {"zh", "en"}:
            row["language_family"] = family
            grouped[(row["entity_type"], str(row["entity_id"]))].append(row)

    support_cache: dict[tuple[str, str], int] = {}

    def support_count(family: str, normalized_term: str) -> int:
        key = (family, normalized_term)
        if key not in support_cache:
            support_cache[key] = SemanticChunk.objects.filter(
                _target_language_query(family),
                normalized_text__icontains=normalized_term,
            ).count()
        return support_cache[key]

    proposals: list[dict] = []
    for entity_key in sorted(grouped):
        entity_rows = sorted(grouped[entity_key], key=_term_priority)
        by_family = {
            family: [row for row in entity_rows if row["language_family"] == family]
            for family in ("zh", "en")
        }
        if not by_family["zh"] or not by_family["en"]:
            continue
        canonical = next(
            (row for row in entity_rows if row["term_type"] == QueryLexiconEntry.TermType.CANONICAL),
            entity_rows[0],
        )
        entity_type, entity_id = entity_key
        for direction, query_family, target_family in (
            ("zh_to_zh", "zh", "zh"),
            ("zh_to_en", "zh", "en"),
            ("en_to_zh", "en", "zh"),
            ("en_to_en", "en", "en"),
        ):
            query_row = by_family[query_family][0]
            target_row = by_family[target_family][0]
            count = support_count(target_family, target_row["normalized_term"])
            if count < 1:
                continue
            is_alias = query_row["term_type"] not in {
                QueryLexiconEntry.TermType.CANONICAL,
                QueryLexiconEntry.TermType.TRANSLATION,
            }
            if entity_type == QueryLexiconEntry.EntityType.PERSON:
                query_type = "scholar_alias" if is_alias else "exact_scholar"
            else:
                query_type = "theory_alias" if is_alias else "exact_theory"
            proposals.append(
                {
                    "candidate_id": f"{direction}-{entity_type}-{entity_id[:8]}",
                    "candidate_query": query_row["term"],
                    "query_language": query_family,
                    "direction": direction,
                    "query_type": query_type,
                    "potential_entity": {
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "label": canonical["term"],
                        "query_term_type": query_row["term_type"],
                        "target_term": target_row["term"],
                    },
                    "rationale": (
                        f"活动 QueryLexicon 有已确认的 {query_family}/{target_family} 术语；"
                        f"目标语言馆藏中有 {count} 个 substring 候选，必须人工核对语义。"
                    ),
                    "target_term_occurrence_hint": count,
                    "requires_human_selection": True,
                    "automatic_gold": False,
                }
            )
        mixed_count = SemanticChunk.objects.filter(
            language="mixed"
        ).filter(
            Q(normalized_text__icontains=by_family["zh"][0]["normalized_term"])
            | Q(normalized_text__icontains=by_family["en"][0]["normalized_term"])
        ).count()
        if mixed_count:
            proposals.append(
                {
                    "candidate_id": f"mixed-{entity_type}-{entity_id[:8]}",
                    "candidate_query": f"{by_family['zh'][0]['term']} {by_family['en'][0]['term']}",
                    "query_language": "mixed",
                    "direction": "mixed",
                    "query_type": "mixed_language",
                    "potential_entity": {
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "label": canonical["term"],
                        "query_term_type": "mixed_verified_terms",
                    },
                    "rationale": (
                        f"同一实体有中英文确认术语，馆藏中有 {mixed_count} 个 mixed chunk 候选。"
                    ),
                    "target_term_occurrence_hint": mixed_count,
                    "requires_human_selection": True,
                    "automatic_gold": False,
                }
            )

    ambiguous_terms = {
        "capital",
        "field",
        "practice",
        "recognition",
        "structure",
        "资本",
        "场域",
        "实践",
        "承认",
        "结构",
    }
    for term in sorted(ambiguous_terms):
        normalized = normalize_term(term)
        matching = next(
            (row for row in rows if row["normalized_term"] == normalized),
            None,
        )
        if matching is None:
            continue
        language = "zh" if _language_family(detect_language(term)) == "zh" else "en"
        count = support_count(language, normalized)
        if count < 1:
            continue
        proposals.append(
            {
                "candidate_id": f"ambiguous-{language}-{normalized}",
                "candidate_query": term,
                "query_language": language,
                "direction": f"{language}_to_{language}",
                "query_type": "ambiguous_term",
                "potential_entity": {
                    "entity_type": matching["entity_type"],
                    "entity_id": str(matching["entity_id"]),
                    "label": matching["term"],
                    "query_term_type": matching["term_type"],
                },
                "rationale": (
                    f"该普通词也能映射到 QueryLexicon；馆藏有 {count} 个 literal 候选，"
                    "适合人工加入理论相关与普通用法 hard negative。"
                ),
                "target_term_occurrence_hint": count,
                "requires_human_selection": True,
                "automatic_gold": False,
            }
        )

    deduplicated = {
        (row["direction"], normalize_term(row["candidate_query"]), row["query_type"]): row
        for row in proposals
    }
    proposals = list(deduplicated.values())
    proposals.sort(
        key=lambda row: sha256(
            f"{guard['snapshot_id']}:{row['candidate_id']}".encode("utf-8")
        ).hexdigest()
    )
    direction_order = ("zh_to_zh", "zh_to_en", "en_to_zh", "en_to_en", "mixed")
    selected: list[dict] = []
    selected_ids: set[str] = set()
    for direction in direction_order:
        for row in [item for item in proposals if item["direction"] == direction][
            : max(1, int(per_direction_minimum))
        ]:
            selected.append(row)
            selected_ids.add(row["candidate_id"])
    for row in proposals:
        if len(selected) >= max(1, int(limit)):
            break
        if row["candidate_id"] not in selected_ids:
            selected.append(row)
            selected_ids.add(row["candidate_id"])

    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for row in selected:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    by_direction = Counter(row["direction"] for row in selected)
    by_type = Counter(row["query_type"] for row in selected)
    return {
        "snapshot_id": guard["snapshot_id"],
        "output": str(target),
        "candidate_count": len(selected),
        "available_before_limit": len(proposals),
        "by_direction": {
            direction: by_direction.get(direction, 0) for direction in direction_order
        },
        "by_query_type": dict(sorted(by_type.items())),
        "minimum_per_direction": max(1, int(per_direction_minimum)),
        "direction_shortfall": {
            direction: max(0, int(per_direction_minimum) - by_direction.get(direction, 0))
            for direction in direction_order
        },
        "manual_query_types_still_required": [
            "conceptual",
            "comparison",
            "mechanism",
            "quoted_phrase",
        ],
        "automatic_relevance_grades": False,
        "contains_candidate_passage_ids": False,
    }
