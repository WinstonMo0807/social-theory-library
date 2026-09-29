import importlib.util
import subprocess
import tarfile
from pathlib import Path
import pytest


def test_package_uses_commit_not_large_local_artifacts_and_refuses_runtime_blob(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/package_release_source.py"
    spec = importlib.util.spec_from_file_location("release_source", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    repo = tmp_path / "repo"
    repo.mkdir()
    def git(*args):
        return subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.org", *args],
                              cwd=repo, capture_output=True, check=True)
    git("init")
    (repo / "app.py").write_text("print('fixture')\n")
    route = repo / "web/app/admin/backups"
    route.mkdir(parents=True)
    (route / "page.tsx").write_text("export default function Page(){return null;}\n")
    storage_route = repo / "web/app/admin/storage"
    storage_route.mkdir(parents=True)
    (storage_route / "page.tsx").write_text("export default function Page(){return null;}\n")
    git("add", "app.py", "web"); git("commit", "-m", "source")
    (repo / "model.onnx").write_bytes(b"local model")
    output = tmp_path / "source.tar.gz"
    report = module.package_source(repo, "HEAD", output)
    assert report["archive_files"] == 3
    with tarfile.open(output) as archive:
        assert "app.py" in archive.getnames() and "web/app/admin/backups/page.tsx" in archive.getnames()
    with pytest.raises(ValueError, match="overwrite"):
        module.package_source(repo, "HEAD", output)
    git("add", "model.onnx"); git("commit", "-m", "forbidden fixture")
    with pytest.raises(ValueError, match="Forbidden"):
        module.package_source(repo, "HEAD", tmp_path / "bad.tar.gz")
