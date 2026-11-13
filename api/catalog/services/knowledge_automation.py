"""New public sources join the existing compilation ledger, never a second queue."""
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog import models as m
from common.capabilities import Capability, has_capability

SETTING_KEY = "knowledge_new_source_policy"
DEFAULT = {"version": 0, "mode": "retrieval", "profile_key": "", "applies_after": None}


def policy_data(actor):
    from catalog.services.knowledge_core import require_editor
    from common.ai_runtime import AICapability, current_profile_document
    require_editor(actor)
    row = m.SiteSetting.objects.filter(key=SETTING_KEY, public=False).first()
    value = {**DEFAULT, **(row.value if row else {})}
    profiles = current_profile_document().get("profiles", [])
    return {**value, "can_manage": has_capability(actor, Capability.MANAGE_AI),
        "profiles": [{"key": p["key"], "model": p.get("model", ""), "enabled": p.get("enabled", False)}
            for p in profiles if p.get("capability") == AICapability.CURATION_REASONING]}


@transaction.atomic
def save_policy(actor, *, version, mode, profile_key=""):
    from catalog.services.knowledge_core import require_editor
    from common.ai_runtime import AICapability, AIRuntimeProfileError, runtime_profile
    from ingestion.models import AuditEvent
    require_editor(actor)
    if not has_capability(actor, Capability.MANAGE_AI):
        raise PermissionDenied("当前账户不能修改新馆藏自动维护设置。")
    if type(version) is not int or mode not in {"retrieval", "draft"}:
        raise ValidationError("自动维护设置无效。")
    if mode == "draft":
        try:
            profile_key = runtime_profile(AICapability.CURATION_REASONING, profile_key or None).key
        except AIRuntimeProfileError as exc:
            raise ValidationError(str(exc)) from exc
    else:
        profile_key = ""
    row, _ = m.SiteSetting.objects.get_or_create(key=SETTING_KEY, defaults={"value": dict(DEFAULT)})
    row = m.SiteSetting.objects.select_for_update().get(pk=row.pk)
    before = {**DEFAULT, **row.value}
    if version != before["version"]:
        raise ValidationError("设置已由其他管理员修改，请重新读取后再保存。", code="stale_policy")
    # Enabling never backfills the old collection. Re-enabling starts a new
    # admission interval; individual subscriptions keep their own pause state.
    since = before["applies_after"] if before["mode"] == "draft" else timezone.now().isoformat()
    row.value = {"version": version+1, "mode": mode, "profile_key": profile_key,
        "applies_after": since if mode == "draft" else None}
    row.updated_by, row.public = actor, False
    row.save()
    AuditEvent.objects.create(actor=actor, action="knowledge_automation_policy", object_type="SiteSetting",
        object_id=SETTING_KEY, before=before, after=row.value)
    return policy_data(actor)


def eligible_sources(value):
    from catalog.services.discovery_sources import source_queryset
    since = parse_datetime(value.get("applies_after") or "")
    if value.get("mode") != "draft" or since is None:
        return m.Edition.objects.none()
    return source_queryset("edition").filter(first_published_at__gte=since,
        knowledge_compilation__isnull=True).order_by("first_published_at", "pk")


@transaction.atomic
def enroll(edition_id):
    """Cheap publication callback: identity and authorization only, no parsing."""
    from catalog.services.knowledge_core import require_editor
    from ingestion.models import AuditEvent
    policy = m.SiteSetting.objects.select_for_update().filter(key=SETTING_KEY, public=False).select_related("updated_by").first()
    if not policy or policy.value.get("mode") != "draft":
        return None
    try:
        require_editor(policy.updated_by)
        if not has_capability(policy.updated_by, Capability.MANAGE_AI):
            return None
    except PermissionDenied:
        return None
    edition = eligible_sources(policy.value).filter(pk=edition_id).first()
    if not edition:
        return None
    subscription, created = m.KnowledgeCompilation.objects.get_or_create(edition=edition, defaults={
        "scope": {"mode": "whole"}, "profile_key": policy.value["profile_key"],
        "execution_mode": "provider", "updated_by": policy.updated_by, "pending_refresh": True})
    if created:
        AuditEvent.objects.create(actor=policy.updated_by, action="knowledge_automatic_enrollment",
            object_type="KnowledgeCompilation", object_id=str(subscription.pk),
            after={"policy_version": policy.value["version"], "edition_id": str(edition.pk),
                "document_revision_id": str(edition.active_catalog_revision.document_revision_id),
                "profile_key": subscription.profile_key, "publication": "review_required"})
    return subscription if created else None


def recover_new_sources():
    """Bounded recovery for a missed after-commit notification, not a bulk run."""
    policy = m.SiteSetting.objects.filter(key=SETTING_KEY, public=False).first()
    if policy:
        for key in eligible_sources(policy.value).values_list("pk", flat=True)[:5]:
            enroll(key)


def resume_configured_sources():
    """A newly enabled configured model resumes its waiting sources, without fallback."""
    from catalog.services.intelligence_provider import configuration
    from ingestion.services.ai_client import AIConfigurationError
    rows = m.KnowledgeCompilation.objects.filter(enabled=True, execution_mode="provider",
        pending_refresh=False, latest_run__status="waiting_configuration")
    # Profiles are an existing bounded registry. Resolve each once, then select
    # a finite batch; disabled profiles cannot starve enabled profiles.
    for key in rows.order_by().values_list("profile_key", flat=True).distinct():
        try:
            ready = configuration(key).enabled
        except AIConfigurationError:
            rows.filter(profile_key=key).update(last_error={"code": "configuration_missing",
                "message": "所选编纂配置已不可用，请在模型管理中恢复；原产物保留。"})
            continue
        if ready:
            ids = list(rows.filter(profile_key=key).order_by("updated_at").values_list("pk", flat=True)[:5])
            m.KnowledgeCompilation.objects.filter(pk__in=ids).update(pending_refresh=True)
