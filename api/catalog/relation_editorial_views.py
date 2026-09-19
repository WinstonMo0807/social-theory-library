"""The two dedicated editors use the shared draft/version service."""
from django.db import transaction
from rest_framework.response import Response

from catalog.editorial_read import AdminEditorialDraftReadMixin
from catalog.models import EditorialRevision


class StagedRelationEditorMixin(AdminEditorialDraftReadMixin):
    public_status_field = "status"
    public_status_value = "published"
    draft_status_value = "draft"

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code < 300:
            target = self.get_queryset().get(pk=response.data["id"])
            response.data = self._draft_read_rows([target])[0]
        return response

    def perform_create(self, serializer):
        from catalog.services.editorial_drafts import save_object_editorial_patch
        requested = serializer.validated_data.get(self.public_status_field)
        if requested == self.public_status_value:
            target = serializer.save(**{self.public_status_field: self.draft_status_value})
            save_object_editorial_patch(self.editorial_target_type, target.pk,
                {self.public_status_field: requested}, actor=self.request.user,
                change_note="准备首次发布")
        else:
            serializer.save()

    def update(self, request, *args, **kwargs):
        from catalog.services.editorial_drafts import save_object_editorial_patch
        from catalog.services.editorial_revision import EditorialRevisionError
        from catalog.services.relation_editorial import validated_editorial_values
        target = self.get_object()
        has_draft = EditorialRevision.objects.filter(target_type=self.editorial_target_type, target_id=target.pk, status="draft").exists()
        current_public = getattr(target, self.public_status_field) == self.public_status_value
        if not current_public and not has_draft and request.data.get(self.public_status_field) != self.public_status_value:
            return super().update(request, *args, **kwargs)
        serializer = self.get_serializer(target, data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        try:
            save_object_editorial_patch(self.editorial_target_type, target.pk,
                validated_editorial_values(target, serializer.validated_data), actor=request.user,
                request_key=request.headers.get("Idempotency-Key", ""), change_note="保存待发布修改")
        except EditorialRevisionError as error:
            return Response({"detail": str(error), "code": "editorial_revision_error"}, status=400)
        return Response(self._draft_read_rows([target])[0], status=202)
