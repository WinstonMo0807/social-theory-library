"""Read deployed-source URL resolution without production data or schema requests.

Run with the project's existing Python dependencies. This records declarations,
not successful interactions. No serializers, querysets or permission checks run.
"""
from pathlib import Path
import ast
import inspect
import json
import os
import sys
import csv
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/stl4/public-visual-20261110"
RAW = ROOT / "output/public-visual-20261110/audit"
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings", DATABASE_URL="sqlite:///:memory:",
                  DJANGO_DEBUG="true", PUBLIC_DEPLOYMENT_MODE="false",
                  CELERY_BROKER_URL="memory://", CELERY_RESULT_BACKEND="cache+memory://")
sys.path.insert(0, str(ROOT / "api"))
import django
django.setup()
from django.urls import URLResolver, get_resolver


def location(obj):
    try:
        file = Path(inspect.getsourcefile(obj)).resolve()
        return {"file": file.relative_to(ROOT).as_posix(), "line": inspect.getsourcelines(obj)[1]}
    except (TypeError, OSError, ValueError):
        return None


def qualified(obj):
    return obj.__module__ + "." + obj.__name__ if obj and hasattr(obj, "__name__") else None


def scan_source(obj):
    """Literal fields are search aids; nested services and validation need review."""
    loc = location(obj)
    if not loc:
        return {}
    source = inspect.getsource(obj)
    import textwrap
    tree = ast.parse(textwrap.dedent(source))
    inputs, outputs, calls, errors, schemas = set(), set(), set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id.endswith(("Input", "Output", "Serializer", "Query", "Command")):
            schemas.add(node.id)
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            calls.add(name)
            if name.endswith((".get", ".getlist", ".pop")) and node.args and isinstance(node.args[0], ast.Constant):
                if any(term in name for term in ("data", "params", "query", "validated")):
                    inputs.add(str(node.args[0].value))
            if name.endswith(("ValidationError", "PermissionDenied", "NotFound")):
                errors.add(name)
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    outputs.add(key.value)
    return {"literal_input_candidates": sorted(inputs), "dict_key_candidates": sorted(outputs),
            "calls": sorted(calls), "schema_references": sorted(schemas), "exception_types": sorted(errors)}


rows = []
handlers = {}


def walk(patterns, prefix=""):
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            if not route.startswith("admin/"):
                walk(pattern.url_patterns, route)
            continue
        if not route.startswith("api/"):
            continue
        callback = pattern.callback
        cls = getattr(callback, "cls", getattr(callback, "view_class", None))
        actions = getattr(callback, "actions", None)
        methods = list(actions) if actions else [m for m in getattr(cls, "http_method_names", []) if hasattr(cls, m)]
        if cls is None:
            methods = ["get"]
        serializer = getattr(cls, "serializer_class", None)
        effective_handlers = {}
        for method in methods:
            if method in {"head", "options"}:
                continue
            action = actions[method] if actions else method
            handler = getattr(cls, action, None) if cls else callback
            key = handler.__module__ + "." + handler.__qualname__ if handler else None
            effective_handlers[method] = {"action": action, "source": location(handler), "key": key}
            if key and key not in handlers:
                handlers[key] = scan_source(handler)
        rows.append({"path": "/" + route, "name": pattern.name, "view": qualified(cls or callback),
                     "methods": methods, "actions": actions, "source": location(cls or callback),
                     "handlers": effective_handlers,
                     "permissions": [qualified(p) or str(p) for p in getattr(cls, "permission_classes", [])],
                     "permission_selector": location(getattr(cls, "get_permissions", None)),
                     "serializer": qualified(serializer), "serializer_source": location(serializer),
                     "serializer_selector": location(getattr(cls, "get_serializer_class", None)),
                     "pagination": qualified(getattr(cls, "pagination_class", None)),
                     "search_fields": getattr(cls, "search_fields", None),
                     "ordering_fields": getattr(cls, "ordering_fields", None),
                     "filterset_fields": getattr(cls, "filterset_fields", None),
                     "review_status": "declaration_only; business and runtime review pending"})


