"""Package the existing 20261014 exports; no downloads, exports or inference."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "inference_service"))
from artifact_identity import deep_artifact_id

MODELS = {
    "embedding": ("eg2", "eg2-int8", "google/embeddinggemma-2", "914f7f89142e33e77833254d9c9b90c3cef7303b", 8192),
    "reranker": ("bge_reranker", "bge-reranker-int8", "BAAI/bge-reranker-v2-m3", "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e", 512),
    "context": ("convmemory_v2", "convmemory_v2-fp32", "Purdy0228/ConvMemory-v2-Evidence-Reranker", "1dc4b55b08965e2d4378c7d05d308f07752a1be4", 512),
}


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(source: Path, destination: Path, generation: str) -> dict:
    source, destination = source.resolve(), destination.resolve()
    generation = str(UUID(generation))
    # Preserve prior candidates, conversions and interrupted attempts.
    destination.mkdir(parents=True, exist_ok=False)
    bundle = {"schema": 1, "bundle_id": destination.name, "pipeline": "stl4-recommended-deep-v1",
              "generation": generation, "runtime_id": "onnxruntime-1.22.1-cpu-sequential-v1", "models": {}}
    provenance = {}
    for role, (key, folder, repo, revision, tokens) in MODELS.items():
        resolved_path = source / "models" / key / "resolved.json"
        resolved = json.loads(resolved_path.read_text("utf-8"))
        if resolved.get("repo_id", resolved.get("repo")) != repo or resolved.get("revision") != revision:
            raise ValueError(f"Unexpected inherited model identity: {key}")
        conversion_path = source / "onnx" / folder / "conversion.json"
        conversion = json.loads(conversion_path.read_text("utf-8"))
        if conversion.get("source_conversion_sha256"):
            original = source / "onnx" / folder.replace("-int8", "-fp32") / "conversion.json"
            if sha(original) != conversion["source_conversion_sha256"]:
                raise ValueError(f"Original conversion changed: {key}")
            original_spec = json.loads(original.read_text("utf-8"))
            if original_spec.get("source_manifest_sha256") and original_spec["source_manifest_sha256"] != sha(resolved_path):
                raise ValueError(f"Original model manifest changed: {key}")
        target = destination / role
        target.mkdir()
        files = conversion["files"]
        if len({item["path"] for item in files}) != len(files):
            raise ValueError(f"Duplicate conversion file: {key}")
        for item in files:
            name = item["path"]
            if Path(name).name != name:
                raise ValueError("Only immediate exported artifact files are accepted")
            path = conversion_path.parent / name
            if path.stat().st_size != item["bytes"] or sha(path) != item["sha256"]:
                raise ValueError(f"Inherited export checksum changed: {key}/{name}")
            shutil.copy2(path, target / name)
        spec = {"repo_id": repo, "revision": revision, "directory": role,
                "model_file": "model.onnx", "tokenizer_file": "tokenizer.json",
                "precision": conversion["precision"], "max_tokens": tokens, "files": files}
        spec["artifact_id"] = deep_artifact_id(role, spec, pipeline=bundle["pipeline"], runtime_id=bundle["runtime_id"])
        bundle["models"][role] = spec
        provenance[role] = {"source_manifest_sha256": sha(resolved_path), "conversion_sha256": sha(conversion_path)}
    for name in ("manifest.json", "model-lock.json"):
        (destination / name).write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return bundle


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--generation", required=True)
    args = parser.parse_args()
    manifest = prepare(args.source, args.destination, args.generation)
    print(json.dumps({"bundle": str(args.destination), "generation": manifest["generation"],
                      "artifacts": {role: spec["artifact_id"] for role, spec in manifest["models"].items()}}, indent=2))
