"""Publication commands over the existing canonical snapshot/outbox services."""
from datetime import date
from hashlib import sha256
import json
from uuid import UUID

from django.db import transaction

from catalog.contracts.fields import FIELD_CONTRACTS
from catalog.models import Asset, CatalogPublicationRevision, Discipline, Edition, EditorialRevision, KnowledgeNode, Person, PublisherAuthority, Subdiscipline, Topic, Work


class PublicationCommandError(ValueError):
    pass


def validate_revision(revision, *, edition=None, for_rollback=False):
    edition = edition or revision.edition
    errors = []
    if revision.edition_id != edition.pk:
        errors.append("发布修订不属于当前版本。")
    if for_rollback and (revision.activated_at is None or revision.status not in {"active", "superseded"}):
        errors.append("只能恢复曾合法公开的修订。")
    if not revision.metadata_ready:
        errors.append("该修订的书目尚未就绪。")
    if revision.reader_asset_id:
        asset = revision.reader_asset
        if asset.edition_id != edition.pk or asset.status != Asset.Status.READY or asset.validation_status == Asset.ValidationStatus.INVALID:
            errors.append("该修订的阅读文件不属于当前版本或未通过验证。")
        if for_rollback:
            from ingestion.services.publication import _asset_storage_readable

            if not _asset_storage_readable(asset):
                errors.append("历史阅读文件当前无法读取，不能恢复此修订。")
    if revision.document_revision_id:
        document = revision.document_revision
        if not revision.reader_asset_id or document.asset_id != revision.reader_asset_id:
            errors.append("文档修订与阅读文件不一致。")
    if revision.fulltext_ready and not revision.document_revision_id:
        errors.append("全文就绪修订缺少文档依据。")
    return errors


def publication_history(edition):
    return [{"id": str(row.pk), "revision": row.revision, "title": row.snapshot.get("work", {}).get("title", ""),
             "status": row.status, "activated_at": row.activated_at, "is_current": row.pk == edition.active_catalog_revision_id,
             "can_rollback": row.activated_at is not None and row.status in {"active", "superseded"}}
            for row in edition.catalog_revisions.order_by("-revision")[:50]]


def catalog_publication_state(edition):
    """Report actual public visibility separately from the editorial decision."""
    edition = Edition.objects.select_related("active_catalog_revision").get(pk=edition.pk)
    revision = edition.active_catalog_revision
    visible = bool(
        edition.state == "published" and edition.is_primary and revision is not None
        and revision.edition_id == edition.pk and revision.status == "active" and revision.metadata_ready
    )
    if edition.state == "withdrawn":
        state, detail = "withdrawn", "馆藏已撤回，文件与历史版本保留。"
    elif visible:
        state, detail = "published", "书目已公开。"
        if edition.intelligence_status == "failed":
            detail += "部分智能处理异常，不影响当前书目和获准阅读的 PDF。"
        elif edition.intelligence_status == "processing":
            detail += "智能内容仍在后台处理。"
    elif edition.state == "published":
        state = "publishing"
        detail = "已确认发布，公开版本尚未就绪。请查看发布处理状态。"
        if not edition.is_primary:
            detail = "已确认发布。此版本不是主版本，不在公开书目列表中展示。"
        elif not edition.catalog_revisions.exists():
            detail = "已记录发布决定，但缺少正式发布修订，请核查历史发布记录。"
    else:
        state, detail = "unpublished", "馆藏尚未确认发布。"
    return {
        "editorial_state": edition.state, "public_state": state,
        "publicly_visible": visible, "detail": detail,
        "active_revision_id": str(revision.pk) if revision else None,
        "fulltext_ready": bool(visible and revision.fulltext_ready and revision.document_revision_id),
        "public_url": f"/works/{edition.public_slug}" if visible and edition.public_slug else "",
    }


def catalog_health(edition, *, field_state=None):
    from catalog.services.field_decisions import field_readiness

    fields = field_state if field_state is not None else field_readiness(edition)
    editorial_fields = [row for row in fields if row.field_name not in {"file", "reader_asset", "ocr_text", "page_labels"}]
    editorial = "conflict" if any(row.status == "conflict" for row in editorial_fields) else "draft" if any(
        row.required and row.status == "empty" for row in editorial_fields
    ) else "needs_review" if any(row.status in {"stale", "needs_review"} for row in editorial_fields) else "ready"
    processing = {"draft": "idle", "processing": "processing", "failed": "failed", "active": "ready", "withdrawn": "idle"}.get(edition.intelligence_status, "partial")
    visibility = catalog_publication_state(edition)
    if not visibility["publicly_visible"]:
        publication = visibility["public_state"]
    elif processing == "processing" and edition.catalog_revisions.filter(
        revision__gt=edition.active_catalog_revision.revision,
        status__in=["preparing", "failed"],
    ).exists():
        publication = "publishing"
    elif EditorialRevision.objects.filter(target_type="work", target_id=edition.work_id, status="draft").exists():
        publication = "changes_pending"
    else:
        snapshot = edition.active_catalog_revision.snapshot or {}
        public = _public_values(snapshot)
        actual = {row.field_name: row.value for row in fields}
        relevant = set(actual).intersection(public) - {"file", "reader_asset", "publication_mode"}
        pending_changes = any(not _same_public_value(public[name], actual[name]) for name in relevant)
        publication = "changes_pending" if pending_changes else "published"
    return {"editorial": editorial, "processing": processing, "publication": publication}


