import asyncio
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime, timezone
from functools import lru_cache, partial
from importlib.metadata import PackageNotFoundError, version as package_version
import multiprocessing
from pathlib import Path
import json
import os
import tempfile
import threading
import time
import hashlib
import re
from collections import OrderedDict

import fitz
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from rapid_models import MODEL_ID, MODEL_REVISION
from rapid_runtime import load_engine
from toc_layout import repair_contents


app = FastAPI(title="Social Theory Library OCR", version="4.0.0-rapidocr-2")
PRIMARY_LANGUAGE = os.getenv("OCR_PRIMARY_LANGUAGE", "ch")
RENDER_DPI = int(os.getenv("OCR_RENDER_DPI", "180"))
MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "2000"))
CPU_THREADS = max(1, min(int(os.getenv("OCR_CPU_THREADS", "1")), 4))
MODEL_LOCK = threading.Lock()
PROCESS_POOL_LOCK = threading.Lock()
OCR_PROCESS_POOL = None
RUNTIME_WORKER_PID = None
REQUESTS = OrderedDict()
REQUEST_GATE = asyncio.Lock()
MAX_REQUESTS = 32
MODEL_STATUS = {"engines": {}}


def ocr_process_pool() -> ProcessPoolExecutor:
    """Return the single persistent OCR worker process.

    Rendering and inference must not occupy the HTTP process. A
    thread keeps the ASGI event loop logically free but can still starve the
    process that serves health checks. The dedicated spawned process keeps one
    model instance warm while the HTTP process remains responsive.
    """

    global OCR_PROCESS_POOL
    with PROCESS_POOL_LOCK:
        if OCR_PROCESS_POOL is None:
            OCR_PROCESS_POOL = ProcessPoolExecutor(
                max_workers=1,
                mp_context=multiprocessing.get_context("spawn"),
            )
        return OCR_PROCESS_POOL


def discard_ocr_process_pool(executor: ProcessPoolExecutor | None = None) -> None:
    global OCR_PROCESS_POOL, RUNTIME_WORKER_PID
    with PROCESS_POOL_LOCK:
        current = OCR_PROCESS_POOL
        if current is None or (executor is not None and current is not executor):
            return
        OCR_PROCESS_POOL = None
        RUNTIME_WORKER_PID = None
        for state in MODEL_STATUS["engines"].values():
            state.update(loaded=False, inference_success=False)
    current.shutdown(wait=False, cancel_futures=True)


def _execute_with_model_status(function, args, kwargs):
    try:
        result = function(*args, **kwargs)
    except Exception as exc:
        return None, MODEL_STATUS, os.getpid(), exc
    return result, MODEL_STATUS, os.getpid(), None


async def run_in_ocr_process(function, /, *args, **kwargs):
    global RUNTIME_WORKER_PID
    executor = ocr_process_pool()
    job = partial(_execute_with_model_status, function, args, kwargs)
    try:
        result, status, worker_pid, failure = await asyncio.get_running_loop().run_in_executor(executor, job)
    except BrokenProcessPool:
        discard_ocr_process_pool(executor)
        raise
    # Spawned globals are separate. Return both successful and failed inference
    # state; a malformed PDF alone must not invalidate an already working engine.
    MODEL_STATUS.update(status)
    RUNTIME_WORKER_PID = worker_pid
    if failure is not None:
        raise failure
    return result


@app.on_event("shutdown")
def shutdown_ocr_process_pool() -> None:
    discard_ocr_process_pool()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def installed_version(distribution: str) -> str:
    try:
        return package_version(distribution)
    except PackageNotFoundError:
        return "unknown"


def model_paths() -> dict:
    root = Path(os.getenv("OCR_MODEL_DIR", "/models"))
    return {
        "root": root,
        "manifest": root / "library-ocr-model-manifest.json",
    }


def cache_inventory(*, include_files: bool = False) -> dict:
    paths = model_paths()
    root = paths["root"]
    files = []
    total_bytes = 0
    file_count = 0
    if root.is_dir():
        for path in root.rglob("*"):
            if not path.is_file() or path == paths["manifest"]:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            file_count += 1
            total_bytes += size
            if include_files:
                files.append({"path": path.relative_to(root).as_posix(), "bytes": size})
    manifest = None
    if paths["manifest"].is_file():
        try:
            stored = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            manifest = {
                "valid": True,
                "schema": stored.get("schema"),
                "created_at": stored.get("created_at"),
                "file_count": stored.get("file_count"),
                "total_bytes": stored.get("total_bytes"),
                "probe": stored.get("probe"),
            }
        except (OSError, UnicodeError, json.JSONDecodeError):
            manifest = {"valid": False}
    return {
        "root": str(root),
        "root_exists": root.is_dir(),
        "root_writable": os.access(root, os.W_OK) if root.exists() else False,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "manifest": manifest,
        "files": files if include_files else None,
    }


