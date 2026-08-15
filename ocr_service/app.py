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

import fitz
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from paddleocr import PaddleOCR, PPStructureV3


app = FastAPI(title="Social Theory Library OCR", version="2.6.0")
PRIMARY_LANGUAGE = os.getenv("OCR_PRIMARY_LANGUAGE", "ch")
FALLBACK_LANGUAGE = os.getenv("OCR_FALLBACK_LANGUAGE", "chinese_cht")
RENDER_DPI = int(os.getenv("OCR_RENDER_DPI", "180"))
MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "2000"))
ENABLE_STRUCTURE = os.getenv("OCR_ENABLE_STRUCTURE", "false").lower() in {"1", "true", "yes"}
REQUIRE_FALLBACK = os.getenv("OCR_REQUIRE_FALLBACK", "false").lower() in {"1", "true", "yes"}
REQUIRE_STRUCTURE = os.getenv("OCR_REQUIRE_STRUCTURE", "false").lower() in {"1", "true", "yes"}
MODEL_LOCK = threading.Lock()
PROCESS_POOL_LOCK = threading.Lock()
OCR_PROCESS_POOL = None
MODEL_STATUS = {
    "engines": {},
    "structure": {
        "loaded": False,
        "inference_success": False,
        "last_success_at": None,
        "last_error": "",
    },
}


