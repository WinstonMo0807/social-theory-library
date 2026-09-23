"""Private Admin reads over existing serializers and saved editorial previews."""

from hashlib import sha256
import json

from django.db import OperationalError, transaction
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response

from common.capabilities import Capability, has_capability

from catalog.models import CanonicalObjectRevision, EditorialRevision, Person


class EditorialDraftReadError(APIException):
    status_code = 409
    default_detail = "编辑草稿暂不能安全显示，请检查当前编辑版本。"
    default_code = "editorial_draft_unavailable"


class AdminPrivateResponseMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class AdminEditorialDraftReadMixin(AdminPrivateResponseMixin):
    """Opt-in only on protected Admin views, never public catalog views."""

    editorial_target_type = ""

    def get_object(self):
        locked = getattr(self, "_editorial_locked_target", None)
        return locked if locked is not None else super().get_object()

    def _guarded_edit(self, handler, request, *args, **kwargs):
        # Authentication and route permissions have already run in DRF initial().
        target = self.get_object()
        expected = str(request.headers.get("If-Match") or "").strip().strip('"')
        if not expected or expected == "*":
            return Response({"detail": "请重新打开这条资料后再保存，当前页面缺少修改版本。", "code": "edit_version_required"}, status=428)
        try:
            with transaction.atomic():
                target = self.get_queryset().select_for_update(of=("self",), nowait=True).get(pk=target.pk)
                if self.editorial_target_type == "scholar_profile":
                    target.person = Person.objects.select_for_update(nowait=True).get(pk=target.person_id)
                self._editorial_locked_target = target
                current = self._draft_read_rows([target])[0]["edit_version"]
                if not constant_time_compare(expected, current):
                    return Response({"detail": "这条资料已被修改。你的输入没有提交，请先核对最新内容再保存。", "code": "edit_conflict"}, status=409)
                from catalog.services.field_assistant.editorial_prefills import (
                    apply_editorial_prefill_details, prepare_editorial_prefills, record_editorial_prefills,
                )
                prefills = prepare_editorial_prefills(request, self, target) if request.method != "DELETE" else []
                response = handler(request, *args, **kwargs)
                if response.status_code >= 400:
                    transaction.set_rollback(True)
                elif isinstance(response.data, dict) and request.method != "DELETE":
                    details = apply_editorial_prefill_details(prefills, actor=request.user)
                    saved = self.get_queryset().get(pk=target.pk)
                    saved_data = self._draft_read_rows([saved])[0]
                    record_editorial_prefills(prefills, actor=request.user, response=saved_data, details=details)
                    response.data.update(saved_data)
                return response
        except OperationalError as error:
            cause = error.__cause__
            if getattr(cause, "sqlstate", None) == "55P03" or getattr(cause, "pgcode", None) == "55P03":
                return Response({"detail": "有人正在保存这条资料。你的输入已保留，请稍后核对最新内容。", "code": "edit_busy"}, status=409)
            raise
        finally:
            self._editorial_locked_target = None

    def patch(self, request, *args, **kwargs):
        return self._guarded_edit(super().patch, request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return self._guarded_edit(super().put, request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        def command(request, *args, **kwargs):
            from catalog.lifecycle_views import LIFECYCLE_MODELS, _name
            from catalog.services.recycle import recycle_object
            target = self.get_object()
            for kind, config in LIFECYCLE_MODELS.items():
                if isinstance(target, config.model):
                    recycle_object(target, actor=request.user, kind=kind, name=_name(target, config.name_field))
                    return Response(status=204)
            return super(AdminEditorialDraftReadMixin, self).delete(request, *args, **kwargs)
        return self._guarded_edit(command, request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code < 300 and isinstance(response.data, dict) and response.data.get("id"):
            target = self.get_queryset().get(pk=response.data["id"])
            response.data["edit_version"] = self._draft_read_rows([target])[0]["edit_version"]
        return response

    def _draft_read_rows(self, instances):
        if not has_capability(self.request.user, Capability.ACCESS_BACK_OFFICE):
            raise PermissionDenied("当前账户不能读取编辑草稿。")
        from catalog.services.knowledge_studio import KnowledgeObjectEditorAdapter

        rows = list(instances)
        revisions = {}
        for revision in EditorialRevision.objects.filter(
            target_type=self.editorial_target_type,
            target_id__in=[row.pk for row in rows],
            status=EditorialRevision.Status.DRAFT,
        ).order_by("target_id", "-revision"):
            revisions.setdefault(str(revision.target_id), revision)
        canonical = dict(CanonicalObjectRevision.objects.filter(
            object_type=self.editorial_target_type, object_id__in=[row.pk for row in rows],
        ).values_list("object_id", "current_revision"))
        output = []
        for row in rows:
            revision = revisions.get(str(row.pk))
            version = {"type": self.editorial_target_type, "id": row.pk, "updated_at": row.updated_at,
                       "canonical": canonical.get(row.pk, 0),
                       "draft": [revision.pk, revision.updated_at] if revision else None}
            if self.editorial_target_type == "scholar_profile":
                version["person"] = [row.person_id, row.person.updated_at]
            edit_version = sha256(json.dumps(version, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()
            if revision is None:
                output.append({**dict(self.get_serializer(row).data), "edit_version": edit_version})
                continue
            try:
                data = KnowledgeObjectEditorAdapter.serialize_admin_draft(
                    target_type=self.editorial_target_type,
                    target=row,
                    revision=revision,
                    serializer=self.get_serializer,
                )
                output.append({**data, "edit_version": edit_version})
            except ValueError as error:
                raise EditorialDraftReadError(str(error)) from error
        if self.editorial_target_type in {"knowledge_relation", "timeline_event"}:
            for data, row in zip(output, rows):
                data["public_status"] = getattr(row, "review_status", getattr(row, "status", ""))
                data["has_unpublished_changes"] = bool(data.get("editorial_revision"))
        return output

    def retrieve(self, request, *args, **kwargs):
        return Response(self._draft_read_rows([self.get_object()])[0])

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = self._draft_read_rows(page if page is not None else queryset)
        return self.get_paginated_response(rows) if page is not None else Response(rows)
