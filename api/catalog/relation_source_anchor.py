"""Pinned relation evidence over the existing EvidenceSpan and DocumentRevision."""
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from catalog.services.shared_curation import sources
from catalog.services.publication_eligibility import current_retrieval_source_q
from catalog.services.text import page_text_range


class RelationAnchorInput(serializers.Serializer):
    span_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField()

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) != set(self.fields):
            raise ValidationError("只能选择原文编号和准确文档版本，不能传入改写的引文或页码。")
        return super().to_internal_value(data)


class RelationAnchorMaterial(serializers.Serializer):
    available = serializers.BooleanField()
    public_eligible = serializers.BooleanField()
    detail = serializers.CharField(allow_blank=True)
    title = serializers.CharField(allow_blank=True)
    edition_label = serializers.CharField(allow_blank=True)
    work_id = serializers.UUIDField(allow_null=True)
    edition_id = serializers.UUIDField(allow_null=True)
    asset_id = serializers.UUIDField(allow_null=True)
    document_revision_id = serializers.UUIDField(allow_null=True)
    pdf_page = serializers.IntegerField(allow_null=True)
    printed_page_label = serializers.CharField(allow_blank=True)
    quote = serializers.CharField(allow_blank=True)
    reader_href = serializers.CharField(allow_blank=True)


def public_anchor_rows():
    # Only anonymous-readable, activated files can supply public relation text.
    return sources("span", public=True).filter(current_retrieval_source_q(asset_prefix="page__asset", access_statuses=("public", "inherit")),
        document_revision_id=F("page__asset__edition__active_catalog_revision__document_revision_id"))


def valid_locator(span, pinned_revision):
    return bool(span and str(span.document_revision_id) == str(pinned_revision) and not span.is_stale
        and span.document_revision.asset_id == span.page.asset_id and span.page_number == span.page.index
        and span.page.index >= 1 and (not span.page.asset.page_count or span.page.index <= span.page.asset.page_count)
        and span.original_text.strip() and page_text_range(span.page.text or "", span.original_text, span.start_offset, span.end_offset))


def choose_anchor(reference):
    if reference is None:
        return None, None
    span = get_object_or_404(sources("span").select_for_update(of=("self",)), pk=reference["span_id"])
    if not valid_locator(span, reference["document_revision_id"]):
        raise ValidationError("原文与文档版本、页面或文字位置已不一致，请重新核对原材料；不会自动换用其他版本。")
    return span, span.document_revision


def anchor_material(span, pinned_revision, *, public=False, eligible=None):
    empty = {"available": False, "public_eligible": False, "detail": "原文位置或版本已经失效，原引用编号仍保留，请重新核对。",
        "title": "", "edition_label": "", "work_id": None, "edition_id": None, "asset_id": None,
        "document_revision_id": None, "pdf_page": None, "printed_page_label": "", "quote": "", "reader_href": ""}
    if not valid_locator(span, pinned_revision):
        return None if public else empty
    if eligible is None:
        eligible = public_anchor_rows().filter(pk=span.pk).exists()
    if public and not eligible:
        return None
    page, asset = span.page, span.page.asset
    edition = asset.edition
    snapshot = edition.active_catalog_revision.snapshot if eligible else {}
    work, version = (snapshot or {}).get("work") or {}, (snapshot or {}).get("edition") or {}
    return {"available": True, "public_eligible": eligible,
        "detail": "" if eligible else "准确原文尚未公开，只保留为待核对来源，不能确认公开关系。",
        "title": str(work.get("title") or "") if eligible else edition.work.title,
        "edition_label": str(version.get("version_label") or "") if eligible else edition.version_label,
        "work_id": str(edition.work_id), "edition_id": str(edition.pk), "asset_id": str(asset.pk),
        "document_revision_id": str(span.document_revision_id), "pdf_page": page.index,
        "printed_page_label": span.printed_page_label or page.printed_label, "quote": span.original_text,
        "reader_href": f"/reader/{asset.pk}?page={page.index}&passage={span.pk}&revision={span.document_revision_id}" if eligible else ""}
