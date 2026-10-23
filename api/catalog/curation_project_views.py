from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Exists, OuterRef
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.editorial_issue_serializers import IssueItemSerializer
from catalog.models import CurationProject, RecommendationIssue, MediaRendition, EditorialRevision
from catalog.services import curation_projects as service, editorial_issues as ledger
from catalog.services.editorial_issues import EditConflict
from common.capabilities import Capability, has_capability
from common.permissions import CanAccessBackOffice
from ingestion.models import AuditEvent

ACTION = "curation.project.command"


class ProjectValuesSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=600)
    question = serializers.CharField(max_length=4000, allow_blank=True)
    introduction = serializers.CharField(max_length=3000, allow_blank=True)
    visibility = serializers.ChoiceField(choices=["team", "staff"])
    collaborator_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=30)
    cover_rendition_id = serializers.UUIDField(allow_null=True)
    planned_for = serializers.DateField(allow_null=True)


class ProjectCommandSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=["create", "save", "duplicate", "archive", "restore", "create_article", "attach_article", "reorder"])
    project_id = serializers.UUIDField(required=False)
    expected_version = serializers.CharField(max_length=64, required=False)
    values = ProjectValuesSerializer(required=False)
    title = serializers.CharField(max_length=600, required=False)
    article_id = serializers.UUIDField(required=False)
    article_version = serializers.CharField(max_length=64, required=False)
    article_ids = serializers.ListField(child=serializers.UUIDField(), max_length=200, required=False)

    def validate(self, data):
        fields = {"request_id", "action"}
        if data["action"] != "create": fields |= {"project_id", "expected_version"}
        fields |= {"values"} if data["action"] in {"create", "save"} else {"title"} if data["action"] == "create_article" else {"article_id", "article_version"} if data["action"] == "attach_article" else {"article_ids"} if data["action"] == "reorder" else set()
        if set(self.initial_data) != fields: raise serializers.ValidationError("请使用当前项目的完整操作参数。")
        return data


class ProjectPersonSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()


class ProjectCardSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    question = serializers.CharField(allow_blank=True)
    introduction = serializers.CharField(allow_blank=True)
    owner = ProjectPersonSerializer()
    collaborators = ProjectPersonSerializer(many=True)
    visibility = serializers.ChoiceField(choices=["team", "staff"])
    cover_rendition_id = serializers.UUIDField(allow_null=True)
    cover_url = serializers.CharField(allow_blank=True)
    planned_for = serializers.DateField(allow_null=True)
    archived_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField()
    article_count = serializers.IntegerField()
    published_count = serializers.IntegerField()
    can_manage = serializers.BooleanField()
    can_edit = serializers.BooleanField()


class ProjectDirectorySerializer(serializers.Serializer):
    results = ProjectCardSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    summary = serializers.DictField(child=serializers.IntegerField())
    unassigned_count = serializers.IntegerField()
    can_create = serializers.BooleanField()


class ProjectArticleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    introduction = serializers.CharField(allow_blank=True)
    public_byline = serializers.CharField(allow_blank=True)
    cover_url = serializers.CharField(allow_blank=True)
    saved_at = serializers.DateTimeField(allow_null=True)
    saved_by = serializers.CharField(allow_blank=True)
    has_unpublished_changes = serializers.BooleanField()
    edit_version = serializers.CharField()
    published = serializers.BooleanField()
    edit_url = serializers.CharField()
    position = serializers.IntegerField()


class ProjectMaterialSerializer(IssueItemSerializer):
    article_id = serializers.UUIDField()
    article_title = serializers.CharField()


class ProjectProblemSerializer(serializers.Serializer):
    article_id = serializers.UUIDField()
    article_title = serializers.CharField()
    block_id = serializers.UUIDField(allow_null=True, required=False)
    position = serializers.IntegerField(required=False)
    code = serializers.CharField()
    detail = serializers.CharField()


class ProjectActivitySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    at = serializers.DateTimeField()
    action = serializers.CharField()
    actor = serializers.CharField()


class ProjectDetailSerializer(ProjectCardSerializer):
    version = serializers.CharField()
    articles = ProjectArticleSerializer(many=True)
    articles_page = serializers.IntegerField()
    articles_pages = serializers.IntegerField()
    article_ids = serializers.ListField(child=serializers.UUIDField())
    materials = ProjectMaterialSerializer(many=True)
    problems = ProjectProblemSerializer(many=True)
    activity = ProjectActivitySerializer(many=True)
    material_scope = serializers.CharField()


class ProjectReceiptSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    next_url = serializers.CharField(allow_blank=True)
    project_id = serializers.UUIDField(allow_null=True)
    message = serializers.CharField(allow_blank=True)


def receipt(row):
    return {"owner_id": str(row.actor_id), "request_id": row.request_id, "state": "cancelled" if row.after.get("cancelled") else "applied",
            "next_url": row.after.get("next_url", ""), "project_id": row.object_id or None, "message": row.after.get("message", "")}