def compact_cache_inventory(inventory: dict | None = None) -> dict:
    """Return cache diagnostics without embedding an older probe recursively."""

    compact = dict(inventory or cache_inventory())
    manifest = compact.get("manifest")
    if isinstance(manifest, dict):
        compact["manifest"] = {
            key: value
            for key, value in manifest.items()
            if key != "probe"
        }
    return compact


def _engine_state(language: str) -> dict:
    return MODEL_STATUS["engines"].setdefault(
        language,
        {
            "loaded": False,
            "inference_success": False,
            "last_success_at": None,
            "last_error": "",
        },
    )


@lru_cache(maxsize=1)
def engine():
    state = _engine_state(PRIMARY_LANGUAGE)
    try:
        instance = load_engine(model_paths()["root"], CPU_THREADS)
        state.update(loaded=True, last_error="")
        return instance
    except Exception as exc:
        state.update(loaded=False, last_error=str(exc)[:2000])
        raise


def _probe_image() -> np.ndarray:
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (320, 96), "white")
    ImageDraw.Draw(image).text((20, 28), "STL 012345", fill="black", font_size=28)
    return np.asarray(image)


def probe_models() -> dict:
    """Exercise detection, orientation and recognition in the actual worker."""
    started = time.monotonic()
    state = _engine_state(PRIMARY_LANGUAGE)
    with MODEL_LOCK:
        try:
            blocks = recognize(_probe_image(), PRIMARY_LANGUAGE, False)
            if not blocks:
                raise RuntimeError("OCR model probe returned no text.")
            component = {"available": True, "predictions": len(blocks)}
        except Exception as exc:
            state.update(inference_success=False, last_error=str(exc)[:2000])
            component = {"available": False, "error": str(exc)[:2000]}
    return {
        "available": component["available"],
        "components": {f"ocr:{PRIMARY_LANGUAGE}": component},
        "duration_seconds": round(time.monotonic() - started, 3),
        "checked_at": utc_now(),
        "engine": "RapidOCR", "model": MODEL_ID, "model_revision": MODEL_REVISION,
        "versions": {"rapidocr": installed_version("rapidocr"), "onnxruntime": installed_version("onnxruntime")},
        "cache": compact_cache_inventory(),
    }


def extract_blocks(raw: dict) -> list[dict]:
    result = raw.get("res", raw)
    texts = result.get("texts") or []
    scores = result.get("scores") or []
    boxes = result.get("boxes") or []
    blocks = []
    for index, text in enumerate(texts):
        text = str(text).strip()
        if not text:
            continue
        box = boxes[index] if index < len(boxes) else []
        array = np.asarray(box, dtype=float)
        if array.shape == (4,):
            bbox = array.tolist()
        elif array.size >= 8:
            points = array.reshape(-1, 2)
            bbox = [
                float(points[:, 0].min()),
                float(points[:, 1].min()),
                float(points[:, 0].max()),
                float(points[:, 1].max()),
            ]
        else:
            bbox = []
        blocks.append(
            {
                "text": text,
                "bbox": bbox,
                "confidence": float(scores[index]) if index < len(scores) else 0,
                "type": "paragraph",
            }
        )
    blocks.sort(key=lambda block: (
        round(block["bbox"][1] / 12) if len(block["bbox"]) == 4 else 0,
        block["bbox"][0] if len(block["bbox"]) == 4 else 0,
    ))
    return blocks


def recognize(image: np.ndarray, language: str, layout: bool) -> list[dict]:
    # The same multilingual tiny model serves all supported language selections.
    state = _engine_state(PRIMARY_LANGUAGE)
    try:
        def read_region(region):
            result = engine()(np.ascontiguousarray(region[:, :, ::-1]), use_det=True, use_cls=True, use_rec=True)
            return extract_blocks({"texts": list(result.txts or []),
                "scores": list(result.scores) if result.scores is not None else [],
                "boxes": result.boxes.tolist() if result.boxes is not None else []})
        blocks = read_region(image)
        if layout:
            blocks = repair_contents(image, blocks, read_region)
        state.update(loaded=True, inference_success=True, last_success_at=utc_now(), last_error="")
        return blocks
    except Exception as exc:
        state.update(inference_success=False, last_error=str(exc)[:2000])
        raise


