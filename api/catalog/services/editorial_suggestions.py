"""Material suggestions over canonical public lookup; no new retrieval index.

Names/keywords provide candidates, not inferred academic relationships. The
editor chooses a concrete, currently public source before inserting a block.
"""
from hashlib import sha256
import json

from django.core import signing
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import RecommendationIssue
from catalog.services import editorial_issues as ledger
from catalog.services.editorial_blocks import block_references, resolve_target
from catalog.services.publication_eligibility import public_editions
from catalog.services.scoped_search import SearchContext, SearchService, SearchVisibility
from catalog.services.shared_curation import identifier
from ingestion.models import AuditEvent

KINDS = {"work": SearchContext.WORKS, "person": SearchContext.SCHOLARS, "concept": SearchContext.THEORIES}
SALT = "stl4-issue-material-suggestion-v1"
ACTION = "recommendation_issue.material_dismiss"


def suggestions(issue, actor, *, query="", kind="all", batch=1):
    if kind not in {"all", *KINDS}:
        raise ValidationError("请选择书目、人物或概念建议。")
    if type(batch) is not int or not 1 <= batch <= 100:
        raise ValidationError("材料批次须在1至100之间。")
    version = ledger.edit_version("recommendation_issue", issue.pk)
    payload = ledger.issue_draft_payload(issue)
    query = ledger._text(query, 200)
    keywords = payload.get("article_metadata", {}).get("keywords", [])
    if not query:
        query = next((value for value in keywords if value.strip()), payload.get("title", ""))[:200]
    known = {json.dumps(reference, sort_keys=True) for block in payload.get("body_blocks", []) for reference in block_references(block)}
    output, has_more, unavailable = [], False, 0
    per_kind = 1 if kind == "all" else 3
    if query:
        service = SearchService()
        for category, context in KINDS.items():
            if kind not in ("all", category):
                continue
            rows = service.queryset(context, query, visibility=SearchVisibility.PUBLIC, filters={"node_type": "concept"} if category == "concept" else {})
            selected = list(rows[(batch - 1) * per_kind:batch * per_kind + 1])
            has_more = has_more or len(selected) > per_kind
            for row in selected[:per_kind]:
                if category == "work":
                    edition = public_editions().filter(work_id=row.pk).order_by("-is_primary", "pk").first()
                    if edition is None:
                        unavailable += 1
                        continue
                    target = {"type": "work", "id": str(row.pk), "edition_id": str(edition.pk)}
                else:
                    target = {"type": "person" if category == "person" else "node", "id": str(row.person_id if category == "person" else row.pk)}
                try:
                    target, source = resolve_target(target, public=True)
                except (Http404, ValidationError):
                    unavailable += 1
                    continue
                if json.dumps(target, sort_keys=True) in known:
                    continue
                if category == "work":
                    snapshot = edition.active_catalog_revision.snapshot or {}
                    work = snapshot.get("work", {})
                    cover = work.get("cover_media") or {}
                    if work.get("cover") or cover:
                        source["image_url"] = f"/api/catalog/works/{edition.work_id}/cover/?edition_id={edition.pk}"
                        if cover.get("primary_rendition_id"):
                            source["image_url"] += f"&rendition={cover['primary_rendition_id']}"
                elif category == "person":
                    from catalog.services.public_scholars import _formal_profile
                    from catalog.serializers import PersonCompactSerializer
                    profile = _formal_profile(row, row.public_snapshot or {})
                    source["image_url"] = PersonCompactSerializer().get_portrait(profile.person)
                key = sha256(json.dumps([version, target], sort_keys=True).encode()).hexdigest()
                token = signing.dumps({"actor": str(actor.pk), "issue": str(issue.pk), "version": version, "key": key, "target": target}, salt=SALT)
                output.append({"key": key, "token": token, "kind": category, "target": target, "source": source,
                               "reason": f"在公开资料名称、核实别名或简介中匹配“{query}”，请核对与本文的关系。"})
    dismissed = set(AuditEvent.objects.filter(actor=actor, action=ACTION, object_type="recommendation_issue", object_id=str(issue.pk),
        after__edit_version=version, after__candidate_key__in=[row["key"] for row in output]).values_list("after__candidate_key", flat=True))
    ledger._check_version("recommendation_issue", issue.pk, version)
    return {"results": [row for row in output if row["key"] not in dismissed], "query": query, "kind": kind, "batch": batch,
            "has_more": has_more and batch < 100, "edit_version": version, "checked_at": timezone.now(),
            "notice": "建议依据公开资料匹配，尚未建立学术关系或写入正文。" + (f"有{unavailable}项来源状态已改变，未展示旧资料。" if unavailable else "")}


@transaction.atomic
def dismiss(issue_id, actor, data):
    issue = get_object_or_404(RecommendationIssue.objects.select_for_update(), pk=issue_id)
    request_id = str(identifier(data.get("request_id")))
    token = data.get("token")
    if not isinstance(token, str) or len(token) > 4000:
        raise ValidationError("请重新读取这条材料建议。")
    fingerprint = sha256(token.encode()).hexdigest()
    receipt = AuditEvent.objects.filter(actor=actor, action=ACTION, object_type="recommendation_issue", object_id=str(issue.pk), request_id=request_id).first()
    if receipt:
        if receipt.after.get("fingerprint") != fingerprint:
            raise ledger.EditConflict("此请求编号已用于另一条建议。")
        return {"dismissed": True, "key": receipt.after["candidate_key"]}
    try:
        value = signing.loads(token, salt=SALT, max_age=3600)
    except signing.BadSignature:
        raise ValidationError("建议已过期，请重新读取后选择。")
    if value.get("actor") != str(actor.pk) or value.get("issue") != str(issue.pk):
        raise ValidationError("这条建议不属于当前账户与专题。")
    ledger._check_version("recommendation_issue", issue.pk, value["version"])
    AuditEvent.objects.create(actor=actor, action=ACTION, object_type="recommendation_issue", object_id=str(issue.pk), request_id=request_id,
        after={"candidate_key": value["key"], "edit_version": value["version"], "fingerprint": fingerprint})
    return {"dismissed": True, "key": value["key"]}
