from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

from app import compact_cache_inventory, model_paths, probe_models


def hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_file_manifest(root: Path, manifest_path: Path) -> list[dict]:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path == manifest_path or path.name.endswith(".tmp"):
            continue
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": hash_file(path),
            }
        )
    return rows


def write_manifest(probe: dict) -> Path:
    paths = model_paths()
    root = paths["root"]
    root.mkdir(parents=True, exist_ok=True)
    files = build_file_manifest(root, paths["manifest"])
    payload = {
        "schema": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "probe": probe,
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }
    temporary = paths["manifest"].with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(paths["manifest"])
    return paths["manifest"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load PaddleOCR models, run a minimal inference and record a model manifest."
    )
    parser.add_argument("--include-fallback", action="store_true")
    parser.add_argument("--include-structure", action="store_true")
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args()
    probe = probe_models(
        include_fallback=args.include_fallback,
        include_structure=args.include_structure,
    )
    manifest = write_manifest(probe) if probe["available"] and args.write_manifest else None
    result = {
        **probe,
        "manifest_path": str(manifest) if manifest else None,
        "inventory": compact_cache_inventory(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if probe["available"] else 1


if __name__ == "__main__":
    sys.exit(main())
