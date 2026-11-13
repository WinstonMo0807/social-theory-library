"""Knowledge publication uses the existing canonical/editorial transaction."""
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from catalog import models as m
from catalog.services.knowledge_core import require_editor, page_content, page_metadata, entity_data
from catalog.services.knowledge_sources import require_revision_access, locator
from catalog.services.publication_eligibility import public_editions
from common.capabilities import Capability, has_capability
from catalog.services.academic_vocabulary import PREDICATES
from catalog.services.knowledge_identity import canonical_entity


def public_entities():
    """Legacy profile publication remains authoritative for its mapped identity."""
    from django.db.models import Q
    from catalog.services.discovery_sources import source_queryset
    scope = Q(pk__in=[])
    standalone = Q(status="published")
    for field, kind in (("person", "scholar"), ("node", "node"), ("topic", "topic"),
                        ("discipline", "discipline"), ("subdiscipline", "subdiscipline"),
                        ("concept", "concept")):
        scope |= Q(**{f"{field}_id__in": source_queryset(kind).values("person_id" if kind == "scholar" else "pk")})
        standalone &= Q(**{f"{field}__isnull": True})
    scope |= Q(theory_school__editorial_status="published")
    standalone &= Q(theory_school__isnull=True)
    scope |= Q(organization__authority_status="verified")
    scope |= Q(timeline_event__review_status="approved", timeline_event__merged_into__isnull=True)
    scope |= Q(research_object__isnull=False, status="published")
    standalone &= Q(organization__isnull=True, timeline_event__isnull=True, research_object__isnull=True)
    return m.Entity.objects.filter(scope | standalone, merged_into__isnull=True).exclude(status__in=["withdrawn", "archived"])


def prime_assertion_visibility(statements, visibility):
    """Batch the same visibility predicates for prefetched bounded statements.

    The dictionary is valid for this read only. Callers still use
    assertion_public, and create a fresh dictionary after any model call.
    """
    from django.db.models import F
    sources = [s for statement in statements for s in statement.retrieval_sources]
    participants = [p for statement in statements for p in statement.retrieval_participants]
    identities = {s.attribution_id for s in sources if s.attribution_id} | {p.entity_id for p in participants if p.entity_id}
    identities = {key for key in identities if ("entity", key) not in visibility}
    redirects, pending = {}, identities
    while pending:
        found = dict(m.Entity.objects.filter(pk__in=pending).values_list("pk", "merged_into_id"))
        redirects.update(found)
        pending = {key for key in found.values() if key and key not in redirects}
        if len(redirects) > max(1, len(identities)) * 33:
            raise ValueError("身份重定向超过安全范围，请核对归并历史。")
    canonical = {}
    for key in identities:
        cursor, seen = key, set()
        while redirects.get(cursor):
            if cursor in seen or len(seen) >= 32:
                raise ValueError("身份重定向存在循环或超过安全范围，请核对归并历史。")
            seen.add(cursor)
            cursor = redirects[cursor]
        canonical[key] = cursor
    published = set(public_entities().filter(pk__in=set(canonical.values())).values_list("pk", flat=True))
    visibility.update((("entity", key), value in published) for key, value in canonical.items())
    works = {s.work_id for s in sources if s.work_id and not s.document_revision_id} | {p.work_id for p in participants if p.work_id}
    works = {key for key in works if ("work", key) not in visibility}
    published_works = set(public_editions().filter(work_id__in=works).values_list("work_id", flat=True))
    visibility.update((("work", key), key in published_works) for key in works)
    editions = {p.edition_id for p in participants if p.edition_id and ("edition", p.edition_id) not in visibility}
    published_editions = set(public_editions().filter(pk__in=editions).values_list("pk", flat=True))
    visibility.update((("edition", key), key in published_editions) for key in editions)
    pairs = {(s.edition_id, s.document_revision_id) for s in sources if s.document_revision_id}
    pairs = {pair for pair in pairs if ("source", pair) not in visibility}
    fulltext = set(public_editions(require_fulltext=True).filter(pk__in={e for e, _ in pairs}).values_list("pk", flat=True))
    revisions = set(m.CatalogPublicationRevision.objects.filter(document_revision_id__in={r for _, r in pairs},
        reader_asset_id=F("document_revision__asset_id"), status__in=["active", "superseded"], fulltext_ready=True)
        .values_list("document_revision_id", flat=True))
    visibility.update((("source", pair), pair[0] in fulltext and pair[1] in revisions) for pair in pairs)