walk(get_resolver().url_patterns)
sources = {}
serializers = {}
for row in rows:
    key = row["view"]
    if key not in sources:
        module, name = key.rsplit(".", 1)
        sources[key] = scan_source(getattr(sys.modules[module], name))
    key = row["serializer"]
    if key and key not in serializers:
        module, name = key.rsplit(".", 1)
        cls = getattr(sys.modules[module], name)
        serializers[key] = {"source": location(cls), "declared_fields": {
            name: {"type": type(field).__name__, "required": field.required, "read_only": field.read_only,
                   "write_only": field.write_only, "allow_null": field.allow_null}
            for name, field in getattr(cls, "_declared_fields", {}).items()},
            "model_fields": getattr(getattr(cls, "Meta", None), "fields", None),
            "read_only_fields": getattr(getattr(cls, "Meta", None), "read_only_fields", None),
            "extra_kwargs": getattr(getattr(cls, "Meta", None), "extra_kwargs", None)}

OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)
(RAW / "API_ROUTES.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf8")
(RAW / "API_SOURCE_HINTS.json").write_text(json.dumps({"views": sources, "serializers": serializers},
    ensure_ascii=False, indent=2, default=str), encoding="utf8")
fields = {}
for file in (ROOT / "api").rglob("*.py"):
    if "tests" in file.parts or "migrations" in file.parts:
        continue
    tree = ast.parse(file.read_text(encoding="utf8"))
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        declared = {}
        for stmt in cls.body:
            if not isinstance(stmt, ast.Assign) or not isinstance(stmt.value, ast.Call):
                continue
            kind = ast.unparse(stmt.value.func)
            if not any(x in kind for x in ("Field", "Serializer")):
                continue
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    declared[target.id] = {"type": kind, "line": stmt.lineno,
                        "constraints": {kw.arg: ast.unparse(kw.value) for kw in stmt.value.keywords if kw.arg},
                        "positional_arguments": [ast.unparse(a) for a in stmt.value.args]}
        if declared:
            fields[file.relative_to(ROOT).as_posix() + ":" + cls.name] = declared
(RAW / "FIELD_CONTRACTS.json").write_text(json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf8")
(RAW / "API_METHOD_HINTS.json").write_text(json.dumps(handlers, ensure_ascii=False, indent=2), encoding="utf8")
# Refresh declarations without losing the human-reviewed business notes.
previous = {}
contract_file = OUT / "API_CONTRACTS.csv"
if contract_file.exists():
    with contract_file.open(encoding="utf-8-sig", newline="") as stream:
        previous = {(row["method"], row["path"]): row for row in csv.DictReader(stream)}
def public_template(route):
    """Readable URL parameters; preserve the resolver declaration separately."""
    route = re.sub(r"\(\?P<(\w+)>[^)]+\)", r"{\1}", route)
    route = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", route)
    return route.replace("^", "").replace("$", "").replace(r"\.", ".").replace("/?", "/")


with (OUT / "API_CONTRACTS.csv").open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["method", "path", "public_path_template", "name", "view", "handler", "permission_classes", "permission_selector", "input_candidates", "return_key_candidates", "serializer", "schema_references", "pagination", "errors", "source", "state_transition", "page_mapping", "review_status", "verified_notes"])
    for row in rows:
        for method, handler in row["handlers"].items():
            hint = handlers.get(handler["key"], {})
            old = previous.get((method.upper(), row["path"]), {})
            writer.writerow([method.upper(), row["path"], public_template(row["path"]), row["name"], row["view"], handler["action"],
                ";".join(row["permissions"]), json.dumps(row["permission_selector"]),
                ";".join(hint.get("literal_input_candidates", [])), ";".join(hint.get("dict_key_candidates", [])),
                row["serializer"], ";".join(hint.get("schema_references", [])), row["pagination"], ";".join(hint.get("exception_types", [])),
                json.dumps(handler["source"] or row["source"]), old.get("state_transition", "待追踪服务与任务"),
                old.get("page_mapping", "待对应 COVERAGE.csv"), old.get("review_status", row["review_status"]), old.get("verified_notes", "")])
print(json.dumps({"route_patterns": len(rows), "unique_views": len(sources), "static_serializers": len(serializers),
                  "method_paths": sum(len(set(row["methods"]) - {"head", "options"}) for row in rows),
                  "scope": "local deployed-source resolver; no DB or production requests"}))
