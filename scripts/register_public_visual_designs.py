"""Register inspected native Image Gen outputs; never generates substitute pictures."""
import argparse
import csv
import hashlib
import json
import shutil
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/stl4/public-visual-20261110"
parser = argparse.ArgumentParser()
parser.add_argument("input", help="JSON list of inspected image records")
args = parser.parse_args()
records = json.loads(Path(args.input).read_text(encoding="utf-8"))
index_path = BASE / "DESIGN_IMAGES.json"
index = json.loads(index_path.read_text(encoding="utf-8"))
manifest = json.loads((BASE / "DESIGN_MANIFEST.json").read_text(encoding="utf-8"))
by_id = {d["id"]: d for d in manifest}
for existing in index:
    if existing["status"] == "generated_inspected":
        by_id[existing["id"]].update(image=existing["path"], version=existing["version"],
                                      status="generated_inspected", inspection_notes=existing.get("notes", ""))
for record in records:
    design = by_id[record["id"]]
    assert record["status"] in {"generated_inspected", "superseded", "needs_revision"}
    source = Path(record["source"])
    raw = source.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", source
    width, height = struct.unpack(">II", raw[16:24])
    relative = f"output/public-visual-20261110/design/{record['id']}-{record['version']}.png"
    destination = ROOT / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        assert destination.read_bytes() == raw, "Refuse overwriting a different design version"
    else:
        shutil.copy2(source, destination)
    record.update(path=relative, sha256=hashlib.sha256(raw).hexdigest(), dimensions=[width, height],
                  generator="built-in image_gen", synthetic_content=True)
    index = [r for r in index if (r["id"], r["version"]) != (record["id"], record["version"])]
    if record["status"] == "generated_inspected":
        for old in index:
            if old["id"] == record["id"]:
                old["status"] = "superseded"
        design.update(status="generated_inspected", version=record["version"], image=relative,
                      inspection_notes=record["notes"])
    index.append(record)
for image_record in index:
    raw = (ROOT / image_record["path"]).read_bytes()
    image_record.update(sha256=hashlib.sha256(raw).hexdigest(),
                        dimensions=list(struct.unpack(">II", raw[16:24])),
                        generator="built-in image_gen", synthetic_content=True)
index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
(BASE/"DESIGN_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
with (BASE/"COVERAGE.csv").open(encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))
for row in rows:
    designs = [d for d in manifest if row["id"] in d["coverage"]]
    ready = [d for d in designs if d["status"] == "generated_inspected"]
    row["design_version"] = " ; ".join(f"{d['id']} {d['version']} {d['image']}" for d in ready)
    if designs:
        pending = [d["id"] for d in designs if d["status"] != "generated_inspected"]
        row["uncovered_reason"] = ("待生成/核对设计：" + ",".join(pending) + "；" if pending else "") + "实现和逐消费者运行验证待完成。"
with (BASE/"COVERAGE.csv").open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
pending = [d["id"] for d in manifest if d["status"] != "generated_inspected"]
gate = {"status": "pending" if pending else "ready_for_implementation_review",
        "planned_designs": len(manifest), "generated_inspected":len(manifest)-len(pending),
        "pending":pending, "meaning":"Image existence and explicit mapping only; full design/business correspondence and responsive review still required before UI implementation."}
(BASE/"DESIGN_GATE.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({k:v for k,v in gate.items() if k not in {"pending", "meaning"}}, ensure_ascii=False))
