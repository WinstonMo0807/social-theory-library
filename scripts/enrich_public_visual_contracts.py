"""Add source-resolved contracts without executing business logic or databases.

Read inherited handlers, named serializers, pagination and local source calls.
Keep these source facts separate from manual notes and runtime observations.
"""
from pathlib import Path
import ast
import csv
import inspect
import importlib
import json
import os
import sys
import textwrap
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/stl4/public-visual-20261110"
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings", DATABASE_URL="sqlite:///:memory:",
                  DJANGO_DEBUG="true", PUBLIC_DEPLOYMENT_MODE="false",
                  CELERY_BROKER_URL="memory://", CELERY_RESULT_BACKEND="cache+memory://")
sys.path.insert(0, str(ROOT / "api"))
import django
django.setup()
from django.db import connection
from django.urls import URLResolver, get_resolver
from rest_framework.serializers import BaseSerializer


def no_database(execute, sql, params, many, context):
    raise RuntimeError("Contract enrichment must not access a database")


def location(obj):
    try:
        path = Path(inspect.getsourcefile(obj)).resolve().relative_to(ROOT)
        return f"{path.as_posix()}:{inspect.getsourcelines(obj)[1]}"
    except (ValueError, TypeError, OSError):
        return ""


def qualified(obj):
    return f"{obj.__module__}.{obj.__qualname__}"


def resolve(expr, namespace, cls):
    if isinstance(expr, ast.Name):
        return cls if expr.id == "self" else namespace.get(expr.id)
    if isinstance(expr, ast.Attribute):
        parent = resolve(expr.value, namespace, cls)
        if parent is not None:
            try:
                return inspect.getattr_static(parent, expr.attr)
            except AttributeError:
                pass
    return None


def describe(obj, cls=None):
    where = location(obj)
    if not where.startswith("api/"):
        return None
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(obj)))
    except (TypeError, OSError, SyntaxError):
        return None
    module = sys.modules[obj.__module__]
    namespace = dict(vars(module))
    # A number of deployed handlers import their serializer or service locally.
    # Resolve these symbols from the trusted local module, still under the DB fence.
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom): continue
        module_name = node.module or ""
        if node.level:
            module_name = importlib.util.resolve_name("." * node.level + module_name, module.__package__)
        if module_name.split(".", 1)[0] not in {"accounts", "catalog", "reading", "ingestion", "distribution", "common"}: continue
        imported = importlib.import_module(module_name)
        for alias in node.names:
            if alias.name != "*" and hasattr(imported, alias.name):
                namespace[alias.asname or alias.name] = getattr(imported, alias.name)
    schemas, callees, guards, query, body, headers = set(), {}, [], set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Name, ast.Attribute)):
            value = resolve(node, namespace, cls)
            if inspect.isclass(value) and issubclass(value, BaseSerializer):
                schemas.add(qualified(value))
        if isinstance(node, ast.Raise):
            guards.append(ast.unparse(node))
        if not isinstance(node, ast.Call):
            continue
        name = ast.unparse(node.func)
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            field = node.args[0].value
            if "query_params" in name:
                query.add(field)
            if "request.data" in name:
                body.add(field)
            if any(part in name for part in ("request.headers", "request.META")):
                headers.add(field)
        value = resolve(node.func, namespace, cls)
        if inspect.isfunction(value) or inspect.ismethod(value):
            source = location(value)
            if source.startswith("api/"):
                callees[qualified(value)] = {"source": source, "object": value}
    return {"source": where, "schemas": schemas, "callees": callees,
            "guards": guards, "query": query, "body": body, "headers": headers}


routes = {}
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
        actions = getattr(callback, "actions", {})
        methods = actions or {m: m for m in getattr(cls, "http_method_names", []) if hasattr(cls, m)}
        if cls is None:
            methods = {"get": "get"}
        for method, action in methods.items():
            if method in {"head", "options"}:
                continue
            routes[(method.upper(), "/" + route)] = (cls, getattr(cls, action) if cls else callback)


