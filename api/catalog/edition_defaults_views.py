from uuid import uuid4

from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Work
from catalog.services.edition_defaults import EditionDefaultsError, serialize_work_edition_defaults, update_work_edition_defaults
from common.permissions import CanAccessBackOffice, CanPublishWork


class AdminWorkEditionDefaultsView(AdminPrivateResponseMixin, APIView):
    def get_permissions(self):
        return [CanPublishWork()] if self.request.method in {"PUT", "PATCH"} else [CanAccessBackOffice()]

    def get(self, request, work_id):
        try:
            work = Work.objects.get(pk=work_id)
        except Work.DoesNotExist as error:
            raise Http404 from error
        return Response(serialize_work_edition_defaults(work))

    def _save(self, request, work_id):
        data = request.data if isinstance(request.data, dict) else {}
        if data.get("confirmed") is not True:
            return Response({"code": "edition_defaults.confirmation_required", "detail": "请明确确认在线阅读和下载入口会使用新的出版版本。"}, status=400)
        request_id = str(data.get("request_id") or uuid4())
        try:
            result = update_work_edition_defaults(
                work_id,
                reader_default_edition_id=data.get("reader_default_edition_id"),
                download_default_edition_id=data.get("download_default_edition_id"),
                actor=request.user,
                request_id=request_id,
            )
        except Work.DoesNotExist as error:
            raise Http404 from error
        except EditionDefaultsError as error:
            return Response({"code": "edition_defaults.invalid", "detail": str(error), "request_id": request_id}, status=409)
        return Response(result)

    def put(self, request, work_id):
        return self._save(request, work_id)

    def patch(self, request, work_id):
        return self._save(request, work_id)
