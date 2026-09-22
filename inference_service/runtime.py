"""Offline CPU inference. The service never downloads weights or edits source text."""
from __future__ import annotations

import bisect
import ctypes
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time

import numpy as np
import onnxruntime as ort
from opencc import OpenCC
from tokenizers import Tokenizer


NORMALIZATION = "stl-t2s-dehyphen-nfkc-v1"
PIPELINE = "stl-e5-mean-l2-fp32-v1"
MAX_TOKENS = 512


class InferenceError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 503):
        self.code, self.status = code, status
        super().__init__(message)


def file_hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


class Runtime:
    def __init__(self, root: Path):
        self.root = root
        self.models: dict = {}
        self.tokenizers: dict[str, Tokenizer] = {}
        self.error = "models_missing"
        self.session = None
        self.session_role = ""
        self.loaded_roles: set[str] = set()
        self.completed_roles: set[str] = set()
        self.lock = threading.Lock()
        self.opencc = OpenCC("t2s")
        self.threads = max(1, min(int(os.getenv("INFERENCE_THREADS", "2")), 4))
        self.batch_size = max(1, min(int(os.getenv("INFERENCE_BATCH_SIZE", "1")), 4))
        self.seconds = max(5, min(int(os.getenv("INFERENCE_REQUEST_SECONDS", "120")), 240))
        self.bundle_id = ""

    def prepare(self) -> None:
        # Hash verification happens once at startup against the fixed bundle, not
        # for every request. The directory is mounted read-only by Compose.
        try:
            manifest = json.loads((self.root / "manifest.json").read_text("utf-8"))
            lock = json.loads(Path(__file__).with_name("model-lock.json").read_text("utf-8"))
            if manifest.get("pipeline") != PIPELINE or manifest.get("normalization") != NORMALIZATION:
                raise ValueError("pipeline mismatch")
            self.bundle_id = manifest["bundle_id"]
            for role in ("embedding", "reranker"):
                spec = manifest["models"][role]
                pinned = lock["models"][role]
                if spec["repo_id"] != pinned["repo_id"] or spec["revision"] != pinned["revision"]:
                    raise ValueError("revision mismatch")
                by_path = {item["path"]: item for item in spec["files"]}
                for item in pinned["files"]:
                    relative = item["path"]
                    path = self.root / role / relative
                    recorded = by_path[relative]
                    if not path.is_file() or path.stat().st_size != recorded["bytes"]:
                        raise ValueError("file missing")
                    actual = file_hash(path)
                    if actual != recorded["sha256"] or (item.get("sha256") and actual != item["sha256"]):
                        raise ValueError("checksum mismatch")
                    if item.get("git_oid"):
                        data = path.read_bytes()
                        git_hash = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
                        if git_hash != item["git_oid"]:
                            raise ValueError("source checksum mismatch")
                expected_id = artifact_id(role, spec)
                if spec["artifact_id"] != expected_id:
                    raise ValueError("artifact identity mismatch")
                tokenizer = Tokenizer.from_file(str(self.root / role / "tokenizer.json"))
                tokenizer.no_truncation()
                tokenizer.no_padding()
                self.models[role] = spec
                # These multilingual vocabularies are large in memory. Validate
                # one at a time, then keep only the active role during requests.
                del tokenizer
                self.trim_memory()
            self.error = ""
        except Exception:
            self.models.clear()
            self.tokenizers.clear()
            self.error = "model_manifest_invalid"

    def health(self) -> dict:
        return {
            "status": "ready" if len(self.completed_roles) == 2 else "prepared" if not self.error else "unavailable",
            "ready": not self.error and len(self.completed_roles) == 2,
            "manifest_ready": not self.error,
            "error": self.error,
            "backend": "onnxruntime-cpu",
            "runtime_version": ort.__version__,
            "pipeline": PIPELINE,
            "normalization": NORMALIZATION,
            "bundle_id": self.bundle_id,
            "threads": self.threads,
            "batch_size": self.batch_size,
            "resident_model": self.session_role,
            "resident_tokenizer": next(iter(self.tokenizers), ""),
            "models": {role: {**self.identity(role), "loaded": role in self.loaded_roles,
                              "inference_completed": role in self.completed_roles}
                       for role in self.models},
        }

    def identity(self, role: str) -> dict:
        spec = self.models[role]
        return {"model": spec["repo_id"], "revision": spec["revision"],
                "artifact_id": spec["artifact_id"], "pipeline": PIPELINE,
                "normalization": NORMALIZATION}

    def require(self, role: str, expected: str = "") -> None:
        if self.error or role not in self.models:
            raise InferenceError("model_missing", "本地模型未准备完成，请核对模型清单。")
        if expected and expected != self.models[role]["artifact_id"]:
            raise InferenceError("artifact_mismatch", "查询模型与索引模型不一致。", 409)

    def normalize(self, text: str) -> str:
        import unicodedata
        text = re.sub(r"(?<=[A-Za-z])-\s*\r?\n\s*(?=[A-Za-z])", "", text)
        return re.sub(r"\s+", " ", self.opencc.convert(unicodedata.normalize("NFKC", text))).strip()

    def count(self, text: str, role: str = "embedding") -> int:
        return len(self.tokenizer(role).encode(text).ids)

    @staticmethod
    def trim_memory() -> None:
        gc.collect()
        if os.name == "posix":
            try:
                ctypes.CDLL("libc.so.6").malloc_trim(0)
            except (OSError, AttributeError):
                pass

    def tokenizer(self, role: str) -> Tokenizer:
        if role not in self.tokenizers:
            # Drop the previous model before loading the next large tokenizer,
            # not only before the next ONNX session. Calls hold runtime.lock.
            self.session = None
            self.session_role = ""
            self.tokenizers.clear()
            self.trim_memory()
            tokenizer = Tokenizer.from_file(str(self.root / role / "tokenizer.json"))
            tokenizer.no_truncation()
            tokenizer.no_padding()
            self.tokenizers[role] = tokenizer
        return self.tokenizers[role]

    def clipped_title(self, title: str) -> tuple[str, bool]:
        value = self.normalize(title)
        tokenizer = self.tokenizer("embedding")
        encoding = tokenizer.encode(value, add_special_tokens=False)
        if len(encoding.ids) <= 48:
            return value, False
        return value[:encoding.offsets[47][1]], True

    def chunk(self, text: str, title: str, max_tokens: int, overlap: int) -> dict:
        self.require("embedding")
        deadline = time.monotonic() + self.seconds
        title, title_clipped = self.clipped_title(title)
        heading = title + "\n" if title else ""
        tokenizer = self.tokenizer("embedding")
        source_tokens = tokenizer.encode(text, add_special_tokens=False)
        offsets = source_tokens.offsets
        ends = [pair[1] for pair in offsets]
        boundaries = [match.end() for match in re.finditer(r"(?:[。！？!?；;](?:[”’\"']?)|(?<=[.!?])\s|\n\s*\n)", text)]
        chunks, start = [], 0
        while start < len(text):
            if time.monotonic() >= deadline:
                raise InferenceError("inference_timeout", "文字分块达到时间上限，请按原始页分批。", 504)
            if not text[start:].strip():
                # Trailing spaces belong to the last original-text slice.
                if chunks:
                    chunks[-1]["end"] = len(text)
                    chunks[-1]["text"] = text[chunks[-1]["start"]:]
                break
            # Search on original character boundaries, and COUNT the prepared
            # normalized text plus prefix/title with the actual E5 tokenizer.
            low, high = start + 1, min(len(text), start + max_tokens * 32)
            end = start
            while low <= high:
                middle = (low + high) // 2
                prepared = "passage: " + heading + self.normalize(text[start:middle])
                if self.count(prepared) <= max_tokens:
                    end, low = middle, middle + 1
                else:
                    high = middle - 1
            if end <= start:
                raise InferenceError("token_budget", "标题或文字超出分块预算。", 422)
            previous_end = chunks[-1]["end"] if chunks else -1
            if end <= previous_end:
                # An unusually long overlap must not repeat a complete prior
                # slice forever; start exactly at the first uncovered character.
                start = previous_end
                continue
            preferred = [value for value in boundaries
                         if max(previous_end + 1, start + (end - start) // 2) <= value <= end]
            if end < len(text) and preferred:
                end = preferred[-1]
            original = text[start:end]
            normalized = self.normalize(original)
            prepared = heading + normalized
            flags = []
            if title_clipped:
                flags.append("title_token_clipped")
            if "\ufffd" in original:
                flags.append("replacement_characters")
            if sum(not char.isalnum() and not char.isspace() for char in original) > max(20, len(original) * .45):
                flags.append("possible_text_noise")
            chunks.append({"text": original, "start": start, "end": end,
                           "normalized_text": normalized, "embedding_text": prepared,
                           "token_count": self.count("passage: " + prepared), "truncated": False,
                           "quality_flags": flags})
            if len(chunks) > 512:
                raise InferenceError("too_many_chunks", "单次文字过长，请按原始页分批。", 422)
            if end == len(text):
                break
            # Overlap is measured in source tokenizer positions. No original
            # characters are lost even when normalization changes their length.
            token_end = bisect.bisect_right(ends, end)
            back = max(0, token_end - overlap)
            candidate = offsets[back][0] if overlap and back < len(offsets) else end
            start = max(start + 1, candidate) if candidate < end else end
        return {**self.identity("embedding"), "chunks": chunks, "truncated": False}

    def get_session(self, role: str):
        if role == self.session_role and self.session is not None:
            return self.session
        self.session = None
        self.session_role = ""
        self.trim_memory()
        options = ort.SessionOptions()
        options.intra_op_num_threads = self.threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        # No architecture-specific graph rewrite, quantization or ISA flag.
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        options.add_session_config_entry("session.inter_op.allow_spinning", "0")
        try:
            self.session = ort.InferenceSession(str(self.root / role / "onnx/model.onnx"),
                                                sess_options=options, providers=["CPUExecutionProvider"])
        except Exception as exc:
            self.completed_roles.discard(role)
            raise InferenceError("model_load_failed", "本地 CPU 模型加载失败。") from exc
        self.session_role = role
        self.loaded_roles.add(role)
        return self.session

    def run(self, role: str, inputs: list, deadline: float):
        tokenizer = self.tokenizer(role)
        session = self.get_session(role)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise InferenceError("inference_timeout", "本地推理达到时间上限。", 504)
        tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
        try:
            encoded = tokenizer.encode_batch(inputs)
        finally:
            tokenizer.no_padding()
        if any(len(value.ids) > MAX_TOKENS for value in encoded):
            raise InferenceError("input_too_long", "文字超过模型 token 上限。", 422)
        available = {
            "input_ids": np.asarray([item.ids for item in encoded], dtype=np.int64),
            "attention_mask": np.asarray([item.attention_mask for item in encoded], dtype=np.int64),
            "token_type_ids": np.asarray([item.type_ids for item in encoded], dtype=np.int64),
        }
        feeds = {item.name: available[item.name] for item in session.get_inputs()}
        options = ort.RunOptions()
        timer = threading.Timer(remaining, lambda: setattr(options, "terminate", True))
        timer.daemon = True
        timer.start()
        try:
            output = session.run(None, feeds, options)[0]
        except Exception as exc:
            self.completed_roles.discard(role)
            code = "inference_timeout" if time.monotonic() >= deadline else "inference_failed"
            raise InferenceError(code, "本地推理未能完成，请稍后重试。", 504 if code.endswith("timeout") else 503) from exc
        finally:
            timer.cancel()
        if not np.isfinite(output).all():
            self.completed_roles.discard(role)
            raise InferenceError("invalid_output", "本地模型返回了无效数值。")
        self.completed_roles.add(role)
        return output, available["attention_mask"]

    def embed(self, texts: list[str], kind: str, expected: str) -> dict:
        self.require("embedding", expected)
        prepared = [kind + ": " + self.normalize(text) for text in texts]
        counts = [self.count(text) for text in prepared]
        if any(count > MAX_TOKENS for count in counts):
            raise InferenceError("input_too_long", "编码文字过长，请先按 tokenizer 分块。", 422)
        vectors = []
        deadline = time.monotonic() + self.seconds
        for start in range(0, len(prepared), self.batch_size):
            hidden, mask = self.run("embedding", prepared[start:start + self.batch_size], deadline)
            if hidden.ndim != 3 or hidden.shape[-1] != 384:
                raise InferenceError("invalid_output", "向量模型输出形状不符合固定契约。")
            weights = mask[..., None].astype(np.float32)
            pooled = (hidden * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1)
            normalized = pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
            vectors.extend(normalized.tolist())
        return {**self.identity("embedding"), "dimensions": 384, "vectors": vectors,
                "token_counts": counts, "truncated": [False] * len(texts)}

    def rerank(self, query: str, documents: list[str], top_n: int, expected: str) -> dict:
        self.require("reranker", expected)
        tokenizer = self.tokenizer("reranker")
        query = self.normalize(query)
        query_encoding = tokenizer.encode(query, add_special_tokens=False)
        query_truncated = len(query_encoding.ids) > 128
        if query_truncated:
            query = query[:query_encoding.offsets[127][1]]
        deadline = time.monotonic() + self.seconds
        results = []
        for index, document in enumerate(documents):
            document = self.normalize(document)
            encoding = tokenizer.encode(document, add_special_tokens=False)
            budget = MAX_TOKENS - len(tokenizer.encode(query, pair="").ids) - 2
            total = len(encoding.ids)
            starts = list(range(0, max(1, total), max(1, budget - 32)))
            truncated = len(starts) > 3
            if truncated:
                starts = [starts[0], starts[len(starts) // 2], starts[-1]]
            scores = []
            for start in starts:
                stop = min(start + budget, total)
                part = document[encoding.offsets[start][0]:encoding.offsets[stop - 1][1]] if total else ""
                # Boundary retokenization can add a leading token; trim only this
                # already bounded window and expose the fact to the caller.
                while len(tokenizer.encode(query, pair=part).ids) > MAX_TOKENS:
                    part = part[:-1]
                    truncated = True
                logits, _ = self.run("reranker", [(query, part)], deadline)
                if logits.shape != (1, 1):
                    raise InferenceError("invalid_output", "重排模型输出形状不符合固定契约。")
                scores.append(float(logits[0, 0]))
            results.append({"index": index, "relevance_score": max(scores),
                            "windows": len(starts), "truncated": truncated})
        results.sort(key=lambda value: (-value["relevance_score"], value["index"]))
        return {**self.identity("reranker"), "results": results[:top_n],
                "query_truncated": query_truncated}


def artifact_id(role: str, spec: dict) -> str:
    files = {item["path"]: item["sha256"] for item in spec["files"]}
    identity = {"repo": spec["repo_id"], "revision": spec["revision"],
                "model_sha256": files["onnx/model.onnx"], "tokenizer_sha256": files["tokenizer.json"],
                "role": role, "pipeline": PIPELINE, "normalization": NORMALIZATION,
                "runtime": "onnxruntime-1.22.1-cpu-fp32"}
    return "stl308-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
