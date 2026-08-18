from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
import json
import logging
import math
from pathlib import Path
import re
import time

import httpx
from django.conf import settings
from django.db.models import Count, Q
from django.urls import reverse

from catalog.models import (
    Asset,
    Concept,
    DocumentType,
    Passage,
    PublicationState,
    SemanticChunk,
    SemanticSearchFeedback,
    SiteSetting,
    TheorySchool,
    Topic,
)
from catalog.services.semantic_indexing import active_semantic_index_uid, ensure_semantic_index
from catalog.services.text import clean_page_label, normalize_search_text
from ingestion.services.indexing import _headers


SEMANTIC_RUNTIME_KEY = "semantic_search_runtime"
SEMANTIC_ENGINES = {"lightweight", "meilisearch_hybrid"}
SEMANTIC_PROVIDERS = {"huggingFace", "openAi", "ollama"}
DEFAULT_EMBEDDER_NAME = "social-science-library"
DEFAULT_LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
LATIN_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'_-]{1,}", re.IGNORECASE)
CJK_RUN_RE = re.compile(r"[\u3400-\u9fff]{2,}")
STOP_WORDS = {
    "and", "are", "for", "from", "have", "into", "that", "the", "this", "with",
    "一个", "一些", "什么", "可能", "如何", "我们", "有关", "这种", "这个", "进行",
}
YEAR_FILTERS = {
    "before-1900": (None, 1899),
    "1900-1949": (1900, 1949),
    "1950-1999": (1950, 1999),
    "2000-2009": (2000, 2009),
    "2010-2019": (2010, 2019),
    "2020-now": (2020, None),
}


def _language_filter_values(values) -> list[str]:
    """Accept legacy bibliographic labels and new passage-level labels.

    This is a filter compatibility adapter only. It does not alter V1 ranking
    or query analysis, and lets newly detected ``zh``/``en`` chunks remain
    reachable through existing ``zh-CN``/``en`` UI filters.
    """

    expanded: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = str(raw or "").strip()
        folded = value.casefold()
        candidates = [value]
        if folded in {"zh", "zh-cn", "zh-hans", "zh-sg"}:
            candidates.extend(["zh", "zh-Hans", "zh-CN", "zh-cn", "zh-SG"])
        elif folded in {"zh-tw", "zh-hant", "zh-hk", "zh-mo"}:
            candidates.extend(["zh", "zh-Hant", "zh-TW", "zh-HK", "zh-MO"])
        elif folded in {"en", "en-us", "en-gb"}:
            candidates.extend(["en", "en-US", "en-GB"])
        elif folded in {"unknown", "und"}:
            candidates.extend(["unknown", "und"])
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                expanded.append(candidate)
    return expanded

logger = logging.getLogger(__name__)


def viewer_access_statuses(*, authenticated: bool = False, staff: bool = False) -> list[str]:
    """Return the asset visibility set for a search caller.

    Older assets use ``inherit`` and historically behaved as public.  Registered
    assets may expose full text only after login, while restricted and private
    assets remain staff-only.  Search must enforce the same boundary as the
    reader endpoint before serializing a snippet.
    """

    statuses = [Asset.AccessStatus.INHERIT, Asset.AccessStatus.PUBLIC]
    if authenticated:
        statuses.append(Asset.AccessStatus.REGISTERED)
    if staff:
        statuses.extend([Asset.AccessStatus.RESTRICTED, Asset.AccessStatus.PRIVATE])
    return [str(value) for value in statuses]


@dataclass(slots=True)
class PassageFallbackChunk:
    """Read-only adapter for page passages that predate semantic chunking.

    It lets viewpoint search keep using the existing ranking and serializer
    without creating database rows during a public request.  The stable
    ``passage:`` identifier also prevents confusion with SemanticChunk UUIDs.
    """

    passage_id: str
    asset: object
    work_id: object
    page_start: int
    page_end: int
    chapter_title: str
    section_title: str
    original_text: str
    normalized_text: str
    context_before: str
    context_after: str
    locators: list
    quality_flags: list

    @property
    def id(self):
        return f"passage:{self.passage_id}"


