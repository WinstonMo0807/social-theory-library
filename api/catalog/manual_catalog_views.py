"""Material-first cataloguing using canonical editions and the existing draft service."""
import json
from hashlib import sha256

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Prefetch
from django.shortcuts import get_object_or_404
from django.utils.crypto import salted_hmac
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import CatalogingSession, Contribution, DocumentType, Edition, Person, Work
from catalog.services.cataloging_sessions import open_cataloging_session, OPEN_STATUSES, CatalogingSessionConflict
from catalog.services.editorial_issues import EditConflict
from catalog.services.work_editor import save_workflow_section, WorkflowEditError
from catalog.workflow_serializers import WorkSectionSerializer, BibliographySectionSerializer
from common.capabilities import Capability, has_capability
from common.permissions import CanEditMetadata
from ingestion.models import AuditEvent
from catalog.manual_catalog_candidates import PrefillSelection, unpack_selections, record_prefills

ACTION = "manual_catalog.command"


def actor_for(request, lock=False):
    if request.headers.get("X-Editor-Owner") != str(request.user.pk):
        raise PermissionDenied("登录账户已变化，请重新打开书目草稿。")
    if not lock: return request.user
    actor = get_object_or_404(get_user_model().objects.select_for_update(), pk=request.user.pk, is_active=True)
    if actor.token_version != request.user.token_version or not has_capability(actor, Capability.EDIT_METADATA):
        raise PermissionDenied("当前会话不能保存书目。")
    return actor


def version(edition):
    from catalog.services.workspace_edits import workspace_edit_version
    parts = [str(edition.pk), str(edition.updated_at), str(edition.work.updated_at)]
    parts.append(workspace_edit_version(edition))
    parts.extend(f"{row.pk}:{row.updated_at}:{row.person_id}:{row.role}" for row in edition.contributions.order_by("pk"))
    return sha256("|".join(parts).encode()).hexdigest()


def work_rows(query):
    return Work.objects.filter(Q(title__icontains=query) | Q(editions__contributions__person__preferred_name__icontains=query) |
        Q(editions__isbn__icontains=query) | Q(editions__doi__icontains=query)).distinct().prefetch_related(
            Prefetch("editions", queryset=Edition.objects.order_by("-publication_year", "pk").prefetch_related("contributions__person"))).order_by("title", "pk")


def person_rows(query):
    return Person.objects.filter(Q(preferred_name__icontains=query) | Q(original_name__icontains=query)).exclude(
        authority_status__in=["merged", "archived", "rejected"]).order_by("preferred_name", "pk")


class ManualPersonSerializer(serializers.Serializer):
    person_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    name = serializers.CharField(max_length=240)
    role = serializers.ChoiceField(choices=Contribution.Role.choices)
    create_new = serializers.BooleanField(default=False)


class ManualFormSerializer(serializers.Serializer):
    work = WorkSectionSerializer()
    bibliography = BibliographySectionSerializer()
    contributors = ManualPersonSerializer(many=True, max_length=50)

    def to_internal_value(self, data):
        permitted_work = {"title", "document_type", "language", "subtitle", "abstract"}
        permitted_bibliography = {"version_label", "publication_year", "publisher", "publication_place", "isbn", "doi", "series", "series_number", "container_title", "extent", "journal_title", "volume", "issue", "page_range", "degree_institution", "degree_type", "report_institution"}
        if not isinstance(data, dict) or not isinstance(data.get("work"), dict) or not isinstance(data.get("bibliography"), dict):
            raise ValidationError("请提供完整的作品和版本字段。")
        if set(data) - set(self.fields) or set(data.get("work", {})) - permitted_work or set(data.get("bibliography", {})) - permitted_bibliography:
            raise ValidationError("请通过完整馆藏编辑页修改其他书目字段。")
        return super().to_internal_value(data)

    def validate(self, attrs):
        if not str(attrs["work"].get("title") or "").strip(): raise ValidationError({"work": {"title": "请填写题名。"}})
        # Nested workflow serializers add a blank note; do not accept it as a metadata field.
        attrs["work"].pop("note", None); attrs["bibliography"].pop("note", None)
        return attrs


class ManualCommandSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    session_id = serializers.UUIDField(required=False, allow_null=True)
    expected_version = serializers.CharField(required=False, allow_blank=True)
    mode = serializers.ChoiceField(choices=["use_edition", "new_version", "new_work"])
    edition_id = serializers.UUIDField(required=False, allow_null=True)
    candidate_version = serializers.CharField(required=False, allow_blank=True)
    acknowledge_similar = serializers.BooleanField(default=False)
    continue_files = serializers.BooleanField(default=False)
    form = ManualFormSerializer()
    prefills = PrefillSelection(many=True, required=False, max_length=30)


class ManualQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=160, required=False, allow_blank=True)
    people = serializers.CharField(max_length=160, required=False, allow_blank=True)
    page = serializers.IntegerField(min_value=1, default=1)
    session = serializers.UUIDField(required=False)


class ManualWorkspaceSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    results = serializers.ListField(child=serializers.JSONField())
    people = serializers.ListField(child=serializers.JSONField())
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    saved = serializers.JSONField(allow_null=True)


class ManualReceiptSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    session_id = serializers.UUIDField(allow_null=True)
    edition_id = serializers.UUIDField(allow_null=True)
    work_id = serializers.UUIDField(allow_null=True)
    version = serializers.CharField(allow_blank=True)
    next_url = serializers.CharField(allow_blank=True)
    form = serializers.JSONField(allow_null=True)
    manual_form = serializers.BooleanField()
    shared_work = serializers.BooleanField()


def receipt(event):
    return {"owner_id": str(event.actor_id), "request_id": event.request_id,
        "state": "cancelled" if event.after.get("cancelled") else "applied",
        **{key: event.after.get(key) for key in ("session_id", "edition_id", "work_id", "form")},
        "version": event.after.get("version", ""), "next_url": event.after.get("next_url", ""), "manual_form": event.after.get("manual_form", False), "shared_work": event.after.get("shared_work", False)}


def form_for(edition):
    fields = ManualFormSerializer().fields
    names = fields["bibliography"].fields
    return {"work": {key: getattr(edition.work, key) for key in ("title", "document_type", "language", "subtitle", "abstract")},
        "bibliography": {key: getattr(edition, key) for key in names if hasattr(edition, key) and key not in {"publication_date", "publisher_authority_id", "publication_mode", "isbn10", "isbn13", "responsibility_statement"}},
        "contributors": [{"person_id": str(row.person_id), "name": row.person.preferred_name, "role": row.role, "create_new": False} for row in edition.contributions.select_related("person")]}