def _same_public_value(before, after):
    # Model DateFields are date objects; immutable JSON snapshots use ISO text.
    # Compare their public value without changing either the draft or snapshot.
    if isinstance(before, date):
        before = before.isoformat()
    if isinstance(after, date):
        after = after.isoformat()
    empty = (None, "", [])
    return before == after or (before in empty and after in empty)


def _public_values(snapshot):
    values = {**snapshot.get("work", {}), **snapshot.get("edition", {})}
    if snapshot.get("edition"):
        # Pre-3.0.5 publications were document-backed and lacked this new field.
        values.setdefault("publication_mode", "document")
    roles = {"authors": "author", "translators": "translator", "chief_editors": "chief_editor",
             "editors": "editor", "annotators": "annotator", "photographers": "photographer", "other_contributors": "other"}
    for name, role in roles.items():
        values[name] = [row["person_id"] for row in snapshot.get("contributions", []) if row.get("role") == role]
    for name, section, key in (("disciplines", "classification", "disciplines"), ("subdisciplines", "classification", "subdisciplines"),
                               ("topics", "knowledge", "topics"), ("theories", "knowledge", "nodes")):
        values[name] = [row["id"] for row in snapshot.get(section, {}).get(key, [])]
    values["reader_asset"] = snapshot.get("document", {}).get("asset_id")
    values["file"] = values["reader_asset"]
    values["journal_contents"] = snapshot.get("journal_contents", [])
    values["translation_of"] = values.get("translation_of_id")
    return values