def _runtime_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def current_semantic_runtime():
    stored = SiteSetting.objects.filter(key=SEMANTIC_RUNTIME_KEY).first()
    value = stored.value if stored and isinstance(stored.value, dict) else {}
    default_engine = "meilisearch_hybrid" if settings.SEMANTIC_SEARCH_ENABLED else "lightweight"
    engine = str(value.get("engine") or default_engine)
    if engine not in SEMANTIC_ENGINES:
        engine = default_engine
    provider = str(value.get("provider") or settings.SEMANTIC_SEARCH_PROVIDER)
    if provider not in SEMANTIC_PROVIDERS:
        provider = "huggingFace"
    try:
        semantic_ratio = float(value.get("semantic_ratio", settings.SEMANTIC_SEARCH_RATIO))
    except (TypeError, ValueError):
        semantic_ratio = settings.SEMANTIC_SEARCH_RATIO
    try:
        dimensions = int(value["dimensions"]) if value.get("dimensions") else None
    except (TypeError, ValueError):
        dimensions = None
    try:
        max_results_per_work = int(
            value.get("max_results_per_work", settings.SEMANTIC_SEARCH_MAX_RESULTS_PER_WORK)
        )
    except (TypeError, ValueError):
        max_results_per_work = settings.SEMANTIC_SEARCH_MAX_RESULTS_PER_WORK
    runtime = {
        "enabled": settings.SEMANTIC_SEARCH_ENABLED,
        "engine": engine,
        "provider": provider,
        "embedder_name": str(value.get("embedder_name") or DEFAULT_EMBEDDER_NAME),
        "model": str(value.get("model") or settings.SEMANTIC_SEARCH_MODEL or DEFAULT_LOCAL_MODEL),
        "model_repo_id": str(
            value.get("model_repo_id")
            or value.get("model")
            or settings.SEMANTIC_SEARCH_MODEL
            or DEFAULT_LOCAL_MODEL
        ),
        "model_local_path": str(
            value.get("model_local_path") or settings.SEMANTIC_SEARCH_MODEL_CACHE
        ),
        "model_revision": str(
            value.get("model_revision") or settings.SEMANTIC_SEARCH_MODEL_REVISION
        ),
        "dimensions": dimensions,
        "pooling": str(value.get("pooling") or settings.SEMANTIC_SEARCH_MODEL_POOLING),
        "offline_mode": _runtime_bool(
            value.get("offline_mode"), settings.SEMANTIC_SEARCH_OFFLINE_MODE
        ),
        "service_url": str(value.get("service_url") or value.get("endpoint") or ""),
        "endpoint": str(value.get("endpoint") or value.get("service_url") or ""),
        "semantic_ratio": min(1.0, max(0.0, semantic_ratio)),
        "reranker": str(value.get("reranker") or settings.SEMANTIC_SEARCH_RERANKER),
        "query_rewrite_enabled": _runtime_bool(
            value.get("query_rewrite_enabled"), settings.SEMANTIC_SEARCH_QUERY_REWRITE_ENABLED
        ),
        "max_results_per_work": min(20, max(1, max_results_per_work)),
        "api_key_configured": bool(settings.SEMANTIC_EMBEDDING_API_KEY),
        "external_text_warning": provider == "openAi",
        "saved_configuration_version": stored.updated_at.isoformat() if stored else "environment-default",
    }
    runtime["viewpoint_v2"] = {
        "enabled": bool(getattr(settings, "SEMANTIC_SEARCH_V2_ENABLED", False)),
        "profile": str(getattr(settings, "SEMANTIC_SEARCH_PROFILE", "precision")),
        "dense_top_k": int(getattr(settings, "SEMANTIC_SEARCH_DENSE_TOP_K", 50)),
        "sparse_top_k": int(getattr(settings, "SEMANTIC_SEARCH_SPARSE_TOP_K", 50)),
        "fusion_top_k": int(getattr(settings, "SEMANTIC_SEARCH_FUSION_TOP_K", 24)),
        "rerank_top_k": int(getattr(settings, "SEMANTIC_SEARCH_RERANK_TOP_K", 24)),
        "final_top_k": int(getattr(settings, "SEMANTIC_SEARCH_FINAL_TOP_K", 10)),
        "query_expansion_enabled": bool(
            getattr(settings, "SEMANTIC_SEARCH_V2_QUERY_EXPANSION_ENABLED", True)
        ),
        "query_expansion_max": int(
            getattr(settings, "SEMANTIC_SEARCH_QUERY_EXPANSION_MAX", 3)
        ),
        "rerank_provider": str(
            getattr(settings, "SEMANTIC_SEARCH_V2_RERANK_PROVIDER", "rules")
        ),
        "rerank_model": str(
            getattr(settings, "SEMANTIC_SEARCH_V2_RERANK_MODEL", "")
        ),
        "rerank_service_configured": bool(
            getattr(settings, "SEMANTIC_SEARCH_V2_RERANK_URL", "")
        ),
    }
    return runtime


def semantic_model_health(config: dict | None = None) -> dict:
    config = config or current_semantic_runtime()
    provider = config.get("provider")
    if config.get("engine") != "meilisearch_hybrid":
        return {
            "configured": True,
            "available": False,
            "reason": "当前使用关键词检索，语义模型未启用。",
            "files": {},
        }
    if provider != "huggingFace":
        return {
            "configured": bool(config.get("service_url") or provider == "openAi"),
            "available": None,
            "reason": "外部或 Ollama 模型需要通过测试查询确认。",
            "files": {},
        }

    root = Path(str(config.get("model_local_path") or settings.SEMANTIC_SEARCH_MODEL_CACHE))
    repo_id = str(config.get("model_repo_id") or config.get("model") or "")
    cache_name = f"models--{repo_id.replace('/', '--')}"
    candidates = [root / cache_name, root / "hub" / cache_name]
    model_root = next((candidate for candidate in candidates if candidate.is_dir()), None)
    revision = str(config.get("model_revision") or "").strip()
    offline_mode = bool(config.get("offline_mode"))
    snapshot_root = None
    resolved_revision = ""
    referenced_revision = ""
    revision_reference_available = not offline_mode or not revision
    if model_root is not None:
        snapshots_root = model_root / "snapshots"
        if revision:
            reference = model_root / "refs" / Path(revision)
            if reference.is_file():
                try:
                    referenced_revision = reference.read_text(encoding="utf-8").strip()
                except (OSError, UnicodeError):
                    referenced_revision = ""
                revision_reference_available = bool(
                    referenced_revision
                    and (snapshots_root / referenced_revision).is_dir()
                )
        direct_snapshot = snapshots_root / revision if revision else None
        if direct_snapshot is not None and direct_snapshot.is_dir():
            snapshot_root = direct_snapshot
            resolved_revision = direct_snapshot.name
        elif revision:
            if referenced_revision:
                resolved_revision = referenced_revision
                referenced_snapshot = snapshots_root / resolved_revision
                if referenced_snapshot.is_dir():
                    snapshot_root = referenced_snapshot
        if snapshot_root is None and not revision and snapshots_root.is_dir():
            snapshot_root = next(
                (candidate for candidate in snapshots_root.iterdir() if candidate.is_dir()),
                None,
            )
            resolved_revision = snapshot_root.name if snapshot_root else ""
    search_root = snapshot_root or model_root or root
    config_path = next(search_root.rglob("config.json"), None) if search_root.is_dir() else None
    detected_dimensions = None
    if config_path is not None:
        try:
            model_config = json.loads(config_path.read_text(encoding="utf-8"))
            for key in ("sentence_embedding_dimension", "projection_dim", "hidden_size"):
                if model_config.get(key):
                    detected_dimensions = int(model_config[key])
                    break
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
            detected_dimensions = None
    expected_dimensions = config.get("dimensions")
    dimensions_match = (
        expected_dimensions is None
        or (
            detected_dimensions is not None
            and int(expected_dimensions) == detected_dimensions
        )
    )
    files = {
        "root_exists": root.is_dir(),
        "model_cache_exists": model_root is not None,
        "revision_available": not revision or snapshot_root is not None,
        "meilisearch_revision_ref": revision_reference_available,
        "config": config_path is not None,
        "tokenizer": False,
        "weights": False,
        "dimensions_match": dimensions_match,
    }
    if search_root.is_dir():
        files["tokenizer"] = any(search_root.rglob("tokenizer.json")) or any(
            search_root.rglob("tokenizer_config.json")
        )
        files["weights"] = any(search_root.rglob("*.safetensors")) or any(
            search_root.rglob("pytorch_model*.bin")
        )
    available = all(files.values())
    return {
        "configured": bool(repo_id),
        "available": available,
        "error_code": None if available else "MODEL_UNAVAILABLE",
        "reason": (
            "本地模型缓存已通过文件检查。"
            if available
            else (
                "本地 snapshot 已存在，但缺少 Meilisearch 离线读取所需的 revision 引用。"
                if files["revision_available"]
                and not files["meilisearch_revision_ref"]
                else "本地缓存不完整；语义查询将自动降级为关键词检索。"
            )
        ),
        "repo_id": repo_id,
        "revision": revision,
        "resolved_revision": resolved_revision,
        "expected_dimensions": expected_dimensions,
        "detected_dimensions": detected_dimensions,
        "offline_mode": offline_mode,
        "cache_root": str(root),
        "files": files,
    }


