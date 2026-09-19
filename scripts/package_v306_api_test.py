"""Freeze tracked/unignored API source for an isolated NAS integration run."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

root=Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--name", required=True, help="Unique evidence directory name, for example pg-source-20260914-2010")
arguments = parser.parse_args()
if not arguments.name or Path(arguments.name).name != arguments.name or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in arguments.name):
    parser.error("--name must be a simple directory name")
destination=root/"output"/"verification"/"v306"/arguments.name
# Evidence from earlier runs is immutable; choose another name on a rerun.
destination.mkdir(parents=True,exist_ok=False)
listed=subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard","--","api"],cwd=root).decode("utf-8").splitlines()
files=[]
for name in sorted(set(listed)):
    path=root/name
    if not path.is_file():
        continue
    if any(part.lower() in {"data","storage","backups","logs","cache","__pycache__",".env",".venv"} for part in Path(name).parts):
        raise RuntimeError(f"Forbidden source archive path: {name}")
    if path.suffix.lower() not in {".py",".txt",".ini",".json"} and path.name not in {"Dockerfile",".dockerignore"}:
        continue
    if path.suffix==".json" and name!="api/openapi/schema.json":
        continue
    files.append((name,path))
manifest={"base_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),"scope":"isolated_api_source_only_no_production_data","files":[{"path":name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()} for name,path in files]}
archive=destination/"api-source.tar.gz"
with tarfile.open(archive,"w:gz") as bundle:
    for name,path in files:
        bundle.add(path,arcname=name,recursive=False)
manifest["archive_sha256"]=hashlib.sha256(archive.read_bytes()).hexdigest()
(destination/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"archive":str(archive),"sha256":manifest["archive_sha256"],"files":len(files)},ensure_ascii=False))
