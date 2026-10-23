"""Prepare hashed Linux service wheels without installing packages or running models."""
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
        paths = [name for name in archive.namelist() if name.count("/") == 1 and name.endswith(".dist-info/METADATA")]
        if len(paths) != 1:
            raise RuntimeError(f"Invalid wheel metadata: {path.name}")
        return BytesParser().parsebytes(archive.read(paths[0]))


def linux_missing(wheels, python_version="3.12", requested_extras=None):
    metadata = [wheel_metadata(path) for path in wheels.glob("*.whl")]
    versions = {canonicalize_name(item["Name"]): item["Version"] for item in metadata}
    if len(versions) != len(metadata):
        raise RuntimeError("Duplicate package versions in prepared wheels")
    environment = {"implementation_name": "cpython", "implementation_version": python_version + ".0",
                   "os_name": "posix", "platform_machine": "x86_64", "platform_python_implementation": "CPython",
                   "platform_release": "", "platform_system": "Linux", "platform_version": "",
                   "python_full_version": python_version + ".0", "python_version": python_version, "sys_platform": "linux", "extra": ""}
    extras = {canonicalize_name(name): set(values) for name, values in (requested_extras or {}).items()}
    # Extras can introduce further extras. Close that graph before checking versions.
    changed = True
    while changed:
        changed = False
        for item in metadata:
            contexts = {"", *extras.get(canonicalize_name(item["Name"]), set())}
            for value in item.get_all("Requires-Dist", []):
                requirement = Requirement(value)
                if requirement.marker and not any(requirement.marker.evaluate({**environment, "extra": extra}) for extra in contexts):
                    continue
                selected = extras.setdefault(canonicalize_name(requirement.name), set())
                if not requirement.extras.issubset(selected):
                    selected.update(requirement.extras)
                    changed = True
    missing = set()
    for item in metadata:
        contexts = {"", *extras.get(canonicalize_name(item["Name"]), set())}
        for value in item.get_all("Requires-Dist", []):
            requirement = Requirement(value)
            if requirement.marker and not any(requirement.marker.evaluate({**environment, "extra": extra}) for extra in contexts):
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
    parser.add_argument("--requirements", type=Path)
    parser.add_argument("--python-version", choices=["3.11", "3.12"], default="3.12")
    args = parser.parse_args()
    requirements = args.requirements or Path(__file__).resolve().parents[1] / "inference_service/requirements.txt"
    roots = [Requirement(line.strip()) for line in requirements.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    roots.append(Requirement("pip==26.2.2"))
    extras = {canonicalize_name(item.name): item.extras for item in roots}
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    wheels = destination / "wheels"
    wheels.mkdir(exist_ok=True)
    download = [
            sys.executable, "-m", "pip", "download", "--disable-pip-version-check",
            "--only-binary=:all:", "--python-version", args.python_version, "--implementation", "cp",
            "--abi", "cp" + args.python_version.replace(".", ""), "--abi", "abi3", "--abi", "none",
            "--platform", "manylinux_2_28_x86_64", "--platform", "manylinux_2_27_x86_64",
            "--platform", "manylinux_2_17_x86_64", "--platform", "manylinux2014_x86_64",
            "--dest", str(wheels),
        ]
    if args.python_version == "3.11":
        download.extend(["--platform", "manylinux_2_35_x86_64", "--platform", "manylinux_2_36_x86_64"])
    if not args.offline:
        subprocess.run([*download, "-r", str(requirements), "pip==26.2.2"], check=True)
    # pip's cross-platform download still evaluates some markers on the host.
    # Explicitly close Linux's dependency set (e.g. hf-xet on x86_64) without
    # installing or importing any downloaded package.
    for _ in range(8):
        missing = linux_missing(wheels, args.python_version, extras)
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
    prepared = {canonicalize_name(item["name"]): item["version"] for item in entries}
    for requirement in roots:
        version = prepared.get(canonicalize_name(requirement.name))
        if version is None or version not in requirement.specifier:
            raise RuntimeError(f"Missing/incompatible direct runtime wheel: {requirement}")
    (destination / "requirements-linux.lock").write_text("\n".join(locked) + "\n", encoding="utf-8")
    (destination / "runtime-manifest.json").write_text(json.dumps({
        "python": "CPython " + args.python_version, "platform": "linux-x86_64", "files": entries,
        "requirements_sha256": hashlib.sha256(requirements.read_bytes()).hexdigest(),
        "total_bytes": sum(item["bytes"] for item in entries),
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"destination": str(destination), "packages": len(entries),
                      "total_bytes": sum(item["bytes"] for item in entries)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
