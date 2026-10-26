import asyncio
import io
import json
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
    async def asyncSetUp(self):
        ocr_app.REQUESTS.clear()
        ocr_app.REQUEST_GATE = asyncio.Lock()

    async def test_historical_manifest_cannot_claim_current_runtime_ready(self):
        inventory = {'root_writable': True, 'manifest': {'valid': True,
            'probe': {'checked_at': '2026-08-08T00:00:00Z',
                      'components': {'ocr:ch': {'available': True}}}}}
        with patch.object(ocr_app, 'cache_inventory', return_value=inventory), \
             patch.object(ocr_app, 'RUNTIME_WORKER_PID', None), \
             patch.object(ocr_app, 'PRIMARY_LANGUAGE', 'ch'):
            response = await ocr_app.readiness()
        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.body)
        self.assertFalse(payload['runtime_verified'])
        self.assertTrue(payload['installation_probe']['components']['ocr:ch']['available'])

    async def test_deep_success_is_current_runtime_evidence(self):
        probe = {'components': {'ocr:ch': {'available': True}}}
        with patch.object(ocr_app, 'cache_inventory', return_value={'root_writable': True}), \
             patch.object(ocr_app, 'run_in_ocr_process', new=AsyncMock(return_value=probe)), \
             patch.object(ocr_app, 'PRIMARY_LANGUAGE', 'ch'):
            response = await ocr_app.readiness(deep=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.body)['runtime_verified'])

    def test_one_shared_tiny_engine_obeys_cpu_bound(self):
        with patch.object(ocr_app, 'load_engine') as factory:
            ocr_app.engine.cache_clear()
            ocr_app.engine()
            ocr_app.engine()
            factory.assert_called_once()
            self.assertLessEqual(factory.call_args.args[1], 4)
            ocr_app.engine.cache_clear()

    def test_cropped_rotated_pdf_records_actual_render_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'rotated.pdf'
            document=ocr_app.fitz.open()
            page=document.new_page(width=600,height=800)
            page.set_cropbox(ocr_app.fitz.Rect(40,60,540,760))
            page.set_rotation(90)
            document.save(path);document.close()
            with patch.object(ocr_app,'recognize',return_value=[{'text':'synthetic',
                 'bbox':[20,30,100,60],'confidence':1.0,'type':'paragraph'}]):
                result=ocr_app._parse_pdf_path(path,primary='ch',layout=False,page_numbers='1')
            rendered=result['pages'][0];geometry=rendered['geometry']
            self.assertEqual(geometry['coordinate_space'],'rendered_pixels')
            self.assertEqual(geometry['rotation'],90)
            self.assertEqual(geometry['crop_box'],[40,60,540,760])
            self.assertEqual(geometry['page_rect'],[0,0,700,500])
            self.assertEqual(geometry['render_width'],rendered['width'])
            self.assertEqual(geometry['render_height'],rendered['height'])
            self.assertEqual(rendered['blocks'][0]['bbox'],[20,30,100,60])

    async def test_worker_status_returns_to_http_process_and_dies_with_worker(self):
        from concurrent.futures import Future
        fake = Future()
        fake.set_result((17, {'engines': {'ch': {'loaded': True, 'inference_success': True}},
                             'structure': {'loaded': False, 'inference_success': False}}, 123, None))
        from unittest.mock import Mock
        executor = Mock()
        executor.submit.return_value = fake
        with patch.object(ocr_app, 'ocr_process_pool', return_value=executor), \
             patch.object(ocr_app, 'OCR_PROCESS_POOL', executor), \
             patch.object(ocr_app, 'MODEL_STATUS', {'engines': {}, 'structure': {}}), \
             patch.object(ocr_app, 'RUNTIME_WORKER_PID', None):
            self.assertEqual(await ocr_app.run_in_ocr_process(burn_cpu, 0.01), 17)
            self.assertEqual(ocr_app.RUNTIME_WORKER_PID, 123)
            self.assertTrue(ocr_app.MODEL_STATUS['engines']['ch']['inference_success'])
            ocr_app.discard_ocr_process_pool(executor)
            self.assertIsNone(ocr_app.RUNTIME_WORKER_PID)
            self.assertFalse(ocr_app.MODEL_STATUS['engines']['ch']['inference_success'])

    async def test_repeated_request_shares_work_after_client_disconnect(self):
        started, finish = asyncio.Event(), asyncio.Event()
        async def recognize(*args, **kwargs):
            started.set()
            await finish.wait()
            return {"pages": [{"index": 1, "blocks": [{"text": "saved text"}]}]}
        def upload():
            return UploadFile(filename="one.pdf", file=io.BytesIO(b"%PDF-same-source"))
        async def request():
            return await ocr_app.parse_pdf(file=upload(), languages="ch", layout=False, page_numbers="1", request_id="request-identity-001")
        with patch.object(ocr_app, "run_in_ocr_process", side_effect=recognize) as compute:
            first = asyncio.create_task(request())
            await started.wait()
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            self.assertEqual((await ocr_app.request_status("request-identity-001"))["state"], "running")
            retry = asyncio.create_task(request())
            await asyncio.sleep(0)
            finish.set()
            result = await retry
            self.assertEqual(result["pages"][0]["index"], 1)
            self.assertEqual(compute.call_count, 1)
            self.assertFalse(compute.call_args.args[1].exists())
            replay = await request()
            self.assertEqual(replay, result)
            self.assertEqual(compute.call_count, 1)

    async def test_request_identity_cannot_be_reused_for_different_pdf(self):
        from fastapi import HTTPException
        with patch.object(ocr_app, "run_in_ocr_process", new=AsyncMock(return_value={"pages": []})):
            await ocr_app.parse_pdf(file=UploadFile(filename="one.pdf", file=io.BytesIO(b"%PDF-first")), languages="ch", layout=False, page_numbers="1", request_id="request-identity-002")
            with self.assertRaises(HTTPException) as error:
                await ocr_app.parse_pdf(file=UploadFile(filename="two.pdf", file=io.BytesIO(b"%PDF-other")), languages="ch", layout=False, page_numbers="1", request_id="request-identity-002")
            self.assertEqual(error.exception.status_code, 409)

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
        expected = {"engine": "RapidOCR", "pages": []}

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
        self.assertNotIn("fallback", kwargs)
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
            with patch.dict(ocr_app.os.environ, {"OCR_MODEL_DIR": model_root}):
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
                with patch.dict(ocr_app.os.environ, {"OCR_MODEL_DIR": model_root}):
                    response = executor.submit(ocr_app.health).result(timeout=0.5)
        finally:
            ocr_app.MODEL_LOCK.release()
            executor.shutdown(wait=True)

        self.assertEqual(response["status"], "ok")
        self.assertLess(time.monotonic() - started, 0.5)


if __name__ == "__main__":
    unittest.main()