def configure_semantic_embedder(config: dict):
    ensure_semantic_index(config)
    return {
        "configured": True,
        "index": active_semantic_index_uid(),
        "model": config["model"],
    }


def _query_terms(value: str):
    folded = normalize_search_text(value)
    terms: list[str] = []
    terms.extend(word for word in LATIN_WORD_RE.findall(folded) if word not in STOP_WORDS)
    for run in CJK_RUN_RE.findall(folded):
        if run not in STOP_WORDS:
            terms.append(run)
        width = 2 if len(run) <= 8 else 3
        terms.extend(run[index : index + width] for index in range(len(run) - width + 1))
    unique = []
    for term in sorted(terms, key=len, reverse=True):
        if len(term) < 2 or term in STOP_WORDS or term in unique:
            continue
        unique.append(term)
        if len(unique) >= 24:
            break
    return folded, unique


def _ngrams(value: str, width: int = 2):
    compact = re.sub(r"\s+", "", normalize_search_text(value))
    if len(compact) <= width:
        return Counter([compact]) if compact else Counter()
    return Counter(compact[index : index + width] for index in range(len(compact) - width + 1))


def _cosine(left: Counter, right: Counter):
    if not left or not right:
        return 0.0
    common = sum(left[key] * right.get(key, 0) for key in left)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return common / (left_norm * right_norm)


def _taxonomy_matches(query: str, terms: list[str]):
    candidates = []
    for model, label, extra_field in (
        (TheorySchool, "理论流派", "key_themes"),
        (Topic, "研究专题", "key_concepts"),
        (Concept, "概念", "definition"),
    ):
        queryset = model.objects.filter(editorial_status="published")
        for item in queryset.only("id", "name", "description", "search_aliases", extra_field)[:500]:
            extra = getattr(item, extra_field, "")
            if isinstance(extra, list):
                extra = " ".join(str(value) for value in extra)
            source = " ".join([item.name, item.description or "", " ".join(item.search_aliases or []), str(extra or "")])
            folded = normalize_search_text(source)
            coverage = sum(1 for term in terms if term in folded) / max(1, len(terms))
            similarity = SequenceMatcher(None, query[:500], folded[:1200]).ratio()
            score = coverage * 0.72 + similarity * 0.28
            if score >= 0.12:
                candidates.append(
                    {"id": str(item.id), "slug": item.slug, "name": item.name, "label": label, "score": score}
                )
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:12]


def understand_query(query: str) -> dict:
    folded, terms = _query_terms(query)
    if any(token in query for token in ("为什么", "如何", "是否", "什么原因", "?", "？")):
        query_type = "研究问题"
    elif any(token in query for token in ("导致", "造成", "因为", "因此", "使得", "影响")):
        query_type = "因果判断"
    elif any(token in query for token in ("相比", "不同于", "一方面", "另一方面", "更", "较")):
        query_type = "比较判断"
    elif len(query) >= 36:
        query_type = "观点陈述"
    elif len(terms) <= 3:
        query_type = "理论概念"
    else:
        query_type = "原句记忆"
    taxonomy = _taxonomy_matches(folded, terms)
    expanded = list(dict.fromkeys([item["name"] for item in taxonomy[:5]]))
    rewrites = [query]
    if expanded:
        rewrites.append(f"{query} {' '.join(expanded[:3])}")
    return {
        "type": query_type,
        "terms": terms[:10],
        "related_concepts": [
            {"name": item["name"], "kind": item["label"], "slug": item["slug"]}
            for item in taxonomy[:8]
        ],
        "rewrites": rewrites[:5],
        "rewrite_source": "馆内词表",
    }


