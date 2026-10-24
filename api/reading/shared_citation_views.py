"""Transient public citation preview. No private text is accepted as an authority."""
import json

from django.contrib.auth.models import AnonymousUser
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Edition
from catalog.services.citations import citation_bundle
from catalog.services.media import snapshot_cover
from catalog.services.publication_eligibility import active_catalog_snapshot, public_edition_q
from . import research
from .research_serializers import EvidenceReferenceInput


class PublicCitationInput(serializers.Serializer):
    edition_id = serializers.UUIDField(required=False)
    reference = EvidenceReferenceInput(required=False)
    selected_text = serializers.CharField(max_length=20000, required=False, allow_blank=True, trim_whitespace=False)


class PublicCitationOutput(serializers.Serializer):
    source = serializers.JSONField(read_only=True)
    reference = serializers.JSONField(read_only=True, allow_null=True)
    citations = serializers.DictField(child=serializers.JSONField(), read_only=True)


def selection_range(source, selected):
    """Ignore layout whitespace only; ambiguous or changed text is never guessed."""
    wanted = "".join(character for character in selected if not character.isspace())
    positions = [i for i, character in enumerate(source) if not character.isspace()]
    normalized = "".join(source[i] for i in positions)
    start = normalized.find(wanted)
    if not wanted or start < 0 or normalized.find(wanted, start + 1) >= 0:
        raise ValidationError({"selected_text": "这段文字无法唯一对应当前原文。请重新选择更完整的段落。"})
    return positions[start], positions[start + len(wanted) - 1] + 1


class PublicCitationPreviewView(APIView):
    permission_classes = [AllowAny]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    @extend_schema(request=PublicCitationInput, responses=PublicCitationOutput)
    def post(self, request):
        if not isinstance(request.data, dict) or len(json.dumps(request.data)) > 150000:
            raise ValidationError({"detail": "引用请求过大或无效。"})
        serializer = PublicCitationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Even administrators get the public snapshot here; draft/editor permissions
        # never turn an anonymous local selection into a private-source export.
        reference = None
        if data.get("reference"):
            raw = json.loads(json.dumps(data["reference"], default=str))
            reference = research.resolve_reference(raw, AnonymousUser(), strict=True)
            if data.get("selected_text"):
                if reference.get("anchors"):
                    raise ValidationError({"selected_text": "跨页证据请按完整来源引用，或逐页选择文字。"})
                start, end = selection_range(reference["quote"], data["selected_text"])
                offset = reference.get("selection_start", 0)
                raw = {**research.compact_reference(reference), "selection_start": start + offset, "selection_end": end + offset}
                reference = research.resolve_reference(raw, AnonymousUser(), strict=True)
            edition_id = reference.get("edition_id")
            if data.get("edition_id") and str(data["edition_id"]) != edition_id:
                raise ValidationError({"edition_id": "所选原文与出版版本不一致。"})
        else:
            if data.get("selected_text"):
                raise ValidationError({"reference": "选文必须有可复核的原文身份。"})
            edition_id = data.get("edition_id")
        if not edition_id:
            raise ValidationError({"edition_id": "请指定出版版本或原文来源。"})
        edition = get_object_or_404(Edition.objects.select_related("work", "active_catalog_revision").filter(public_edition_q()), pk=edition_id)
        if reference and (str(edition.active_catalog_revision.reader_asset_id) != reference.get("asset_id")
                or str(edition.active_catalog_revision.document_revision_id) != reference.get("document_revision_id")):
            raise ValidationError({"reference": "公开来源刚刚更新，请从新版本重新选择。"})
        snapshot = active_catalog_snapshot(edition)
        work = snapshot.get("work") or {}
        edition_values = snapshot.get("edition") or {}
        printed = reference.get("printed_label") or "" if reference else ""
        page = reference.get("pdf_page") if reference else None
        label = printed or (str(page) if page else "")
        source = {"edition_id": str(edition.id), "work_id": str(edition.work_id), "title": work.get("title") or "未题名",
            "authors": [str((row.get("person") or {}).get("preferred_name") or row.get("name") or "")
                for row in snapshot.get("contributions", []) if isinstance(row, dict) and row.get("role") == "author"],
            "publication_year": edition_values.get("publication_year"), "publisher": edition_values.get("publisher") or "",
            **snapshot_cover(edition), "work_url": f"/works/{edition_values.get('public_slug') or edition.id}",
            "reader_url": reference.get("reader_url") if reference else None,
            "pdf_page": page, "printed_label": printed, "source_status": "available"}
        response = Response({"source": source, "reference": reference, "citations": citation_bundle(edition, label, snapshot=snapshot)})
        response["Cache-Control"] = "no-store"
        return response
