"""Join discovered page paths to deployed API declarations; never claim runtime use."""
from pathlib import Path
import csv
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/stl4/public-visual-20261110"
RAW = ROOT / "output/public-visual-20261110/audit"
web = json.loads((RAW / "WEB_SOURCE_MAP.json").read_text(encoding="utf8"))
api = json.loads((RAW / "API_ROUTES.json").read_text(encoding="utf8"))

def abstract_path(value):
    """Treat interpolation as an opaque segment, retaining literal surrounding path."""
    result, index = "", 0
    while index < len(value):
        if value[index:index+2] == "${":
            index += 2
            depth = 1
            while index < len(value) and depth:
                depth += (value[index] == "{") - (value[index] == "}")
                index += 1
            result += "{dynamic}"
        else:
            result += value[index]
            index += 1
    return result.split("?", 1)[0].replace("/api/", "/", 1).rstrip("/") + "/"

def api_shape(value):
    value = value.removeprefix("/api").replace("^", "").replace("$", "")
    value = re.sub(r"\(\?P<[^>]+>\[\^/\.\]\+\)", "{dynamic}", value)
    value = re.sub(r"<(?:[^:>]+:)?[^>]+>", "{dynamic}", value)
    return value.rstrip("/") + "/"

def matches(left, right):
    a, b = left.strip("/").split("/"), right.strip("/").split("/")
    return len(a) == len(b) and all(x == y or x == "{dynamic}" or y == "{dynamic}" for x, y in zip(a, b))

rows = []
routes = web["routes"] if isinstance(web, dict) else web
for page in routes:
    expanded = [{**request, "path": value} for request in page["requests"]
                for value in (request.get("path_alternatives") or [request.get("path")])]
    for request in expanded:
        if not request.get("path") or not request["path"].startswith("/"):
            continue
        shape = abstract_path(request["path"])
        for endpoint in api:
            if "format" in endpoint["path"] or not matches(shape, api_shape(endpoint["path"])):
                continue
            method = request["method"].lower()
            compatible = method in endpoint["methods"] and not request["requires_review"]
            rows.append({"page": page["route"], "frontend_source": f'{request["file"]}:{request["line"]}',
                "request_expression": request["path"], "method_candidate": request["method"],
                "api_path": endpoint["path"], "view": endpoint["view"],
                "evidence": "literal/template path match; method consistent" if compatible else "path match; method/dispatch unresolved",
                "runtime": "not observed by this static join"})
with (OUT / "PAGE_API_LINKS.csv").open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
print(json.dumps({"page_endpoint_links": len(rows), "pages_with_path_matches": len({r["page"] for r in rows}),
    "limitation": "Dynamic wrappers unresolved; path matches are candidate mappings, not business completion."}))
