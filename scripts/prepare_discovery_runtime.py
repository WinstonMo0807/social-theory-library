"""Prepare Linux CPU wheels without installing dependencies or running models."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.utils import canonicalize_name


def wheel_metadata(path):
    with zipfile.ZipFile(path) as archive:
        paths = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(paths) != 1:
            raise RuntimeError(f"Invalid wheel metadata: {path.name}")
        return BytesParser().parsebytes(archive.read(paths[0]))


def linux_missing(wheels):
    metadata = [wheel_metadata(path) for path in wheels.glob("*.whl")]
    versions = {canonicalize_name(item["Name"]): item["Version"] for item in metadata}
    environment = {"implementation_name": "cpython", "implementation_version": "3.12.0",
                   "os_name": "posix", "platform_machine": "x86_64", "platform_python_implementation": "CPython",
                   "platform_release": "", "platform_system": "Linux", "platform_version": "",
                   "python_full_version": "3.12.0", "python_version": "3.12", "sys_platform": "linux", "extra": ""}
    missing = set()
    for item in metadata:
        for value in item.get_all("Requires-Dist", []):
            requirement = Requirement(value)
            if requirement.marker and not requirement.marker.evaluate(environment):
                continue
            version = versions.get(canonicalize_name(requirement.name))
            if version is None:
                missing.add(requirement.name + str(requirement.specifier))
            elif version not in requirement.specifier:
                raise RuntimeError(f"Incompatible prepared versions: {item['Name']} requires {requirement.name}{requirement.specifier}")
    return sorted(missing)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    wheels = destination / "wheels"
    wheels.mkdir(exist_ok=True)
    download = [
            sys.executable, "-m", "pip", "download", "--disable-pip-version-check",
            "--only-binary=:all:", "--python-version", "312", "--implementation", "cp",
            "--abi", "cp312", "--abi", "abi3", "--abi", "none",
            "--platform", "manylinux_2_28_x86_64", "--platform", "manylinux_2_27_x86_64",
            "--platform", "manylinux_2_17_x86_64", "--platform", "manylinux2014_x86_64",
            "--dest", str(wheels),
        ]
    if not args.offline:
        requirements = Path(__file__).resolve().parents[1] / "inference_service/requirements.txt"
        subprocess.run([*download, "-r", str(requirements)], check=True)
    # pip's cross-platform download still evaluates some markers on the host.
    # Explicitly close Linux's dependency set (e.g. hf-xet on x86_64) without
    # installing or importing any downloaded package.
    for _ in range(8):
        missing = linux_missing(wheels)
        if not missing:
            break
        if args.offline:
            raise RuntimeError("Linux dependency wheels missing: " + ", ".join(missing))
        subprocess.run([*download, "--no-deps", *missing], check=True)
    else:
        raise RuntimeError("Linux dependency resolution did not converge")
    entries, locked, names = [], [], set()
    for path in sorted(wheels.glob("*.whl")):
        metadata = wheel_metadata(path)
        name, version = metadata["Name"], metadata["Version"]
        if not name or not version or name.casefold() in names:
            raise RuntimeError(f"Duplicate/missing package identity: {path.name}")
        names.add(name.casefold())
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        locked.append(f"{name}=={version} --hash=sha256:{sha}")
        entries.append({"name": name, "version": version, "file": path.name,
                        "bytes": path.stat().st_size, "sha256": sha})
    if not {"onnxruntime", "tokenizers", "numpy", "fastapi", "uvicorn", "opencc-python-reimplemented"}.issubset(names):
        raise RuntimeError("Missing direct runtime wheels")
    (destination / "requirements-linux.lock").write_text("\n".join(locked) + "\n", encoding="utf-8")
    (destination / "runtime-manifest.json").write_text(json.dumps({
        "python": "CPython 3.12", "platform": "linux-x86_64", "files": entries,
        "total_bytes": sum(item["bytes"] for item in entries),
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"destination": str(destination), "packages": len(entries),
                      "total_bytes": sum(item["bytes"] for item in entries)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
