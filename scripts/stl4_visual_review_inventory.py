"""Refresh reference navigation from the maintained atlas; no app or database execution."""
import csv
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
rows = list(csv.DictReader((ROOT / "docs/stl4/ATLAS_INDEX.csv").open(encoding="utf-8-sig")))
patterns = []
for file in (ROOT / "web/app").rglob("page.tsx"):
    parts = [part for part in file.parent.relative_to(ROOT / "web/app").parts if not part.startswith("(")]
    pattern = "^/" + "/".join(".+" if part.startswith("[...") else "[^/]+" if part.startswith("[") else re.escape(part) for part in parts) + "/?$"
    patterns.append((re.compile(pattern), file.relative_to(ROOT).as_posix()))
shared = {"R34-sub04": ("/", "web/components/site-header.tsx"),
          "R34-main": ("/explore/original", "web/components/shared-citation-overlay.tsx"),
          "R34-sub01": ("/explore/original", "web/components/shared-citation-overlay.tsx"),
          "R34-states": ("/explore/original", "web/components/shared-citation-overlay.tsx"),
          "R34-sub02": ("/recommendations", "web/components/shared-citation-overlay.tsx"),
          "R34-sub03": ("/account/sharing/new", "web/components/research/share-composer.tsx")}
result, missing = [], []
for row in rows:
    item = {key: row[key] for key in ("page", "id", "module", "title", "route", "implementation_status", "visual_gaps")}
    path = re.sub(r"\{([^}]+)\}", r"[\1]", row["route"].split("；")[0].split("及")[0])
    if row["id"].startswith("M30-"):
        item.update(start_path="", route_kind="excluded", route_files=[], implementation_status="按D010排除，本轮不开展检索质量评审")
    elif row["id"] in shared:
        start, component = shared[row["id"]]
        item.update(start_path=start, route_kind="shared", route_files=[component] if component and (ROOT/component).is_file() else [])
    else:
        files = [file for pattern, file in patterns if pattern.fullmatch(path.split("?")[0].split("#")[0])]
        item.update(start_path=path if files else "", route_kind="dynamic" if "[" in path else "page", route_files=files)
        if not files:
            missing.append(row["id"])
    result.append(item)
(ROOT / "api/catalog/data/stl4_visual_atlas.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(f"Reference directory: {len(result)} views; unmatched page entries: {', '.join(missing) or 'none'}; shared/excluded entries are explicit.")