def actor_for(request):
    if request.headers.get("X-Editor-Owner") != str(request.user.pk): raise PermissionDenied("请从当前账户的项目工作区提交操作。")
    actor = get_object_or_404(get_user_model().objects.select_for_update(), pk=request.user.pk, is_active=True)
    if actor.token_version != request.user.token_version or not has_capability(actor, Capability.EDIT_METADATA): raise PermissionDenied("当前会话不能编辑策划项目。")
    return actor


def apply_values(project, values):
    members = list(get_user_model().objects.filter(pk__in=values["collaborator_ids"], is_active=True))
    if len(members) != len(set(values["collaborator_ids"])) or any(not has_capability(user, Capability.EDIT_METADATA) for user in members):
        raise ValidationError("协作者须为有效的馆内编辑账户。")
    if values["cover_rendition_id"]: get_object_or_404(MediaRendition, pk=values["cover_rendition_id"])
    for key in ("title", "question", "introduction", "visibility", "cover_rendition_id", "planned_for"): setattr(project, key, values[key])
    project.save(); project.collaborators.set(members)


class CurationProjectView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(operation_id="curation_project_directory", responses=ProjectDirectorySerializer, parameters=[OpenApiParameter(name, type=str) for name in ("q", "scope", "page")])
    def get(self, request):
        all_rows = service.visible_projects(request.user).select_related("owner").prefetch_related("collaborators")
        summary = {"all": all_rows.filter(archived_at__isnull=True).count(), "mine": all_rows.filter(owner=request.user, archived_at__isnull=True).count(),
                   "archived": all_rows.filter(archived_at__isnull=False).count()}
        published = ledger.published_issues().exclude(project_id=None).values("project_id")
        drafts = EditorialRevision.objects.filter(target_type="recommendation_issue", target_id=OuterRef("pk"), status="draft")
        draft_projects = RecommendationIssue.objects.filter(Exists(drafts)).exclude(project_id=None).values("project_id")
        summary.update(published=all_rows.filter(archived_at__isnull=True, pk__in=published).count(), draft=all_rows.filter(archived_at__isnull=True).filter(Q(pk__in=draft_projects) | ~Exists(RecommendationIssue.objects.filter(project_id=OuterRef("pk")))).count())
        rows = all_rows.filter(archived_at__isnull=request.query_params.get("scope") != "archived")
        if request.query_params.get("scope") == "mine": rows = rows.filter(owner=request.user)
        if request.query_params.get("scope") == "published": rows = rows.filter(pk__in=published)
        if request.query_params.get("scope") == "draft": rows = rows.filter(Q(pk__in=draft_projects) | ~Exists(RecommendationIssue.objects.filter(project_id=OuterRef("pk"))))
        if request.query_params.get("q"):
            q = str(request.query_params["q"])[:200]
            rows = rows.filter(Q(title__icontains=q) | Q(question__icontains=q) | Q(pk__in=RecommendationIssue.objects.filter(title__icontains=q).values("project_id")))
        page = Paginator(rows, 12).get_page(request.query_params.get("page", 1))
        return Response({"results": [service.project_card(project, request.user) for project in page.object_list], "count": page.paginator.count,
            "page": page.number, "pages": page.paginator.num_pages, "summary": summary,
            "unassigned_count": RecommendationIssue.objects.filter(project__isnull=True).count(), "can_create": has_capability(request.user, Capability.EDIT_METADATA)})

    @extend_schema(request=ProjectCommandSerializer, responses=ProjectReceiptSerializer)
    @transaction.atomic
    def post(self, request):
        actor = actor_for(request)
        serializer = ProjectCommandSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        signature = sha256(json.dumps(data, default=str, sort_keys=True).encode()).hexdigest()
        prior = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(data["request_id"])).first()
        if prior:
            if not prior.after.get("cancelled") and prior.after.get("signature") != signature: raise EditConflict("原请求编号不能用于不同项目操作。")
            return Response(receipt(prior))
        action, next_url = data["action"], ""
        if action == "create":
            project = CurationProject(owner=actor); apply_values(project, data["values"])
        else:
            project = get_object_or_404(CurationProject.objects.select_for_update(), pk=data["project_id"])
            get_object_or_404(service.visible_projects(actor), pk=project.pk)
            if service.project_version(project) != data["expected_version"]: raise EditConflict("项目或文章已经变化，请读取最新内容后再操作。")
            if action in {"save", "archive", "restore", "reorder", "attach_article"} and project.owner_id != actor.pk:
                raise PermissionDenied("项目设置、归档与文章组织由负责人修改。")
            if project.archived_at and action not in {"restore", "duplicate"}: raise EditConflict("项目已归档，请先恢复。")
            if action == "save": apply_values(project, data["values"])
            elif action in {"archive", "restore"}:
                project.archived_at = timezone.now() if action == "archive" else None; project.save(update_fields=["archived_at", "updated_at"])
            elif action == "duplicate":
                articles = list(project.articles.order_by("project_position", "pk")[:51])
                if len(articles) > 50: raise ValidationError("一次复制最多50篇文章，请先拆分项目。")
                duplicate = CurationProject.objects.create(owner=actor, title=f"{project.title[:590]}（副本）", question=project.question, introduction=project.introduction,
                    cover_rendition=project.cover_rendition, visibility="team")
                for index, article in enumerate(articles):
                    payload = deepcopy(ledger.issue_draft_payload(article)); payload.pop("slug", None); payload["display_from"] = None
                    mapping = {block["id"]: str(uuid4()) for block in payload.get("body_blocks", [])}
                    for block in payload.get("body_blocks", []): block["id"] = mapping[block["id"]]
                    for item in payload.get("items", []): item["id"] = str(uuid4()); item["section_id"] = mapping.get(item.get("section_id"), "")
                    copied = ledger.create_issue(payload, actor); copied.project = duplicate; copied.project_position = index; copied.save(update_fields=["project", "project_position", "updated_at"])
                project = duplicate
            elif action in {"create_article", "attach_article"}:
                if project.articles.count() >= 200: raise ValidationError("一个项目最多200篇文章。")
                if action == "create_article":
                    article = ledger.create_issue({"title": data["title"], "selection_workspace": {"question": project.question}}, actor)
                else:
                    article = get_object_or_404(RecommendationIssue.objects.select_for_update(), pk=data["article_id"], project__isnull=True, created_by=actor)
                    ledger._check_version("recommendation_issue", article.pk, data["article_version"])
                article.project = project; article.project_position = project.articles.count(); article.save(update_fields=["project", "project_position", "updated_at"])
                next_url = f"/admin/recommendations/issues/{article.pk}"
            elif action == "reorder":
                articles = list(project.articles.select_for_update().order_by("pk"))
                ids = data["article_ids"]
                if len(set(ids)) != len(ids) or set(ids) != {article.pk for article in articles}: raise ValidationError("排序须包含此项目全部文章各一次。")
                positions = {identifier: position for position, identifier in enumerate(ids)}
                for article in articles: article.project_position = positions[article.pk]
                RecommendationIssue.objects.bulk_update(articles, ["project_position"])
                project.save(update_fields=["updated_at"])
        next_url = next_url or f"/admin/recommendations?project={project.pk}"
        messages = {"create": "项目已建立。", "save": "项目设置已保存。", "duplicate": "已复制为新的团队私密项目，文章均为草稿。", "archive": "项目已归档，文章、公开版本与原文保留。", "restore": "项目已恢复。", "create_article": "文章草稿已建立。", "attach_article": "原文章身份与版本保留，已加入项目。", "reorder": "文章顺序已保存。"}
        row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="curation_project", object_id=str(project.pk), request_id=str(data["request_id"]),
            after={"signature": signature, "operation": action, "next_url": next_url, "message": messages[action]})
        return Response(receipt(row))


