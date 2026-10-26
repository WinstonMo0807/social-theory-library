"""Pinned OCR assets. Network access is only used by the explicit installer."""
import argparse
from hashlib import sha256
import os
from pathlib import Path
import shutil
import urllib.request

MODEL_ID = "PP-OCRv6-tiny"
MODEL_REVISION = "rapidocr-3.10.0-ppocrv6-tiny-1"
BASE_URL = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/"
MODELS = {
    "det": ("PP-OCRv6_det_tiny.onnx", "PP-OCRv6/det/", "f42c0fbd294d95eac1a550e131b277dac97462c8025fa4b6c3cec1b7894bd3d5"),
    "rec": ("PP-OCRv6_rec_tiny.onnx", "PP-OCRv6/rec/", "e16e242de5937ad92609223f19bc2aff3727ee40b095f996907c24749bad251b"),
    "cls": ("ch_ppocr_mobile_v2.0_cls_mobile.onnx", "PP-OCRv4/cls/", "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c"),
}


def verify_models(root):
    root = Path(root)
    paths = {}
    for kind, (name, _, expected) in MODELS.items():
        path = root / name
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"OCR model is missing or checksum differs: {name}. Run the model installer.")
        paths[kind] = str(path)
    return paths


def prepare_models(root, *, bundled=Path('/opt/ocr-models'), download=False):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name, folder, expected in MODELS.values():
        target = root / name
        if target.exists():
            continue
        temporary = target.with_suffix('.onnx.tmp')
        try:
            source = Path(bundled) / name
            if source.is_file():
                shutil.copyfile(source, temporary)
            elif download:
                with urllib.request.urlopen(BASE_URL + folder + name, timeout=120) as response, temporary.open('wb') as out:
                    shutil.copyfileobj(response, out)
            else:
                raise RuntimeError(f"Bundled OCR model missing: {name}")
            if sha256(temporary.read_bytes()).hexdigest() != expected:
                raise RuntimeError(f"OCR model checksum failed: {name}")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return verify_models(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=os.getenv('OCR_MODEL_DIR', '/models'))
    parser.add_argument('--download', action='store_true')
    arguments = parser.parse_args()
    prepare_models(arguments.root, download=arguments.download)
    print(f"Verified {MODEL_ID}: {len(MODELS)} ONNX assets")
