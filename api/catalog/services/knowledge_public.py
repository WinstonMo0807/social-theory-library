"""Knowledge publication uses the existing canonical/editorial transaction."""
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from catalog import models as m
from catalog.services.knowledge_core import require_editor, page_content
from catalog.services.knowledge_sources import require_revision_access, locator
from catalog.services.publication_eligibility import public_editions
from common.capabilities import Capability, has_capability


def assertion_public(statement):
    sources = list(statement.sources.select_related("document_revision__asset").all())
    if statement.status != "published" or not sources:
        return False
    for source in sources:
        if source.document_revision_id and not (public_editions(require_fulltext=True).filter(pk=source.edition_id).exists()
            and m.CatalogPublicationRevision.objects.filter(document_revision=source.document_revision,
                reader_asset_id=source.document_revision.asset_id, status__in=["active", "superseded"], fulltext_ready=True).exists()):
            return False
        if not source.document_revision_id and not public_editions().filter(work_id=source.work_id).exists():
            return False
    return True


def assertion_data(statement, actor, *, draft=False):
    if draft:
        require_editor(actor)
    elif not assertion_public(statement):
        raise Http404
    evidence = []
    for link in statement.evidence.select_related("anchor__document_revision__asset__edition"):
        value = {"anchor_id": str(link.anchor_id), "stance": link.stance}
        if actor and actor.is_authenticated:
            value["locator"] = locator(link.anchor, actor, editorial=draft)
        evidence.append(value)
    return {"id": str(statement.pk), "text": statement.text, "category": statement.category,
        "predicate": statement.predicate, "expression": statement.expression, "conditions": statement.conditions,
        "status": statement.status, "evidence": evidence,
        "participants": list(statement.participants.values("role", "entity_id", "entity__label", "work_id", "edition_id")),
        "sources": list(statement.sources.values("work_id", "work__title", "edition_id", "document_revision_id", "node_id", "attribution_id", "attribution__label", "expression"))}


def page_data(page, actor, *, draft=False):
    if draft:
        require_editor(actor)
        blocks, revision = page_content(page)
    else:
        if page.status != "published" or page.work_id and not public_editions().filter(work_id=page.work_id).exists():
            raise Http404
        blocks = page.body_blocks
        revision = m.EditorialRevision.objects.filter(target_type="knowledge_page", target_id=page.pk, status="published").order_by("-revision").first()
    assertions, visible = {}, []
    for block in blocks:
        keep = True
        for ref in block.get("references", []):
            if ref.get("type") == "assertion":
                statement = get_object_or_404(m.Assertion, pk=ref["id"])
                if not draft and not assertion_public(statement):
                    keep = False
                    break
                assertions[ref["id"]] = assertion_data(statement, actor, draft=draft)
        if keep:
            visible.append(block)
    return {"id": str(page.pk), "title": page.title, "status": "draft" if draft else page.status,
        "revision_id": str(revision.pk) if revision else None, "blocks": visible, "assertions": list(assertions.values()),
        "publication_scope": {"page_id": str(page.pk), "assertion_ids": list(assertions)}}


@transaction.atomic
def publish_page(page_id, revision_id, actor):
    require_editor(actor)
    if not has_capability(actor, Capability.PUBLISH_AUTHORITY):
        raise PermissionDenied("当前账户不能公开发布知识。")
    page = get_object_or_404(m.KnowledgePage.objects.select_for_update(), pk=page_id)
    from catalog.services.editorial_revision import create_editorial_revision, publish_editorial_revision
    latest = get_object_or_404(m.EditorialRevision.objects.select_for_update(), pk=revision_id,
        target_type="knowledge_page", target_id=page.pk)
    if latest.status == "published":
        return page_data(page, actor)
    blocks, current = page_content(page)
    if not current or current.pk != latest.pk:
        raise ValidationError("知识页草稿已变化，请重新预览再发布。")
    for block in blocks:
        for ref in block.get("references", []):
            if ref.get("type") == "assertion":
                statement = get_object_or_404(m.Assertion.objects.select_for_update(), pk=ref["id"])
                # Only an applied human-reviewed item may enter publication.
                if not m.ChangeItem.objects.filter(application__id=str(statement.pk), decision="accepted").exists():
                    raise ValidationError("陈述尚未经过管理员审核保存。")
                if not statement.evidence.exists():
                    raise ValidationError("陈述尚无可验证原文证据。")
                for link in statement.evidence.select_related("anchor__document_revision__asset__edition"):
                    require_revision_access(link.anchor.document_revision, actor, editorial=False)
                statement.status = "published"
                statement.save(update_fields=["status", "updated_at"])
                m.Entity.objects.filter(assertion_participations__assertion=statement, status="draft").update(status="published")
            elif ref.get("type") == "anchor":
                anchor = get_object_or_404(m.EvidenceAnchor, pk=ref["id"])
                require_revision_access(anchor.document_revision, actor, editorial=False)
            else:
                from catalog.services.editorial_blocks import resolve_target
                resolve_target(ref, public=True)
    publish = create_editorial_revision(target_type="knowledge_page", target_id=page.pk,
        patch={"title": latest.materialized_preview["title"], "scope": latest.materialized_preview.get("scope", ""),
            "body_blocks": blocks, "status": "published"}, actor=actor,
        idempotency_key=f"knowledge-publish:{latest.pk}", change_note="发布已预览知识页及其已审核陈述")
    publish_editorial_revision(publish.pk, actor=actor)
    page.refresh_from_db()
    return page_data(page, actor)