def _base_queryset(filters: dict):
    queryset = SemanticChunk.objects.filter(
        asset__edition__state=PublicationState.PUBLISHED,
        asset__edition__is_primary=True,
        asset__kind="normalized",
        asset__status="ready",
        asset__is_current=True,
    ).select_related("asset__edition__work")
    queryset = queryset.filter(
        asset__access_status__in=(
            filters.get("_allowed_access_statuses")
            or viewer_access_statuses()
        )
    )
    if filters.get("work_ids"):
        queryset = queryset.filter(work_id__in=filters["work_ids"])
    if filters.get("document_types"):
        mapped = ["journal_article" if value in {"article", "journal_article"} else value for value in filters["document_types"]]
        queryset = queryset.filter(document_type__in=mapped)
    if filters.get("languages"):
        queryset = queryset.filter(language__in=_language_filter_values(filters["languages"]))
    if filters.get("authors"):
        queryset = queryset.filter(
            asset__edition__contributions__person_id__in=filters["authors"],
            asset__edition__contributions__approved=True,
        )
    years = filters.get("years") or []
    if years:
        condition = Q()
        for value in years:
            start, end = YEAR_FILTERS.get(value, (None, None))
            item = Q()
            if start is not None:
                item &= Q(asset__edition__publication_year__gte=start)
            if end is not None:
                item &= Q(asset__edition__publication_year__lte=end)
            if start is not None or end is not None:
                condition |= item
        if condition:
            queryset = queryset.filter(condition)
    if filters.get("theories"):
        queryset = queryset.filter(
            work__knowledge_relations__theory_school__slug__in=filters["theories"],
            work__knowledge_relations__approved=True,
        )
    if filters.get("topics"):
        queryset = queryset.filter(
            work__knowledge_relations__topic__slug__in=filters["topics"],
            work__knowledge_relations__approved=True,
        )
    if filters.get("concepts"):
        queryset = queryset.filter(
            work__knowledge_relations__concept__slug__in=filters["concepts"],
            work__knowledge_relations__approved=True,
        )
    return queryset.distinct()


def _keyword_candidates(query: str, terms: list[str], filters: dict, limit: int = 100):
    queryset = _base_queryset(filters)
    lexical = Q()
    for term in terms[:14]:
        lexical |= Q(normalized_text__icontains=term)
        lexical |= Q(chapter_title__icontains=term)
        lexical |= Q(section_title__icontains=term)
    candidates = list(queryset.filter(lexical)[:800]) if lexical else list(queryset.order_by("-updated_at")[:300])
    query_grams = _ngrams(query)
    rows = []
    for chunk in candidates:
        coverage = sum(1 for term in terms if term in chunk.normalized_text) / max(1, len(terms))
        cosine = _cosine(query_grams, _ngrams(chunk.normalized_text))
        phrase = SequenceMatcher(None, query[:600], chunk.normalized_text[:1400]).ratio()
        title = SequenceMatcher(
            None,
            query[:300],
            normalize_search_text(chunk.asset.edition.work.title)[:500],
        ).ratio()
        penalty = 0.65 if any(flag in chunk.quality_flags for flag in ("references", "table_of_contents")) else 1.0
        score = (coverage * 0.44 + cosine * 0.30 + phrase * 0.18 + title * 0.08) * penalty
        if score > 0.015:
            rows.append((chunk, score))
    rows.sort(key=lambda item: item[1], reverse=True)
    return rows[:limit]


def _passage_base_queryset(filters: dict):
    queryset = Passage.objects.filter(
        page__asset__edition__state=PublicationState.PUBLISHED,
        page__asset__edition__is_primary=True,
        page__asset__kind="normalized",
        page__asset__status="ready",
        page__asset__is_current=True,
    ).select_related("page__asset__edition__work")
    queryset = queryset.filter(
        page__asset__access_status__in=(
            filters.get("_allowed_access_statuses")
            or viewer_access_statuses()
        )
    )
    if filters.get("work_ids"):
        queryset = queryset.filter(page__asset__edition__work_id__in=filters["work_ids"])
    if filters.get("document_types"):
        mapped = [
            "journal_article" if value in {"article", "journal_article"} else value
            for value in filters["document_types"]
        ]
        queryset = queryset.filter(page__asset__edition__work__document_type__in=mapped)
    if filters.get("languages"):
        queryset = queryset.filter(
            page__asset__edition__work__language__in=_language_filter_values(
                filters["languages"]
            )
        )
    if filters.get("authors"):
        queryset = queryset.filter(
            page__asset__edition__contributions__person_id__in=filters["authors"],
            page__asset__edition__contributions__approved=True,
        )
    years = filters.get("years") or []
    if years:
        condition = Q()
        for value in years:
            start, end = YEAR_FILTERS.get(value, (None, None))
            item = Q()
            if start is not None:
                item &= Q(page__asset__edition__publication_year__gte=start)
            if end is not None:
                item &= Q(page__asset__edition__publication_year__lte=end)
            if start is not None or end is not None:
                condition |= item
        if condition:
            queryset = queryset.filter(condition)
    if filters.get("theories"):
        queryset = queryset.filter(
            page__asset__edition__work__knowledge_relations__theory_school__slug__in=filters["theories"],
            page__asset__edition__work__knowledge_relations__approved=True,
        )
    if filters.get("topics"):
        queryset = queryset.filter(
            page__asset__edition__work__knowledge_relations__topic__slug__in=filters["topics"],
            page__asset__edition__work__knowledge_relations__approved=True,
        )
    if filters.get("concepts"):
        queryset = queryset.filter(
            page__asset__edition__work__knowledge_relations__concept__slug__in=filters["concepts"],
            page__asset__edition__work__knowledge_relations__approved=True,
        )
    return queryset.distinct()


