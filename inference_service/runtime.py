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


DEFAULT_NORMALIZATION = "stl-t2s-dehyphen-nfkc-v1"
DEFAULT_PIPELINE = "stl-e5-mean-l2-fp32-v1"
DEFAULT_RUNTIME_ID = "onnxruntime-1.22.1-cpu-fp32"
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
        self.pipeline = DEFAULT_PIPELINE
        self.normalization = DEFAULT_NORMALIZATION
        self.runtime_id = os.getenv("INFERENCE_RUNTIME_ID", DEFAULT_RUNTIME_ID)
        self.embedding_dimensions = 384
        # Deep retrieval is an explicitly opt-in lane.  It has its own bundle
        # and generation so a BGE/ConvMemory experiment can never masquerade
        # as the production E5/mMARCO runtime.
        self.generation = os.getenv("INFERENCE_GENERATION", "").strip()
        self.deep_root = Path(os.getenv("DEEP_INFERENCE_MODEL_ROOT", str(root / "deep")))
        self.deep_generation = os.getenv("DEEP_INFERENCE_GENERATION", "").strip()
        self.deep_models: dict = {}
        self.deep_bundle_id = ""
        self.deep_pipeline = ""
        self.deep_runtime_id = f"onnxruntime-{ort.__version__}-cpu-sequential-v1"
        self.deep_error = "deep_disabled" if os.getenv("DEEP_INFERENCE_ENABLED", "0") != "1" else "model_missing"

    def prepare(self) -> None:
        # Hash verification happens once at startup against the fixed bundle, not
        # for every request. The directory is mounted read-only by Compose.
        try:
            manifest = json.loads((self.root / "manifest.json").read_text("utf-8"))
            lock_path = Path(__file__).with_name("model-lock.json")
            # Production keeps the code-pinned lock. An isolated experiment
            # may opt into a bundle-local lock only in its own container.
            bundle_lock = self.root / "model-lock.json"
            if os.getenv("DISCOVERY_ALLOW_BUNDLE_LOCK", "0") == "1" and bundle_lock.is_file():
                lock_path = bundle_lock
            lock = json.loads(lock_path.read_text("utf-8"))
            pipeline = str(manifest.get("pipeline") or "")
            normalization = str(manifest.get("normalization") or "")
            if not pipeline or not normalization or pipeline != str(lock.get("pipeline") or "") or normalization != str(lock.get("normalization") or ""):
                raise ValueError("pipeline mismatch")
            self.pipeline = pipeline
            self.normalization = normalization
            self.bundle_id = manifest["bundle_id"]
            # A model bundle may carry the index generation it was built for.
            # It is deliberately empty when the bundle does not declare one;
            # callers that need generation pinning then receive a safe 503.
            self.generation = str(manifest.get("generation") or self.generation or "").strip()
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
                expected_id = artifact_id(
                    role,
                    spec,
                    pipeline=self.pipeline,
                    normalization=self.normalization,
                    runtime_id=self.runtime_id,
                )
                if spec["artifact_id"] != expected_id:
                    raise ValueError("artifact identity mismatch")
                tokenizer = Tokenizer.from_file(str(self.root / role / "tokenizer.json"))
                tokenizer.no_truncation()
                tokenizer.no_padding()
                self.models[role] = spec
                if role == "embedding":
                    dimensions = int(spec.get("dimensions") or 384)
                    if not 1 <= dimensions <= 4096:
                        raise ValueError("embedding dimensions invalid")
                    self.embedding_dimensions = dimensions
                # These multilingual vocabularies are large in memory. Validate
                # one at a time, then keep only the active role during requests.
                del tokenizer
                self.trim_memory()
            self.error = ""
        except Exception:
            self.models.clear()
            self.tokenizers.clear()
            self.error = "model_manifest_invalid"
        self._prepare_deep_manifest()

    def _prepare_deep_manifest(self) -> None:
        """Verify a read-only isolated bundle; never download or mutate artifacts."""
        if os.getenv("DEEP_INFERENCE_ENABLED", "0") != "1":
            self.deep_models.clear()
            self.deep_error = "deep_disabled"
            return
        manifest_path = Path(os.getenv("DEEP_INFERENCE_MANIFEST", str(self.deep_root / "manifest.json")))
        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
            lock_path = Path(os.getenv("DEEP_INFERENCE_LOCK", str(self.deep_root / "model-lock.json")))
            lock = json.loads(lock_path.read_text("utf-8"))
            models = manifest.get("models") or {}
            pipeline = str(manifest.get("pipeline") or "")
            generation = str(manifest.get("generation") or self.deep_generation or "").strip()
            if not pipeline or pipeline != lock.get("pipeline") or not generation or generation != lock.get("generation"):
                raise ValueError("deep pipeline or generation mismatch")
            if self.deep_generation and generation != self.deep_generation:
                raise ValueError("configured deep generation mismatch")
            verified = {}
            roles = {"reranker": ("deep_reranker", "reranker"), "context": ("context", "conv_memory")}
            expected_models = {"reranker": "BAAI/bge-reranker-v2-m3",
                               "context": "Purdy0228/ConvMemory-v2-Evidence-Reranker"}
            for role, aliases in roles.items():
                key = next((name for name in aliases if name in models), None)
                if key is None and role == "context":
                    continue
                spec = models[key]
                pinned = lock["models"][key]
                if spec.get("repo_id") != expected_models[role] or not spec.get("revision"):
                    raise ValueError("deep model identity invalid")
                for field in ("repo_id", "revision", "directory", "model_file", "tokenizer_file", "precision", "max_tokens", "artifact_id"):
                    if spec.get(field) != pinned.get(field):
                        raise ValueError("deep lock mismatch")
                if not spec.get("precision") or not 128 <= int(spec.get("max_tokens", 256)) <= 512:
                    raise ValueError("deep token budget or precision missing")
                folder = bundle_path(self.deep_root, spec.get("directory", key))
                files = {item["path"]: item for item in spec["files"]}
                pinned_files = {item["path"]: item for item in pinned["files"]}
                if len(files) != len(spec["files"]) or len(pinned_files) != len(pinned["files"]) or files.keys() != pinned_files.keys():
                    raise ValueError("deep file list mismatch")
                for relative, recorded in files.items():
                    path = bundle_path(folder, relative)
                    checksum = str(pinned_files[relative].get("sha256") or "")
                    if not re.fullmatch(r"[0-9a-f]{64}", checksum) or recorded.get("sha256") != checksum:
                        raise ValueError("deep checksum not pinned")
                    if not path.is_file() or path.stat().st_size != recorded["bytes"] or recorded["bytes"] != pinned_files[relative]["bytes"] or file_hash(path) != checksum:
                        raise ValueError("deep artifact changed")
                if spec.get("model_file", "model.onnx") not in files or spec.get("tokenizer_file", "tokenizer.json") not in files:
                    raise ValueError("deep executable artifacts not pinned")
                if spec.get("artifact_id") != deep_artifact_id(role, spec, pipeline=pipeline, runtime_id=self.deep_runtime_id):
                    raise ValueError("deep artifact identity mismatch")
                verified[role] = {**spec, "directory": str(folder), "max_tokens": int(spec.get("max_tokens", 256))}
            self.deep_models = verified
            self.deep_generation = generation
            self.deep_bundle_id = str(manifest.get("bundle_id") or "")
            self.deep_pipeline = pipeline
            self.deep_error = ""
        except Exception:
            self.deep_models.clear()
            self.deep_bundle_id = ""
            self.deep_error = "model_manifest_invalid"

    def health(self) -> dict:
        baseline_completed = {"embedding", "reranker"}.issubset(self.completed_roles)
        return {
            "status": "ready" if not self.error and baseline_completed else "prepared" if not self.error else "unavailable",
            "ready": not self.error and baseline_completed,
            "manifest_ready": not self.error,
            "error": self.error,
            "backend": "onnxruntime-cpu",
            "runtime_version": ort.__version__,
            "pipeline": self.pipeline,
            "normalization": self.normalization,
            "runtime_id": self.runtime_id,
            "embedding_dimensions": self.embedding_dimensions,
            "bundle_id": self.bundle_id,
            "generation": self.generation,
            "threads": self.threads,
            "batch_size": self.batch_size,
            "resident_model": self.session_role,
            "resident_tokenizer": next(iter(self.tokenizers), ""),
            "models": {role: {**self.identity(role), "loaded": self.session is not None and self.session_role == role,
                              "inference_completed": role in self.completed_roles}
                       for role in self.models},
            "deep": self.deep_health(),
        }

    def deep_health(self) -> dict:
        """Expose optional deep state without claiming a model ran."""
        prepared = not self.deep_error and bool(self.deep_models)
        completed = prepared and all(f"deep:{role}" in self.completed_roles for role in self.deep_models)
        output = {
            "status": "ready" if completed else "prepared" if prepared else "unavailable",
            "manifest_ready": prepared,
            "error": self.deep_error,
            "bundle_id": self.deep_bundle_id,
            "generation": self.deep_generation,
            "pipeline": self.deep_pipeline,
            "runtime_id": self.deep_runtime_id,
            "threads": 1,
            "batch_size": 1,
            "models": {},
        }
        for role, spec in self.deep_models.items():
            output["models"][role] = {
                "model": spec.get("repo_id", ""),
                "revision": spec.get("revision", ""),
                "artifact_id": spec.get("artifact_id", ""),
                "generation": self.deep_generation,
                "loaded": self.session_role == f"deep:{role}",
                "inference_completed": f"deep:{role}" in self.completed_roles,
            }
        return output

    def identity(self, role: str) -> dict:
        spec = self.models[role]
        output = {"model": spec["repo_id"], "revision": spec["revision"],
                  "artifact_id": spec["artifact_id"], "pipeline": self.pipeline,
                  "normalization": self.normalization, "runtime_id": self.runtime_id}
        if role == "embedding":
            output["dimensions"] = self.embedding_dimensions
        return output

    def require(self, role: str, expected: str = "", *, model: str = "", generation: str = "") -> None:
        if self.error or role not in self.models:
            raise InferenceError("model_missing", "本地模型未准备完成，请核对模型清单。")
        if expected and expected != self.models[role]["artifact_id"]:
            raise InferenceError("artifact_mismatch", "查询模型与索引模型不一致。", 409)
        if model and model != self.models[role].get("repo_id"):
            raise InferenceError("model_mismatch", "查询模型身份不一致。", 409)
        if generation:
            if not self.generation:
                raise InferenceError("generation_unavailable", "当前推理包没有绑定索引 generation。")
            if generation != self.generation:
                raise InferenceError("generation_mismatch", "查询 generation 与模型包不一致。", 409)

    def require_deep(self, *, model: str = "", artifact: str = "", generation: str = "") -> None:
        if self.deep_error or "reranker" not in self.deep_models:
            raise InferenceError("deep_unavailable", "BGE 深度重排当前不可用，请保留即时结果并稍后重试。")
        spec = self.deep_models["reranker"]
        if model and model != spec.get("repo_id"):
            raise InferenceError("model_mismatch", "深度重排模型身份不一致。", 409)
        if artifact and artifact != spec.get("artifact_id"):
            raise InferenceError("artifact_mismatch", "深度重排模型制品不一致。", 409)
        if generation and generation != self.deep_generation:
            raise InferenceError("generation_mismatch", "深度重排 generation 不一致。", 409)

    def deep_rerank(self, query: str, documents: list[str], top_n: int, *,
                    model: str = "", artifact: str = "", generation: str = "", contexts=None) -> dict:
        """Run the approved scalar-logit ONNX path, sequentially on bounded pairs."""
        self.require_deep(model=model, artifact=artifact, generation=generation)
        if contexts is not None:
            raise InferenceError("context_unsupported", "BGE 只重排原始候选；邻文使用独立上下文组织入口。", 422)
        results = self._deep_scores("reranker", query, documents)
        results.sort(key=lambda item: (-item["relevance_score"], item["index"]))
        return {**self.deep_identity("reranker"), "status": "completed", "stage": "deep",
                "results": results[:top_n], "query_truncated": any(item["query_truncated"] for item in results)}

    def organize_context(self, *, model: str = "", artifact: str = "", generation: str = "",
                         query: str = "", hits: list[dict] | None = None) -> dict:
        """Score context windows without changing the caller's evidence order."""
        context = self.deep_models.get("context")
        candidate_count = len(hits or [])
        if self.deep_error or not context:
            return {"status": "unavailable", "stage": "context", "model": model or "ConvMemory-v2",
                    "artifact_id": artifact, "generation": generation or self.deep_generation,
                    "candidate_count": candidate_count, "selected_count": 0,
                    "notice": "ConvMemory 上下文层当前不可用；保留原始证据与邻文。"}
        if model and model not in {context.get("repo_id"), "ConvMemory-v2"}:
            raise InferenceError("model_mismatch", "上下文模型身份不一致。", 409)
        if artifact and artifact != context.get("artifact_id"):
            raise InferenceError("artifact_mismatch", "上下文模型制品不一致。", 409)
        if generation and generation != self.deep_generation:
            raise InferenceError("generation_mismatch", "上下文 generation 不一致。", 409)
        hits = hits or []
        # These are verbatim input windows, never generated paraphrases. The
        # canonical hit and neighbouring EvidenceSpan identities stay upstream.
        windows = ["\n".join(str(hit.get(key) or "") for key in ("title", "before", "text", "after") if hit.get(key)) for hit in hits]
        scores = self._deep_scores("context", query, windows)
        ranks = {item["index"]: rank for rank, item in enumerate(
            sorted(scores, key=lambda item: (-item["relevance_score"], item["index"])), 1)}
        results = []
        for item, hit, window in zip(scores, hits, windows):
            score = item.pop("relevance_score")
            results.append({**item, "id": hit["id"], "context_score": score,
                            "context_rank": ranks[item["index"]], "context": window})
        return {**self.deep_identity("context"), "status": "completed", "stage": "context",
                "candidate_count": candidate_count, "selected_count": len(results),
                "query_truncated": any(item["query_truncated"] for item in results), "results": results}

    def deep_identity(self, role: str) -> dict:
        spec = self.deep_models[role]
        return {"model": spec["repo_id"], "revision": spec["revision"], "artifact_id": spec["artifact_id"],
                "generation": self.deep_generation, "pipeline": self.deep_pipeline,
                "runtime_id": self.deep_runtime_id, "precision": spec["precision"],
                "max_tokens": spec["max_tokens"], "batch_size": 1, "threads": 1}

    def _deep_runner(self, role: str):
        key = f"deep:{role}"
        if self.session_role == key and self.session is not None:
            return self.tokenizers[key], self.session
        # Reuse the existing single resident model slot. This avoids keeping
        # BGE, ConvMemory and the baseline model in memory at the same time.
        self.session = None
        self.session_role = ""
        self.tokenizers.clear()
        self.trim_memory()
        spec = self.deep_models[role]
        folder = Path(spec["directory"])
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        options.add_session_config_entry("session.inter_op.allow_spinning", "0")
        try:
            tokenizer = Tokenizer.from_file(str(bundle_path(folder, spec.get("tokenizer_file", "tokenizer.json"))))
            tokenizer.no_padding()
            # Same pair tokenizer, longest_first truncation, scalar logit,
            # CPU provider and BASIC graph optimization as run_ort_reranker.py.
            tokenizer.enable_truncation(max_length=spec["max_tokens"], strategy="longest_first")
            session = ort.InferenceSession(str(bundle_path(folder, spec.get("model_file", "model.onnx"))),
                                           sess_options=options, providers=["CPUExecutionProvider"])
            if not {item.name for item in session.get_inputs()}.issubset({"input_ids", "attention_mask", "token_type_ids"}):
                raise ValueError("unsupported deep inputs")
        except Exception as exc:
            self.completed_roles.discard(key)
            raise InferenceError("model_load_failed", "深度模型加载失败，已保留即时结果。") from exc
        self.tokenizers[key] = tokenizer
        self.session, self.session_role = session, key
        self.loaded_roles.add(key)
        return tokenizer, session

    def _deep_scores(self, role: str, query: str, documents: list[str]) -> list[dict]:
        deadline = time.monotonic() + self.seconds
        tokenizer, session = self._deep_runner(role)
        results = []
        for index, document in enumerate(documents):
            # Encode once without truncation for an honest token/truncation
            # receipt, then use the audited longest_first policy for inference.
            tokenizer.no_truncation()
            try:
                full = tokenizer.encode(query, document)
                original_query_tokens = len(tokenizer.encode(query, add_special_tokens=False).ids)
            finally:
                tokenizer.enable_truncation(max_length=self.deep_models[role]["max_tokens"], strategy="longest_first")
            encoded = tokenizer.encode(query, document)
            values = {"input_ids": encoded.ids, "attention_mask": encoded.attention_mask,
                      "token_type_ids": encoded.type_ids}
            feeds = {item.name: np.asarray([values[item.name]], dtype=np.int64) for item in session.get_inputs()}
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.completed_roles.discard(f"deep:{role}")
                raise InferenceError("inference_timeout", "深度推理达到时间上限，已保留即时结果。", 504)
            options = ort.RunOptions()
            timer = threading.Timer(remaining, lambda: setattr(options, "terminate", True))
            timer.daemon = True
            timer.start()
            try:
                output = np.asarray(session.run([session.get_outputs()[0].name], feeds, options)[0])
                if output.size != 1 or not np.isfinite(output).all():
                    raise InferenceError("invalid_output", "深度模型输出不符合单候选分数契约。")
            except Exception as exc:
                self.completed_roles.discard(f"deep:{role}")
                if isinstance(exc, InferenceError):
                    raise
                timed_out = time.monotonic() >= deadline
                raise InferenceError("inference_timeout" if timed_out else "inference_failed",
                                     "深度推理未完成，已保留即时结果。", 504 if timed_out else 503) from exc
            finally:
                timer.cancel()
            results.append({"index": index, "relevance_score": float(output.reshape(-1)[0]),
                            "token_count": len(encoded.ids), "truncated": len(encoded.ids) < len(full.ids),
                            "query_truncated": sum(value == 0 for value in encoded.sequence_ids) < original_query_tokens,
                            "input_hash": hashlib.sha256(json.dumps([query, document], ensure_ascii=False).encode()).hexdigest()})
        self.completed_roles.add(f"deep:{role}")
        return results

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
            output = session.run([session.get_outputs()[0].name], feeds, options)[0]
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
            if hidden.ndim != 3 or hidden.shape[-1] != self.embedding_dimensions:
                raise InferenceError("invalid_output", "向量模型输出形状不符合固定契约。")
            weights = mask[..., None].astype(np.float32)
            # The hidden tensor is owned by this call; avoid a second tensor of
            # the same size without changing multiplication/reduction order.
            hidden *= weights
            pooled = hidden.sum(axis=1) / np.maximum(weights.sum(axis=1), 1)
            normalized = pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
            vectors.extend(normalized.tolist())
        return {**self.identity("embedding"), "dimensions": self.embedding_dimensions, "vectors": vectors,
                "token_counts": counts, "truncated": [False] * len(texts)}

    def rerank(self, query: str, documents: list[str], top_n: int, expected: str, contexts=None) -> dict:
        self.require("reranker", expected)
        tokenizer = self.tokenizer("reranker")
        query = self.normalize(query)
        query_encoding = tokenizer.encode(query, add_special_tokens=False)
        query_truncated = len(query_encoding.ids) > 128
        if contexts is not None and (len(contexts) != len(documents) or query_truncated):
            raise InferenceError("context_budget", "上下文实验不允许截断问题或错配邻文。", 422)
        if query_truncated:
            query = query[:query_encoding.offsets[127][1]]
        deadline = time.monotonic() + self.seconds
        results = []
        for index, document in enumerate(documents):
            document = self.normalize(document)
            if contexts is not None:
                from context_window import fit_context
                try:
                    prepared, clipped = fit_context(tokenizer, query, document,
                        self.normalize(contexts[index]["before"]), self.normalize(contexts[index]["after"]))
                except ValueError as exc:
                    raise InferenceError("context_budget", "命中原文超出上下文实验预算。", 422) from exc
                logits, _ = self.run("reranker", [(query, prepared)], deadline)
                if logits.shape != (1, 1):
                    raise InferenceError("invalid_output", "重排模型输出形状不符合固定契约。")
                results.append({"index": index, "relevance_score": float(logits[0, 0]),
                                "windows": 1, "truncated": clipped,
                                "input_hash": hashlib.sha256(prepared.encode()).hexdigest()})
                continue
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
        output = {**self.identity("reranker"), "results": results[:top_n], "query_truncated": query_truncated}
        if contexts is not None:
            from context_window import CONTEXT_POLICY
            output["context_policy"] = CONTEXT_POLICY
        return output


