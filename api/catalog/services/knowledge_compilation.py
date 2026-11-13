"""Incremental source subscriptions and interactive-agent stage receipts.

Provider and agent execution share the same immutable inputs, chapter cache,
validators and ChangeSet writer. Agent work is explicit, never a fake Provider.
"""
import json
from types import SimpleNamespace
from uuid import uuid5
from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services.knowledge_core import require_editor, page_content, page_metadata
from catalog.services.knowledge_sources import current_structure, digest, require_revision_access


class AgentStagePending(Exception):
    pass


def run_configuration(run):
    from catalog.services.intelligence_provider import configuration
    if run.execution_mode == "provider":
        return configuration(run.profile_key)
    return SimpleNamespace(enabled=True, provider="interactive_agent", model="session_unspecified",
        profile_key="interactive-agent", base_url="", reasoning="", capability="curation_reasoning",
        max_input_chars=20000, max_output_tokens=4096, temperature=0, timeout=300)


def affected_pages(revision, subscription=None):
    related = m.KnowledgeBlockDependency.objects.filter(
        Q(source_type="work", source_id=revision.asset.edition.work_id)
        | Q(source_type="document_revision", source_id=revision.pk)).values("page_id")
    scope = Q(pk__in=related) | Q(work_id=revision.asset.edition.work_id)
    if subscription:
        scope |= Q(compilation_sources=subscription)
    return m.KnowledgePage.objects.filter(scope).distinct().order_by("pk")


@transaction.atomic
def configure(revision, actor, *, enabled=True, scope=None, profile_key="", execution_mode="provider", target_page_ids=()):
    require_editor(actor)
    require_revision_access(revision, actor, editorial=True)
    if execution_mode not in {"provider", "agent"} or type(enabled) is not bool:
        raise ValidationError("编纂执行方式或启用状态无效。")
    from catalog.services.intelligence import validate_scope
    scope = validate_scope(revision, scope)
    if not isinstance(target_page_ids, (list, tuple)) or len(target_page_ids) > 30:
        raise ValidationError("每部文献最多指定30个专题或知识页。")
    from catalog.services.intelligence_changes import uuid_value
    ids = {uuid_value(key) for key in target_page_ids}
    pages = list(m.KnowledgePage.objects.filter(pk__in=ids))
    if len(pages) != len(ids):
        raise ValidationError("目标知识页不存在。")
    subscription, _ = m.KnowledgeCompilation.objects.select_for_update().get_or_create(
        edition=revision.asset.edition, defaults={"updated_by":actor})
    subscription.enabled, subscription.scope = enabled, scope
    subscription.profile_key, subscription.execution_mode = profile_key, execution_mode
    subscription.updated_by = actor
    subscription.save()
    subscription.target_pages.set(pages)
    if enabled:
        reconcile(revision, subscription=subscription)
    elif subscription.latest_run_id:
        from catalog.services.intelligence import control_run
        if subscription.latest_run.status not in {"succeeded", "empty", "partial", "canceled"}:
            control_run(subscription.latest_run_id, actor, "cancel")
    subscription.refresh_from_db()
    return subscription


def request_page_refresh(page_ids):
    works = m.KnowledgeBlockDependency.objects.filter(page_id__in=page_ids, source_type="work").values("source_id")
    own_works = m.KnowledgePage.objects.filter(pk__in=page_ids, work__isnull=False).values("work_id")
    rows = m.KnowledgeCompilation.objects.filter(enabled=True).filter(
        Q(target_pages__in=page_ids) | Q(edition__work_id__in=works) | Q(edition__work_id__in=own_works)).distinct()
    ids = list(rows.values_list("pk", flat=True))
    if not ids:
        return
    m.KnowledgeCompilation.objects.filter(pk__in=ids).update(pending_refresh=True)
    def dispatch():
        from catalog.intelligence_tasks import refresh_compilations
        try:
            refresh_compilations.apply_async(queue="intelligence")
        except Exception:
            # The durable flag is drained by the existing beat/queue machinery.
            m.KnowledgeCompilation.objects.filter(pk__in=ids).update(last_error={
                "code":"queue_unavailable", "message":"更新已记录，等待执行队列恢复。"})
    transaction.on_commit(dispatch)


