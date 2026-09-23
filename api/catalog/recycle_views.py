from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from common.permissions import IsLibraryStaff
from .models import RecycleEntry
from .services.recycle import require_editor, restore_object


class AdminRecycleView(APIView):
    permission_classes = [IsLibraryStaff]

    def get(self, request):
        require_editor(request.user)
        rows = RecycleEntry.objects.filter(restored_at__isnull=True).order_by("-updated_at", "id")
        search = str(request.query_params.get("search", ""))[:200]
        if search:
            rows = rows.filter(name__icontains=search)
        try:
            offset = max(0, int(request.query_params.get("offset", 0)))
        except (ValueError, TypeError):
            offset = 0
        return Response({"count": rows.count(), "results": [
            {"id": str(row.pk), "kind": row.kind, "object_id": str(row.object_id), "name": row.name,
             "deleted_at": row.updated_at.isoformat()}
            for row in rows[offset:offset + 50]
        ]}, headers={"Cache-Control": "private, no-store"})

    def post(self, request):
        require_editor(request.user)
        entry_id = serializers.UUIDField().run_validation(request.data.get("id"))
        entry = get_object_or_404(RecycleEntry, pk=entry_id)
        restore_object(entry.pk, actor=request.user)
        return Response({"restored": True, "kind": entry.kind, "id": str(entry.object_id),
                         "detail": "已恢复到管理列表。尚未重新发布或启动处理。"}, headers={"Cache-Control": "private, no-store"})