class CurationProjectDetailView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=ProjectDetailSerializer, parameters=[OpenApiParameter("articles_page", type=int)])
    def get(self, request, project_id):
        project = get_object_or_404(service.visible_projects(request.user).select_related("owner").prefetch_related("collaborators"), pk=project_id)
        return Response(service.project_detail(project, request.user, request.query_params.get("articles_page", 1)))


class ProjectPeopleSerializer(serializers.Serializer):
    results = ProjectPersonSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()


class CurationProjectPeopleView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=ProjectPeopleSerializer, parameters=[OpenApiParameter("q", type=str), OpenApiParameter("page", type=int)])
    def get(self, request):
        if not has_capability(request.user, Capability.EDIT_METADATA): raise PermissionDenied("当前账户不能选择项目协作者。")
        from accounts.ownership import configured_library_owner_email
        users = get_user_model().objects.filter(is_active=True).filter(Q(role__in=["editor", "reviewer", "admin"]) | Q(email__iexact=configured_library_owner_email())).order_by("display_name", "pk")
        if request.query_params.get("q"): users = users.filter(display_name__icontains=str(request.query_params["q"])[:100])
        page = Paginator(users, 30).get_page(request.query_params.get("page", 1))
        return Response({"results": [service.person_label(user) for user in page.object_list], "count": page.paginator.count, "page": page.number, "pages": page.paginator.num_pages})


class ProjectStopSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class CurationProjectReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=ProjectReceiptSerializer)
    def get(self, request, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk): raise PermissionDenied("请使用原账户查回操作。")
        return Response(receipt(get_object_or_404(AuditEvent, actor=request.user, action=ACTION, request_id=str(request_id))))

    @extend_schema(request=ProjectStopSerializer, responses=ProjectReceiptSerializer)
    @transaction.atomic
    def post(self, request, request_id):
        actor = actor_for(request)
        serializer = ProjectStopSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        if set(request.data) != {"action"}: raise ValidationError("只可停止原请求。")
        row = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(request_id)).first()
        if row is None: row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="curation_project", object_id="", request_id=str(request_id), after={"cancelled": True})
        return Response(receipt(row))
