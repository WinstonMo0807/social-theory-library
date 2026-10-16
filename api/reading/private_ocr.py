"""Private in-memory inputs to the existing local OCR gateway; no catalog writes."""
from copy import deepcopy
import hashlib
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from zipfile import ZipFile

import fitz
import httpx
from django.conf import settings

from ingestion.services.ocr_provider import _request_document_gateway
from .local_analysis import AIServiceError, AIServiceUnavailable, PrivateLocalTransport

MAX_UNITS = 1000
UNITS_PER_ATTEMPT = 4
MAX_IMAGE_PIXELS = 40_000_000
MAX_UNIT_CHARS = 100_000
MAX_TOTAL_CHARS = 1_000_000


def _local_gateway():
    base = str(getattr(settings, "PADDLEOCR_SERVICE_URL", "") or "").strip()
    parsed = urlsplit(base)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in {"", "/", "/v1/parse-pdf"}):
        raise AIServiceUnavailable("私人扫描稿件的本地 OCR 地址未配置或无效。")
    allowed = getattr(settings, "PRIVATE_OCR_ALLOWED_HOSTS", ("localhost", "127.0.0.1", "::1", "paddleocr",
        "paddleocr-service", "paddleocr-nas", "ocr", "host.docker.internal"))
    return base, allowed


def _units(paragraphs, kind):
    units = []
    for index, paragraph in enumerate(paragraphs):
        if kind == "pdf" and paragraph.get("needs_ocr"):
            units.append({"id": f"pdf:{paragraph['location']['pdf_page']}", "paragraph_index": index,
                "pdf_page": paragraph["location"]["pdf_page"], "location": paragraph["location"]})
        if kind == "docx":
            for image_index, image in enumerate(paragraph.get("embedded_images", [])):
                identity = "|".join(str(value) for value in (paragraph["location"]["part"], image["xml_node"], image["sha256"]))
                units.append({**image, "id": "image:" + hashlib.sha256(identity.encode()).hexdigest(),
                    "paragraph_index": index, "image_index": image_index,
                    "location": {**paragraph["location"], "xml_node": image["xml_node"],
                        "media_path": image["media_path"], "image_index": image_index, "pdf_page": None}})
    if len(units) > MAX_UNITS:
        raise ValueError("私人 OCR 页或图像数超过上限。")
    return units


def _image_pdf(blob, unit):
    from PIL import Image
    with ZipFile(BytesIO(blob)) as archive:
        content = archive.read(unit["media_path"])
    if hashlib.sha256(content).hexdigest() != unit["sha256"]:
        raise ValueError("嵌入图像与原稿修订不符。")
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("嵌入图像超过像素上限。")
    except Image.DecompressionBombError as exc:
        raise ValueError("嵌入图像超过像素上限。") from exc
    extension = PurePosixPath(unit["media_path"]).suffix.lower().lstrip(".")
    if extension not in {"png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"}:
        raise ValueError("本地 OCR 暂不支持此嵌入图像格式。")
    with fitz.open(stream=content, filetype=extension) as image_document:
        return image_document.convert_to_pdf()


