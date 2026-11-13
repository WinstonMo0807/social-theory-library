"""Knowledge compilation actions; no independent Intelligence workbench."""
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from catalog import models as m
from catalog.services import knowledge_compilation as service
from common.permissions import CanEditMetadata


class CompilationInput(serializers.Serializer):
    document_revision_id = serializers.UUIDField()
    enabled = serializers.BooleanField(default=True)
    scope = serializers.JSONField(default={"mode":"whole"})
    profile_key = serializers.CharField(max_length=80, default="", allow_blank=True)
    execution_mode = serializers.ChoiceField(choices=["provider", "agent"], default="provider")
    target_page_ids = serializers.ListField(child=serializers.UUIDField(), max_length=30, default=list)


class Compilations(APIView):
    permission_classes = [CanEditMetadata]

    def get(self, request):
        rows = m.KnowledgeCompilation.objects.select_related("edition__work", "latest_run__document_revision__asset").order_by("-updated_at")
        if request.query_params.get("work_id"):
            rows = rows.filter(edition__work_id=serializers.UUIDField().run_validation(request.query_params["work_id"]))
        offset = serializers.IntegerField(min_value=0, max_value=100000).run_validation(request.query_params.get("offset", 0))
        page = list(rows[offset:offset+31])
        return Response({"compilations":[service.compilation_data(row, request.user) for row in page[:30]], "has_more":len(page)>30})

    def post(self, request):
        serializer = CompilationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        revision = get_object_or_404(m.DocumentRevision, pk=values.pop("document_revision_id"))
        result = service.configure(revision, request.user, **values)
        return Response(service.compilation_data(result, request.user), status=202)


class CompilationDetail(APIView):
    permission_classes = [CanEditMetadata]

    def get(self, request, compilation_id):
        subscription = get_object_or_404(m.KnowledgeCompilation, pk=compilation_id)
        value = service.compilation_data(subscription, request.user)
        if subscription.latest_run_id:
            # Metadata only; source packets have a separate authenticated action.
            value["windows"] = list(subscription.latest_run.artifacts.filter(stage=2).order_by("created_at", "pk")
                .values("id", "unit", "status", "elapsed_ms", "usage", "output_hash"))
            value["synthesis"] = subscription.latest_run.artifacts.filter(stage=3, status__in=["succeeded", "empty"]).order_by("-created_at").values("output").first()
        return Response(value)

    def post(self, request, compilation_id):
        from catalog.services.knowledge_core import require_editor
        from catalog.services.intelligence import control_run
        subscription = get_object_or_404(m.KnowledgeCompilation, pk=compilation_id)
        require_editor(request.user)
        if not subscription.latest_run:
            raise serializers.ValidationError("尚无可恢复的编纂记录。")
        action = serializers.ChoiceField(choices=["pause", "resume", "refresh"]).run_validation(request.data.get("action"))
        if action == "pause":
            if subscription.latest_run.status not in {"succeeded", "empty", "partial", "canceled"}:
                control_run(subscription.latest_run_id, request.user, "cancel")
            subscription.enabled = False
            subscription.save(update_fields=["enabled", "updated_at"])
        else:
            subscription.enabled, subscription.updated_by = True, request.user
            subscription.save(update_fields=["enabled", "updated_by", "updated_at"])
            revision = subscription.latest_run.document_revision
            # Follow the new active text of the same file; never guess across editions.
            current = m.DocumentRevision.objects.filter(asset=revision.asset, is_active=True).first()
            service.reconcile(current or revision, retry=True)
        subscription.refresh_from_db()
        return Response(service.compilation_data(subscription, request.user), status=202)


class AgentArtifact(APIView):
    permission_classes = [CanEditMetadata]

    def get(self, request, artifact_id):
        return Response(service.agent_packet(get_object_or_404(m.CurationArtifact, pk=artifact_id), request.user))

    def post(self, request, artifact_id):
        get_object_or_404(m.CurationArtifact, pk=artifact_id)
        result = service.submit_agent_result(artifact_id, request.user,
            input_hash=serializers.CharField(max_length=64).run_validation(request.data.get("input_hash")),
            run_version=serializers.IntegerField(min_value=1).run_validation(request.data.get("run_version")),
            output=request.data.get("output"),
            executor_label=serializers.CharField(max_length=160).run_validation(request.data.get("executor_label")))
        return Response({"artifact_id":str(result.pk), "status":result.status, "output_hash":result.output_hash})


class CompilationProduct(APIView):
    permission_classes = [CanEditMetadata]

    def get(self, request, artifact_id):
        from catalog.services.knowledge_sources import require_revision_access
        artifact = get_object_or_404(m.CurationArtifact.objects.select_related("run__document_revision"),
            pk=artifact_id, stage=2, status__in=["succeeded", "empty"])
        require_revision_access(artifact.run.document_revision, request.user, editorial=True)
        return Response({"id":str(artifact.pk), "unit":artifact.unit, "output":artifact.output,
            "document_revision_id":str(artifact.run.document_revision_id),
            "reader_url":f"/reader/{artifact.run.document_revision.asset_id}?revision={artifact.run.document_revision_id}&preview=1",
            "chapter_path":artifact.input_manifest.get("chapter_path", []),
            "ranges":[{key:value for key,value in row.items() if key != "text"}
                for row in artifact.input_manifest.get("ranges", [])],
            "executor_id":artifact.executor_id, "usage":artifact.usage})


class Reviews(APIView):
    permission_classes = [CanEditMetadata]

    def get(self, request):
        rows = m.ChangeSet.objects.select_related("document_revision__asset__edition__work", "subject_work", "subject_entity", "subject_page").order_by("-created_at")
        return Response({"drafts":[{"id":str(row.pk), "origin":row.origin, "status":row.status,
            "title":row.document_revision.asset.edition.work.title if row.document_revision_id else row.subject_work.title if row.subject_work_id else row.subject_entity.label if row.subject_entity_id else row.subject_page.title}
            for row in rows[:100]]})


urlpatterns = [path("compilations/", Compilations.as_view()),
    path("compilations/<uuid:compilation_id>/", CompilationDetail.as_view()),
    path("compilation-products/<uuid:artifact_id>/", CompilationProduct.as_view()),
    path("compilation-artifacts/<uuid:artifact_id>/", AgentArtifact.as_view()), path("reviews/", Reviews.as_view())]
