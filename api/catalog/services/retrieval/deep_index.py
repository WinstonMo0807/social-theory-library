"""EG2 projection of existing Discovery documents; canonical data stays unchanged."""
from types import SimpleNamespace
from uuid import UUID

from django.conf import settings

from catalog.services.discovery_inference import embed_texts
from catalog.services.discovery_projection import DiscoveryIndexError, meili, validate_discovery_results
from catalog.services.discovery_sources import fingerprint


def configuration():
    generation = str(getattr(settings, "STL_DEEP_RETRIEVAL_GENERATION", ""))
    artifact = str(getattr(settings, "STL_DEEP_RETRIEVAL_EMBEDDING_ARTIFACT", ""))
    uid = str(getattr(settings, "STL_DEEP_RETRIEVAL_INDEX_UID", ""))
    try:
        expected = "stl4_deep_" + UUID(generation).hex + "_" + artifact.removeprefix("stl4-deep-")
    except ValueError as exc:
        raise DiscoveryIndexError("deep_configuration", "请先配置深度模型制品和独立索引。") from exc
    if (not artifact.startswith("stl4-deep-") or len(artifact) != 74 or uid != expected
            or int(getattr(settings, "STL_DEEP_RETRIEVAL_EMBEDDING_DIMENSIONS", 768)) != 768):
        raise DiscoveryIndexError("deep_configuration", "独立索引须绑定当前EG2制品及代次，不能写入基础索引。")
    return uid, artifact, generation


def prepare_index():
    from catalog.services.discovery_indexing import ensure_index

    uid, _, _ = configuration()
    ensure_index(SimpleNamespace(uid=uid, dimensions=768, config_snapshot={}),
        extra_filterable=("baseline_generation",), persist_configuration=False)
    return uid


def project_document(document):
    from catalog.services.discovery_indexing import wait_index_task

    if document.channel != "passages" or document.access_status != "public" or not document.keyword_ready:
        return False
    identity = {"id": str(document.pk), "source_revision": document.source_revision}
    if not validate_discovery_results("passages", [identity], ["public"]):
        return False
    uid, artifact, generation = configuration()
    title = str(document.payload.get("title") or "")
    input_hash = fingerprint([artifact, title, document.normalized_text])
    try:
        stored = meili("GET", f"/indexes/{uid}/documents/{document.pk}")
        if stored.get("input_hash") == input_hash and stored.get("source_revision") == document.source_revision:
            return False
    except DiscoveryIndexError as exc:
        if exc.code != "index_missing":
            raise
        prepare_index()
    vector = embed_texts([document.normalized_text], titles=[title], expected_artifact=artifact,
                        expected_dimensions=768, deep_generation=generation)["vectors"][0]
    # A publication may change while the model runs. Reuse the canonical
    # source/permission check; never treat old experiment rows as current data.
    if not validate_discovery_results("passages", [identity], ["public"]):
        return False
    row = {**identity, "channel": "passages", "source_type": document.source_type,
           "baseline_generation": str(document.generation_id),
           "source_id": str(document.source_id), "scope_token": document.scope_token,
           "access_status": "public", "input_hash": input_hash, "title": title,
           "aliases": document.payload.get("aliases", []), "authors": document.payload.get("authors", []),
           "language": document.payload.get("language", "unknown"), "normalized_text": document.normalized_text,
           "_vectors": {"discovery": vector}}
    wait_index_task(meili("POST", f"/indexes/{uid}/documents", [row]))
    return True


def remove_source(filters):
    from catalog.services.discovery_indexing import wait_index_task

    uid, _, _ = configuration()
    try:
        meili("GET", f"/indexes/{uid}")
    except DiscoveryIndexError as exc:
        if exc.code == "index_missing":
            return
        raise
    wait_index_task(meili("POST", f"/indexes/{uid}/documents/delete", {"filter": filters}))
