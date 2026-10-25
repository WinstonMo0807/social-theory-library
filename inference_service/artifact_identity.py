"""Shared identity for the prepared deep bundle and its offline runtime."""
import hashlib
import json


def deep_artifact_id(role: str, spec: dict, *, pipeline: str, runtime_id: str) -> str:
    identity = {"role": role, "repo": spec["repo_id"], "revision": spec["revision"],
                "files": {item["path"]: item["sha256"] for item in spec["files"]},
                "model_file": spec.get("model_file", "model.onnx"),
                "tokenizer_file": spec.get("tokenizer_file", "tokenizer.json"),
                "precision": spec["precision"], "max_tokens": int(spec.get("max_tokens", 256)),
                "pipeline": pipeline, "runtime": runtime_id, "truncation": "longest_first"}
    if role == "embedding":
        identity.update(truncation="reject", dimensions=768, pooling="exported-mean-l2",
                        prompt="eg2-search-result-title-v1", normalization="stl-t2s-dehyphen-nfkc-v1")
    return "stl4-deep-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
