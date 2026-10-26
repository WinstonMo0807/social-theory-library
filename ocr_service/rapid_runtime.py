"""The only inference backend; loaded lazily in the OCR worker."""
from rapid_models import verify_models


def load_engine(root, threads):
    from rapidocr import RapidOCR, ModelType, OCRVersion
    paths = verify_models(root)
    return RapidOCR(params={
        'Global.model_root_dir': str(root),
        'Det.model_type': ModelType.TINY,
        'Rec.model_type': ModelType.TINY,
        'Det.ocr_version': OCRVersion.PPOCRV6,
        'Rec.ocr_version': OCRVersion.PPOCRV6,
        'Det.model_path': paths['det'],
        'Rec.model_path': paths['rec'],
        'Cls.model_path': paths['cls'],
        'EngineConfig.onnxruntime.intra_op_num_threads': threads,
        'EngineConfig.onnxruntime.inter_op_num_threads': 1,
        'EngineConfig.onnxruntime.enable_cpu_mem_arena': False,
    })
