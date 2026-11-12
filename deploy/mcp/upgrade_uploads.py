"""NAS operator: add the existing website upload channel to the MCP service.

Sources are prepared on the workstation. No file trials, business migrations,
dependency builds or credential output. Keep the previous container for rollback.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

SERVICE = "stl-mcp"
CANDIDATE = "stl-mcp-upload-candidate"
PREVIOUS = "stl-mcp-before-uploads-20261112"
NETWORK = "social-science-library_backend"
EDGE = "social-science-library-edge-1"


def run(*args, timeout=30):
    return subprocess.check_output(args, stderr=subprocess.PIPE, timeout=timeout).decode().strip()


def inspect(name):
    return json.loads(run("docker", "inspect", name))[0]


def private(path, data):
    path.write_bytes(data)
    path.chmod(0o600)


def main(release):
    os.umask(0o077)
    original, api, edge = inspect(SERVICE), inspect("social-science-library-api-1"), inspect(EDGE)
    old_runtime = Path(next(row["Source"] for row in original["Mounts"] if row["Destination"] == "/opt/stl-mcp"))
    runtime = release / "runtime"
    runtime.mkdir(mode=0o755)
    runtime.chmod(0o755)
    shutil.copytree(old_runtime / "vendor", runtime / "vendor", copy_function=os.link)
    for name in ("bridge.py", "domain.py", "server.py", "public_server.py"):
        shutil.copyfile(release / name, runtime / name)
        (runtime / name).chmod(0o644)
    private(release / "container.before.json", json.dumps(original).encode())
    private(release / "api.before.json", json.dumps(api).encode())
    environment = dict(item.split("=", 1) for item in original["Config"]["Env"])
    env_file = release / "container.env"
    private(env_file, "\n".join(f"{key}={value}" for key, value in environment.items()).encode())
    args = ["docker", "run", "-d", "--name", CANDIDATE, "--restart", "unless-stopped", "--network", NETWORK,
            "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--memory", "512m",
            "--memory-swap", "512m", "--cpus", "0.5", "--pids-limit", "96", "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=32m",
            "--env-file", str(env_file), "--workdir", "/app", "--entrypoint", "python",
            "--mount", f"type=bind,src={runtime},dst=/opt/stl-mcp,readonly"]
    for mount in original["Mounts"]:
        if mount["Destination"] != "/opt/stl-mcp":
            args += ["--mount", f"type=bind,src={mount['Source']},dst={mount['Destination']}" + (",readonly" if not mount["RW"] else "")]
    incoming = next(row["Source"] for row in api["Mounts"] if row["Destination"] == "/data/incoming")
    args += ["--mount", f"type=bind,src={incoming},dst=/data/incoming", api["Image"], "/opt/stl-mcp/public_server.py"]
    run(*args)
    for attempt in range(60):
        logs = subprocess.run(["docker", "logs", CANDIDATE], capture_output=True).stderr.decode()
        if "Application startup complete" in logs:
            break
        if "Traceback" in logs or inspect(CANDIDATE)["State"]["Status"] == "exited":
            private(release / "startup.log", logs.encode())
            raise RuntimeError("MCP startup failed; original service retained. See the private startup log.")
        if attempt == 59:
            raise RuntimeError("MCP startup did not finish; original service retained.")
        time.sleep(1)
    template = Path(next(row["Source"] for row in edge["Mounts"] if row["Destination"] == "/etc/nginx/templates/default.conf.template"))
    before = template.read_bytes()
    private(release / "nginx.before", before)
    text = before.decode()
    marker = "location ^~ /mcp/ {"
    snippet = (release / "nginx-location.conf").read_text()
    upload = snippet[snippet.index("location ^~ /mcp/uploads/ {"):snippet.index(marker)]
    if "location ^~ /mcp/uploads/ {" in text:
        raise RuntimeError("An upload route already exists; preserve the active operator's configuration.")
    if marker not in text:
        raise RuntimeError("Existing MCP route is missing; original service retained.")
    candidate = text.replace(marker, upload + marker, 1).encode()
    address = original["NetworkSettings"]["Networks"][NETWORK]["IPAddress"]
    switched = False
    try:
        run("docker", "stop", "--time", "120", SERVICE, timeout=135)
        run("docker", "network", "disconnect", NETWORK, SERVICE)
        run("docker", "rename", SERVICE, PREVIOUS)
        switched = True
        run("docker", "network", "disconnect", NETWORK, CANDIDATE)
        run("docker", "rename", CANDIDATE, SERVICE)
        run("docker", "network", "connect", "--ip", address, "--alias", SERVICE, NETWORK, SERVICE)
        if template.read_bytes() != before:
            raise RuntimeError("Nginx changed concurrently; refusing to overwrite.")
        template.write_bytes(candidate)  # Preserve the bind-mounted inode.
        run("docker", "exec", EDGE, "/docker-entrypoint.d/20-envsubst-on-templates.sh")
        run("docker", "exec", EDGE, "nginx", "-t")
        run("docker", "exec", EDGE, "nginx", "-s", "reload")
    except BaseException:
        if template.read_bytes() == candidate:
            template.write_bytes(before)
            run("docker", "exec", EDGE, "/docker-entrypoint.d/20-envsubst-on-templates.sh")
            run("docker", "exec", EDGE, "nginx", "-s", "reload")
        if switched:
            current = subprocess.run(["docker", "inspect", SERVICE], capture_output=True)
            if current.returncode == 0:
                run("docker", "stop", "--time", "120", SERVICE, timeout=135)
                subprocess.run(["docker", "network", "disconnect", NETWORK, SERVICE], capture_output=True)
                run("docker", "rename", SERVICE, "stl-mcp-upload-failed-20261112")
            run("docker", "rename", PREVIOUS, SERVICE)
            run("docker", "network", "connect", "--ip", address, NETWORK, SERVICE)
            run("docker", "start", SERVICE)
        else:
            if NETWORK not in inspect(SERVICE)["NetworkSettings"]["Networks"]:
                run("docker", "network", "connect", "--ip", address, NETWORK, SERVICE)
            run("docker", "start", SERVICE)
        raise
    report = {"deployed": True, "service": SERVICE, "previous_container": PREVIOUS, "image": api["Image"],
              "upload_path": "/mcp/uploads/", "business_rules": "original website upload views",
              "file_trials_run": False, "extra_tests_run": False, "memory_mib": 512}
    private(release / "result.json", json.dumps(report, indent=2).encode())
    print(json.dumps(report))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
