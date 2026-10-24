"""Deferred status-only check; run in the inference dependency environment."""
import unittest
from unittest.mock import Mock
from inference_service.runtime import Runtime


class RuntimeHealthCheck(unittest.TestCase):
    def test_residency_is_not_historical_load_or_completed_inference(self):
        runtime=Runtime.__new__(Runtime)
        runtime.error=''
        runtime.pipeline=runtime.normalization=runtime.runtime_id=runtime.bundle_id=runtime.generation='fixture'
        runtime.embedding_dimensions=8
        runtime.threads=2
        runtime.batch_size=1
        runtime.models={'embedding':{},'reranker':{}}
        runtime.identity=lambda role:{'model':role,'revision':'fixture','artifact_id':role}
        runtime.tokenizers={}
        runtime.completed_roles={'embedding','reranker'}
        runtime.loaded_roles={'embedding','reranker'}
        runtime.deep_health=Mock(return_value={})
        runtime.session=object()
        runtime.session_role='reranker'
        health=runtime.health()
        self.assertFalse(health['models']['embedding']['loaded'])
        self.assertTrue(health['models']['reranker']['loaded'])
        self.assertTrue(health['models']['embedding']['inference_completed'])
        runtime.session=None
        self.assertFalse(runtime.health()['models']['reranker']['loaded'])