def reconcile_pending():
    from catalog.services.knowledge_automation import recover_new_sources, resume_configured_sources
    recover_new_sources()
    resume_configured_sources()
    ids = list(m.KnowledgeCompilation.objects.filter(enabled=True, pending_refresh=True).order_by("updated_at").values_list("pk", flat=True)[:30])
    for key in ids:
        try:
            with transaction.atomic():
                subscription = m.KnowledgeCompilation.objects.select_for_update().get(pk=key)
                if not subscription.enabled or not subscription.pending_refresh:
                    continue
                revision = subscription.latest_run.document_revision if subscription.latest_run_id else subscription.edition.active_catalog_revision.document_revision
                published = subscription.edition.active_catalog_revision
                if (published and published.document_revision_id and published.document_revision.asset_id != revision.asset_id
                        and published.document_revision.created_at > revision.created_at):
                    revision = published.document_revision
                revision = m.DocumentRevision.objects.filter(asset=revision.asset, is_active=True).first() or revision
                reconcile(revision, retry=True)
                m.KnowledgeCompilation.objects.filter(pk=key).update(pending_refresh=False, last_error={})
        except Exception as exc:
            m.KnowledgeCompilation.objects.filter(pk=key).update(last_error={
                "code":type(exc).__name__, "message":"编纂接续失败，已保留原产物；请核对来源和执行配置后重试。"})


@transaction.atomic
def reconcile(revision, *, subscription=None, retry=False):
    from catalog.services.intelligence import create_run, control_run, SOURCE_SELECTION_VERSION
    from catalog.services.intelligence_provider import identity, configuration
    subscription = m.KnowledgeCompilation.objects.select_for_update(of=("self",)).filter(
        edition_id=revision.asset.edition_id, enabled=True).select_related("updated_by", "latest_run").first()
    if not subscription:
        return None
    require_editor(subscription.updated_by)
    require_revision_access(revision, subscription.updated_by, editorial=True)
    structure = current_structure(revision, prepare=True)
    targets = list(affected_pages(revision, subscription))
    # Page edits affect compilation, not chapter analysis. Input hashes for each
    # chapter and Wiki block remain independent within the shared run cache.
    page_versions = [(str(p.pk), digest({"blocks":page_content(p)[0],
        "metadata":page_metadata(p, draft=True)})) for p in targets]
    config = configuration(subscription.profile_key) if subscription.execution_mode == "provider" else None
    key = digest([str(revision.pk), structure.input_hash, SOURCE_SELECTION_VERSION, subscription.scope, page_versions,
        subscription.execution_mode, identity(config) if config else "interactive-agent-v1"])
    previous = subscription.latest_run
    if previous and subscription.requested_hash == key:
        if retry and previous.status in {"failed", "waiting_configuration", "waiting_resource", "waiting_executor", "canceled"}:
            control_run(previous.pk, subscription.updated_by, "resume")
        return previous
    if previous and previous.status not in {"succeeded", "partial", "empty", "canceled", "failed"}:
        control_run(previous.pk, subscription.updated_by, "cancel")
    scope = {**subscription.scope, "target_page_ids":[str(p.pk) for p in targets], "compilation_id":str(subscription.pk)}
    run = create_run(revision, subscription.updated_by, request_id=uuid5(subscription.pk, key), scope=scope,
        profile_key=subscription.profile_key, execution_mode=subscription.execution_mode)
    subscription.latest_run, subscription.requested_hash = run, key
    subscription.save(update_fields=["latest_run", "requested_hash", "updated_at"])
    return run


def queue_agent_stage(run, stage, unit, data, prompt, schema, config, key, lease):
    from catalog.services.intelligence import _guard
    from catalog.services.intelligence_provider import identity, PROMPT_VERSION
    with transaction.atomic():
        m.CurationRun.objects.select_for_update().get(pk=run.pk)
        _guard(run, lease)
        m.CurationArtifact.objects.update_or_create(run=run, stage=stage, unit=unit, defaults={
            "cache_key":key, "schema_version":PROMPT_VERSION, "status":"waiting_agent",
            "input_manifest":data, "output":{}, "output_hash":"", "model_identity":identity(config),
            "execution_request":{"prompt":prompt, "schema":schema, "run_version":run.version},
            "usage":{"model_calls":0, "agent_responses":0}})
        m.CurationRun.objects.filter(pk=run.pk, version=run.version).update(status="waiting_agent", stage=stage,
            error={"code":"waiting_agent", "message":"原文窗口已准备，等待本次代理提交编纂结果；未调用配置中的模型。"})
    raise AgentStagePending()


