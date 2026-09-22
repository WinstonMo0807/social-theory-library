"""Explicit, resumable preparation of the two pinned offline ONNX artifacts.

Uses only Python's standard library. It does not import or execute a model.
The models already contain portable FP32 ONNX exports from their publishers;
there is no architecture-specific quantization or unpinned export dependency.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import tarfile
import time
import urllib.error
import urllib.request


LOCK_PATH = Path(__file__).resolve().parents[1] / "inference_service/model-lock.json"


def digest(path: Path, algorithm: str = "sha256", prefix: bytes = b"") -> str:
    hasher = hashlib.new(algorithm)
    hasher.update(prefix)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verified(path: Path, record: dict) -> bool:
    if not path.is_file() or path.stat().st_size != record["bytes"]:
        return False
    if record.get("sha256"):
        return digest(path) == record["sha256"]
    prefix = b"blob " + str(record["bytes"]).encode() + b"\0"
    return digest(path, "sha1", prefix) == record["git_oid"]


def download(path: Path, record: dict, url: str) -> None:
    if verified(path, record):
        return
    if path.exists():
        raise RuntimeError(f"Existing file differs from the pinned artifact; preserve and inspect: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    for attempt in range(8):
        if partial.exists() and verified(partial, record):
            partial.replace(path)
            return
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > record["bytes"]:
            raise RuntimeError(f"Oversized partial file requires inspection: {partial}")
        headers = {"User-Agent": "SocialTheoryLibrary/3.0.8 explicit-model-preparation"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as response:
                append = response.status == 206 and offset > 0
                if append and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise RuntimeError("Download server returned a different range")
                written = offset if append else 0
                reported = written
                with partial.open("ab" if append else "wb") as output:
                    for block in iter(lambda: response.read(1024 * 1024), b""):
                        written += len(block)
                        if written > record["bytes"]:
                            raise RuntimeError("Download exceeded the pinned file length")
                        output.write(block)
                        if written - reported >= 8 * 1024 * 1024:
                            output.flush()
                            print(json.dumps({"downloading": record["path"], "bytes": written,
                                              "total_bytes": record["bytes"]}), flush=True)
                            reported = written
            if not verified(partial, record):
                raise RuntimeError(f"Downloaded file failed its pinned checksum: {partial}")
            partial.replace(path)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, http.client.IncompleteRead):
            if attempt == 7:
                # Deliberately suppress signed redirect URLs/proxy credentials.
                raise RuntimeError(f"Could not download {record['path']}; partial retained") from None
            time.sleep(min(2 ** attempt, 4))


def identity(role: str, spec: dict, lock: dict) -> str:
    files = {item["path"]: item["sha256"] for item in spec["files"]}
    values = {"repo": spec["repo_id"], "revision": spec["revision"],
              "model_sha256": files["onnx/model.onnx"], "tokenizer_sha256": files["tokenizer.json"],
              "role": role, "pipeline": lock["pipeline"], "normalization": lock["normalization"],
              "runtime": "onnxruntime-1.22.1-cpu-fp32"}
    return "stl308-" + hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def prepare(destination: Path, lock: dict, offline: bool) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    total = sum(file["bytes"] for model in lock["models"].values() for file in model["files"])
    if not offline and shutil.disk_usage(destination).free < total + 256 * 1024 * 1024:
        raise RuntimeError("Insufficient free disk space for a preserved complete bundle")
    manifest = {"schema": 1, "bundle_id": lock["bundle"], "pipeline": lock["pipeline"],
                "normalization": lock["normalization"], "created_at": datetime.now(timezone.utc).isoformat(),
                "preparation": "publisher-fp32-onnx-no-local-export", "models": {}}
    def prepare_model(item):
        role, model = item
        spec = {"repo_id": model["repo_id"], "revision": model["revision"], "files": []}
        for entry in model["files"]:
            path = destination / role / entry["path"]
            if offline:
                if not verified(path, entry):
                    raise RuntimeError(f"Offline preparation lacks verified {role}/{entry['path']}")
            else:
                url = f"https://huggingface.co/{model['repo_id']}/resolve/{model['revision']}/{entry['path']}"
                download(path, entry, url)
            spec["files"].append({"path": entry["path"], "bytes": path.stat().st_size, "sha256": digest(path)})
            print(json.dumps({"prepared": f"{role}/{entry['path']}", "bytes": path.stat().st_size}), flush=True)
        spec["artifact_id"] = identity(role, spec, lock)
        return role, spec
    # Two fixed models only. Keep each model's files sequential, so interrupted
    # transfers retain independent partials and at most two downloads are active.
    with ThreadPoolExecutor(max_workers=2) as executor:
        for role, spec in executor.map(prepare_model, lock["models"].items()):
            manifest["models"][role] = spec
    manifest["total_bytes"] = total
    content = json.dumps(manifest, ensure_ascii=False, indent=2)
    temporary = destination / "manifest.json.partial"
    temporary.write_text(content + "\n", encoding="utf-8")
    temporary.replace(destination / "manifest.json")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path,
                        help="Exact version directory, for example /models/discovery/v308-fp32-v1")
    parser.add_argument("--offline", action="store_true", help="Verify and package existing artifacts without network")
    parser.add_argument("--archive", type=Path, help="Optional new archive; existing archives are never overwritten")
    args = parser.parse_args()
    lock = json.loads(LOCK_PATH.read_text("utf-8"))
    manifest = prepare(args.destination.resolve(), lock, args.offline)
    if args.archive:
        args.archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(args.archive, "x:gz") as archive:
            archive.add(args.destination, arcname=lock["bundle"], recursive=True,
                        filter=lambda info: None if info.name.endswith(".partial") else info)
    print(json.dumps({"bundle": str(args.destination), "total_bytes": manifest["total_bytes"],
                      "models": {role: spec["artifact_id"] for role, spec in manifest["models"].items()},
                      "archive": str(args.archive) if args.archive else None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