def _passage_keyword_candidates(query: str, terms: list[str], filters: dict, limit: int = 100):
    """Fallback to the page-mapped full-text index when chunks are unavailable."""

    queryset = _passage_base_queryset(filters)
    lexical = Q()
    for term in terms[:14]:
        lexical |= Q(normalized_text__icontains=term)
        lexical |= Q(page__chapter_title__icontains=term)
    candidates = list(queryset.filter(lexical)[:800]) if lexical else []
    query_grams = _ngrams(query)
    rows = []
    for passage in candidates:
        normalized = passage.normalized_text or normalize_search_text(passage.text)
        coverage = sum(1 for term in terms if term in normalized) / max(1, len(terms))
        cosine = _cosine(query_grams, _ngrams(normalized))
        phrase = SequenceMatcher(None, query[:600], normalized[:1400]).ratio()
        title = SequenceMatcher(
            None,
            query[:300],
            normalize_search_text(passage.page.asset.edition.work.title)[:500],
        ).ratio()
        score = coverage * 0.44 + cosine * 0.30 + phrase * 0.18 + title * 0.08
        if score <= 0.015:
            continue
        chunk = PassageFallbackChunk(
            passage_id=str(passage.id),
            asset=passage.page.asset,
            work_id=passage.page.asset.edition.work_id,
            page_start=passage.page.index,
            page_end=passage.page.index,
            chapter_title=passage.page.chapter_title,
            section_title="",
            original_text=passage.text,
            normalized_text=normalized,
            context_before="",
            context_after="",
            locators=[
                {
                    "page": passage.page.index,
                    "printed_label": passage.page.printed_label,
                    "bbox": passage.bbox_union,
                }
            ],
            quality_flags=[],
        )
        rows.append((chunk, score))
    rows.sort(key=lambda item: item[1], reverse=True)
    return rows[:limit]


def _json_value(value) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _meili_filters(
    filters: dict,
    *,
    include_access_status: bool = True,
) -> list[str]:
    output = ["is_public = true"]
    if include_access_status:
        allowed_access = (
            filters.get("_allowed_access_statuses")
            or viewer_access_statuses()
        )
        output.append(
            "access_status IN ["
            + ", ".join(_json_value(value) for value in allowed_access)
            + "]"
        )
    mapping = {
        "document_types": "document_type",
        "languages": "language",
        "authors": "author_ids",
        "theories": "theory_slugs",
        "topics": "topic_slugs",
        "concepts": "concept_slugs",
        "work_ids": "work_id",
    }
    for source, target in mapping.items():
        values = filters.get(source) or []
        if source == "document_types":
            values = ["journal_article" if value in {"article", "journal_article"} else value for value in values]
        if source == "languages":
            values = _language_filter_values(values)
        if values:
            output.append(f"{target} IN [{', '.join(_json_value(value) for value in values)}]")
    year_groups = []
    for value in filters.get("years") or []:
        start, end = YEAR_FILTERS.get(value, (None, None))
        parts = []
        if start is not None:
            parts.append(f"publication_year >= {start}")
        if end is not None:
            parts.append(f"publication_year <= {end}")
        if parts:
            year_groups.append("(" + " AND ".join(parts) + ")")
    if year_groups:
        output.append("(" + " OR ".join(year_groups) + ")")
    return output


def _is_legacy_access_filter_error(response: httpx.Response) -> bool:
    """Recognize an old active index that predates access-level filtering.

    The V1 production index only exposed ``is_public``.  New indexes also
    expose ``access_status``.  Retrying only this explicit compatibility error
    preserves the old public-only boundary without hiding other Meilisearch
    failures or mutating the active index during a release.
    """

    if response.status_code != 400:
        return False
    try:
        details = response.json()
    except (TypeError, ValueError):
        return False
    code = str(details.get("code") or "")
    message = str(details.get("message") or "")
    return code == "invalid_search_filter" and "access_status" in message


def _vector_candidates(
    query: str,
    config: dict,
    filters: dict,
    limit: int = 100,
    *,
    index_uid: str | None = None,
):
    index_uid = index_uid or active_semantic_index_uid()
    payload = {
        "q": query,
        "limit": min(200, max(1, limit)),
        "filter": " AND ".join(_meili_filters(filters)),
        "attributesToRetrieve": ["id"],
        "showRankingScore": True,
        "hybrid": {
            # This request is the dense candidate set. Keyword candidates are
            # recalled separately and combined below with weighted RRF.
            "semanticRatio": 1.0,
            "embedder": config["embedder_name"],
        },
    }
    response = httpx.post(
        f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{index_uid}/search",
        headers=_headers(),
        json=payload,
        timeout=min(5, settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS),
    )
    if _is_legacy_access_filter_error(response):
        logger.warning(
            "Semantic index %s predates access_status filtering; "
            "retrying with the legacy public-only filter.",
            index_uid,
        )
        payload = {
            **payload,
            "filter": " AND ".join(
                _meili_filters(filters, include_access_status=False)
            ),
        }
        response = httpx.post(
            f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{index_uid}/search",
            headers=_headers(),
            json=payload,
            timeout=min(5, settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS),
        )
    response.raise_for_status()
    hits = response.json().get("hits", [])
    return [(str(hit["id"]), float(hit.get("_rankingScore") or 0)) for hit in hits if hit.get("id")]


def _rrf(
    keyword_rows,
    vector_rows,
    *,
    filters=None,
    semantic_ratio: float = 0.72,
    k: int = 60,
):
    semantic_weight = min(1.0, max(0.0, float(semantic_ratio)))
    keyword_weight = 1.0 - semantic_weight
    if not vector_rows:
        keyword_weight = 1.0
    if not keyword_rows:
        semantic_weight = 1.0
    ranks: dict[str, dict] = {}
    for rank, (chunk, lexical_score) in enumerate(keyword_rows, start=1):
        ranks[str(chunk.id)] = {
            "chunk": chunk,
            "keyword_rank": rank,
            "keyword_score": lexical_score,
            "vector_rank": None,
            "vector_score": None,
            "rrf": keyword_weight / (k + rank),
        }
    missing_ids = []
    for rank, (chunk_id, vector_score) in enumerate(vector_rows, start=1):
        row = ranks.setdefault(
            chunk_id,
            {
                "chunk": None,
                "keyword_rank": None,
                "keyword_score": None,
                "vector_rank": rank,
                "vector_score": vector_score,
                "rrf": 0,
            },
        )
        row["vector_rank"] = rank
        row["vector_score"] = vector_score
        row["rrf"] += semantic_weight / (k + rank)
        if row["chunk"] is None:
            missing_ids.append(chunk_id)
    if missing_ids:
        chunks = _base_queryset(filters or {}).filter(pk__in=missing_ids)
        chunk_map = {str(chunk.id): chunk for chunk in chunks}
        for chunk_id in missing_ids:
            ranks[chunk_id]["chunk"] = chunk_map.get(chunk_id)
    return [row for row in ranks.values() if row["chunk"] is not None]


