"""Temporary OCR endpoint for the November curation batch; no website UI changes."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ocr_service'))
os.environ['OCR_MODEL_DIR'] = str(ROOT / 'tmp/stl4-rapidocr-20261027/models')
os.environ['OCR_CPU_THREADS'] = '2'
os.environ['OMP_NUM_THREADS'] = '2'
temporary = ROOT / 'tmp/nas-optimize-20261108/ocr-temp'
temporary.mkdir(parents=True, exist_ok=True)
os.environ['OCR_TEMP_DIR'] = str(temporary)
from app import app
from fastapi.responses import JSONResponse


@app.middleware('http')
async def restrict_source(request, call_next):
    if request.client.host not in {'192.168.5.6', '192.168.5.3', '127.0.0.1'}:
        return JSONResponse({'detail': 'forbidden'}, status_code=403)
    return await call_next(request)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='192.168.5.3', port=18091, workers=1, proxy_headers=False,
                access_log=False, log_level='warning')
