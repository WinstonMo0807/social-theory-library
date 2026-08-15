from contextlib import contextmanager
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
import re
import tempfile

import fitz
from PIL import Image, ImageStat
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify

from catalog.models import Asset, CoverCandidate, DocumentType, Work


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

    pixmap = page.get_pixmap(matrix=fitz.Matrix(0.55, 0.55), alpha=False)
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
def select_cover_candidate(candidate: CoverCandidate, *, automatic: bool = False):
    candidate = (
        CoverCandidate.objects.select_for_update()
        .select_related("work", "asset")
        .get(pk=candidate.pk)
    )
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
    CoverCandidate.objects.filter(work=candidate.work).exclude(pk=candidate.pk).update(
        selected=False
    )
    candidate.selected = True
    candidate.save(update_fields=["selected", "updated_at"])
    filename = f"{slugify(candidate.work.title)[:100] or candidate.work_id}-cover.jpg"
    candidate.work.cover.save(filename, ContentFile(content), save=False)
    candidate.work.save(update_fields=["cover", "updated_at"])
    return {
        "candidate": candidate,
        "automatic": automatic,
    }


def generate_cover_candidates(asset: Asset, *, force: bool = False):
    asset = Asset.objects.select_related("edition__work").get(pk=asset.pk)
    work = asset.edition.work
    if work.document_type != DocumentType.BOOK:
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
        finally:
            document.close()
    ranked.sort(key=lambda item: (-item[1]["score"], item[0]))
    retained_pages = {page_index for page_index, _metrics in ranked[:4]}

    for candidate in existing:
        if candidate.page_index not in retained_pages:
            candidate.thumbnail.delete(save=False)
            candidate.delete()

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
                "selected": False,
            },
        )
        if candidate.thumbnail:
            candidate.thumbnail.delete(save=False)
        candidate.thumbnail.save(
            f"page-{page_index}.jpg",
            ContentFile(metrics["thumbnail"]),
            save=True,
        )
        candidates.append(candidate)

    preferred = next(
        (
            candidate
            for candidate in candidates
            if candidate.page_index == previous_selected_page
        ),
        None,
    )
    if preferred is not None:
        select_cover_candidate(preferred)
    elif not work.cover and candidates and candidates[0].score >= settings.COVER_AUTO_SELECT_THRESHOLD:
        select_cover_candidate(candidates[0], automatic=True)
    return list(asset.cover_candidates.order_by("-score", "page_index"))


def generate_recommendation_image(asset: Asset, *, force: bool = False):
    """Create a stable visual card for non-book documents.

    Books keep using the selected cover. Articles, theses and reports use the
    first non-blank page among the first six pages. This runs during ingestion,
    so public recommendation requests never render PDF pages on demand.
    """
    asset = Asset.objects.select_related("edition__work").get(pk=asset.pk)
    work = asset.edition.work
    if work.document_type == DocumentType.BOOK:
        return work.cover
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
            pixmap = selected_page.get_pixmap(matrix=fitz.Matrix(0.55, 0.55), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            output = BytesIO()
            image.save(output, format="JPEG", quality=86, optimize=True)
        finally:
            document.close()
    filename = f"{slugify(work.title)[:100] or work.id}-document.jpg"
    work.recommendation_image.save(filename, ContentFile(output.getvalue()), save=False)
    work.save(update_fields=["recommendation_image", "updated_at"])
    return work.recommendation_image