def assertion_public(statement, *, visibility=None):
    # A caller may reuse checks within one bounded read, never across requests
    # or across a model call/publication change.
    visibility = visibility if visibility is not None else {}
    def visible(kind, identity, check):
        key = (kind, identity)
        if key not in visibility:
            visibility[key] = check()
        return visibility[key]
    sources = getattr(statement, "retrieval_sources", None)
    if sources is None:
        sources = list(statement.sources.select_related("document_revision__asset").all())
    if statement.status not in {"published", "superseded"}:
        return False
    if not sources and not statement.origin.get("human_confirmation_preserved"):
        return False
    for source in sources:
        if source.attribution_id and not visible("entity", source.attribution_id,
                lambda: public_entities().filter(pk=canonical_entity(source.attribution).pk).exists()):
            return False
        if source.document_revision_id and not visible("source", (source.edition_id, source.document_revision_id),
                lambda: public_editions(require_fulltext=True).filter(pk=source.edition_id).exists()
                and m.CatalogPublicationRevision.objects.filter(document_revision=source.document_revision,
                    reader_asset_id=source.document_revision.asset_id, status__in=["active", "superseded"], fulltext_ready=True).exists()):
            return False
        if not source.document_revision_id and source.work_id and not visible("work", source.work_id,
                lambda: public_editions().filter(work_id=source.work_id).exists()):
            return False
        if not source.document_revision_id and not source.work_id and not source.citation.strip() and not statement.origin.get("human_confirmation_preserved"):
            return False
    participants = getattr(statement, "retrieval_participants", None)
    if participants is None:
        participants = statement.participants.select_related("entity")
    for participant in participants:
        if participant.work_id and not visible("work", participant.work_id,
                lambda: public_editions().filter(work_id=participant.work_id).exists()):
            return False
        if participant.edition_id and not visible("edition", participant.edition_id,
                lambda: public_editions().filter(pk=participant.edition_id).exists()):
            return False
        if participant.entity_id:
            if not visible("entity", participant.entity_id,
                    lambda: public_entities().filter(pk=canonical_entity(participant.entity).pk).exists()):
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
        "predicate": statement.predicate, "predicate_label": PREDICATES.get(statement.predicate, statement.predicate),
        "direction": statement.direction, "expression": statement.expression, "conditions": statement.conditions,
        "source_quality": statement.source_quality, "supersedes_id": str(statement.supersedes_id) if statement.supersedes_id else None,
        "status": statement.status, "evidence": evidence,
        "participants": list(statement.participants.values("role", "entity_id", "entity__label", "work_id", "edition_id")),
        "sources": list(statement.sources.values("work_id", "work__title", "edition_id", "document_revision_id", "node_id", "attribution_id", "attribution__label", "expression", "citation"))}


def publication_entities(page, statements):
    from django.db.models import Q
    ids = m.AssertionParticipant.objects.filter(assertion_id__in=statements).exclude(entity=None).values("entity_id")
    attributions = m.AssertionSource.objects.filter(assertion_id__in=statements).exclude(attribution=None).values("attribution_id")
    entities = m.Entity.objects.filter(Q(pk__in=ids) | Q(pk__in=attributions) | Q(pk=page.entity_id))
    canonical = {canonical_entity(row).pk for row in entities}
    return list(m.Entity.objects.filter(pk__in=canonical).exclude(pk__in=public_entities().values("pk")))


