"""Build a NAS runtime on the workstation; never print the bearer credential.

Download CPython 3.12 Linux wheels first as described in README.md. The NAS
reuses its existing API image and only unpacks this verified artifact.
"""
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import tarfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / ".local/stl-mcp/public-build"


def main():
    import win32crypt
    runtime = BUILD / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    for wheel in sorted((BUILD / "wheels").glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                path = Path(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name:
                    raise ValueError("Unsafe wheel entry")
            archive.extractall(runtime / "vendor")
    for name in ("bridge.py", "domain.py", "server.py", "public_server.py"):
        shutil.copyfile(Path(__file__).with_name(name), runtime / name)
    manifest = {str(path.relative_to(runtime)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(runtime.rglob("*")) if path.is_file()}
    (BUILD / "runtime-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with tarfile.open(BUILD / "runtime.tgz", "w:gz") as archive:
        archive.add(runtime, arcname="runtime")
    token_path = ROOT / ".local/stl-mcp/public-token.dpapi"
    if not token_path.exists():
        token = secrets.token_urlsafe(48).encode("ascii")
        token_path.write_bytes(win32crypt.CryptProtectData(token, "STL MCP", None, None, None, 0))
    token = win32crypt.CryptUnprotectData(token_path.read_bytes(), None, None, None, 0)[1]
    config = json.loads((ROOT / ".local/stl-mcp/config.json").read_text(encoding="utf-8"))
    config = {**{key: config[key] for key in ("actor_id", "token_version", "allowed_work_ids", "required_sections")},
              "work_scope": config.get("work_scope", "selected")}
    expires = int(time.time()) + 30 * 86400
    (BUILD / "runtime-config.json").write_text(json.dumps(config), encoding="utf-8")
    (BUILD / "gateway-auth.json").write_text(json.dumps({
        "token_sha256": hashlib.sha256(token).hexdigest(), "expires_at": expires,
        "allowed_hosts": ["books.winstonmo.com"], "allowed_origins": ["https://books.winstonmo.com"]}), encoding="utf-8")
    metadata = {"sha256": hashlib.sha256((BUILD / "runtime.tgz").read_bytes()).hexdigest(),
                "files": len(manifest), "archive_bytes": (BUILD / "runtime.tgz").stat().st_size, "expires_at": expires}
    (BUILD / "package.json").write_text(json.dumps(metadata), encoding="utf-8")
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
