from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tarfile

from huggingface_hub import __version__ as huggingface_hub_version
from huggingface_hub import snapshot_download


DEFAULT_REPO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
MODEL_FILES = [
    "1_Pooling/config.json",
    "config.json",
    "config_sentence_transformers.json",
    "model.safetensors",
    "modules.json",
    "sentence_bert_config.json",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "unigram.json",
]


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_for(snapshot: Path, *, repo_id: str, revision: str) -> dict:
    missing = [relative for relative in MODEL_FILES if not (snapshot / relative).is_file()]
    if missing:
        raise RuntimeError(f"模型 snapshot 缺少文件：{', '.join(missing)}")
    files = []
    for relative in MODEL_FILES:
        path = snapshot / relative
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return {
        "schema": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo_id": repo_id,
        "revision": revision,
        "huggingface_hub_version": huggingface_hub_version,
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }


def create_archive(cache_root: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz", dereference=True) as handle:
        handle.add(cache_root, arcname="hub", recursive=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and verify the pinned Hugging Face model cache used by Meilisearch."
    )
    parser.add_argument("--repo-id", default=DEFAULT_REPO)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()
    if len(args.revision) != 40 or any(character not in "0123456789abcdef" for character in args.revision):
        raise SystemExit("--revision 必须是 40 位小写 commit hash")

    args.cache_root.mkdir(parents=True, exist_ok=True)
    snapshot = Path(
        snapshot_download(
            repo_id=args.repo_id,
            revision=args.revision,
            cache_dir=args.cache_root,
            allow_patterns=MODEL_FILES,
            max_workers=max(1, min(args.max_workers, 8)),
        )
    )
    if snapshot.name != args.revision:
        raise RuntimeError(f"下载结果 revision 不一致：{snapshot.name}")
    offline_snapshot = Path(
        snapshot_download(
            repo_id=args.repo_id,
            revision=args.revision,
            cache_dir=args.cache_root,
            allow_patterns=MODEL_FILES,
            local_files_only=True,
        )
    )
    if offline_snapshot.resolve() != snapshot.resolve():
        raise RuntimeError("离线复查解析到不同 snapshot")

    # Meilisearch 1.37 embeds hf-hub 0.3.2. That Rust client resolves even an
    # exact commit through refs/<revision> before opening snapshots/<commit>.
    # Python snapshot_download does not create that ref for commit revisions.
    repo_cache = snapshot.parent.parent
    revision_ref = repo_cache / "refs" / args.revision
    revision_ref.parent.mkdir(parents=True, exist_ok=True)
    revision_ref.write_text(args.revision, encoding="utf-8")
    if revision_ref.read_text(encoding="utf-8") != args.revision:
        raise RuntimeError("Meilisearch revision ref 写入后复核失败")

    manifest = manifest_for(snapshot, repo_id=args.repo_id, revision=args.revision)
    manifest["meilisearch_revision_ref"] = revision_ref.relative_to(args.cache_root).as_posix()
    manifest_path = args.cache_root / "library-huggingface-model-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if args.archive:
        create_archive(args.cache_root, args.archive)
    print(
        json.dumps(
            {
                "snapshot": str(snapshot),
                "manifest": str(manifest_path),
                "archive": str(args.archive) if args.archive else None,
                "meilisearch_revision_ref": str(revision_ref),
                "file_count": manifest["file_count"],
                "total_bytes": manifest["total_bytes"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
