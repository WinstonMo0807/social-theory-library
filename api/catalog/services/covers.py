from contextlib import contextmanager
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
import re
import tempfile
from uuid import uuid4

import fitz
from PIL import Image, ImageStat
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify

from catalog.models import Asset, CatalogFieldDecision, CoverCandidate, DocumentType, Edition, PublicationState, Work


class CoverCandidateUnavailable(RuntimeError):
    pass


@contextmanager
def _local_asset_path(asset: Asset):
    try:
        yield Path(asset.file.path)
        return
    except (AttributeError, NotImplementedError):
        pass
    suffix = Path(asset.file.name).suffix or ".pdf"
    temporary = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    temporary_path = Path(temporary.name)
    try:
        with temporary, asset.file.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                temporary.write(chunk)
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)


def _fold(value: str) -> str:
    return re.sub(r"[\W_]+", "", (value or "").casefold(), flags=re.UNICODE)


def _page_metrics(page, page_index: int, work: Work, author_names: list[str], max_pages: int):
    text = page.get_text("text", sort=True).strip()
    folded_text = _fold(text[:4000])
    folded_title = _fold(work.title)
    title_similarity = (
        1.0
        if folded_title and folded_title in folded_text
        else SequenceMatcher(None, folded_title[:160], folded_text[:600]).ratio()
        if folded_title and folded_text
        else 0.0
    )
    author_hits = sum(
        1 for name in author_names if _fold(name) and _fold(name) in folded_text
    )
    author_score = min(author_hits / max(len(author_names), 1), 1.0)

    raw = page.get_text("dict", sort=True)
    spans = [
        span
        for block in raw.get("blocks", [])
        if block.get("type") == 0
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if str(span.get("text", "")).strip()
    ]
    font_sizes = [float(span.get("size", 0)) for span in spans]
    largest_font = max(font_sizes, default=0)
    median_font = sorted(font_sizes)[len(font_sizes) // 2] if font_sizes else 1
    title_prominence = min(largest_font / max(median_font * 2.4, 1), 1.0)

    page_area = max(float(page.rect.width * page.rect.height), 1)
    image_area = 0.0
    for image in page.get_image_info(xrefs=True):
        bbox = image.get("bbox") or ()
        if len(bbox) == 4:
            image_area += max(float(bbox[2]) - float(bbox[0]), 0) * max(
                float(bbox[3]) - float(bbox[1]),
                0,
            )
    image_coverage = min(image_area / page_area, 1.0)
    text_density = min(len(re.sub(r"\s+", "", text)) / 1500, 1.0)
    cover_density = max(0.0, 1.0 - abs(text_density - 0.2) / 0.8)

    penalty_terms = (
        "目录",
        "版权",
        "图书在版编目",
        "contents",
        "copyright",
        "bibliography",
        "references",
        "index",
    )
    penalty_hits = [term for term in penalty_terms if term in text.casefold()]
    content_penalty = min(len(penalty_hits) * 0.2, 0.55)
    position_score = max(0.0, 1.0 - (page_index - 1) / max(max_pages - 1, 1))

    zoom = min(0.8, 640 / max(page.rect.width, page.rect.height, 1))
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, annots=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    small_gray = image.resize((64, 64)).convert("L")
    gray_variance = min(float(ImageStat.Stat(small_gray).var[0]) / 2800, 1.0)

    score = (
        title_similarity * 0.34
        + author_score * 0.08
        + title_prominence * 0.13
        + image_coverage * 0.15
        + cover_density * 0.09
        + position_score * 0.14
        + gray_variance * 0.07
        - content_penalty
    )
    score = round(max(0.0, min(score, 1.0)), 4)
    reasons = []
    if title_similarity >= 0.72:
        reasons.append("题名与馆藏元数据高度一致")
    elif title_similarity >= 0.4:
        reasons.append("页面文字与题名部分一致")
    if author_score:
        reasons.append("识别到作者姓名")
    if title_prominence >= 0.65:
        reasons.append("页面存在明显的大字号标题")
    if image_coverage >= 0.25:
        reasons.append("页面具有较高图像覆盖率")
    if position_score >= 0.72:
        reasons.append("位于文档前部")
    if penalty_hits:
        reasons.append(f"检测到非封面提示词：{'、'.join(penalty_hits[:3])}")
    if not reasons:
        reasons.append("根据页面位置、文字密度与版式综合排序")

    output = BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    return {
        "score": score,
        "reasons": reasons,
        "metrics": {
            "title_similarity": round(title_similarity, 4),
            "author_score": round(author_score, 4),
            "title_prominence": round(title_prominence, 4),
            "image_coverage": round(image_coverage, 4),
            "text_density": round(text_density, 4),
            "position_score": round(position_score, 4),
            "visual_variance": round(gray_variance, 4),
            "penalty_terms": penalty_hits,
        },
        "thumbnail": output.getvalue(),
    }


@transaction.atomic
def select_cover_candidate(candidate: CoverCandidate, *, automatic: bool = False, actor=None, edition_id=None):
    candidate = CoverCandidate.objects.select_related("asset").get(pk=candidate.pk)
    edition = Edition.objects.select_for_update().get(pk=candidate.asset.edition_id)
    if edition_id and str(edition.pk) != str(edition_id):
        raise CoverCandidateUnavailable("该封面不属于当前版本，请查找本版本封面。")
    if edition.work_id != candidate.work_id:
        raise CoverCandidateUnavailable("该封面对应的作品已变化，请重新查找。")
    work = Work.objects.select_for_update().get(pk=edition.work_id)
    edition.work = work
    candidate = CoverCandidate.objects.select_for_update(of=("self",)).select_related("asset").get(pk=candidate.pk)
    if candidate.asset.edition_id != edition.pk or candidate.work_id != work.pk:
        raise CoverCandidateUnavailable("封面对应的版本已变化，请重新进入当前作品。")
    requires_revision = work.editions.filter(state=PublicationState.PUBLISHED).exists()
    from ingestion.models import FieldLock
    if automatic and FieldLock.objects.filter(edition__work=work, field_name="cover").exists():
        return {"candidate": candidate, "automatic": True, "saved": False}
    if automatic and CatalogFieldDecision.objects.filter(
        edition__work=work, field_name="cover",
        status__in={CatalogFieldDecision.Status.CONFIRMED, CatalogFieldDecision.Status.NOT_APPLICABLE},
    ).exists():
        return {"candidate": candidate, "automatic": True, "saved": False}
    if requires_revision and (automatic or actor is None):
        # Background discovery may prepare alternatives, never change an
        # already published holding or create a human-confirmed revision.
        return {"candidate": candidate, "automatic": automatic, "saved": False}
    thumbnail_name = candidate.thumbnail.name
    if (
        not thumbnail_name
        or not candidate.thumbnail.storage.exists(thumbnail_name)
    ):
        raise CoverCandidateUnavailable(
            "封面候选文件已不存在，请点击“重新分析”后再选择。"
        )
    try:
        candidate.thumbnail.open("rb")
        try:
            content = candidate.thumbnail.read()
        finally:
            candidate.thumbnail.close()
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise CoverCandidateUnavailable(
            "封面候选文件暂时不可用，请点击“重新分析”后再选择。"
        ) from exc
    CoverCandidate.objects.filter(work=work).exclude(pk=candidate.pk).update(
        selected=False
    )
    candidate.selected = True
    candidate.save(update_fields=["selected", "updated_at"])
    revision = None
    if requires_revision:
        from catalog.services.editorial_revision import save_workflow_editorial_revision

        name = f"public/covers/editorial/{work.pk}/{uuid4().hex}.jpg"
        stored_name = work.cover.storage.save(name, ContentFile(content))
        revision = save_workflow_editorial_revision(
            work_id=work.pk, edition_id=edition.pk, section_patch={"cover": stored_name, "cover_rendition": None}, actor=actor,
            change_note="确认本版本封面，等待发布编辑草稿",
        )
        value = stored_name
    else:
        filename = f"{slugify(work.title)[:100] or work.pk}-{uuid4().hex}-cover.jpg"
        work.cover.save(filename, ContentFile(content), save=False)
        work.cover_rendition = None
        work.save(update_fields=["cover_rendition", "cover", "updated_at"])
        value = work.cover.name
    from catalog.services.field_decisions import record_edition_field_decision

    provenance = {"source": "pdf_cover", "page": candidate.page_index, "asset_id": str(candidate.asset_id)}
    if revision:
        provenance.update(editorial_revision_id=str(revision.pk), canonical_write_deferred=True)
    record_edition_field_decision(
        edition, "cover", status=CatalogFieldDecision.Status.SUGGESTED if automatic else CatalogFieldDecision.Status.CONFIRMED,
        value=value, actor=actor,
        confirmation_method=CatalogFieldDecision.ConfirmationMethod.CANDIDATE,
        provenance=provenance, candidate_type="cover", candidate_id=candidate.pk,
        reason="从当前版本PDF选取封面",
    )
    return {
        "candidate": candidate,
        "automatic": automatic,
        "saved": True,
        "canonical_write_deferred": revision is not None,
        "editorial_revision_id": str(revision.pk) if revision else None,
    }


def generate_cover_candidates(asset: Asset, *, force: bool = False, auto_select: bool = True, include_non_book: bool = False):
    asset = Asset.objects.select_related("edition__work").get(pk=asset.pk)
    work = asset.edition.work
    if not include_non_book and work.document_type not in {DocumentType.BOOK, DocumentType.JOURNAL_ISSUE}:
        return []
    existing = list(asset.cover_candidates.order_by("-score", "page_index"))
    if existing and not force:
        return existing

    previous_selected_page = next(
        (candidate.page_index for candidate in existing if candidate.selected),
        None,
    )
    max_pages = min(
        asset.page_count or settings.COVER_SCAN_MAX_PAGES,
        settings.COVER_SCAN_MAX_PAGES,
    )
    author_names = list(
        asset.edition.contributions.filter(role="author", approved=True)
        .order_by("order")
        .values_list("person__preferred_name", flat=True)
    )
    ranked = []
    with _local_asset_path(asset) as path:
        document = fitz.open(str(path))
        try:
            for page_index in range(1, min(document.page_count, max_pages) + 1):
                metrics = _page_metrics(
                    document[page_index - 1],
                    page_index,
                    work,
                    author_names,
                    max_pages,
                )
                ranked.append((page_index, metrics))
                metrics["metrics"]["pdf_page_count"] = document.page_count
        finally:
            document.close()
    ranked.sort(key=lambda item: (-item[1]["score"], item[0]))
    # Keep manually chosen pages and prior evidence. A refresh only replaces
    # the current ranking; it must not delete an administrator's selection.
    candidates = []
    for page_index, metrics in ranked[:4]:
        candidate, _created = CoverCandidate.objects.update_or_create(
            asset=asset,
            page_index=page_index,
            defaults={
                "work": work,
                "score": metrics["score"],
                "reasons": metrics["reasons"],
                "metrics": metrics["metrics"],
            },
        )
        candidate.thumbnail.save(
            f"page-{page_index}.jpg",
            ContentFile(metrics["thumbnail"]),
            save=False,
        )
        candidate.save(update_fields=["thumbnail", "updated_at"])
        candidates.append(candidate)

    preferred = next(
        (
            candidate
            for candidate in candidates
            if candidate.page_index == previous_selected_page
        ),
        None,
    )
    if auto_select and preferred is not None and not work.cover:
        select_cover_candidate(preferred, automatic=True)
    elif auto_select and not work.cover and candidates and candidates[0].score >= settings.COVER_AUTO_SELECT_THRESHOLD:
        select_cover_candidate(candidates[0], automatic=True)
    return list(asset.cover_candidates.order_by("-score", "page_index"))


def prepare_cover_page(asset: Asset, page_index: int):
    """Render one explicitly requested PDF page; never write Page or the PDF."""
    with _local_asset_path(asset) as path, fitz.open(str(path)) as document:
        if page_index < 1 or page_index > document.page_count:
            raise CoverCandidateUnavailable(f"页码须在 1—{document.page_count} 之间，按PDF实际页序填写。")
        page = document[page_index - 1]
        scale = min(2, 1400 / max(page.rect.width, page.rect.height, 1))
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, annots=False)
        candidate, _ = CoverCandidate.objects.get_or_create(
            asset=asset, page_index=page_index,
            defaults={"work_id": asset.edition.work_id, "reasons": ["管理员按PDF实际页序选择"], "metrics": {"manual_page": True, "pdf_page_count": document.page_count}},
        )
        if candidate.work_id != asset.edition.work_id:
            raise CoverCandidateUnavailable("这份PDF对应的作品已变化，请重新进入当前作品。")
        candidate.thumbnail.save(f"page-{page_index}-{uuid4().hex}.jpg", ContentFile(pixmap.tobytes("jpeg", jpg_quality=90)), save=False)
        candidate.save(update_fields=["thumbnail", "updated_at"])
        return candidate


