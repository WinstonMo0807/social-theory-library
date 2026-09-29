"""Archive one exact Git commit, excluding runtime/build data by construction.

Unlike tarring the NAS application directory, git archive never follows local
model, dependency, backup or previous release directories.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile


def package_source(root, ref, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    commit = subprocess.check_output(["git", "rev-parse", "--verify", ref + "^{commit}"], cwd=root, text=True).strip()
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    if output.exists() or manifest_path.exists():
        raise ValueError("Refusing to overwrite an existing release artifact")
    listing = subprocess.check_output(["git", "ls-tree", "-rlz", commit], cwd=root).split(b"\0")
    count = 0
    for entry in filter(None, listing):
        metadata, raw = entry.split(b"\t", 1)
        mode, kind, _oid, size = metadata.decode().split()
        path = PurePosixPath(raw.decode("utf-8"))
        parts = {part.casefold() for part in path.parts}
        if (kind != "blob" or mode not in {"100644", "100755"} or int(size) > 10 * 1024 * 1024 or
                parts.intersection({"node_modules", ".venv", "__pycache__", "dist", ".next"}) or
                path.suffix.casefold() in {".pdf", ".caj", ".sqlite", ".sqlite3", ".db", ".dump", ".onnx", ".whl", ".zip", ".gz", ".key", ".pem"} or
                path.name.startswith(".env") and path.name != ".env.example" or
                path.parts[:2] == ("api", "data") or
                path.parts[0] in {"data", "storage", "models", "backups", "output", "tmp", "release", ".codex-deploy-temp", ".codex-local-preview"}):
            raise ValueError("Forbidden release source path: " + str(path))
        count += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "archive", "--format=tar.gz", "--output=" + str(output), commit], cwd=root, check=True)
    with tarfile.open(output, "r:gz") as archive:
        actual = sum(member.isfile() for member in archive)
    manifest = {"commit": commit, "git_files": count, "archive_files": actual,
                "archive_bytes": output.stat().st_size, "source_only": True,
                "archive_sha256": hashlib.file_digest(output.open("rb"), "sha256").hexdigest()}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(package_source(Path(__file__).resolve().parents[1], args.ref, args.output)))
