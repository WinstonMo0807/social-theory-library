"""Run as root on the NAS: stage / expose / rollback one isolated MCP service.

No builds, API restarts, database migrations or plaintext credential output.
Upload the locally built package and this file to a fresh release directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

API = "social-science-library-api-1"
EDGE = "social-science-library-edge-1"
SERVICE = "stl-mcp"
BASE = Path("/volume2/library/stl-mcp")


def run(*args):
    result = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode().strip()


def inspect(name):
    return json.loads(run("docker", "inspect", name))[0]


def sha(value):
    return hashlib.sha256(value).hexdigest()


def write(path, data, mode=0o600):
    # Existing template is a bind-mounted file: preserve its inode.
    path.write_bytes(data)
    path.chmod(mode)


def inventory():
    rows = json.loads(run("docker", "inspect", *run("docker", "ps", "-q").split()))
    return {row["Name"].lstrip("/"): {"id": row["Id"], "image": row["Image"], "started_at": row["State"]["StartedAt"]}
            for row in rows if row["Name"].lstrip("/") != SERVICE}


def stage(release):
    os.umask(0o077)
    if subprocess.run(["docker", "inspect", SERVICE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        raise ValueError("MCP container already exists; inspect it before replacing anything")
    api, edge = inspect(API), inspect(EDGE)
    expected = json.loads((release / "nas-inventory.json").read_text())
    if any(inspect(name)["Image"] != expected[name]["image"] for name in (API, EDGE)):
        raise ValueError("API or edge image changed since preparation")
    write(release / "before-services.json", json.dumps(inventory()).encode())
    archive_path = release / "runtime.tgz"
    package = json.loads((release / "package.json").read_text())
    if sha(archive_path.read_bytes()) != package["sha256"]:
        raise ValueError("Runtime archive checksum mismatch")
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            target = (release / member.name).resolve()
            if not target.is_relative_to(release / "runtime") or not (member.isdir() or member.isfile()):
                raise ValueError("Unsafe runtime archive entry")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
    manifest = json.loads((release / "runtime-manifest.json").read_text())
    for name, digest in manifest.items():
        path = (release / "runtime" / name).resolve()
        if not path.is_relative_to(release / "runtime") or sha(path.read_bytes()) != digest:
            raise ValueError("Runtime file checksum mismatch")
    for path in (release / "runtime").rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    (release / "runtime").chmod(0o755)
    for path in (BASE, BASE / "config", BASE / "state"):
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, 100, 101)
        path.chmod(0o700)
    for source, destination in (("runtime-config.json", "runtime.json"), ("gateway-auth.json", "auth.json")):
        path = BASE / "config" / destination
        if path.exists():
            raise ValueError("Existing MCP configuration must be reviewed before replacement")
        write(path, (release / source).read_bytes())
        os.chown(path, 100, 101)
    # Credentials remain on the NAS. Never emit inspect.Config.Env or this file.
    environment = {}
    for item in api["Config"]["Env"]:
        key, value = item.split("=", 1)
        if "\n" in value or "\r" in value:
            raise ValueError("Multiline environment requires explicit handling")
        environment[key] = value
    environment.update(STL_MCP_BACKEND="django", STL_MCP_CONFIG="/run/stl-mcp/runtime.json",
                       STL_MCP_STATE_DIR="/var/lib/stl-mcp", STL_MCP_HTTP_AUTH_FILE="/run/stl-mcp/auth.json",
                       PYTHONPATH="/opt/stl-mcp/vendor:/app", PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1",
                       WEB_CONCURRENCY="1", DJANGO_DEBUG="false")
    env_file = BASE / "container.env"
    write(env_file, "\n".join(f"{key}={value}" for key, value in environment.items()).encode())
    args = ["docker", "run", "-d", "--name", SERVICE, "--restart", "unless-stopped",
            "--network", "social-science-library_backend", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--memory", "384m", "--memory-swap", "384m",
            "--cpus", "0.5", "--pids-limit", "96", "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m",
            "--env-file", str(env_file), "--workdir", "/app", "--entrypoint", "python",
            "--mount", f"type=bind,src={release / 'runtime'},dst=/opt/stl-mcp,readonly",
            "--mount", f"type=bind,src={BASE / 'config'},dst=/run/stl-mcp,readonly",
            "--mount", f"type=bind,src={BASE / 'state'},dst=/var/lib/stl-mcp"]
    for mount in api["Mounts"]:
        if mount["Destination"] in {"/data/archive", "/data/public"}:
            args += ["--mount", f"type=bind,src={mount['Source']},dst={mount['Destination']},readonly"]
    args += [api["Image"], "/opt/stl-mcp/public_server.py"]
    container_id = run(*args)
    write(release / "service.json", json.dumps({"id": container_id, "image": api["Image"]}).encode())
    if inventory() != json.loads((release / "before-services.json").read_text()):
        raise ValueError("Existing services changed during staging; investigate before exposing")
    print(json.dumps({"staged": True, "id": container_id, "files": len(manifest), "host_ports": []}))


def edge_template():
    edge = inspect(EDGE)
    return Path(next(row["Source"] for row in edge["Mounts"] if row["Destination"] == "/etc/nginx/templates/default.conf.template"))


def expose(release):
    template = edge_template()
    original = template.read_bytes()
    if b"stl_mcp_api" in original or b"location = /mcp" in original:
        raise ValueError("Existing MCP route must be inspected before modification")
    write(release / "edge-template.before", original)
    compiled = subprocess.run(["docker", "exec", EDGE, "cat", "/etc/nginx/conf.d/default.conf"], check=True, stdout=subprocess.PIPE).stdout
    write(release / "edge-compiled.before", compiled)
    snippet = (release / "nginx-location.conf").read_text()
    zones = 'limit_req_zone $binary_remote_addr zone=stl_mcp_api:1m rate=5r/s;\nlimit_conn_zone $server_name zone=stl_mcp_connections:1m;\n'
    text = original.decode()
    marker = "server {\n"
    if text.count(marker) != 1:
        raise ValueError("Unexpected Nginx server layout")
    candidate = (zones + text.replace(marker, marker + snippet + "\n", 1)).encode()
    write(release / "edge-template.candidate", candidate)
    write(release / "edge-change.json", json.dumps({"before": sha(original), "after": sha(candidate), "template": str(template)}).encode())
    try:
        if template.read_bytes() != original:
            raise ValueError("Nginx template changed concurrently")
        # Preserve source mode as this is shared with the edge container.
        mode = template.stat().st_mode & 0o777
        write(template, candidate, mode)
        run("docker", "exec", EDGE, "/docker-entrypoint.d/20-envsubst-on-templates.sh")
        run("docker", "exec", EDGE, "nginx", "-t")
        run("docker", "exec", EDGE, "nginx", "-s", "reload")
    except Exception:
        rollback(release)
        raise
    print(json.dumps({"exposed": True, "path": "/mcp", "before": sha(original), "after": sha(candidate)}))


def rollback(release):
    change = json.loads((release / "edge-change.json").read_text())
    path = edge_template()
    if sha(path.read_bytes()) != change["after"]:
        raise ValueError("Nginx changed after this release; refusing to overwrite another change")
    write(path, (release / "edge-template.before").read_bytes(), path.stat().st_mode & 0o777)
    run("docker", "exec", EDGE, "/docker-entrypoint.d/20-envsubst-on-templates.sh")
    run("docker", "exec", EDGE, "nginx", "-t")
    run("docker", "exec", EDGE, "nginx", "-s", "reload")
    print(json.dumps({"rolled_back": True, "service_retained_for_investigation": SERVICE}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["stage", "expose", "rollback"])
    parser.add_argument("release", type=Path)
    arguments = parser.parse_args()
    release = arguments.release.resolve()
    if not release.is_relative_to("/volume2/library/stl-releases") or not release.is_dir():
        raise ValueError("Expected an existing release inside /volume2/library/stl-releases")
    globals()[arguments.action](release)
