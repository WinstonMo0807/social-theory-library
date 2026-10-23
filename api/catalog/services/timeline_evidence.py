"""Resolve timeline citations through existing Assets and reader eligibility."""
from django.db.models import BooleanField, Case, F, Q, Value, When
from rest_framework import serializers

from catalog.models import Asset, Page
from catalog.services.publication_eligibility import active_document_q


def validate_timeline_identity(*, work, subject_edition, start_year, end_year, date_precision, start_date=None, end_date=None):
    if date_precision in {"month", "day"}:
        if not start_date or start_year != start_date.year:
            raise ValueError("精确日期须填写起始日期，并与开始年份一致。")
        if end_date and (end_date < start_date or end_year != end_date.year):
            raise ValueError("结束日期不能早于起始日期，且应与结束年份一致。")
        if not end_date and end_year not in (None, start_year):
            raise ValueError("跨年日期须填写明确的结束日期。")
        if date_precision == "month" and (start_date.day != 1 or (end_date and end_date.day != 1)):
            raise ValueError("月份精度仅保存到月份，不记录推定日期。")
    elif start_date or end_date:
        raise ValueError("年份或约年不应携带未声明的精确日期。")
    if subject_edition and work and subject_edition.work_id != work.pk:
        raise ValueError("事件所属版本不属于所选作品；出处文献可以是另一作品，请分别选择。")
    if start_year is not None and end_year is not None and end_year < start_year:
        raise ValueError("结束年不能早于开始年。")
    if date_precision == "year" and (start_year is None or end_year not in (None, start_year)):
        raise ValueError("确切年份须填写开始年，结束年应留空或与开始年相同。")
    if date_precision == "approximate" and start_year is None and end_year is None:
        raise ValueError("约年须至少填写一个年份。")
    if date_precision == "range" and (start_year is None or end_year is None or start_year >= end_year):
        raise ValueError("时间区间须填写开始年和较晚的结束年。")


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
    # Two batched queries for assets and page text, including non-primary editions.
    # This is a read of saved eligibility, not a storage probe or OCR check.
    readable = active_document_q(asset_prefix="") & Q(
        edition__active_catalog_revision__document_revision__asset_id=F("pk"),
        edition__active_catalog_revision__document_revision__is_active=True,
        kind=Asset.Kind.NORMALIZED, status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        access_status__in=[Asset.AccessStatus.PUBLIC, Asset.AccessStatus.INHERIT, Asset.AccessStatus.REGISTERED],
        page_count__gt=0,
    ) & ~Q(file="")
    assets = {str(asset.pk): asset for asset in Asset.objects.filter(pk__in=identifiers)
              .select_related("edition__work", "edition__active_catalog_revision__document_revision")
              .annotate(timeline_readable=Case(When(readable, then=Value(True)), default=Value(False), output_field=BooleanField()))}
    pages = {}
    for asset_id, index, text in Page.objects.filter(
        asset_id__in=identifiers, index__in={row.evidence_page for row in events if row.evidence_page},
    ).values_list("asset_id", "index", "text"):
        pages.setdefault(str(asset_id), {})[index] = text or ""
    for identifier, asset in assets.items():
        asset.timeline_pages = pages.get(identifier, {})
    # Keep negative lookups as well, so a missing file is not queried repeatedly.
    return {str(identifier): assets.get(str(identifier)) for identifier in identifiers}


class TimelineEvidenceListSerializer(serializers.ListSerializer):
    def to_representation(self, data):
        rows = list(data.all() if hasattr(data, "all") else data)
        files = self.context.setdefault("timeline_files", {})
        for identifier, asset in timeline_files(rows).items():
            previous = files.get(identifier)
            if asset and previous:
                asset.timeline_pages = {**previous.timeline_pages, **asset.timeline_pages}
            files[identifier] = asset
        return super().to_representation(rows)


def timeline_file(event, context):
    files = context.get("timeline_files")
    if files is None:
        files = timeline_files([event])
        context["timeline_files"] = files
    elif event.evidence_asset_id and str(event.evidence_asset_id) not in files:
        files.update(timeline_files([event]))
    return files.get(str(event.evidence_asset_id))


def timeline_reader_href(event, context):
    asset = timeline_file(event, context)
    if asset and asset.timeline_readable and event.evidence_page in asset.timeline_pages:
        quote = event.evidence_text or ""
        if quote and (not quote.strip() or quote not in asset.timeline_pages[event.evidence_page]):
            # A saved excerpt is not proof that today's OCR revision contains it.
            return None
        from catalog.services.semantic_search import viewer_access_statuses
        user = getattr(context.get("request"), "user", None)
        authenticated = bool(user and getattr(user, "is_authenticated", False))
        statuses = viewer_access_statuses(
            authenticated=authenticated,
            staff=authenticated and (getattr(user, "is_staff", False) or getattr(user, "role", "") in {"admin", "editor", "reviewer"}),
        )
        if asset.access_status in statuses and 1 <= event.evidence_page <= asset.page_count:
            return f"/reader/{asset.pk}?page={event.evidence_page}&revision={asset.edition.active_catalog_revision.document_revision_id}"
    return None


def admin_timeline_file(event, context):
    asset = timeline_file(event, context)
    if asset is None:
        return None
    href = timeline_reader_href(event, context)
    if href:
        detail = "读者可按此页序打开出处。" if asset.access_status != "registered" else "读者登录后可按此页序打开出处。"
    else:
        detail = "文件引用仍保留，但目前不能作为公开阅读链接。请核对文件验证、访问权限和该出版版本的当前阅读文件；不会自动改指新文件。"
    return {"id": str(asset.pk), "work_id": str(asset.edition.work_id), "work_title": asset.edition.work.title,
            "edition_id": str(asset.edition_id), "edition_label": asset.edition.version_label or str(asset.edition.publication_year or "出版信息待补"),
            "filename": asset.original_filename, "version": asset.version, "page_count": asset.page_count,
            "reader_href": href, "detail": detail}
