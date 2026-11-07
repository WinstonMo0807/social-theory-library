"""Pack a clean exported Linux runtime on the workstation, without running Docker.

Input is an unstarted image-only container export, never a business container.
The image inspect JSON supplies its runtime configuration. Replacements are
explicit paths; no workspace-wide copy and no new package installation occurs.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def pack(rootfs, metadata, replacements, tag, output):
    info = json.loads(Path(metadata).read_text(encoding="utf-8"))
    if isinstance(info, list):
        info = info[0]
    if info.get("Os") != "linux" or info.get("Config", {}).get("Volumes"):
        raise ValueError("Only volume-free Linux runtime images are supported")
    files = {}
    for destination, source in replacements.items():
        target = PurePosixPath(destination.lstrip("/"))
        if ".." in target.parts or not target.parts or str(target) in files:
            raise ValueError("Invalid replacement path")
        files[str(target)] = Path(source)
    layer = output.with_suffix(".layer.tar")
    if layer.exists() or output.exists():
        raise FileExistsError("Output already exists; use a new release path")
    seen = set()
    with tarfile.open(rootfs, "r|") as src, tarfile.open(layer, "w", format=tarfile.PAX_FORMAT) as dst:
        for entry in src:
            name = str(PurePosixPath(entry.name)).removeprefix("./")
            if name in files:
                if not entry.isfile():
                    raise ValueError("Replacement must be a regular file: " + name)
                entry = copy.copy(entry)
                entry.size = files[name].stat().st_size
                entry.pax_headers = {}
                with files[name].open("rb") as data:
                    dst.addfile(entry, data)
                seen.add(name)
            else:
                dst.addfile(entry, src.extractfile(entry) if entry.isfile() else None)
        for name in sorted(files.keys() - seen):
            entry = tarfile.TarInfo(name)
            entry.mode, entry.uid, entry.gid = 0o644, 0, 0
            entry.size = files[name].stat().st_size
            with files[name].open("rb") as data:
                dst.addfile(entry, data)
    digest = sha(layer)
    created = datetime.now(timezone.utc).isoformat()
    config = {"architecture": info["Architecture"], "os": info["Os"],
              "created": created, "config": info["Config"],
              "rootfs": {"type": "layers", "diff_ids": ["sha256:" + digest]},
              "history": [{"created": created, "created_by": "workstation runtime packaging"}]}
    config_bytes = json.dumps(config, separators=(",", ":")).encode()
    config_name = hashlib.sha256(config_bytes).hexdigest() + ".json"
    manifest = [{"Config": config_name, "RepoTags": [tag], "Layers": [digest + "/layer.tar"]}]
    with tarfile.open(output, "w") as archive:
        for name, data in [(config_name, config_bytes), ("manifest.json", json.dumps(manifest).encode())]:
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
        archive.add(layer, arcname=digest + "/layer.tar", recursive=False)
    return {"image_id": "sha256:" + config_name[:-5], "archive_sha256": sha(output),
            "bytes": output.stat().st_size, "layers": 1,
            "files": {name: sha(path) for name, path in files.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rootfs", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--replacements", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = pack(args.rootfs, args.metadata, json.loads(args.replacements.read_text(encoding="utf-8")), args.tag, args.output)
    args.output.with_suffix(".manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
