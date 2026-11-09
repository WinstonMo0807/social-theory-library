"""Intelligence transports. All actions delegate to permission-checked services."""
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from catalog import models as m
from catalog.services import intelligence, intelligence_changes as changes, intelligence_queries as queries
from catalog.services.intelligence_provider import configuration, identity
from common.permissions import CanEditMetadata


class CreateRunInput(serializers.Serializer):
    document_revision_id = serializers.UUIDField()
    request_id = serializers.UUIDField()
    scope = serializers.JSONField(default={"mode": "whole"})
    profile_key = serializers.CharField(required=False, default="", allow_blank=True, max_length=80)


class Runs(APIView):
    permission_classes = [CanEditMetadata]

    def get(self, request):
        rows = m.CurationRun.objects.select_related("work", "document_revision__asset__edition").order_by("-created_at")
        if request.query_params.get("work_id"):
            rows = rows.filter(work_id=serializers.UUIDField().run_validation(request.query_params["work_id"]))
        config = configuration()
        return Response({"runs": [queries.run_data(r, request.user) for r in rows[:100]],
            "drafts": [{"id": str(c.pk), "title": c.document_revision.asset.edition.work.title if c.document_revision_id else c.subject_work.title if c.subject_work_id else c.subject_entity.label if c.subject_entity_id else c.subject_page.title, "origin": c.origin}
                for c in m.ChangeSet.objects.filter(run__isnull=True).select_related("document_revision__asset__edition__work", "subject_work", "subject_entity", "subject_page").order_by("-created_at")[:100]],
            "stages": intelligence.STAGES, "configuration": {**identity(config), "enabled": config.enabled,
                "settings_url": "/admin/intelligence/settings", "protocol": "openai_compatible"}})

    def post(self, request):
        value = CreateRunInput(data=request.data)
        value.is_valid(raise_exception=True)
        args = dict(value.validated_data)
        revision = get_object_or_404(m.DocumentRevision, pk=args.pop("document_revision_id"))
        run = intelligence.create_run(revision, request.user, **args)
        return Response(queries.run_data(run, request.user, detail=True), status=201)


class RunDetail(APIView):
    permission_classes = [CanEditMetadata]

    def get(self, request, run_id):
        return Response(queries.run_data(get_object_or_404(m.CurationRun, pk=run_id), request.user, detail=True))

    def post(self, request, run_id):
        get_object_or_404(m.CurationRun, pk=run_id)
        run = intelligence.control_run(run_id, request.user, request.data.get("action"))
        return Response(queries.run_data(run, request.user, detail=True))


class Sources(APIView):
    permission_classes = [CanEditMetadata]

    def get(self, request):
        work_id = request.query_params.get("work_id")
        if work_id:
            work_id = serializers.UUIDField().run_validation(work_id)
        return Response({"sources": queries.sources(request.user, work_id=work_id)})


class Drafts(APIView):
    permission_classes = [CanEditMetadata]

    def post(self, request):
        revision = get_object_or_404(m.DocumentRevision, pk=serializers.UUIDField().run_validation(request.data.get("document_revision_id")))
        result = changes.submit_draft(revision, request.data.get("items"), request.user, request_id=request.data.get("request_id"))
        return Response(queries.changeset_data(result, request.user), status=201)


class ChangeSetDetail(APIView):
    permission_classes = [CanEditMetadata]

    def get(self, request, changeset_id):
        return Response(queries.changeset_data(get_object_or_404(m.ChangeSet, pk=changeset_id), request.user))


class Review(APIView):
    permission_classes = [CanEditMetadata]

    def post(self, request, changeset_id):
        get_object_or_404(m.ChangeSet, pk=changeset_id)
        version = serializers.IntegerField(min_value=1).run_validation(request.data.get("expected_version"))
        result = changes.review(changeset_id, request.data.get("decisions"), request.user, expected_version=version)
        return Response(queries.changeset_data(result, request.user))


class Apply(APIView):
    permission_classes = [CanEditMetadata]

    def post(self, request, changeset_id):
        get_object_or_404(m.ChangeSet, pk=changeset_id)
        version = serializers.IntegerField(min_value=1).run_validation(request.data.get("expected_version"))
        selected = serializers.ListField(child=serializers.UUIDField(), max_length=2000).run_validation(request.data.get("selected_ids"))
        return Response(changes.apply(changeset_id, selected, request.user, request_id=request.data.get("request_id"), expected_version=version))


urlpatterns = [path("runs/", Runs.as_view()), path("runs/<uuid:run_id>/", RunDetail.as_view()),
    path("sources/", Sources.as_view()), path("changesets/", Drafts.as_view()),
    path("changesets/<uuid:changeset_id>/", ChangeSetDetail.as_view()),
    path("changesets/<uuid:changeset_id>/review/", Review.as_view()),
    path("changesets/<uuid:changeset_id>/apply/", Apply.as_view())]