def ocr_process_pool() -> ProcessPoolExecutor:
    """Return the single persistent OCR worker process.

    Paddle inference can hold the Python GIL for minutes on the NAS CPU. A
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
    global OCR_PROCESS_POOL
    with PROCESS_POOL_LOCK:
        current = OCR_PROCESS_POOL
        if current is None or (executor is not None and current is not executor):
            return
        OCR_PROCESS_POOL = None
    current.shutdown(wait=False, cancel_futures=True)


async def run_in_ocr_process(function, /, *args, **kwargs):
    executor = ocr_process_pool()
    job = partial(function, *args, **kwargs)
    try:
        return await asyncio.get_running_loop().run_in_executor(executor, job)
    except BrokenProcessPool:
        discard_ocr_process_pool(executor)
        raise


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
    root = Path(os.getenv("PADDLE_HOME", "/models"))
    paddlex = Path(os.getenv("PADDLE_PDX_CACHE_HOME", str(root / ".paddlex")))
    return {
        "root": root,
        "paddlex": paddlex,
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
        "paddlex_cache": str(paths["paddlex"]),
        "paddlex_cache_exists": paths["paddlex"].is_dir(),
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


@lru_cache(maxsize=3)
def engine(language: str):
    state = _engine_state(language)
    try:
        instance = PaddleOCR(
            lang=language,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
        )
        state.update({"loaded": True, "last_error": ""})
        return instance
    except Exception as exc:
        state.update({"loaded": False, "last_error": str(exc)[:2000]})
        raise


@lru_cache(maxsize=1)
def structure_engine():
    options = {
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": True,
        "use_seal_recognition": False,
        "use_table_recognition": False,
        "use_formula_recognition": False,
        "cpu_threads": 4,
    }
    state = MODEL_STATUS["structure"]
    try:
        try:
            instance = PPStructureV3(**options)
        except TypeError:
            instance = PPStructureV3(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
            )
        state.update({"loaded": True, "last_error": ""})
        return instance
    except Exception as exc:
        state.update({"loaded": False, "last_error": str(exc)[:2000]})
        raise


def _probe_image() -> np.ndarray:
    image = np.full((96, 320, 3), 255, dtype=np.uint8)
    image[36:60, 24:296] = 32
    return image


def _consume_predictions(predictor, image: np.ndarray) -> int:
    return sum(1 for _prediction in predictor.predict(input=image))


def probe_models(
    *,
    include_fallback: bool = False,
    include_structure: bool = False,
) -> dict:
    """Load configured models and execute a minimal in-process inference."""

    started = time.monotonic()
    image = _probe_image()
    components = {}
    with MODEL_LOCK:
        languages = [PRIMARY_LANGUAGE]
        if include_fallback and FALLBACK_LANGUAGE not in languages:
            languages.append(FALLBACK_LANGUAGE)
        for language in languages:
            state = _engine_state(language)
            try:
                predictions = _consume_predictions(engine(language), image)
                state.update(
                    {
                        "loaded": True,
                        "inference_success": True,
                        "last_success_at": utc_now(),
                        "last_error": "",
                    }
                )
                components[f"ocr:{language}"] = {
                    "available": True,
                    "predictions": predictions,
                }
            except Exception as exc:
                state.update(
                    {
                        "inference_success": False,
                        "last_error": str(exc)[:2000],
                    }
                )
                components[f"ocr:{language}"] = {
                    "available": False,
                    "error": str(exc)[:2000],
                }
        if include_structure:
            state = MODEL_STATUS["structure"]
            try:
                predictions = _consume_predictions(structure_engine(), image)
                state.update(
                    {
                        "loaded": True,
                        "inference_success": True,
                        "last_success_at": utc_now(),
                        "last_error": "",
                    }
                )
                components["structure"] = {
                    "available": True,
                    "predictions": predictions,
                }
            except Exception as exc:
                state.update(
                    {
                        "inference_success": False,
                        "last_error": str(exc)[:2000],
                    }
                )
                components["structure"] = {
                    "available": False,
                    "error": str(exc)[:2000],
                }
    return {
        "available": all(component["available"] for component in components.values()),
        "components": components,
        "duration_seconds": round(time.monotonic() - started, 3),
        "checked_at": utc_now(),
        "versions": {
            "paddleocr": installed_version("paddleocr"),
            "paddlepaddle": installed_version("paddlepaddle"),
        },
        "cache": compact_cache_inventory(),
    }


def result_payload(result) -> dict:
    if hasattr(result, "json"):
        value = result.json
        return value() if callable(value) else value
    if hasattr(result, "res"):
        return result.res
    return result if isinstance(result, dict) else {}


def extract_blocks(raw: dict) -> list[dict]:
    result = raw.get("res", raw)
    texts = result.get("rec_texts") or result.get("texts") or []
    scores = result.get("rec_scores") or result.get("scores") or []
    boxes = result.get("rec_boxes") or result.get("dt_polys") or result.get("boxes") or []
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


def extract_structure_blocks(raw: dict) -> list[dict]:
    result = raw.get("res", raw)
    parsed = result.get("parsing_res_list") or []
    blocks = []
    for item in parsed:
        text = str(item.get("block_content", "")).strip()
        if not text:
            continue
        bbox = np.asarray(item.get("block_bbox", []), dtype=float).reshape(-1)
        blocks.append(
            {
                "text": text,
                "bbox": bbox[:4].tolist() if bbox.size >= 4 else [],
                "confidence": float(item.get("score", 1)),
                "type": item.get("sub_label") or item.get("block_label") or "paragraph",
                "segment_start": bool(item.get("seg_start_flag", True)),
                "segment_end": bool(item.get("seg_end_flag", True)),
                "reading_order": int(item.get("index", len(blocks))),
            }
        )
    blocks.sort(key=lambda block: block["reading_order"])
    return blocks


def recognize(image: np.ndarray, language: str, layout: bool) -> list[dict]:
    if layout and ENABLE_STRUCTURE:
        try:
            structured = []
            for prediction in structure_engine().predict(input=image):
                structured.extend(extract_structure_blocks(result_payload(prediction)))
            MODEL_STATUS["structure"].update(
                {
                    "inference_success": True,
                    "last_success_at": utc_now(),
                    "last_error": "",
                }
            )
            if structured:
                return structured
        except Exception as exc:
            MODEL_STATUS["structure"].update(
                {
                    "inference_success": False,
                    "last_error": str(exc)[:2000],
                }
            )
    state = _engine_state(language)
    try:
        predictions = engine(language).predict(input=image)
        blocks = []
        for prediction in predictions:
            blocks.extend(extract_blocks(result_payload(prediction)))
        state.update(
            {
                "inference_success": True,
                "last_success_at": utc_now(),
                "last_error": "",
            }
        )
        return blocks
    except Exception as exc:
        state.update(
            {
                "inference_success": False,
                "last_error": str(exc)[:2000],
            }
        )
        raise


def _parse_pdf_path(
    temp_path: Path,
    *,
    primary: str,
    fallback: str | None,
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
        # PaddleOCR model instances are process-wide singletons and are not
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
                if fallback and mean_confidence < 0.72:
                    fallback_blocks = recognize(image, fallback, False)
                    fallback_confidence = (
                        sum(block["confidence"] for block in fallback_blocks) / len(fallback_blocks)
                        if fallback_blocks
                        else 0
                    )
                    if fallback_confidence > mean_confidence:
                        blocks = fallback_blocks
                        mean_confidence = fallback_confidence
                pages.append(
                    {
                        "index": index,
                        "width": pixmap.width,
                        "height": pixmap.height,
                        "confidence": mean_confidence,
                        "blocks": blocks,
                    }
                )
        return {
            "engine": "PaddleOCR",
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
        "fallback_language": FALLBACK_LANGUAGE,
        "structure_enabled": ENABLE_STRUCTURE,
        "model_root": inventory["root"],
        "model_root_writable": inventory["root_writable"],
        "model_manifest_present": bool(inventory["manifest"]),
    }


@app.get("/ready")
async def readiness(
    deep: bool = False,
    include_fallback: bool = False,
    include_structure: bool = False,
):
    include_fallback = include_fallback or REQUIRE_FALLBACK
    include_structure = include_structure or REQUIRE_STRUCTURE
    probe = None
    if deep:
        probe = await run_in_ocr_process(
            probe_models,
            include_fallback=include_fallback,
            include_structure=include_structure,
        )
    manifest_probe = (inventory_probe := cache_inventory()).get("manifest") or {}
    manifest_components = (manifest_probe.get("probe") or {}).get("components") or {}

    def component_ready(name: str, state: dict) -> bool:
        if probe is not None and name in probe.get("components", {}):
            return bool(probe["components"][name].get("available"))
        return bool(state.get("inference_success")) or bool(
            manifest_components.get(name, {}).get("available")
        )

    primary = _engine_state(PRIMARY_LANGUAGE)
    required = [component_ready(f"ocr:{PRIMARY_LANGUAGE}", primary)]
    if include_fallback:
        required.append(
            component_ready(
                f"ocr:{FALLBACK_LANGUAGE}",
                _engine_state(FALLBACK_LANGUAGE),
            )
        )
    if include_structure:
        required.append(
            component_ready("structure", MODEL_STATUS["structure"])
        )
    inventory = compact_cache_inventory(inventory_probe)
    available = all(required) and inventory["root_writable"]
    payload = {
        "status": "ready" if available else "not_ready",
        "available": available,
        "service_version": app.version,
        "required": {
            "primary": PRIMARY_LANGUAGE,
            "fallback": FALLBACK_LANGUAGE if include_fallback else None,
            "structure": include_structure,
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
):
    header = await file.read(5)
    if header != b"%PDF-":
        raise HTTPException(status_code=415, detail="Only PDF files are accepted.")
    await file.seek(0)
    requested = [item.strip() for item in languages.split(",") if item.strip()]
    primary = PRIMARY_LANGUAGE if PRIMARY_LANGUAGE in requested else requested[0]
    fallback = FALLBACK_LANGUAGE if FALLBACK_LANGUAGE in requested else None
    with tempfile.NamedTemporaryFile(suffix=".pdf", dir="/tmp/ocr", delete=False) as handle:
        while chunk := await file.read(1024 * 1024):
            handle.write(chunk)
        temp_path = Path(handle.name)
    try:
        return await run_in_ocr_process(
            _parse_pdf_path,
            temp_path,
            primary=primary,
            fallback=fallback,
            layout=layout,
            page_numbers=page_numbers,
        )
    finally:
        temp_path.unlink(missing_ok=True)