def enrich_private_manuscript(*, blob, kind, paragraphs, cache, generation, checkpoint, is_current):
    """Return derived paragraphs, safe warnings and whether another task is needed.

    Completed units survive cancellation; failed units are tried again only in a
    new owner-requested generation. The caller encrypts every checkpoint.
    """
    units = _units(paragraphs, kind)
    pending = [unit for unit in units if unit["id"] not in cache or (
        cache[unit["id"]].get("status") in {"failed", "no_text"} and cache[unit["id"]].get("generation") != generation)]
    gateway_error = False
    gateway = None
    if pending:
        try:
            gateway = _local_gateway()
        except (AIServiceError, ValueError):
            gateway_error = True
    if gateway_error:
        if not is_current():
            return None
        for unit in pending:
            cache[unit["id"]] = {"generation": generation, "location": unit["location"], "provider": "paddleocr_local",
                "status": "failed", "error_code": "private_ocr_unavailable", "text": "", "blocks": []}
        if not checkpoint(cache, len(units), len(units)):
            return None
    for unit in ([] if gateway_error else pending[:UNITS_PER_ATTEMPT]):
        if not is_current():
            return None
        result = {"generation": generation, "location": unit["location"], "provider": "paddleocr_local",
                  "status": "failed", "error_code": "private_ocr_unavailable", "text": "", "blocks": []}
        try:
            content = _image_pdf(blob, unit) if kind == "docx" else blob
            page_number = 1 if kind == "docx" else unit["pdf_page"]
            with PrivateLocalTransport(gateway[0], allowed_hosts=gateway[1]) as transport:
                payload = _request_document_gateway(None, base_url=gateway[0], pdf_bytes=content,
                    page_numbers=[page_number], transport=transport,
                    timeout_seconds=min(120, max(5, int(getattr(settings, "PRIVATE_OCR_REQUEST_TIMEOUT_SECONDS", 90)))))
            pages = payload.get("pages", []) if isinstance(payload, dict) else []
            if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], dict) or pages[0].get("index") != page_number:
                raise ValueError("本地 OCR 未返回请求的单页。")
            page = pages[0]
            from catalog.services.page_geometry import locator_geometry, ocr_geometry
            geometry = {}
            if page.get("geometry"):
                with fitz.open(stream=content, filetype="pdf") as source_document:
                    geometry = ocr_geometry(page, source_document[page_number - 1])
            if not isinstance(page.get("blocks", []), list) or len(page.get("blocks", [])) > 5000:
                raise ValueError("本地 OCR 返回的文本块无效或超限。")
            blocks = [{"text": str(block.get("text", "")), "bbox": block.get("bbox", []),
                       "confidence": block.get("confidence"), "type": block.get("type", "paragraph"),
                       **locator_geometry(block.get("bbox", []), geometry)}
                      for block in page.get("blocks", []) if isinstance(block, dict) and str(block.get("text", "")).strip()]
            text_value = "\n".join(block["text"] for block in blocks)
            if len(text_value) > MAX_UNIT_CHARS or len(blocks) > 5000:
                raise ValueError("本地 OCR 响应超过本页上限。")
            if len(text_value) + sum(len(row.get("text", "")) for key, row in cache.items() if key != unit["id"]) > MAX_TOTAL_CHARS:
                result["error_code"] = "private_ocr_text_limit"
                raise ValueError("本地 OCR 文字总量超过上限。")
            result.update(status="completed" if text_value.strip() else "no_text", error_code="", text=text_value,
                blocks=blocks, width=page.get("width"), height=page.get("height"), geometry=geometry,
                coordinate_space={"unit": "ocr_page_coordinates", "width": page.get("width"), "height": page.get("height"),
                    "requires_reader_transform": True}, image_sha256=unit.get("sha256"),
                source_hash=hashlib.sha256(content).hexdigest(), quality_status="ocr_unverified")
        except (AIServiceError, httpx.HTTPError, ValueError, RuntimeError, KeyError, OSError):
            # Never expose service URLs, source text or parser exceptions.
            pass
        cache[unit["id"]] = result
        if not checkpoint(cache, sum(key in cache for key in [row["id"] for row in units]), len(units)):
            return None
    remaining = any(unit["id"] not in cache or (cache[unit["id"]].get("status") in {"failed", "no_text"}
        and cache[unit["id"]].get("generation") != generation) for unit in units)
    by_paragraph = {}
    warnings = []
    for unit in units:
        result = cache.get(unit["id"])
        if not result:
            continue
        if result["status"] == "failed":
            warnings.append({"code": result["error_code"], "unit_id": unit["id"],
                "message": "此扫描页或嵌入图像尚未完成本地 OCR；已保留原稿和完成的页，可重试。"})
        if result["status"] == "no_text":
            warnings.append({"code": "private_ocr_no_text", "unit_id": unit["id"],
                "message": "此页或图像未识别出文字，不能据此确认没有引文；请对照原稿。"})
        if result["status"] == "completed":
            by_paragraph.setdefault(unit["paragraph_index"], []).append((unit, result))
    output = []
    for index, original in enumerate(paragraphs):
        paragraph = deepcopy(original)
        found = by_paragraph.get(index, [])
        if kind == "pdf" and found:
            unit, result = found[0]
            paragraph.update(text=result["text"], ocr_text=result["text"])
            paragraph["location"] = {**paragraph["location"], "text_source": "ocr", "ocr_unit_id": unit["id"]}
        output.append(paragraph)
        if kind == "docx":
            for unit, result in found:
                output.append({"text": result["text"], "fields": [], "note_refs": [], "embedded_images": [],
                    "location": {**unit["location"], "text_source": "ocr", "ocr_unit_id": unit["id"]}})
    return output, warnings, remaining
