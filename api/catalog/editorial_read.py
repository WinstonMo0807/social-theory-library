"""Private Admin reads over existing serializers and saved editorial previews."""

from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response

from common.capabilities import Capability, has_capability

from catalog.models import EditorialRevision


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
        output = []
        for row in rows:
            revision = revisions.get(str(row.pk))
            if revision is None:
                output.append(dict(self.get_serializer(row).data))
                continue
            try:
                output.append(KnowledgeObjectEditorAdapter.serialize_admin_draft(
                    target_type=self.editorial_target_type,
                    target=row,
                    revision=revision,
                    serializer=self.get_serializer,
                ))
            except ValueError as error:
                raise EditorialDraftReadError(str(error)) from error
        return output

    def retrieve(self, request, *args, **kwargs):
        return Response(self._draft_read_rows([self.get_object()])[0])

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = self._draft_read_rows(page if page is not None else queryset)
        return self.get_paginated_response(rows) if page is not None else Response(rows)
