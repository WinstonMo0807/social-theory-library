from pathlib import Path
from contextlib import ExitStack
from io import BytesIO

import fitz
import httpx
from django.conf import settings

from catalog.models import SiteSetting


OCR_RUNTIME_KEY = "ocr_runtime"
OCR_MODES = {"nas_preferred", "nas_only", "remote_only"}


class OCRConfigurationError(RuntimeError):
    pass


class OCRServiceUnavailable(RuntimeError):
    pass


def ocr_runtime_config():
    stored = SiteSetting.objects.filter(key=OCR_RUNTIME_KEY).first()
    value = stored.value if stored and isinstance(stored.value, dict) else {}
    mode = str(value.get("mode") or "nas_preferred")
    if mode not in OCR_MODES:
        mode = "nas_preferred"
    return {
        "mode": mode,
        "remote_url": str(value.get("remote_url") or settings.OCR_REMOTE_API_URL).strip(),
        "remote_model": str(value.get("remote_model") or settings.OCR_REMOTE_MODEL).strip(),
        "nas_url": settings.PADDLEOCR_SERVICE_URL.strip(),
        "remote_key_configured": bool(settings.OCR_REMOTE_API_KEY),
        "saved_configuration_version": (
            stored.updated_at.isoformat() if stored else "environment-default"
        ),
    }


def _parse_endpoint(base_url: str):
    cleaned = base_url.rstrip("/")
    return cleaned if cleaned.endswith("/v1/parse-pdf") else f"{cleaned}/v1/parse-pdf"


def _request_document_gateway(
    path: str | Path,
    *,
    base_url: str,
    model: str = "",
    api_key: str = "",
    page_numbers: list[int] | None = None,
):
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    data = {
        "languages": "ch,en,chinese_cht",
        "layout": "true",
    }
    if model:
        data["model"] = model
    page_map = {}
    with ExitStack() as stack:
        if page_numbers:
            # A page-level progress update must not upload a whole large PDF
            # for every page. The temporary request contains only this batch;
            # response indexes are mapped back to the immutable source file.
            selected = sorted(set(page_numbers))
            source = stack.enter_context(fitz.open(str(path)))
            subset = stack.enter_context(fitz.open())
            for index in selected:
                if index < 1 or index > source.page_count:
                    raise ValueError("OCR 请求包含无效 PDF 页序。")
                subset.insert_pdf(source, from_page=index - 1, to_page=index - 1)
            page_map = {index + 1: original for index, original in enumerate(selected)}
            data["page_numbers"] = ",".join(str(index) for index in page_map)
            handle = stack.enter_context(BytesIO(subset.tobytes(garbage=3, deflate=True)))
        else:
            handle = stack.enter_context(Path(path).open("rb"))
        response = httpx.post(
            _parse_endpoint(base_url),
            files={"file": (Path(path).name, handle, "application/pdf")},
            data=data,
            headers=headers,
            timeout=settings.OCR_REQUEST_TIMEOUT_SECONDS,
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("pages"), list):
        raise ValueError("OCR 服务返回了无法识别的数据格式。")
    if page_map:
        mapped = []
        for page in payload["pages"]:
            try:
                index = int(page["index"])
            except (TypeError, ValueError, KeyError):
                raise ValueError("OCR 服务返回了无法识别的页序。")
            if index not in page_map:
                raise ValueError("OCR 服务返回的页序不属于本次请求。")
            mapped.append({**page, "index": page_map[index]})
        payload = {**payload, "pages": mapped}
    return payload


def _parse_pdf(path: str | Path, *, page_numbers: list[int] | None = None):
    config = ocr_runtime_config()
    providers = []
    if config["mode"] in {"nas_preferred", "nas_only"}:
        providers.append(
            (
                "paddleocr_nas",
                config["nas_url"],
                "",
                "",
            )
        )
    if config["mode"] in {"nas_preferred", "remote_only"}:
        remote_complete = bool(
            config["remote_url"]
            and config["remote_model"]
            and config["remote_key_configured"]
        )
        providers.append(
            (
                "remote_ocr",
                config["remote_url"] if remote_complete else "",
                config["remote_model"],
                settings.OCR_REMOTE_API_KEY,
            )
        )

    failures = []
    configured = 0
    for provider, base_url, model, api_key in providers:
        if not base_url:
            failures.append(f"{provider} 未配置")
            continue
        configured += 1
        try:
            payload = _request_document_gateway(
                path,
                base_url=base_url,
                model=model,
                api_key=api_key,
                page_numbers=page_numbers,
            )
            return payload, provider
        except (httpx.HTTPError, ValueError) as exc:
            failures.append(f"{provider} 不可用：{exc.__class__.__name__}")
    if configured == 0:
        raise OCRConfigurationError("没有配置可用的 OCR 服务。")
    raise OCRServiceUnavailable("；".join(failures) or "OCR 服务当前不可用。")


def parse_pdf_with_ocr(path: str | Path):
    return _parse_pdf(path)


def parse_pdf_pages_with_ocr(path: str | Path, page_numbers: list[int]):
    if not page_numbers:
        return {"pages": []}, "not_required"
    return _parse_pdf(path, page_numbers=page_numbers)
