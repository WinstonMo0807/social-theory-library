"""An explicit proposal can seed public bibliography in the original article draft.

Authored questions, notes, excerpts and messages remain in the revocable grant.
This service never copies them into editorial revisions or audit events.
"""
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.models import Edition
from catalog.services.contribution_projection import edition_author_projection
from catalog.services.curation_projects import visible_issues
from catalog.services.editorial_issues import EditConflict, create_issue
from catalog.services.publication_eligibility import public_edition_q
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent
from reading import reader_shares, research, share_scope
from reading.models import ReadingList, ResearchProject
from reading.sharing_models import ReaderShare

ACTION = "recommendation_issue.reader_proposal"


def grant(actor, proposal_id, *, lock=False):
    if not all(has_capability(actor, capability) for capability in (
        Capability.ACCESS_BACK_OFFICE, Capability.EDIT_METADATA, Capability.REVIEW_CANDIDATE,
    )):
        raise PermissionDenied("接手提案需要策划审核和文章编辑权限。")
    row = get_object_or_404(ReaderShare, pk=proposal_id, destination="proposal")
    if lock:
        # Match the original source -> grant order without locking a different
        # author's User row after the editor's command lock.
        model = ReadingList if row.source_kind == "booklist" else ResearchProject
        get_object_or_404(model.objects.select_for_update(), pk=row.source_id, user_id=row.user_id)
        row = get_object_or_404(ReaderShare.objects.select_for_update(), pk=row.pk, destination="proposal")
    return row


def association(row):
    return AuditEvent.objects.filter(action=ACTION, object_type="ReaderShare", object_id=str(row.pk)).order_by("created_at", "id").first()


def projection(row, actor):
    content = reader_shares.read(row, user=actor)
    materials, seen = [], set()
    for selected in content["sections"]["materials"]:
        reference = selected.get("reference") or {}
        work_id = reference.get("work_id") or selected.get("work", {}).get("id")
        edition_id = reference.get("edition_id")
        editions = Edition.objects.filter(public_edition_q(), work_id=work_id)
        edition = editions.filter(**({"pk": edition_id} if edition_id else {"is_primary": True})).select_related("active_catalog_revision").first()
        if edition is None or (row.source_kind == "research" and not edition_id):
            raise EditConflict("提案中的公开版本已变化，请返回原提案重新核对。")
        if edition.pk in seen:
            continue
        seen.add(edition.pk)
        snapshot = edition.active_catalog_revision.snapshot or {}
        work, version = snapshot.get("work") or {}, snapshot.get("edition") or {}
        materials.append({"work_id": str(edition.work_id), "edition_id": str(edition.pk),
            "catalog_revision_id": str(edition.active_catalog_revision_id), "title": work.get("title") or "题名待补",
            "authors": edition_author_projection(snapshot)["authors"], "version_note": str(version.get("version_label") or ""),
            "href": f"/works/{version.get('public_slug') or edition.pk}"})
    preview_hash = share_scope.digest({"owner": str(actor.pk), "proposal": str(row.pk), "revision": row.revision,
        "content_hash": research.unpack(row)["content_hash"], "expires_at": row.expires_at, "materials": materials})
    return {"owner_id": str(actor.pk), "proposal_id": str(row.pk), "expected_revision": row.revision,
        "preview_hash": preview_hash, "review_state": row.review_state, "expires_at": row.expires_at,
        "materials": materials, "selected_material_count": len(content["sections"]["materials"]),
        "excluded": ["研究问题与私人笔记", "材料摘录与引用定位", "原研究或书单标题", "提交附言", "PDF原件与附件", "账户信息与学术记忆授权"]}


def preview(actor, proposal_id):
    row = grant(actor, proposal_id)
    result = projection(row, actor)
    linked = association(row)
    issue_id = linked.after.get("issue_id") if linked else None
    available = bool(issue_id and visible_issues(actor).filter(pk=issue_id).exists())
    # Check the original grant once more before returning a private preview.
    if projection(row, actor)["preview_hash"] != result["preview_hash"]:
        raise EditConflict("提案或公开书目刚刚变化，请重新读取。")
    return {**result, "already_created": bool(linked), "issue_id": issue_id if available else None,
        "next_url": f"/admin/recommendations/issues/{issue_id}" if available else ""}


def create_from_proposal(actor, data):
    """Called within IssueCreateView's transaction and original editor lock."""
    source = data["proposal"]
    row = grant(actor, source["id"], lock=True)
    current = projection(row, actor)
    linked = association(row)
    if linked:
        # A different editor/request must converge on the same original draft.
        # The caller's receipt masks its ID if project visibility has changed.
        return linked.after["issue_id"]
    if current["review_state"] == "declined":
        raise ValidationError("此提案目前为未采用，请先在原提案中恢复策划讨论状态。")
    if current["expected_revision"] != source["expected_revision"] or current["preview_hash"] != source["preview_hash"]:
        raise EditConflict("提案或公开书目已更新，请重新核对入编范围。")
    edition_ids = [value["edition_id"] for value in current["materials"]]
    list(Edition.objects.select_for_update().filter(pk__in=edition_ids).order_by("pk").values_list("pk", flat=True))
    if projection(row, actor)["preview_hash"] != current["preview_hash"]:
        raise EditConflict("公开版本刚刚更新，请重新核对入编范围。")
    issue = create_issue({"title": data["title"], "article_metadata": {"kind": data["kind"]},
        "items": [{"kind": "catalog", "work_id": value["work_id"], "edition_id": value["edition_id"]}
            for value in current["materials"]]}, actor)
    if projection(row, actor)["preview_hash"] != current["preview_hash"]:
        raise EditConflict("提案授权或来源刚刚变化，本次未建立草稿，请重新核对。")
    reader_shares.review(actor, row.pk, row.revision, "considering")
    AuditEvent.objects.create(actor=actor, action=ACTION, object_type="ReaderShare", object_id=str(row.pk),
        request_id=str(data["request_id"]), after={"issue_id": str(issue.pk), "material_count": len(current["materials"])})
    return str(issue.pk)
