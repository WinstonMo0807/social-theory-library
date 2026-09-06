import pytest
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from rest_framework.response import Response

from catalog.cataloging_serializers import CatalogingSessionSerializer
from catalog.services.cataloging_sessions import open_cataloging_session, session_payload
from config.renderers import ContractJSONRenderer, error_contract


def test_error_contract_preserves_legacy_details_and_adds_stable_fields():
    legacy = {"error": {"status": 400, "detail": {"isbn13": ["bad checksum"]}}}
    normalized = error_contract(legacy, 400)
    assert normalized["error"] == legacy["error"]
    assert normalized["code"] == "request.invalid"
    assert normalized["details"] == {"isbn13": ["bad checksum"]}
    assert normalized["severity"] == "blocking"


def test_hand_returned_error_is_normalized_and_success_is_not():
    renderer = ContractJSONRenderer()
    response = Response({"code": "catalog.session_conflict", "detail": "请刷新。"}, status=409)
    renderer.render(response.data, renderer_context={"response": response})
    assert response.data["message"] == "请刷新。"
    success = Response({"value": "unchanged"})
    renderer.render(success.data, renderer_context={"response": success})
    assert success.data == {"value": "unchanged"}


@pytest.mark.django_db
def test_verified_schema_is_built_from_actual_serializers_without_database(django_assert_num_queries):
    with django_assert_num_queries(0):
        schema = SchemaGenerator(urlconf="config.schema_urls").get_schema(request=None, public=True)
    operation = schema["paths"]["/api/catalog/admin/cataloging-sessions/"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("CatalogingSessionCreateRequest")
    fields = schema["components"]["schemas"]["CatalogingSession"]["properties"]
    assert fields["upload_item_id"]["nullable"] is True
    assert fields["edition_id"]["format"] == "uuid"


@pytest.mark.django_db
def test_session_response_matches_generated_serializer_contract(admin_user):
    session, _created = open_cataloging_session(actor=admin_user, source_type="manual", title="契约测试")
    output = CatalogingSessionSerializer(session).data
    actual = session_payload(session)
    assert set(output) == set(actual)
    for key in ("id", "source_type", "status", "edition_id", "work_id", "upload_item_id"):
        assert str(output[key]) == str(actual[key])


@pytest.mark.django_db
def test_schema_endpoint_keeps_admin_permission(api_client, reader_user, admin_user):
    url = reverse("api-schema")
    assert api_client.get(url).status_code in {401, 403}
    api_client.force_authenticate(reader_user)
    assert api_client.get(url).status_code == 403
    api_client.force_authenticate(admin_user)
    response = api_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_manual_validation_error_matches_http_error_contract(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    response = api_client.post("/api/catalog/admin/cataloging-sessions/", {"source_type": "upload"}, format="json")
    assert response.status_code == 400
    body = response.json()
    assert set(("code", "message", "field", "severity", "details")) <= body.keys()
    assert "upload_item_id" in body["details"]
