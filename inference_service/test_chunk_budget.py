"""A shorter sentence slice may tokenize to more tokens than its longer prefix."""
from types import SimpleNamespace
import unittest

from inference_service.runtime import Runtime


class ChunkBudgetCheck(unittest.TestCase):
    def test_sentence_preference_cannot_exceed_checked_token_budget(self):
        runtime = Runtime.__new__(Runtime)
        runtime.seconds = 10
        runtime.require = lambda role: None
        runtime.clipped_title = lambda title: ("", False)
        runtime.normalize = lambda text: text
        runtime.identity = lambda role: {"artifact_id": "fixture"}
        runtime.tokenizer = lambda role: SimpleNamespace(encode=lambda text, **kw:
            SimpleNamespace(offsets=[(i, i + 1) for i in range(len(text))]))
        text = "abcdefghij. klmnopqrstuvwxy"
        runtime.count = lambda prepared: 21 if prepared == "passage: " + text[:12] else len(prepared.removeprefix("passage: "))
        chunks = runtime.chunk(text, "", 20, 0)["chunks"]
        assert chunks[0]["end"] == 20
        assert all(chunk["token_count"] <= 20 for chunk in chunks)
        assert "".join(chunk["text"] for chunk in chunks) == text
