from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Edition, KnowledgePublicationEvent
from catalog.services.knowledge_publication import retry_knowledge_publication
from common.capabilities import Capability, has_capability
from common.permissions import CanAccessBackOffice


CONSUMER_LABELS = {
    "query_lexicon": "规范名称更新", "bibliographic_search": "书目检索更新",
    "fulltext": "正文检索处理", "semantic": "正文语义处理", "rag": "馆藏问答材料更新",
    "viewpoint": "观点检索更新", "knowledge_graph": "知识关联更新",
    "person_search": "学者检索更新", "recommendation": "相关推荐更新", "public_cache": "公开页面更新",
}


def publication_status(event, user):
    if event is None:
        return {"event_id": None, "state": "not_started", "label": "尚未开始智能内容更新", "can_retry": False, "failures": []}
    failed = event.status in {"failed", "dead_letter"}
    complete = event.status == "completed"
    withdrawal = event.event_type == "catalog_withdrawn" or bool((event.payload.get("provenance") or {}).get("withdrawal"))
    capability = Capability.PUBLISH_WORK if event.catalog_revision_id else Capability.PUBLISH_AUTHORITY
    return {
        "event_id": str(event.pk), "state": "failed" if failed else "ready" if complete else "processing",
        "label": "智能内容更新异常" if failed else ("已退出智能检索" if withdrawal else "已进入智能检索") if complete else "智能内容处理中",
        "can_retry": failed and has_capability(user, capability),
        "failures": [CONSUMER_LABELS.get(value, "智能内容处理") for value in event.deliveries.filter(status="failed").values_list("consumer", flat=True)],
        "withdrawal": withdrawal,
    }


class PublicationStatusQuery(serializers.Serializer):
    object_type = serializers.ChoiceField(choices=("person", "scholar_profile", "topic", "knowledge_node", "discipline", "subdiscipline", "reading_path", "theory_school", "knowledge_relation"))
    object_id = serializers.UUIDField()


class AdminKnowledgePublicationStatusView(APIView):
    permission_classes = [CanAccessBackOffice]

    def get(self, request, edition_id=None):
        if edition_id:
            get_object_or_404(Edition, pk=edition_id)
            events = KnowledgePublicationEvent.objects.filter(catalog_revision__edition_id=edition_id)
        else:
            query = PublicationStatusQuery(data=request.query_params)
            query.is_valid(raise_exception=True)
            events = KnowledgePublicationEvent.objects.filter(**query.validated_data)
        event = events.order_by("-created_at", "-pk").first()
        return Response(publication_status(event, request.user))


class AdminKnowledgePublicationRetryView(APIView):
    permission_classes = [CanAccessBackOffice]

    def post(self, request, event_id):
        get_object_or_404(KnowledgePublicationEvent, pk=event_id)
        try:
            event = retry_knowledge_publication(event_id, actor=request.user)
        except PermissionError as exc:
            raise PermissionDenied(str(exc)) from exc
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(publication_status(event, request.user), status=status.HTTP_202_ACCEPTED)
