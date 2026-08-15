import asyncio
import io
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import UploadFile

import app as ocr_app


def burn_cpu(seconds: float) -> int:
    deadline = time.monotonic() + seconds
    iterations = 0
    while time.monotonic() < deadline:
        iterations += 1
    return iterations


class OcrServiceConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    def test_cache_diagnostics_do_not_nest_previous_probe(self):
        inventory = {
            "root": "/models",
            "manifest": {
                "valid": True,
                "schema": 1,
                "probe": {"cache": {"manifest": {"probe": {"older": True}}}},
            },
        }

        compact = ocr_app.compact_cache_inventory(inventory)

        self.assertEqual(compact["manifest"], {"valid": True, "schema": 1})
        self.assertIn("probe", inventory["manifest"])

    async def test_parse_endpoint_offloads_cpu_work_from_event_loop(self):
        upload = UploadFile(filename="sample.pdf", file=io.BytesIO(b"%PDF-test"))
        expected = {"engine": "PaddleOCR", "pages": []}

        with patch.object(
            ocr_app,
            "run_in_ocr_process",
            new=AsyncMock(return_value=expected),
        ) as offload:
            response = await ocr_app.parse_pdf(
                file=upload,
                languages="ch,en,chinese_cht",
                layout=True,
                page_numbers="1",
            )

        self.assertEqual(response, expected)
        offload.assert_awaited_once()
        args = offload.await_args.args
        kwargs = offload.await_args.kwargs
        self.assertIs(args[0], ocr_app._parse_pdf_path)
        self.assertIsInstance(args[1], Path)
        self.assertFalse(args[1].exists())
        self.assertEqual(kwargs["primary"], "ch")
        self.assertEqual(kwargs["fallback"], "chinese_cht")
        self.assertEqual(kwargs["page_numbers"], "1")

    def test_process_pool_is_single_worker_and_uses_spawn(self):
        executor = ocr_app.ocr_process_pool()
        try:
            self.assertEqual(executor._max_workers, 1)
            self.assertEqual(executor._mp_context.get_start_method(), "spawn")
        finally:
            ocr_app.discard_ocr_process_pool(executor)

    async def test_process_pool_keeps_health_responsive_during_cpu_work(self):
        with tempfile.TemporaryDirectory() as model_root:
            with patch.dict(ocr_app.os.environ, {"PADDLE_HOME": model_root}):
                work = asyncio.create_task(
                    ocr_app.run_in_ocr_process(burn_cpu, 0.8)
                )
                await asyncio.sleep(0.2)
                started = time.monotonic()
                response = ocr_app.health()
                elapsed = time.monotonic() - started
                iterations = await work
        ocr_app.discard_ocr_process_pool()

        self.assertEqual(response["status"], "ok")
        self.assertGreater(iterations, 0)
        self.assertLess(elapsed, 0.5)

    def test_light_health_does_not_wait_for_model_inference_lock(self):
        executor = ThreadPoolExecutor(max_workers=1)
        ocr_app.MODEL_LOCK.acquire()
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory() as model_root:
                with patch.dict(ocr_app.os.environ, {"PADDLE_HOME": model_root}):
                    response = executor.submit(ocr_app.health).result(timeout=0.5)
        finally:
            ocr_app.MODEL_LOCK.release()
            executor.shutdown(wait=True)

        self.assertEqual(response["status"], "ok")
        self.assertLess(time.monotonic() - started, 0.5)


if __name__ == "__main__":
    unittest.main()
