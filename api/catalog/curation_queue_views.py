"""A paginated inventory of editable curation drafts, one row per object.

All filtering, deduplication, counting and ordering happen in SQL. The response
projects only the current page; it never loads private source text or notes.
"""
from django.core.paginator import Paginator
from django.db.models import BooleanField, Case, CharField, F, OuterRef, Q, Subquery, TextField, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, Concat, Greatest
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from common.capabilities import Capability, capability_snapshot, has_capability
from common.permissions import CanAccessBackOffice
from catalog import models
from catalog.editorial_read import AdminPrivateResponseMixin


class CurationDraftSerializer(serializers.Serializer):
    id = serializers.CharField()
    object_id = serializers.UUIDField()
    object_type = serializers.CharField()
    title = serializers.CharField()
    label = serializers.CharField()
    updated_at = serializers.DateTimeField()
    edit_url = serializers.CharField()
    state = serializers.ChoiceField(choices=["draft", "changes_pending"])
    can_edit = serializers.BooleanField()


class CurationDraftPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = CurationDraftSerializer(many=True)


FIELDS = ("q_id", "q_object_id", "q_type", "q_title", "q_label", "q_updated", "q_url", "q_state", "q_can_edit")


def _objects(queryset, kind, label, title, title_key, state_field, url_prefix, *, url_suffix="", url_expression=None, can_edit=True, query=""):
    latest = models.EditorialRevision.objects.filter(target_type=kind, target_id=OuterRef("pk")).order_by("-revision")
    queryset = queryset.order_by().annotate(q_revision_state=Subquery(latest.values("status")[:1]))
    pending = Q(q_revision_state="draft")
    if state_field:
        pending |= Q(**{f"{state_field}__in": ["draft", "pending", "suggested"]})
    queryset = queryset.filter(pending)
    draft_value = "materialized_preview"
    for key in (title_key or "").split("."):
        draft_value = KeyTextTransform(key, draft_value)
    draft_title = Subquery(latest.annotate(value=draft_value).values("value")[:1], output_field=TextField()) if title_key else title
    draft_date = Subquery(latest.values("updated_at")[:1])
    canonical_title = Cast(title, TextField())
    queryset = queryset.annotate(
        q_id=Concat(Value(f"{kind}:"), Cast("pk", CharField())), q_object_id=Cast("pk", CharField()),
        q_type=Value(kind), q_label=Value(label),
        q_title=Case(When(q_revision_state="draft", then=Coalesce(draft_title, canonical_title)), default=canonical_title, output_field=TextField()),
        q_updated=Greatest(F("updated_at"), Coalesce(draft_date, F("updated_at"))),
        q_url=url_expression if url_expression is not None else Concat(Value(url_prefix), Cast("pk", CharField()), Value(url_suffix)),
        q_state=Case(When(**{f"{state_field}__in": ["published", "approved"]}, then=Value("changes_pending")), default=Value("draft"), output_field=CharField()) if state_field else Value("changes_pending" if kind == "site_content" else "draft"),
        q_can_edit=Value(can_edit, output_field=BooleanField()),
    )
    if query:
        queryset = queryset.filter(q_title__icontains=query)
    return queryset.values(*FIELDS)