def bundle_path(root: Path, relative: str) -> Path:
    """Reject traversal and symlinks that escape the read-only bundle."""
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("invalid bundle path")
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    return path


def deep_artifact_id(role: str, spec: dict, *, pipeline: str, runtime_id: str) -> str:
    identity = {"role": role, "repo": spec["repo_id"], "revision": spec["revision"],
                "files": {item["path"]: item["sha256"] for item in spec["files"]},
                "model_file": spec.get("model_file", "model.onnx"),
                "tokenizer_file": spec.get("tokenizer_file", "tokenizer.json"),
                "precision": spec["precision"], "max_tokens": int(spec.get("max_tokens", 256)),
                "pipeline": pipeline, "runtime": runtime_id, "truncation": "longest_first"}
    return "stl4-deep-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def artifact_id(role: str, spec: dict, *, pipeline: str = DEFAULT_PIPELINE,
                normalization: str = DEFAULT_NORMALIZATION,
                runtime_id: str = DEFAULT_RUNTIME_ID) -> str:
    files = {item["path"]: item["sha256"] for item in spec["files"]}
    identity = {"repo": spec["repo_id"], "revision": spec["revision"],
                "model_sha256": files["onnx/model.onnx"], "tokenizer_sha256": files["tokenizer.json"],
                "role": role, "pipeline": pipeline, "normalization": normalization,
                "runtime": runtime_id}
    return "stl308-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