def agent_packet(artifact, actor):
    require_editor(actor)
    run = artifact.run
    require_revision_access(run.document_revision, actor, editorial=True)
    if run.execution_mode != "agent" or run.status == "canceled" or artifact.execution_request.get("run_version") != run.version:
        raise ValidationError("此编纂窗口已失效。")
    return {"artifact_id":str(artifact.pk), "run_id":str(run.pk), "run_version":run.version,
        "input_hash":artifact.cache_key, "stage":artifact.stage, "unit":artifact.unit,
        "prompt":artifact.execution_request["prompt"], "schema":artifact.execution_request["schema"],
        "input":artifact.input_manifest, "status":artifact.status}


@transaction.atomic
def submit_agent_result(artifact_id, actor, *, input_hash, run_version, output, executor_label):
    require_editor(actor)
    original = m.CurationArtifact.objects.get(pk=artifact_id)
    run = m.CurationRun.objects.select_for_update().get(pk=original.run_id)
    artifact = m.CurationArtifact.objects.select_for_update().get(pk=artifact_id)
    require_revision_access(run.document_revision, actor, editorial=True)
    if (run.execution_mode != "agent" or input_hash != artifact.cache_key
            or run_version != artifact.execution_request.get("run_version")):
        raise ValidationError("结果不属于此窗口和版本。")
    if artifact.status in {"succeeded", "empty"}:
        if artifact.output_hash != digest(output):
            raise ValidationError("此窗口已有不同的完成回执。")
        return artifact
    agent_packet(artifact, actor)
    structure = current_structure(run.document_revision)
    if not structure or structure.pk != run.structure_id:
        raise ValidationError("原文结构已更新，旧窗口不能提交。")
    if artifact.status != "waiting_agent" or not isinstance(executor_label, str) or not executor_label.strip() or len(executor_label) > 160:
        raise ValidationError("窗口状态或代理执行标识无效。")
    if len(json.dumps(output, ensure_ascii=False).encode("utf-8")) > 100000:
        raise ValidationError("单窗口产物过大。")
    from ingestion.services.ai_client import _validate_schema, AIInvalidOutput
    from catalog.services.intelligence_remote import validate_result
    try:
        _validate_schema(output, artifact.execution_request["schema"])
    except AIInvalidOutput as exc:
        raise ValidationError(str(exc)) from exc
    validate_result(artifact, output)
    artifact.output, artifact.output_hash = output, digest(output)
    artifact.status = "empty" if artifact.stage == 2 and not output.get("entities") and not output.get("assertions") else "succeeded"
    artifact.executor_id = executor_label.strip()
    artifact.model_identity = {**artifact.model_identity, "executor_label":executor_label.strip()}
    artifact.usage = {"model_calls":0, "agent_responses":1, "tokens":None, "cost":None}
    artifact.error = {}
    artifact.save()
    run.version += 1
    run.status, run.error = "waiting", {}
    run.save(update_fields=["version", "status", "error", "updated_at"])
    from catalog.services.intelligence import schedule
    schedule(run)
    return artifact


def compilation_data(subscription, actor):
    require_editor(actor)
    run = subscription.latest_run
    if run:
        require_revision_access(run.document_revision, actor, editorial=True)
    waiting = run.artifacts.filter(status="waiting_agent").order_by("stage", "created_at").first() if run else None
    changeset = m.ChangeSet.objects.filter(run=run).first() if run else None
    coverage = {key:value for key,value in run.coverage.items() if key not in {"included_nodes", "excluded_pages"}} if run else {}
    if run:
        start, end = run.scope.get("start", 1), run.scope.get("end", run.document_revision.asset.page_count)
        coverage["missing_text_pages"] = [p for p in coverage.get("missing_text_pages", []) if start <= p <= end]
    return {"id":str(subscription.pk), "edition_id":str(subscription.edition_id),
        "work_id":str(subscription.edition.work_id), "title":subscription.edition.work.title,
        "enabled":subscription.enabled, "execution_mode":subscription.execution_mode,
        "pending_refresh":subscription.pending_refresh, "refresh_error":subscription.last_error,
        "scope":subscription.scope, "profile_key":subscription.profile_key,
        "target_page_ids":[str(key) for key in subscription.target_pages.values_list("pk", flat=True)],
        "run_id":str(run.pk) if run else None, "status":run.status if run else "waiting",
        "plan_version":run.plan_version if run else None,
        "stage":run.stage if run else 1,
        "coverage":coverage,
        "excluded_page_count":len(run.coverage.get("excluded_pages", [])) if run else 0, "error":run.error if run else {},
        "waiting_artifact_id":str(waiting.pk) if waiting else None,
        "changeset_id":str(changeset.pk) if changeset else None,
        "updated_at":subscription.updated_at}
