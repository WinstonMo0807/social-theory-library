"""Resolve inherited serializer fields against the isolated deployed source.

Only field definitions are inspected. Any database execution is blocked. This
does not validate input, invoke views, read production data, or verify services.
"""
from pathlib import Path
import csv
import inspect
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/stl4/public-visual-20261110"
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings", DATABASE_URL="sqlite:///:memory:",
                  DJANGO_DEBUG="true", PUBLIC_DEPLOYMENT_MODE="false",
                  CELERY_BROKER_URL="memory://", CELERY_RESULT_BACKEND="cache+memory://")
sys.path.insert(0, str(ROOT / "api"))
import django
django.setup()
from django.db import connection
from django.urls import get_resolver
from rest_framework import serializers


def no_database(execute, sql, params, many, context):
    raise RuntimeError("Database access is forbidden during serializer inventory")


def load_routes(patterns):
    for pattern in patterns:
        if hasattr(pattern, "url_patterns"):
            load_routes(pattern.url_patterns)
        else:
            _ = pattern.callback


def field_spec(field):
    values = {"type": type(field).__name__}
    for key in ("required", "read_only", "write_only", "allow_null", "allow_blank", "min_length", "max_length", "min_value", "max_value", "allow_empty"):
        value = getattr(field, key, None)
        if value is not None:
            values[key] = value if isinstance(value, (str, int, float, bool)) else str(value)
    if isinstance(field, serializers.ChoiceField):
        values["choices"] = list(field.choices)
    if isinstance(field, serializers.BaseSerializer):
        target = field.child if isinstance(field, serializers.ListSerializer) else field
        values["schema"] = type(target).__module__ + "." + type(target).__name__
    elif isinstance(field, (serializers.ListField, serializers.DictField)):
        values["child"] = field_spec(field.child)
    return values


rows = []
with connection.execute_wrapper(no_database):
    load_routes(get_resolver().url_patterns)
    seen = set()
    for module in list(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        try:
            path = Path(filename).resolve().relative_to(ROOT / "api")
        except ValueError:
            continue
        for cls in list(vars(module).values()):
            if not inspect.isclass(cls) or not issubclass(cls, serializers.Serializer) or cls in seen or cls.__module__ != module.__name__:
                continue
            seen.add(cls)
            try:
                line = inspect.getsourcelines(cls)[1]
            except (OSError, TypeError):
                line = ""  # Dynamically constructed serializers have no class line.
            row = {"schema": cls.__module__ + "." + cls.__name__, "source": "api/" + path.as_posix(),
                   "line": line, "fields": "", "status": "resolved_fields_only", "limitation": "Validation, service transitions and runtime remain separate evidence"}
            try:
                instance = cls()
                fields = {name: field_spec(field) for name, field in instance.fields.items()}
                row["fields"] = json.dumps(fields, ensure_ascii=False, separators=(",", ":"), default=str)
            except Exception as exc:
                row["status"] = "requires_context"
                row["limitation"] = type(exc).__name__ + ": " + str(exc)[:240]
            rows.append(row)

rows.sort(key=lambda row: row["schema"])
with (OUT / "API_FIELD_CONTRACTS.csv").open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=["schema", "source", "line", "fields", "status", "limitation"])
    writer.writeheader()
    writer.writerows(rows)
print(json.dumps({"serializers": len(rows), "resolved": sum(row["status"] == "resolved_fields_only" for row in rows),
                  "scope": "isolated source; database execution blocked; no requests"}))