def prepare_revision(edition):
    """Read-only diff of the actual saved editorial draft and current public view."""
    from catalog.services.field_decisions import formal_field_values
    from catalog.services.publication_eligibility import active_catalog_snapshot
    from ingestion.services.publication import publication_preflight

    edition = Edition.objects.select_related("work", "active_catalog_revision").get(pk=edition.pk)
    values, confirmed = formal_field_values(edition)
    values["file"] = values.get("reader_asset")
    public_snapshot = active_catalog_snapshot(edition)
    public = _public_values(public_snapshot)
    from catalog.services.media import WORK_IMAGE_SLOTS, preview_work_media

    draft = EditorialRevision.objects.filter(target_type="work", target_id=edition.work_id, status="draft").order_by("-revision").first()
    media_values = {
        config["snapshot"]: preview_work_media(edition.work, slot=slot, preview=draft.materialized_preview if draft else None)
        for slot, config in WORK_IMAGE_SLOTS.items()
    }
    fingerprint = sha256(json.dumps({
        "values": values, "public_revision_id": str(edition.active_catalog_revision_id),
        "confirmed_fields": sorted(confirmed), **media_values,
    }, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
    names = {}
    old_names = {str(row["person_id"]): row.get("name", "") for row in public_snapshot.get("contributions", [])}
    for section, fields in (("classification", ("disciplines", "subdisciplines")), ("knowledge", ("topics", "nodes"))):
        for key in fields:
            old_names.update({str(row["id"]): row.get("name", "") for row in public_snapshot.get(section, {}).get(key, [])})
    for resolver, model, label_field in (("person", Person, "preferred_name"), ("publisher", PublisherAuthority, "canonical_name"),
                                        ("work", Work, "title"), ("knowledge_node", KnowledgeNode, "canonical_name_zh"),
                                        ("discipline", Discipline, "name"), ("subdiscipline", Subdiscipline, "name"), ("topic", Topic, "name")):
        ids = set()
        for field in FIELD_CONTRACTS.values():
            if field.authority_resolver != resolver:
                continue
            value = values.get(field.name)
            for item in value if isinstance(value, list) else [value]:
                try:
                    ids.add(UUID(str(item)))
                except (TypeError, ValueError):
                    continue
        names.update({str(row.pk): str(getattr(row, label_field) or getattr(row, "canonical_name_en", "")) for row in model.objects.filter(pk__in=ids)})

    def display(value, name, *, previous=False):
        labels = old_names if previous else names
        if name in {"cover", "recommendation_image"} and isinstance(value, dict):
            media = value.get("media") or {}
            return "\n".join([f"已选{FIELD_CONTRACTS[name].label}", *[
                f"{label}：{media[key]}" for key, label in (
                    ("alt_text", "图片说明"), ("source_label", "来源"), ("source_url", "来源网址"),
                    ("rights", "使用权说明"), ("license", "许可"), ("credit", "署名"),
                ) if media.get(key)
            ]])
        if name in {"file", "reader_asset"}:
            return "已关联文献" if value else "无文献"
        if isinstance(value, list):
            return "、".join(str(item.get("title", "目录条目")) if isinstance(item, dict) else labels.get(str(item), names.get(str(item), "关联对象")) for item in value)
        return "" if value is None else labels.get(str(value), names.get(str(value), str(value)))

    changes = []
    for name, field in FIELD_CONTRACTS.items():
        if name in {"ocr_text", "page_labels", "curation"}:
            continue
        before, after = public.get(name), values.get(name)
        image_config = next((config for config in WORK_IMAGE_SLOTS.values() if config["field"] == name), None)
        if image_config is not None:
            key = image_config["snapshot"]
            if public.get(key):
                before = {"file": before, "media": public[key]}
            if media_values[key]:
                after = {"file": after, "media": media_values[key]}
        empty = (None, "", [])
        state = "unchanged" if _same_public_value(before, after) else "added" if before in empty else "removed" if after in empty else "changed"
        changes.append({"field": name, "label": field.label, "change": state,
                        "before": before, "after": after, "before_display": display(before, name, previous=True), "after_display": display(after, name)})
    checks = publication_preflight(edition)
    return {"edition_id": str(edition.pk), "active_revision_id": str(edition.active_catalog_revision_id) if edition.active_catalog_revision_id else None,
            "fingerprint": fingerprint, "changes": changes, "blocking": checks["blockers"], "warnings": checks["warnings"],
            "background_processing": checks["background_tasks"], "can_publish": not checks["blockers"]}


@transaction.atomic
def activate_revision(edition, actor=None, idempotency_key=None, *, prepared_fingerprint="", **options):
    from ingestion.services.publication import PublicationBlocked, _publish_edition

    edition = Edition.objects.select_for_update(of=("self",)).select_related("active_catalog_revision").get(pk=edition.pk)
    Work.objects.select_for_update().get(pk=edition.work_id)
    if edition.active_catalog_revision_id and edition.active_catalog_revision.edition_id != edition.pk:
        raise PublicationBlocked(["当前公开修订不属于此版本。"])
    if prepared_fingerprint and prepare_revision(edition)["fingerprint"] != prepared_fingerprint:
        raise PublicationBlocked(["内容已在准备发布后变化，请重新检查差异。"])
    return _publish_edition(edition, actor=actor, idempotency_key=idempotency_key, **options)


@transaction.atomic
def withdraw_revision(edition, actor=None, reason=""):
    from ingestion.services.publication import _withdraw_edition

    return _withdraw_edition(edition, actor=actor, reason=reason)


@transaction.atomic
def rollback_revision(edition, revision_id, *, actor, idempotency_key, reason=""):
    """Republish only an already-activated snapshot under a new sequence.

    The original revision stays immutable. A monotonic recovery publication
    ensures delayed deliveries from the abandoned newer revision cannot win.
    Until recovery processing completes, the old active pointer keeps serving.
    """
    from catalog.services.knowledge_publication import create_catalog_publication_event
    from ingestion.models import AuditEvent

    edition = Edition.objects.select_for_update().get(pk=edition.pk)
    target = CatalogPublicationRevision.objects.select_related("reader_asset", "document_revision").get(pk=revision_id)
    errors = validate_revision(target, edition=edition, for_rollback=True)
    if errors:
        raise PublicationCommandError(" ".join(errors))
    if edition.state != "published":
        raise PublicationCommandError("已撤回作品请先明确重新发布，不能通过回滚恢复公开。")
    event = create_catalog_publication_event(
        edition, event_type="catalog_updated", changed_fields=["catalog_publish"], actor=actor,
        idempotency_key=idempotency_key, restore_from_revision=target,
        provenance={"source": "catalog_rollback", "rollback_source_revision_id": str(target.pk), "reason": reason[:1000]},
    )
    if not AuditEvent.objects.filter(action="catalog.rollback_prepared", object_id=str(event.pk)).exists():
        AuditEvent.objects.create(actor=actor, action="catalog.rollback_prepared", object_type="KnowledgePublicationEvent",
                                  object_id=str(event.pk), after={"edition_id": str(edition.pk), "source_revision_id": str(target.pk)})
    return event