def _parse_pdf_path(
    temp_path: Path,
    *,
    primary: str,
    layout: bool,
    page_numbers: str,
) -> dict:
    """Run CPU-bound PDF rendering and OCR away from the ASGI event loop."""

    document = fitz.open(temp_path)
    try:
        if document.page_count > MAX_PAGES:
            raise HTTPException(status_code=413, detail=f"PDF exceeds {MAX_PAGES} pages.")
        selected_pages = None
        if page_numbers.strip():
            try:
                selected_pages = {
                    int(value.strip())
                    for value in page_numbers.split(",")
                    if value.strip()
                }
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="page_numbers must contain integers.") from exc
            if not selected_pages or min(selected_pages) < 1 or max(selected_pages) > document.page_count:
                raise HTTPException(status_code=400, detail="page_numbers contains an invalid PDF page.")

        pages = []
        matrix = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
        # OCR model instances are process-wide singletons and are not
        # assumed to be safe for concurrent inference. Health endpoints do not
        # acquire this lock and remain responsive while a document is running.
        with MODEL_LOCK:
            for index, page in enumerate(document, start=1):
                if selected_pages is not None and index not in selected_pages:
                    continue
                pixmap = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
                image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                    pixmap.height,
                    pixmap.width,
                    pixmap.n,
                )
                blocks = recognize(image, primary, layout)
                mean_confidence = (
                    sum(block["confidence"] for block in blocks) / len(blocks)
                    if blocks
                    else 0
                )
                pages.append(
                    {
                        "index": index,
                        "width": pixmap.width,
                        "height": pixmap.height,
                        "geometry": {
                            "schema": 1,
                            "coordinate_space": "rendered_pixels",
                            "render_width": pixmap.width,
                            "render_height": pixmap.height,
                            "render_dpi": RENDER_DPI,
                            "render_matrix": list(matrix),
                            "page_rect": list(page.rect),
                            "crop_box": list(page.cropbox),
                            "rotation": page.rotation,
                            "pixmap_origin": [pixmap.x, pixmap.y],
                        },
                        "confidence": mean_confidence,
                        "blocks": blocks,
                    }
                )
        return {
            "engine": "RapidOCR",
            "model": MODEL_ID, "model_revision": MODEL_REVISION,
            "runtime": "onnxruntime", "runtime_version": installed_version("onnxruntime"),
            "layout_method": "text_geometry_toc_regions_v1",
            "layout_requested": layout,
            "requested_pages": sorted(selected_pages) if selected_pages is not None else "all",
            "pages": pages,
        }
    finally:
        document.close()


@app.get("/health")
def health():
    inventory = cache_inventory()
    return {
        "status": "ok",
        "service_version": app.version,
        "primary_language": PRIMARY_LANGUAGE,
        "engine": "RapidOCR", "model": MODEL_ID, "model_revision": MODEL_REVISION,
        "languages": ["ch", "en", "chinese_cht"], "layout_method": "text_geometry_toc_regions_v1",
        "model_root": inventory["root"],
        "model_root_writable": inventory["root_writable"],
        "model_manifest_present": bool(inventory["manifest"]),
    }


@app.get("/ready")
async def readiness(
    deep: bool = False,
):
    probe = None
    if deep:
        if REQUEST_GATE.locked():
            return JSONResponse({"available": False, "status": "busy", "detail": "OCR is processing a document; no extra probe was queued."}, status_code=409)
        async with REQUEST_GATE:
            probe = await run_in_ocr_process(probe_models)
    manifest_probe = (inventory_probe := cache_inventory()).get("manifest") or {}
    manifest_components = (manifest_probe.get("probe") or {}).get("components") or {}

    def component_ready(name: str, state: dict) -> bool:
        if probe is not None and name in probe.get("components", {}):
            return bool(probe["components"][name].get("available"))
        return RUNTIME_WORKER_PID is not None and bool(state.get("inference_success"))

    primary = _engine_state(PRIMARY_LANGUAGE)
    required = [component_ready(f"ocr:{PRIMARY_LANGUAGE}", primary)]
    inventory = compact_cache_inventory(inventory_probe)
    available = all(required) and inventory["root_writable"]
    payload = {
        "status": "ready" if available else "not_ready",
        "available": available,
        "runtime_verified": all(required),
        "engine": "RapidOCR", "model": MODEL_ID, "model_revision": MODEL_REVISION,
        "runtime_worker_pid": RUNTIME_WORKER_PID,
        "installation_probe": {
            "checked_at": (manifest_probe.get("probe") or {}).get("checked_at"),
            "components": manifest_components,
            "current_runtime_evidence": False,
        },
        "service_version": app.version,
        "required": {
            "primary": PRIMARY_LANGUAGE,
            "model": MODEL_ID,
        },
        "engines": MODEL_STATUS,
        "cache": inventory,
        "probe": probe,
    }
    return JSONResponse(payload, status_code=200 if available else 503)


