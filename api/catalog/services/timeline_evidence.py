"""Resolve timeline citations through existing Assets and reader eligibility."""
from django.db.models import BooleanField, Case, Q, Value, When
from rest_framework import serializers

from catalog.models import Asset
from catalog.services.publication_eligibility import active_asset_q


def validate_timeline_file(asset, page):
    if asset is None:
        return  # A textual/printed citation does not require a library PDF.
    if asset.kind != Asset.Kind.NORMALIZED:
        raise ValueError("请选择阅读文件；原始文件和 OCR 派生文件不能作为阅读跳转的地址。")
    if asset.status != Asset.Status.READY or asset.validation_status != Asset.ValidationStatus.VALID:
        raise ValueError("这份阅读文件尚未通过验证。请处理文件问题，或移除文件引用后保留文字来源。")
    if page is None or isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= asset.page_count:
        raise ValueError(f"请填写有效的 PDF 页序，范围为 1 至 {asset.page_count}。印刷页码请填在另一栏。")


def timeline_files(events):
    identifiers = {row.evidence_asset_id for row in events if row.evidence_asset_id}
    # One query for a complete serializer page, including non-primary editions.
    # This is a read of saved eligibility, not a storage probe or OCR check.
    readable = active_asset_q(asset_prefix="") & Q(
        kind=Asset.Kind.NORMALIZED, status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        access_status__in=[Asset.AccessStatus.PUBLIC, Asset.AccessStatus.INHERIT, Asset.AccessStatus.REGISTERED],
        page_count__gt=0,
    ) & ~Q(file="")
    return {str(asset.pk): asset for asset in Asset.objects.filter(pk__in=identifiers)
            .select_related("edition__work")
            .annotate(timeline_readable=Case(When(readable, then=Value(True)), default=Value(False), output_field=BooleanField()))}


class TimelineEvidenceListSerializer(serializers.ListSerializer):
    def to_representation(self, data):
        rows = list(data.all() if hasattr(data, "all") else data)
        self.context["timeline_files"] = timeline_files(rows)
        return super().to_representation(rows)


def timeline_file(event, context):
    files = context.get("timeline_files")
    if files is None:
        files = timeline_files([event])
    return files.get(str(event.evidence_asset_id))


def timeline_reader_href(event, context):
    asset = timeline_file(event, context)
    if asset and asset.timeline_readable and event.evidence_page and 1 <= event.evidence_page <= asset.page_count:
        return f"/reader/{asset.pk}?page={event.evidence_page}"
    return None


def admin_timeline_file(event, context):
    asset = timeline_file(event, context)
    if asset is None:
        return None
    href = f"/reader/{asset.pk}?page={event.evidence_page}" if asset.timeline_readable and event.evidence_page and 1 <= event.evidence_page <= asset.page_count else None
    if href:
        detail = "读者可按此页序打开出处。" if asset.access_status != "registered" else "读者登录后可按此页序打开出处。"
    else:
        detail = "文件引用仍保留，但目前不能作为公开阅读链接。请核对文件验证、访问权限和该出版版本的当前阅读文件；不会自动改指新文件。"
    return {"id": str(asset.pk), "work_id": str(asset.edition.work_id), "work_title": asset.edition.work.title,
            "edition_id": str(asset.edition_id), "edition_label": asset.edition.version_label or str(asset.edition.publication_year or "出版信息待补"),
            "filename": asset.original_filename, "version": asset.version, "page_count": asset.page_count,
            "reader_href": href, "detail": detail}