class ManualCatalogView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    def handle_exception(self, error):
        if isinstance(error, (CatalogingSessionConflict, WorkflowEditError)): error = EditConflict(str(error))
        if isinstance(error, ModelValidationError): error = ValidationError(error.messages)
        return super().handle_exception(error)

    @extend_schema(parameters=[ManualQuerySerializer], responses=ManualWorkspaceSerializer)
    def get(self, request):
        actor = actor_for(request)
        query = ManualQuerySerializer(data=request.query_params); query.is_valid(raise_exception=True)
        data = query.validated_data
        pages = Paginator(work_rows(data["q"]) if data.get("q") else Work.objects.none(), 12)
        page = pages.get_page(data["page"])
        rows = []
        for work in page:
            editions = list(work.editions.all())
            rows.append({"id": str(work.pk), "title": work.title, "document_type": work.document_type, "language": work.language,
                "abstract": work.abstract, "subtitle": work.subtitle, "cover_url": f"/api/catalog/admin/media/renditions/{work.cover_rendition_id}/file/" if work.cover_rendition_id else "",
                "editions": [{"id": str(row.pk), "version": version(row), "label": " · ".join(filter(None, [str(row.publication_year or ""), row.version_label, row.publisher])) or "出版信息待补",
                    "state": row.state, "bibliography": form_for(row)["bibliography"], "contributors": form_for(row)["contributors"]} for row in editions]})
        people = person_rows(data["people"])[:15] if data.get("people") else []
        saved = None
        if data.get("session"):
            session = get_object_or_404(CatalogingSession.objects.select_related("edition__work"), pk=data["session"], created_by=actor, source_type="manual")
            saved = {"session_id": str(session.pk), "version": version(session.edition), "edition_id": str(session.edition_id), "work_id": str(session.work_id),
                     "status": session.status, "form": form_for(session.edition), "shared_work": session.edition.work.editions.exclude(pk=session.edition_id).exists(), "editable": session.status in OPEN_STATUSES and session.status != "publishing" and session.edition.state == "draft"}
        return Response({"owner_id": str(actor.pk), "results": rows, "people": [{"id": str(row.pk), "name": row.preferred_name, "original_name": row.original_name, "context": " · ".join(filter(None, [row.country_region, str(row.birth_year or ""), row.authority_status]))} for row in people],
                         "count": pages.count, "page": page.number, "pages": pages.num_pages, "saved": saved})

    @extend_schema(request=ManualCommandSerializer, responses=ManualReceiptSerializer)
    @transaction.atomic
    def post(self, request):
        actor = actor_for(request, True)
        incoming = ManualCommandSerializer(data=request.data); incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        if set(request.data) - set(incoming.fields): raise ValidationError("书目保存包含未支持字段。")
        fingerprint = salted_hmac(ACTION, json.dumps(request.data, sort_keys=True, ensure_ascii=False)).hexdigest()
        previous = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(data["request_id"])).first()
        if previous:
            if previous.after.get("fingerprint") != fingerprint: raise EditConflict("此编号已用于其他内容或已停止，请先查回原请求。")
            return Response(receipt(previous))
        prefills = unpack_selections(data.get("prefills", []), actor)
        if prefills and data["mode"] == "use_edition": raise ValidationError("选用已有版本不会写入预填来源，请移除本次预填后继续。")
        form = data["form"]
        session = None
        if data.get("session_id"):
            session = get_object_or_404(CatalogingSession.objects.select_for_update(of=("self",)).select_related("edition__work"), pk=data["session_id"], created_by=actor, source_type="manual")
            edition = get_object_or_404(Edition.objects.select_for_update(of=("self", "work")).select_related("work"), pk=session.edition_id)
            if session.status not in {"drafting", "reviewing", "ready"} or edition.state != "draft" or edition.active_catalog_revision_id or edition.first_published_at:
                raise EditConflict("此书目已进入后续流程，请在馆藏工作页修订。")
            if data.get("expected_version") != version(edition): raise EditConflict("书目已由其他操作更新，输入保留，请重新核对。")
        elif data["mode"] != "new_work":
            target = get_object_or_404(Edition.objects.select_for_update(of=("self", "work")).select_related("work"), pk=data.get("edition_id"))
            if data.get("candidate_version") != version(target): raise EditConflict("所选版本已经变化，请重新选择。")
            if data["mode"] == "use_edition":
                session, _ = open_cataloging_session(actor=actor, edition_id=target.pk, source_type="existing", request_key=data["request_id"])
                edition = target
            else:
                edition = Edition.objects.create(work=target.work, publication_mode="bibliographic", is_primary=False)
                session, _ = open_cataloging_session(actor=actor, edition_id=edition.pk, source_type="manual", request_key=data["request_id"])
        else:
            if Work.objects.filter(normalized_title=form["work"]["title"].strip().casefold()).exists() and not data["acknowledge_similar"]:
                raise EditConflict("馆内有同名作品，请先核对已有作品，或明确确认另建不同作品。")
            session, _ = open_cataloging_session(actor=actor, source_type="manual", title=form["work"]["title"], document_type=form["work"].get("document_type", "book"), language=form["work"].get("language", "zh-CN"), request_key=data["request_id"])
            edition = session.edition
        if data["mode"] != "use_edition" or data.get("session_id"):
            # Never mutate an existing work's identity through the new-edition form.
            only_edition = edition.work.editions.exclude(pk=edition.pk).exists()
            if only_edition and any(form["work"].get(key, getattr(edition.work, key)) != getattr(edition.work, key) for key in ("title", "document_type", "language", "subtitle", "abstract")):
                raise ValidationError("新增版本沿用已有作品身份；作品题名、类型或语言的修订请进入作品工作页。")
            if not only_edition: save_workflow_section(edition, "work", form["work"], actor=actor, confirm_section=False)
            save_workflow_section(edition, "bibliography", form["bibliography"], actor=actor, confirm_section=False)
            contributors = []
            new_names = [row["name"] for row in form["contributors"] if not row["person_id"] and row["create_new"]]
            if len(set(new_names)) != len(new_names):
                raise ValidationError("同名新人物的身份需要分别核对。请先保存一个明确的人物，之后选择其馆内记录来添加其他责任角色。")
            for index, row in enumerate(form["contributors"]):
                if row["person_id"]:
                    person = get_object_or_404(Person.objects.select_for_update().exclude(authority_status__in=["merged", "archived", "rejected"]), pk=row["person_id"])
                    if person.preferred_name != row["name"]: raise EditConflict("责任者名称已变化，请重新选择馆内人物。")
                elif row["create_new"]:
                    if not has_capability(actor, Capability.CREATE_AUTHORITY):
                        raise PermissionDenied("当前账户不能新建人物草稿，请选择已有馆内人物。")
                    person = Person.objects.create(preferred_name=row["name"], authority_status="draft", authority_note="新建书目时明确建立；身份尚待核对")
                else: raise ValidationError("请为每位责任者选择馆内人物，或明确选择新建人物草稿。")
                contributors.append({"person_id": person.pk, "role": row["role"], "order": index})
            if len({(row["person_id"], row["role"]) for row in contributors}) != len(contributors): raise ValidationError("同一责任者与角色不能重复。")
            save_workflow_section(edition, "contributors", {"contributors": contributors}, actor=actor, confirm_section=False)
            edition.refresh_from_db(); edition.work.refresh_from_db()
        shared_work = edition.work.editions.exclude(pk=edition.pk).exists()
        assistance = record_prefills(prefills, edition, session, actor, data["request_id"], shared_work=shared_work)
        path = f"/admin/library/works/{edition.work_id}"
        event = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="CatalogingSession", object_id=str(session.pk), request_id=str(data["request_id"]),
            after={"fingerprint": fingerprint, "assistance": assistance, "shared_work": shared_work, "session_id": str(session.pk), "edition_id": str(edition.pk), "work_id": str(edition.work_id), "version": version(edition),
                   "form": form_for(edition), "manual_form": data["mode"] != "use_edition", "next_url": f"{path}/files?edition={edition.pk}" if data["continue_files"] else f"{path}?edition={edition.pk}#bibliography"})
        return Response(receipt(event))


class ManualCancelSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class ManualCatalogReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(responses=ManualReceiptSerializer)
    def get(self, request, request_id):
        actor = actor_for(request)
        return Response(receipt(get_object_or_404(AuditEvent, actor=actor, action=ACTION, request_id=str(request_id))))

    @extend_schema(request=ManualCancelSerializer, responses=ManualReceiptSerializer)
    @transaction.atomic
    def post(self, request, request_id):
        actor = actor_for(request, True)
        if request.data != {"action": "cancel_pending"}: raise ValidationError("仅接受停止原待定请求。")
        event = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(request_id)).first()
        if not event: event = AuditEvent.objects.create(actor=actor, action=ACTION, request_id=str(request_id), object_type="CatalogingSession", after={"cancelled": True})
        return Response(receipt(event))