def generate_recommendation_image(asset: Asset, *, force: bool = False, actor=None, automatic: bool = True, expected_work_id=None):
    """Create a stable visual card for non-book documents.

    Books keep using the selected cover. Articles, theses and reports use the
    first non-blank page among the first six pages. This runs during ingestion,
    so public recommendation requests never render PDF pages on demand.
    """
    asset = Asset.objects.select_related("edition__work").get(pk=asset.pk)
    work = asset.edition.work
    if expected_work_id is not None and str(work.pk) != str(expected_work_id):
        raise CoverCandidateUnavailable("版本对应的作品已变化，请重新进入编目工作台。")
    if automatic and work.document_type in {DocumentType.BOOK, DocumentType.JOURNAL_ISSUE}:
        return work.cover
    if automatic and work.editions.filter(state=PublicationState.PUBLISHED).exists():
        # Background file processing cannot replace a published editorial image.
        return work.recommendation_image
    image_name = work.recommendation_image.name
    if (
        image_name
        and work.recommendation_image.storage.exists(image_name)
        and not force
    ):
        return work.recommendation_image

    with _local_asset_path(asset) as path:
        document = fitz.open(str(path))
        try:
            if document.page_count < 1:
                raise CoverCandidateUnavailable("PDF 没有可生成推荐图例的页面。")
            selected_page = document[0]
            for page_index in range(min(document.page_count, 6)):
                page = document[page_index]
                text = re.sub(r"\s+", "", page.get_text("text", sort=True))
                if len(text) >= 30 or page.get_images(full=True):
                    selected_page = page
                    break
            selected_page_number = selected_page.number + 1
            pixmap = selected_page.get_pixmap(matrix=fitz.Matrix(0.55, 0.55), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            output = BytesIO()
            image.save(output, format="JPEG", quality=86, optimize=True)
        finally:
            document.close()
    from django.core.files.uploadedfile import InMemoryUploadedFile
    from catalog.services.media import ingest_image, select_work_image

    content = output.getvalue()
    uploaded = InMemoryUploadedFile(BytesIO(content), "image", f"pdf-{asset.pk}.jpg", "image/jpeg", len(content), None)
    media, _ = ingest_image(uploaded, actor=actor, metadata={
        "source_type": "pdf", "source_label": f"PDF 第 {selected_page_number} 页",
        "alt_text": f"{work.title}推荐图例",
    })
    select_work_image(asset.edition_id, media.pk, slot="recommendation", actor=actor, automatic=automatic, expected_work_id=expected_work_id or work.pk)
    work.refresh_from_db()
    return work.recommendation_image