def publish_reviewed_identity(entity, actor):
    """Publish only an explicitly reviewed new identity, never revive a legacy draft."""
    creation = m.ChangeItem.objects.filter(kind="entity", decision="accepted", application__type="entity", application__id=str(entity.pk))
    creation = next((v for v in creation if not v.payload.get("existing_id")), None)
    if creation is None or entity.status not in {"draft", "published"} or entity.merged_into_id:
        raise ValidationError(f"实体“{entity.label}”尚未公开，请先从其资料页审核发布。")
    from catalog.services.editorial_revision import create_editorial_revision, publish_editorial_revision, EditorialRevisionError
    target, kind, patch = None, None, None
    if entity.person_id:
        target, _ = m.ScholarProfile.objects.get_or_create(person_id=entity.person_id, defaults={"slug": f"scholar-{entity.person_id}"})
        kind, patch = "scholar_profile", {"editorial_status":"published"}
    elif entity.organization_id:
        target, kind, patch = entity.organization, "organization_profile", {"authority_status": "verified"}
    elif entity.timeline_event_id:
        target, kind = entity.timeline_event, "timeline_event"
        # The accepted identity item records the administrator's source review;
        # the original timeline publication validator still checks its evidence.
        patch = {"review_status": "approved", "editorial_details": {**target.editorial_details, "confirmed": True}}
    else:
        for field, target_kind, status_field in (("node","knowledge_node","status"), ("topic","topic","editorial_status"),
                                                ("discipline","discipline","editorial_status")):
            if getattr(entity, f"{field}_id"):
                target, kind, patch = getattr(entity, field), target_kind, {status_field:"published"}
                break
    if target:
        if m.EditorialRevision.objects.filter(target_type=kind, target_id=target.pk, status="draft").exists():
            raise ValidationError(f"“{entity.label}”另有资料编辑稿，请先核对该稿，避免连带发布未预览的修改。")
        try:
            edit = create_editorial_revision(target_type=kind, target_id=target.pk, patch=patch, actor=actor,
                idempotency_key=f"knowledge-identity-publish:{creation.pk}", change_note="随知识页发布已审核的新身份")
            publish_editorial_revision(edit.pk, actor=actor)
        except EditorialRevisionError as exc:
            raise ValidationError(f"{entity.label}：{exc}") from exc
    entity.status = "published"
    entity.save(update_fields=["status", "updated_at"])


def page_data(page, actor, *, draft=False):
    if draft:
        require_editor(actor)
        blocks, revision = page_content(page)
    else:
        if page.status != "published" or page.work_id and not public_editions().filter(work_id=page.work_id).exists():
            raise Http404
        if page.entity_id and not public_entities().filter(pk=canonical_entity(page.entity).pk).exists():
            raise Http404
        blocks = page.body_blocks
        revision = m.EditorialRevision.objects.filter(target_type="knowledge_page", target_id=page.pk, status="published").order_by("-revision").first()
    assertions, anchors, references, visible = {}, {}, {}, []
    from catalog.services.editorial_blocks import block_references
    for block in blocks:
        keep = True
        block_assertions, block_anchors, block_sources = {}, {}, {}
        for ref in block_references(block):
            from catalog.services.editorial_blocks import resolve_target
            try:
                _, card = resolve_target(ref, public=not draft)
                block_sources[f"{ref['type']}:{ref['id']}"] = card
            except Http404:
                if draft:
                    card = {**ref, "title": "来源当前不可用", "unavailable": True}
                    block_sources[f"{ref['type']}:{ref['id']}"] = card
                else:
                    keep = False
                    break
            if ref.get("type") == "assertion":
                statement = get_object_or_404(m.Assertion, pk=ref["id"])
                if not draft and not assertion_public(statement):
                    keep = False
                    break
                block_assertions[ref["id"]] = assertion_data(statement, actor, draft=draft)
            if ref.get("type") == "anchor":
                anchor = get_object_or_404(m.EvidenceAnchor, pk=ref["id"])
                value = {"anchor_id": str(anchor.pk)}
                if actor and actor.is_authenticated:
                    value["locator"] = locator(anchor, actor, editorial=draft)
                block_anchors[ref["id"]] = value
        if keep:
            visible.append(block)
            assertions.update(block_assertions)
            anchors.update(block_anchors)
            references.update(block_sources)
    from catalog.services.academic_relations import pending_withdrawals
    from catalog.services.knowledge_profiles import pending_profiles
    withdrawals = pending_withdrawals(page, blocks) if draft else []
    identity = entity_data(page.entity, public=not draft) if page.entity_id else None
    from catalog.services.knowledge_aliases import alias_preview
    aliases = alias_preview(page) if draft else []
    if draft and identity:
        identity["aliases"] = [v for v in identity["aliases"] if v["review_status"] == "confirmed"]
        known = {(v["text"], v["language"], v["script"]) for v in identity["aliases"]}
        identity["aliases"] += [v for v in aliases if (v["text"], v["language"], v["script"]) not in known]
    if draft and identity:
        for item in pending_profiles(page).order_by("created_at"):
            identity["profile"] = {**(identity.get("profile") or {}), **item.payload["profile"]}
    return {"id": str(page.pk), **page_metadata(page, draft=draft), "status": revision.status if draft and revision else page.status,
        "identity": identity,
        "revision_id": str(revision.pk) if revision else None, "blocks": visible, "assertions": list(assertions.values()), "anchors": list(anchors.values()), "references": list(references.values()),
        "publication_scope": {"page_id": str(page.pk), "assertion_ids": list(assertions),
            "aliases": aliases,
            "profiles": [{"id": v.application["id"], "label": v.payload["label"], "kind": v.payload["kind"]} for v in pending_profiles(page)] if draft else [],
            "withdrawals": [{"id": v.application["id"], "text": v.payload["text"], "reason": v.payload["reason"]} for v in withdrawals],
            "entities": [{"id":str(v.pk), "label":v.label, "kind":v.kind} for v in publication_entities(page, assertions)] if draft else []}}