with connection.execute_wrapper(no_database):
    walk(get_resolver().url_patterns)
    with (OUT / "API_CONTRACTS.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream); fields = list(reader.fieldnames); rows = list(reader)
    pages = defaultdict(set)
    with (OUT / "PAGE_API_LINKS.csv").open(encoding="utf-8-sig", newline="") as stream:
        for item in csv.DictReader(stream):
            pages[(item["method_candidate"], item["api_path"])].add(item["page"])
    extras = ["resolved_schemas", "query_field_names", "body_direct_keys", "required_header_references",
              "pagination_contract", "source_call_chain", "validation_sources", "permission_sources", "source_inventory_scope"]
    fields.extend(name for name in extras if name not in fields)
    for row in rows:
        cls, handler = routes[(row["method"], row["path"])]
        schemas, query, body, headers, callsites, validations, permission_sources = set(), set(), set(), set(), {}, {}, set()
        initial = [handler]
        if cls:
            # These methods often hold permission/owner/serializer/filter logic
            # outside the endpoint method. Do not call any of them.
            for name in ("initial", "get_permissions", "get_queryset", "get_serializer_class", "get_object",
                         "perform_create", "perform_update", "perform_destroy", "get", "post", "patch", "put", "delete"):
                value = getattr(cls, name, None)
                if value and value not in initial:
                    initial.append(value)
            for parent in cls.__mro__:
                for name, value in vars(parent).items():
                    if name in {"check_actor", "check_owner", "actor", "owner", "check_permissions", "check_object_permissions"}:
                        initial.append(value)
            for permission in getattr(cls, "permission_classes", []):
                for name in ("has_permission", "has_object_permission"):
                    value = getattr(permission, name, None)
                    if value:
                        initial.append(value)
                        if location(value): permission_sources.add(location(value))
            value = getattr(cls, "serializer_class", None)
            if value: schemas.add(qualified(value))
        queue = [(value, 0) for value in initial]
        seen = set()
        while queue:
            value, depth = queue.pop(0)
            key = location(value)
            if not key or key in seen:
                continue
            seen.add(key)
            found = describe(value, cls)
            if not found:
                continue
            schemas.update(found["schemas"]); query.update(found["query"])
            body.update(found["body"]); headers.update(found["headers"])
            if found["guards"]:
                validations[key] = found["guards"]
            for name, target in found["callees"].items():
                callsites[name] = target["source"]
                if depth < 2:
                    queue.append((target["object"], depth + 1))
        for name in list(schemas):
            module, symbol = name.rsplit(".", 1)
            value = getattr(sys.modules.get(module), symbol, None)
            if not inspect.isclass(value): continue
            for parent in value.__mro__:
                for validator_name, validator in vars(parent).items():
                    if validator_name == "validate" or validator_name.startswith("validate_"):
                        source = location(validator)
                        if source.startswith("api/"):
                            validations[source] = [f"{name}.{validator_name}"]
        pagination = getattr(cls, "pagination_class", None) if cls else None
        page_spec = {key: getattr(pagination, key) for key in ("page_size", "page_query_param", "page_size_query_param", "max_page_size", "limit_query_param", "offset_query_param", "default_limit", "max_limit") if pagination and hasattr(pagination, key)}
        row.update(resolved_schemas=";".join(sorted(schemas)), query_field_names=";".join(sorted(query)),
                   body_direct_keys=";".join(sorted(body)), required_header_references=";".join(sorted(headers)),
                   pagination_contract=json.dumps(page_spec, ensure_ascii=False),
                   source_call_chain=json.dumps(callsites, ensure_ascii=False),
                   validation_sources=json.dumps(validations, ensure_ascii=False),
                   permission_sources=";".join(sorted(permission_sources)),
                   source_inventory_scope="source resolution only; includes sibling HTTP methods and two nested call levels; dynamic runtime branches are not execution evidence")
        matched = pages.get((row["method"], row["path"]), set())
        if matched:
            row["page_mapping"] = ";".join(sorted(matched))
    with (OUT / "API_CONTRACTS.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"method_paths": len(rows), "schema_linked": sum(bool(row["resolved_schemas"]) for row in rows),
                      "page_linked": sum(row["page_mapping"] != "待对应 COVERAGE.csv" for row in rows),
                      "scope": "source only, no business execution or DB"}))