def draft_inventory(user, *, query=""):
    # These read permissions mirror the existing object editors. An object
    # which the user cannot open is not exposed merely through this inventory.
    staff = has_capability(user, Capability.ACCESS_BACK_OFFICE)
    knowledge = has_capability(user, Capability.EDIT_DRAFT_AUTHORITY)
    rows = [
        _objects(models.ScholarProfile.objects.all(), "scholar_profile", "学者", F("person__preferred_name"), "person.preferred_name", "editorial_status", "/admin/scholars/", can_edit=staff, query=query),
        _objects(models.Topic.objects.exclude(curation__has_key="topic_merge"), "topic", "主题", F("name"), "name", "editorial_status", "/admin/topics/", can_edit=staff, query=query),
        _objects(models.Discipline.objects.all(), "discipline", "学科", F("name"), "name", "editorial_status", "/admin/theories/disciplines?discipline=", can_edit=staff, query=query),
        _objects(models.Subdiscipline.objects.all(), "subdiscipline", "子学科", F("name"), "name", "editorial_status", "/admin/theories/subdisciplines?subdiscipline=", can_edit=staff, query=query),
        _objects(models.RecommendationIssue.objects.all(), "recommendation_issue", "推荐期", F("title"), "title", None, "/admin/recommendations/issues/", can_edit=has_capability(user, Capability.EDIT_METADATA), query=query),
    ]
    if knowledge:
        rows += [
            _objects(models.KnowledgeNode.objects.all(), "knowledge_node", "理论与概念", F("canonical_name_zh"), "canonical_name_zh", "status", "/admin/theories/", query=query),
            _objects(models.KnowledgeRelation.objects.all(), "knowledge_relation", "理论关系", Concat("source_node__canonical_name_zh", Value(" → "), "target_node__canonical_name_zh"), None, "status", "/admin/theories/relations?relation=", query=query),
            _objects(models.ReadingPath.objects.all(), "reading_path", "阅读路径", F("title"), "title", "status", "/admin/theories/reading-paths?path=", query=query),
            _objects(models.TheoryTimelineEvent.objects.all(), "timeline_event", "时间线事件", F("title"), "title", "review_status", "/admin/theories/timeline?event=", query=query),
            _objects(models.ScholarRelation.objects.all(), "scholar_relation", "学者关系", Concat("source_scholar__person__preferred_name", Value(" → "), "target_scholar__person__preferred_name"), None, "status", "", query=query, url_expression=Concat(Value("/admin/scholars/"), Cast("source_scholar_id", CharField()), Value("/relations?relation="), Cast("pk", CharField()))),
            _objects(models.EvidenceCuration.objects.all(), "evidence_curation", "原文策展", Value("原文策展"), "title", None, "", query=query, url_expression=Concat(
                Case(When(object_type="topic", then=Value("/admin/topics/")), When(object_type="scholar", then=Value("/admin/scholars/")), default=Value("/admin/theories/"), output_field=CharField()),
                Cast("object_id", CharField()), Value("?section=passages"))),
        ]
    if capability_snapshot(user).access_level in {"admin", "superadmin"}:
        rows.append(_objects(models.SiteSetting.objects.filter(key="site_config"), "site_content", "网站与关于书库", Value("网站与关于书库"), None, None, "/admin/about?config=", query=query))
    return rows[0].union(*rows[1:], all=True)


class CurationDraftQueueView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=CurationDraftPageSerializer)
    def get(self, request):
        ordering = request.query_params.get("ordering", "-updated_at")
        if ordering not in {"updated_at", "-updated_at"}:
            return Response({"detail": "未知策展草稿排序方式。"}, status=400)
        inventory = draft_inventory(request.user, query=request.query_params.get("q", "").strip())
        paginator = Paginator(inventory.order_by("-q_updated" if ordering.startswith("-") else "q_updated", "q_id"), 30)
        page = paginator.get_page(request.query_params.get("page", 1))
        def page_url(number):
            params = request.query_params.copy()
            params["page"] = number
            return f"{request.path}?{params.urlencode()}"
        field_names = ("id", "object_id", "object_type", "title", "label", "updated_at", "edit_url", "state", "can_edit")
        results = [{field: row[key] for field, key in zip(field_names, FIELDS)} for row in page.object_list]
        return Response({"count": paginator.count, "page": page.number, "page_size": paginator.per_page,
                         "total_pages": paginator.num_pages, "next": page_url(page.next_page_number()) if page.has_next() else None,
                         "previous": page_url(page.previous_page_number()) if page.has_previous() else None, "results": results})
