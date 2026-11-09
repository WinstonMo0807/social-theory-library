"""Compatibility transports. Every academic write produces the same ChangeSet."""
from rest_framework.response import Response
from catalog.services.academic_relations import legacy_relation_draft
from catalog.services.intelligence_queries import changeset_data


def relation_response(request, kind, *, values=None, legacy_id=None):
    draft = legacy_relation_draft(kind, dict(request.data) if values is None else values, request.user,
        request_id=request.headers.get("Idempotency-Key") or request.data.get("request_id"), legacy_id=legacy_id)
    return Response(changeset_data(draft, request.user), status=202)


class AcademicRelationCommandMixin:
    relation_kind = "node"

    def create(self, request, *args, **kwargs):
        return relation_response(request, self.relation_kind)

    def update(self, request, *args, **kwargs):
        return relation_response(request, self.relation_kind, legacy_id=self.get_object().pk)

    def destroy(self, request, *args, **kwargs):
        return relation_response(request, self.relation_kind, values={**request.data, "operation": "withdraw"}, legacy_id=self.get_object().pk)