def validate_page_publication(page, actor):
    """Called inside the canonical publisher, including legacy transport routes."""
    require_editor(actor)
    if not has_capability(actor, Capability.PUBLISH_AUTHORITY):
        raise PermissionDenied("当前账户不能公开发布知识。")
    if page.work_id and not public_editions().filter(work_id=page.work_id).exists():
        raise ValidationError("作品未公开，不能发布对应知识页。")
    from catalog.services.editorial_blocks import block_references, resolve_target
    for block in page.body_blocks:
        for ref in block_references(block):
            if ref["type"] == "assertion":
                statement = get_object_or_404(m.Assertion,pk=ref["id"])
                if not assertion_public(statement):
                    raise ValidationError("知识页引用包含未发布或来源已撤回的陈述。")
            elif ref["type"] == "anchor":
                require_revision_access(get_object_or_404(m.EvidenceAnchor,pk=ref["id"]).document_revision, actor)
            else:
                resolve_target(ref,public=True)


@transaction.atomic
def publish_page(page_id, revision_id, actor):
    require_editor(actor)
    if not has_capability(actor, Capability.PUBLISH_AUTHORITY):
        raise PermissionDenied("当前账户不能公开发布知识。")
    page = get_object_or_404(m.KnowledgePage.objects.select_for_update(), pk=page_id)
    from catalog.services.editorial_revision import create_editorial_revision, publish_editorial_revision
    latest = get_object_or_404(m.EditorialRevision.objects.select_for_update(), pk=revision_id,
        target_type="knowledge_page", target_id=page.pk)
    published_before = m.EditorialRevision.objects.filter(idempotency_key=f"knowledge-publish:{latest.pk}", status="published").exists()
    if published_before:
        return page_data(page, actor)
    if latest.status == "published":
        return page_data(page, actor)
    blocks, current = page_content(page)
    if not current or current.pk != latest.pk:
        raise ValidationError("知识页草稿已变化，请重新预览再发布。")
    from catalog.services.knowledge_profiles import publish_profiles
    publish_profiles(page, actor)
    page.refresh_from_db()
    statement_ids = [ref["id"] for block in blocks for ref in block.get("references", []) if ref.get("type") == "assertion"]
    from catalog.services.academic_relations import publish_withdrawals
    publish_withdrawals(page, blocks, actor)
    for entity in publication_entities(page, statement_ids):
        publish_reviewed_identity(entity, actor)
    from catalog.services.knowledge_aliases import publish_aliases
    publish_aliases(page, actor)
    for block in blocks:
        for ref in block.get("references", []):
            if ref.get("type") == "assertion":
                statement = get_object_or_404(m.Assertion.objects.select_for_update(), pk=ref["id"])
                # Only an applied human-reviewed item may enter publication.
                reviewed = m.ChangeItem.objects.filter(application__id=str(statement.pk), decision="accepted")
                legacy_confirmed = statement.status == "published" and statement.origin.get("human_confirmation_preserved")
                if not reviewed.exists() and not legacy_confirmed:
                    raise ValidationError("陈述尚未经过管理员审核保存。")
                citation_reviewed = (statement.source_quality == "human_citation" and reviewed.filter(changeset__origin="human").exists()
                    and statement.sources.exclude(citation="").exists())
                if not statement.evidence.exists() and not (citation_reviewed or legacy_confirmed):
                    raise ValidationError("陈述尚无可验证原文证据。")
                for link in statement.evidence.select_related("anchor__document_revision__asset__edition"):
                    require_revision_access(link.anchor.document_revision, actor, editorial=False)
                statement.status = "published"
                statement.save(update_fields=["status", "updated_at"])
                if statement.supersedes_id:
                    m.Assertion.objects.filter(pk=statement.supersedes_id, status="published").update(status="superseded", updated_at=statement.updated_at)
                    from catalog.services.knowledge_workspace import invalidate_source
                    invalidate_source("assertion", statement.supersedes_id)
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