def _rule_rerank(rows: list[dict], query: str, terms: list[str]):
    for row in rows:
        chunk = row["chunk"]
        coverage = sum(1 for term in terms if term in chunk.normalized_text) / max(1, len(terms))
        heading_bonus = 0.08 if any(term in normalize_search_text(f"{chunk.chapter_title} {chunk.section_title}") for term in terms) else 0
        quality_penalty = 0.22 if any(flag in chunk.quality_flags for flag in ("references", "table_of_contents")) else 0
        lexical_position = 1 / (20 + (row["keyword_rank"] or 200))
        vector_position = 1 / (20 + (row["vector_rank"] or 200))
        row["reranker_score"] = row["rrf"] + lexical_position + vector_position + coverage * 0.01 + heading_bonus * 0.01 - quality_penalty * 0.01
    rows.sort(key=lambda row: row["reranker_score"], reverse=True)
    return rows


def _apply_feedback_calibration(rows: list[dict], query: str) -> list[dict]:
    """Apply a deliberately small, sample-gated adjustment to relevance ordering.

    Public votes are noisy and can be manipulated. A chunk therefore needs at
    least five votes for the same normalized query before feedback is used. The
    adjustment is bounded to six percent so retrieval evidence remains dominant.
    """

    if not rows:
        return rows
    query_hash = sha256(normalize_search_text(query).encode("utf-8")).hexdigest()
    chunk_ids = [
        row["chunk"].id
        for row in rows
        if isinstance(row["chunk"], SemanticChunk)
    ]
    if not chunk_ids:
        for row in rows:
            row["feedback_total"] = 0
            row["feedback_adjustment"] = 0.0
            row["calibrated_score"] = row.get("reranker_score", row.get("rrf", 0))
        return rows
    aggregates = {
        str(item["chunk_id"]): item
        for item in SemanticSearchFeedback.objects.filter(
            query_hash=query_hash,
            chunk_id__in=chunk_ids,
        )
        .values("chunk_id")
        .annotate(
            total=Count("id"),
            relevant_count=Count("id", filter=Q(relevant=True)),
        )
    }
    for row in rows:
        summary = (
            aggregates.get(str(row["chunk"].id))
            if isinstance(row["chunk"], SemanticChunk)
            else None
        )
        base_score = row.get("reranker_score", row.get("rrf", 0))
        row["feedback_total"] = int(summary["total"]) if summary else 0
        row["feedback_adjustment"] = 0.0
        if not summary or summary["total"] < 5:
            row["calibrated_score"] = base_score
            continue
        # Bayesian smoothing prevents a handful of unanimous votes from
        # overpowering the document and semantic evidence.
        positive_rate = (summary["relevant_count"] + 2) / (summary["total"] + 4)
        adjustment = max(-0.06, min(0.06, (positive_rate - 0.5) * 0.12))
        row["feedback_adjustment"] = adjustment
        row["calibrated_score"] = base_score * (1 + adjustment)
    rows.sort(key=lambda row: row.get("calibrated_score", 0), reverse=True)
    return rows


def _deduplicate_and_limit(rows: list[dict], limit: int, max_per_work: int):
    """Return a diverse result set while preserving the rank inside each work.

    A single long book commonly produces many adjacent high-scoring chunks.  A
    one-pass limiter lets that book occupy the beginning of the page before a
    second work is considered.  We first remove overlap inside each work, then
    interleave the first, second and third passage from every work.  Readers
    therefore see the breadth of the library without losing the best passages
    from a strongly matching title.
    """

    grouped: dict[str, list[dict]] = {}
    work_order: list[str] = []
    for row in rows:
        chunk = row["chunk"]
        work_id = str(chunk.work_id)
        if work_id not in grouped:
            grouped[work_id] = []
            work_order.append(work_id)
        work_rows = grouped[work_id]
        if max_per_work and len(work_rows) >= max_per_work:
            continue
        duplicate = False
        for existing in work_rows:
            other = existing["chunk"]
            same_or_adjacent_page = abs(other.page_start - chunk.page_start) <= 1
            if same_or_adjacent_page and SequenceMatcher(
                None,
                other.normalized_text[:1600],
                chunk.normalized_text[:1600],
            ).ratio() >= 0.82:
                duplicate = True
                break
        if duplicate:
            continue
        work_rows.append(row)

    selected = []
    depth = 0
    while len(selected) < limit:
        added = False
        for work_id in work_order:
            work_rows = grouped[work_id]
            if depth >= len(work_rows):
                continue
            selected.append(work_rows[depth])
            added = True
            if len(selected) >= limit:
                break
        if not added:
            break
        depth += 1
    return selected