@app.post("/v1/parse-pdf")
async def parse_pdf(
    file: UploadFile = File(...),
    languages: str = Form("ch,en,chinese_cht"),
    layout: bool = Form(True),
    page_numbers: str = Form(""),
    request_id: str = Form(""),
):
    request_id = request_id if isinstance(request_id, str) else ""
    if request_id and not re.fullmatch(r"[a-zA-Z0-9-]{16,80}", request_id):
        raise HTTPException(status_code=400, detail="Invalid request identity.")
    header = await file.read(5)
    if header != b"%PDF-":
        raise HTTPException(status_code=415, detail="Only PDF files are accepted.")
    await file.seek(0)
    requested = [item.strip() for item in languages.split(",") if item.strip()]
    primary = PRIMARY_LANGUAGE if PRIMARY_LANGUAGE in requested or not requested else requested[0]
    if any(language not in {"ch", "en", "chinese_cht"} for language in requested):
        raise HTTPException(status_code=400, detail="Supported languages: ch,en,chinese_cht.")
    with tempfile.NamedTemporaryFile(suffix=".pdf", dir="/tmp/ocr", delete=False) as handle:
        fingerprint = hashlib.sha256(f"{languages}:{layout}:{page_numbers}".encode())
        while chunk := await file.read(1024 * 1024):
            handle.write(chunk)
            fingerprint.update(chunk)
        temp_path = Path(handle.name)
    owns_temp = True
    key = request_id or temp_path.name
    try:
        existing = REQUESTS.get(request_id) if request_id else None
        if existing:
            if existing["fingerprint"] != fingerprint.hexdigest():
                raise HTTPException(status_code=409, detail="Request identity was already used for different input.")
            return await asyncio.shield(existing["task"])
        if sum(row["state"] in {"queued", "running"} for row in REQUESTS.values()) >= 2:
            raise HTTPException(status_code=429, detail="OCR is busy. Retry this same request later.", headers={"Retry-After": "30"})
        # Keep only a bounded set of recent receipts. No document bytes remain
        # after computation; duplicate HTTP requests await the original work.
        for old_key in list(REQUESTS):
            if len(REQUESTS) < MAX_REQUESTS:
                break
            if REQUESTS[old_key]["state"] not in {"queued", "running"}:
                del REQUESTS[old_key]
        receipt = {"fingerprint": fingerprint.hexdigest(), "state": "queued", "received_at": utc_now()}
        async def execute():
            try:
                async with REQUEST_GATE:
                    receipt.update(state="running", started_at=utc_now())
                    result = await run_in_ocr_process(_parse_pdf_path, temp_path, primary=primary,
                        layout=layout, page_numbers=page_numbers)
                    receipt.update(state="completed", finished_at=utc_now())
                    # Single-page resumable jobs keep small receipts. Legacy
                    # whole-file/anonymous calls must not retain large OCR text.
                    if not request_id or len(json.dumps(result, ensure_ascii=False).encode()) > 512 * 1024:
                        REQUESTS.pop(key, None)
                    return result
            except BaseException:
                receipt.update(state="failed", finished_at=utc_now())
                # An explicit retry may execute again after a failed receipt.
                REQUESTS.pop(key, None)
                raise
            finally:
                temp_path.unlink(missing_ok=True)
        task = asyncio.create_task(execute())
        owns_temp = False
        receipt["task"] = task
        # Consume background exceptions if a disconnected caller cannot do so.
        task.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)
        REQUESTS[key] = receipt
        return await asyncio.shield(task)
    finally:
        if owns_temp:
            temp_path.unlink(missing_ok=True)


@app.get("/v1/requests/{request_id}")
async def request_status(request_id: str):
    row = REQUESTS.get(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Request not present in this service instance.")
    return {key: row[key] for key in ("state", "received_at", "started_at", "finished_at") if key in row}
