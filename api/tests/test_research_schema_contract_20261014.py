"""New backend contracts must remain usable through the protected schema surface."""
import json

import pytest
from django.urls import URLResolver, include, path, resolve
from drf_spectacular.drainage import GENERATOR_STATS
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema

from config.schema_urls import urlpatterns


MODULES = {
    "catalog.outline_views", "catalog.content_placement_views",
    "catalog.editorial_assistance_views", "reading.research_views",
}
ADDITIONAL_VIEWS = {"AdminReaderRenditionPolicyView", "AssetFileView", "AdminAssetPreviewView", "BackupJobListView",
                    "PassageFocusView", "PublicEvidenceFocusView", "DocumentSearchView"}


def selected_patterns(patterns):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            children = list(selected_patterns(pattern.url_patterns))
            if children:
                yield path(str(pattern.pattern), include(children))
        elif (getattr(getattr(pattern.callback, "cls", None), "__module__", "") in MODULES
              or getattr(getattr(pattern.callback, "cls", None), "__name__", "") in ADDITIONAL_VIEWS):
            yield pattern


@pytest.fixture(scope="module")
def schema(tmp_path_factory):
    GENERATOR_STATS.reset()
    result = SchemaGenerator(patterns=list(selected_patterns(urlpatterns))).get_schema(request=None, public=True)
    evidence = tmp_path_factory.mktemp("new-backend-schema")
    (evidence / "openapi.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (evidence / "diagnostics.json").write_text(json.dumps({
        "errors": dict(GENERATOR_STATS._error_cache), "warnings": dict(GENERATOR_STATS._warn_cache),
        "paths": len(result["paths"]),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    assert not GENERATOR_STATS._error_cache
    assert not GENERATOR_STATS._warn_cache
    validate_schema(result)
    return result


def component(schema, reference):
    return schema["components"]["schemas"][reference["$ref"].rsplit("/", 1)[1]]


def response(schema, route, method="get", code="200"):
    return schema["paths"][route][method]["responses"][code]["content"]["application/json"]["schema"]


def test_all_new_modules_are_exposed_by_original_permission_protected_routes(schema):
    routes = [
        "/api/catalog/assets/{asset_id}/outline/",
        "/api/catalog/admin/content-placements/{page_type}/{page_id}/",
        "/api/catalog/admin/recommendation-issues/{issue_id}/assistant/",
        "/api/reading/research-account/",
        "/api/reading/research-projects/",
        "/api/reading/research-turns/",
        "/api/reading/citation-audits/",
        "/api/reading/reading-plans/",
        "/api/reading/research-memories/",
    ]
    identifier = "9cb786cf-ae21-44a2-8f96-2b3c4da0f027"
    for route in routes:
        assert route in schema["paths"]
        actual = route.format(asset_id=identifier, page_type="scholar", page_id=identifier, issue_id=identifier)
        contract_view = resolve(actual, urlconf="config.schema_urls").func.cls
        assert contract_view is resolve(actual).func.cls
    for route in routes[3:]:
        assert all(schema["paths"][route]["get"]["security"])


def test_turn_list_is_paginated_and_export_preserves_record_and_turns(schema):
    route = "/api/reading/research-projects/{id}/turns/"
    page = component(schema, response(schema, route))
    assert {"count", "next", "previous", "results"} <= page["properties"].keys()
    assert page["properties"]["results"]["type"] == "array"
    assert "202" in schema["paths"][route]["post"]["responses"]
    exported = component(schema, response(schema, "/api/reading/research-projects/{id}/export/"))
    assert {"schema_version", "id", "data", "turns"} <= exported["properties"].keys()
    assert exported["properties"]["turns"]["type"] == "array"


def test_memory_search_documents_results_and_capability_state(schema):
    output = component(schema, response(schema, "/api/reading/research-memories/search/", "post"))
    assert {"results", "mode", "notice", "warning", "semantic_candidate_limit"} <= output["properties"].keys()
    assert output["properties"]["results"]["type"] == "array"
    item = component(schema, output["properties"]["results"]["items"])
    assert "match_reason" in item["properties"]


def test_manuscript_upload_and_original_download_use_binary_file_contracts(schema):
    upload = schema["paths"]["/api/reading/citation-audits/"]["post"]["requestBody"]["content"]
    assert set(upload) == {"multipart/form-data"}
    incoming = component(schema, upload["multipart/form-data"]["schema"])
    assert incoming["properties"]["file"]["format"] == "binary"
    original = schema["paths"]["/api/reading/citation-audits/{id}/original/"]["get"]["responses"]["200"]["content"]
    assert set(original) == {"application/octet-stream"}
    assert original["application/octet-stream"]["schema"] == {"type": "string", "format": "binary"}


def test_outline_submission_documents_async_success(schema):
    expected = {
        "/api/catalog/admin/assets/{asset_id}/outline/": {"200", "202"},
        "/api/catalog/admin/outline-rebuilds/": {"202"},
        "/api/catalog/admin/outline-jobs/{job_id}/": {"202"},
    }
    for route, statuses in expected.items():
        assert set(schema["paths"][route]["post"]["responses"]) == statuses


def test_reader_file_contracts_describe_binary_ranges_and_keep_original_permissions(schema):
    for route in ("/api/distribution/assets/{asset_id}/file/", "/api/distribution/admin/assets/{asset_id}/preview/"):
        operation = schema["paths"][route]["get"]
        for code in ("200", "206"):
            assert operation["responses"][code]["content"]["application/pdf"]["schema"] == {"type": "string", "format": "binary"}
        assert "Content-Range" in operation["responses"]["206"]["headers"]
        assert "416" in operation["responses"]
        assert any(row["name"] == "Range" and row["in"] == "header" for row in operation["parameters"])
    identifier = "9cb786cf-ae21-44a2-8f96-2b3c4da0f027"
    for route in ("/api/distribution/backups/", "/api/catalog/admin/editions/{edition_id}/reader-rendition/"):
        actual = route.format(edition_id=identifier)
        assert resolve(actual, urlconf="config.schema_urls").func.cls is resolve(actual).func.cls
    result = component(schema, response(schema, "/api/catalog/admin/editions/{edition_id}/reader-rendition/", "put"))
    assert set(result["properties"]) == {"policy", "validated_ocr_pdf_available", "effective_rendition", "fallback_active"}


def test_reader_focus_and_document_search_require_the_formal_source_identity(schema):
    for route in ("/api/catalog/passages/{id}/focus/", "/api/catalog/theory-system/evidence/{id}/focus/",
                  "/api/catalog/assets/{asset_id}/search/"):
        result = component(schema, response(schema, route))
        assert {"asset_id", "document_revision_id"} <= set(result["required"])
        assert result["properties"]["document_revision_id"]["format"] == "uuid"