def _relevance_label(rank: int, total: int) -> str:
    if rank <= max(2, min(5, total // 4)):
        return "高度相关"
    if rank <= max(6, total // 2):
        return "较为相关"
    return "可能相关"


def _serialize_row(row: dict, rank: int, total: int, terms: list[str], *, debug=False):
    chunk = row["chunk"]
    asset = chunk.asset
    edition = asset.edition
    work = edition.work
    authors = list(
        edition.contributions.filter(approved=True)
        .order_by("order")
        .values_list("person__preferred_name", flat=True)
    )
    matched_terms = [term for term in terms if term in chunk.normalized_text][:5]
    reasons = []
    if row.get("vector_rank"):
        reasons.append("语义表达与查询接近")
    if matched_terms:
        reasons.append(f"原文包含相关线索：{'、'.join(matched_terms)}")
    if chunk.chapter_title or chunk.section_title:
        reasons.append("结果保留了章节与段落位置")
    if not reasons:
        reasons.append("由馆藏全文候选排序得到")
    first_locator = chunk.locators[0] if chunk.locators else {}
    payload = {
        # Prefix page-passage fallbacks so feedback can be accepted without
        # pretending they are already embedded SemanticChunk records.
        # PassageFallbackChunk.id already carries the ``passage:`` namespace.
        # Keeping the prefix exactly once lets the feedback endpoint resolve
        # the underlying page passage while avoiding UUID collisions.
        "id": str(chunk.id),
        "asset_id": str(asset.id),
        "edition_id": str(edition.id),
        "edition_slug": edition.public_slug,
        "work_id": str(work.id),
        "title": work.title,
        "cover_url": reverse("public-work-cover", kwargs={"work_id": work.id}) if work.cover else "",
        "authors": authors,
        "document_type": work.document_type,
        "language": work.language,
        "publication_year": edition.publication_year,
        "page_index": chunk.page_start,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "printed_label": clean_page_label(first_locator.get("printed_label", "")),
        "chapter_title": chunk.chapter_title,
        "section_title": chunk.section_title,
        "snippet": chunk.original_text,
        "context_before": chunk.context_before,
        "context_after": chunk.context_after,
        "bbox": first_locator.get("bbox", []),
        "locators": chunk.locators,
        "relevance": _relevance_label(rank, total),
        "reasons": reasons,
        "concepts": matched_terms,
        "reader_url": (
            f"/reader/{asset.id}?page={chunk.page_start}&passage={chunk.passage_id}"
            if isinstance(chunk, PassageFallbackChunk)
            else f"/reader/{asset.id}?page={chunk.page_start}&passage={chunk.id}"
        ),
    }
    if debug:
        payload["debug"] = {
            "keyword_rank": row.get("keyword_rank"),
            "vector_rank": row.get("vector_rank"),
            "keyword_score": row.get("keyword_score"),
            "vector_score": row.get("vector_score"),
            "rrf_score": round(row.get("rrf", 0), 8),
            "reranker_score": round(row.get("reranker_score", 0), 8),
            "feedback_total": row.get("feedback_total", 0),
            "feedback_adjustment": round(row.get("feedback_adjustment", 0), 6),
            "final_rank": rank,
        }
    return payload


def semantic_search_v1(
    query: str,
    *,
    filters=None,
    limit=40,
    max_per_work=None,
    debug=False,
    strategy="hybrid_rerank",
    sort="relevance",
    query_override="",
    disable_query_rewrite=False,
    index_uid: str | None = None,
    semantic_ratio_override: float | None = None,
    runtime_config_override: dict | None = None,
):
    started = time.monotonic()
    config = runtime_config_override or current_semantic_runtime()
    filters = filters or {}
    folded, terms = _query_terms(query)
    query_rewrite_fallback = False
    try:
        understanding = understand_query(query)
    except (RuntimeError, TypeError, ValueError):
        query_rewrite_fallback = True
        understanding = {
            "type": "观点陈述",
            "terms": terms[:10],
            "related_concepts": [],
            "rewrites": [query],
            "rewrite_source": "原始查询",
        }
    keyword_rows = (
        _keyword_candidates(folded, terms, filters, limit=160)
        if strategy != "vector"
        else []
    )
    page_fallback_used = False
    if strategy != "vector":
        # Older or partially indexed works can still have accurate page-mapped
        # passages.  Include them even when another work already has semantic
        # chunks so the result set does not collapse to only one or two books.
        passage_rows = _passage_keyword_candidates(folded, terms, filters, limit=160)
        if passage_rows:
            page_fallback_used = True
            keyword_rows = sorted(
                [*keyword_rows, *passage_rows],
                key=lambda item: item[1],
                reverse=True,
            )[:240]
    vector_rows = []
    fallback_used = False
    fallback_reason = ""
    query_override = str(query_override or "").strip()[:1200]
    rewrite_active = bool(config["query_rewrite_enabled"] and not disable_query_rewrite)
    vector_query = query
    if query_override:
        # The original query remains present even when the reader edits the
        # optional expression.
        vector_query = f"{query} {query_override}".strip()
    elif rewrite_active and len(understanding["rewrites"]) > 1:
        vector_query = understanding["rewrites"][-1]
    if (
        strategy not in {"keyword", "legacy"}
        and config["enabled"]
        and config["engine"] == "meilisearch_hybrid"
    ):
        local_health = (
            semantic_model_health(config)
            if config.get("provider") == "huggingFace" and config.get("offline_mode")
            else None
        )
        if local_health is not None and not local_health["available"]:
            fallback_used = True
            fallback_reason = "local_model_unavailable"
        else:
            try:
                vector_rows = _vector_candidates(
                    vector_query,
                    config,
                    filters,
                    limit=160,
                    index_uid=index_uid,
                )
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                fallback_used = True
                fallback_reason = "semantic_service_unavailable"
    else:
        fallback_used = True
        fallback_reason = "semantic_disabled"

    semantic_ratio = (
        config["semantic_ratio"]
        if semantic_ratio_override is None
        else min(1.0, max(0.0, float(semantic_ratio_override)))
    )
    rows = _rrf(
        keyword_rows,
        vector_rows,
        filters=filters,
        semantic_ratio=semantic_ratio,
    )
    reranker_fallback = False
    if strategy in {"hybrid_rerank", "legacy"}:
        try:
            rows = _rule_rerank(rows[:120], folded, terms)
        except (RuntimeError, TypeError, ValueError):
            reranker_fallback = True
            rows = sorted(rows[:120], key=lambda row: row["rrf"], reverse=True)
    else:
        rows = sorted(rows[:120], key=lambda row: row["rrf"], reverse=True)
    if sort == "relevance":
        rows = _apply_feedback_calibration(rows, query)
    elif sort == "newest":
        rows.sort(
            key=lambda row: (
                row["chunk"].asset.edition.first_published_at
                or row["chunk"].asset.edition.published_at
                or row["chunk"].asset.edition.created_at
            ).timestamp(),
            reverse=True,
        )
    elif sort == "year":
        rows.sort(
            key=lambda row: row["chunk"].asset.edition.publication_year or 0,
            reverse=True,
        )
    effective_max = max_per_work if max_per_work is not None else config["max_results_per_work"]
    rows = _deduplicate_and_limit(rows, limit, max(0, int(effective_max)))
    elapsed_ms = round((time.monotonic() - started) * 1000, 2)
    results = [
        _serialize_row(row, rank, len(rows), terms, debug=debug)
        for rank, row in enumerate(rows, start=1)
    ]
    return {
        "search_version": "v1",
        "engine": "hybrid" if vector_rows else "keyword_fallback",
        "index_uid": index_uid or active_semantic_index_uid(),
        "semantic_ratio": semantic_ratio,
        "strategy": strategy,
        "sort": sort,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "page_fallback_used": page_fallback_used,
        "notice": (
            "语义模型当前不可用，已使用馆藏关键词和章节关系继续检索。"
            if fallback_used
            else "结果由原文召回与语义向量共同排序，请回到原页核对上下文。"
        ),
        "understanding": understanding,
        "query_rewrite_enabled": config["query_rewrite_enabled"],
        "query_rewrite_active": rewrite_active,
        "active_rewrite": query_override or (vector_query if vector_query != query else ""),
        "query_rewrite_fallback": query_rewrite_fallback,
        "reranker_fallback": reranker_fallback,
        "results": results,
        "work_count": len({item["work_id"] for item in results}),
        "timing_ms": elapsed_ms if debug else None,
    }


def semantic_search(
    query: str,
    *,
    filters=None,
    limit=40,
    max_per_work=None,
    debug=False,
    strategy="hybrid_rerank",
    sort="relevance",
    query_override="",
    disable_query_rewrite=False,
    index_uid: str | None = None,
    semantic_ratio_override: float | None = None,
    search_version: str | None = None,
    search_profile: str | None = None,
    rerank_top_k_override: int | None = None,
    runtime_config_override: dict | None = None,
    disabled_v2_branch_types=None,
    v2_final_top_k_override: int | None = None,
):
    """Dispatch to the stable V1 or the additive viewpoint-search V2.

    V1 remains the default unless the feature flag is enabled.  Evaluation and
    administrator diagnostics can request a version explicitly, which allows a
    candidate design to be compared without switching the public index.
    """

    requested = str(search_version or "").strip().casefold()
    if not requested:
        requested = (
            "v2"
            if bool(getattr(settings, "SEMANTIC_SEARCH_V2_ENABLED", False))
            else "v1"
        )
    profile_aliases = {
        "v2-a": "fast",
        "v2-b": "balanced",
        "v2-c": "precision",
    }
    if requested in {"v2", *profile_aliases}:
        from catalog.services.semantic_search_v2 import semantic_search_v2

        return semantic_search_v2(
            query,
            filters=filters,
            limit=limit,
            max_per_work=max_per_work,
            debug=debug,
            strategy=strategy,
            sort=sort,
            query_override=query_override,
            disable_query_rewrite=disable_query_rewrite,
            index_uid=index_uid,
            semantic_ratio_override=semantic_ratio_override,
            search_profile=search_profile or profile_aliases.get(requested),
            rerank_top_k_override=rerank_top_k_override,
            runtime_config_override=runtime_config_override,
            disabled_branch_types=disabled_v2_branch_types,
            final_top_k_override=v2_final_top_k_override,
        )
    return semantic_search_v1(
        query,
        filters=filters,
        limit=limit,
        max_per_work=max_per_work,
        debug=debug,
        strategy=strategy,
        sort=sort,
        query_override=query_override,
        disable_query_rewrite=disable_query_rewrite,
        index_uid=index_uid,
        semantic_ratio_override=semantic_ratio_override,
        runtime_config_override=runtime_config_override,
    )


def record_feedback(
    *,
    query: str,
    chunk: SemanticChunk | None,
    relevant: bool,
    rank=0,
    user=None,
    metadata=None,
    actor_identifier: str = "",
):
    query_hash = sha256(normalize_search_text(query).encode("utf-8")).hexdigest()
    store_query = bool(user and getattr(user, "is_staff", False))
    saved_user = user if getattr(user, "is_authenticated", False) else None
    feedback_metadata = metadata or {}
    target = (
        chunk.document_id
        if chunk
        else str(feedback_metadata.get("passage_id") or "query")[:128]
    )
    actor = (
        f"user:{saved_user.pk}"
        if saved_user is not None
        else str(actor_identifier or "").strip()
    )
    feedback_key = (
        sha256(f"{actor}|{query_hash}|{target}".encode("utf-8")).hexdigest()
        if actor
        else ""
    )
    defaults = {
        "chunk": chunk,
        "chunk_document_id": chunk.document_id if chunk else "",
        "user": saved_user,
        "query_hash": query_hash,
        "query_text": query[:1200] if store_query else "",
        "relevant": relevant,
        "result_rank": max(0, min(int(rank or 0), 500)),
        "metadata": feedback_metadata,
    }
    if not feedback_key:
        return SemanticSearchFeedback.objects.create(**defaults)
    feedback, _created = SemanticSearchFeedback.objects.update_or_create(
        feedback_key=feedback_key,
        defaults=defaults,
    )
    return feedback
