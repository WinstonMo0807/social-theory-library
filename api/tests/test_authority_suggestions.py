import pytest
from django.test import override_settings

from catalog.models import Person
from catalog.services import authority_suggestions as service


pytestmark = pytest.mark.django_db


def _wikidata_fixture(url, *, params):
    if params["action"] == "wbsearchentities":
        return {
            "search": [
                {
                    "id": "Q123",
                    "label": "费孝通",
                    "description": "中国社会学家、人类学家",
                    "match": {"type": "label", "text": "费孝通"},
                }
            ]
        }
    return {
        "entities": {
            "Q123": {
                "labels": {"en": {"language": "en", "value": "Fei Xiaotong"}},
                "aliases": {
                    "zh": [{"language": "zh", "value": "费孝通"}],
                    "en": [{"language": "en", "value": "Xiaotong Fei"}],
                },
                "claims": {
                    "P569": [{"mainsnak": {"datavalue": {"value": {"time": "+1910-11-02T00:00:00Z"}}}}],
                    "P570": [{"mainsnak": {"datavalue": {"value": {"time": "+2005-04-24T00:00:00Z"}}}}],
                    "P214": [{"mainsnak": {"datavalue": {"value": "123456"}}}],
                },
            }
        }
    }


@override_settings(
    AUTHORITY_PROVIDER_ENABLED="wikidata",
    AUTHORITY_PROVIDER_VERIFY_DNS=False,
    AI_AUTHORITY_RERANK_ENABLED=False,
)
def test_person_suggestions_combine_local_and_multilingual_authority(monkeypatch, api_client, admin_user):
    local = Person.objects.create(
        preferred_name="费孝通",
        original_name="Fei Xiaotong",
        birth_year=1910,
        death_year=2005,
        aliases=["Xiaotong Fei"],
    )
    monkeypatch.setattr(service, "_request_json", _wikidata_fixture)
    api_client.force_authenticate(admin_user)

    response = api_client.get(
        "/api/catalog/admin/authority-suggestions/",
        {"entity_type": "person", "q": "费孝通"},
    )

    assert response.status_code == 200
    assert response.data["entity_type"] == "person"
    assert response.data["ai_filter"]["status"] == "disabled"
    assert response.data["results"][0]["id"] == f"local:person:{local.id}"
    remote = next(row for row in response.data["results"] if row["id"] == "wikidata:Q123")
    assert remote["original_name"] == "Fei Xiaotong"
    assert remote["birth_year"] == 1910
    assert remote["death_year"] == 2005
    assert remote["external_ids"]["viaf"] == "123456"
    assert {row["name"] for row in remote["aliases"]} >= {"费孝通", "Xiaotong Fei"}
    assert remote["source_record_id"]


@override_settings(
    AUTHORITY_PROVIDER_ENABLED="wikidata",
    AUTHORITY_PROVIDER_VERIFY_DNS=False,
    AI_AUTHORITY_RERANK_ENABLED=False,
)
def test_authority_provider_reuses_source_record_cache(monkeypatch, api_client, admin_user):
    calls = []

    def tracked_request(url, *, params):
        calls.append(params["action"])
        return _wikidata_fixture(url, params=params)

    monkeypatch.setattr(service, "_request_json", tracked_request)
    api_client.force_authenticate(admin_user)

    first = api_client.get(
        "/api/catalog/admin/authority-suggestions/",
        {"entity_type": "person", "q": "费孝通"},
    )
    second = api_client.get(
        "/api/catalog/admin/authority-suggestions/",
        {"entity_type": "person", "q": "费孝通"},
    )

    assert first.status_code == second.status_code == 200
    assert calls == ["wbsearchentities", "wbgetentities"]
    assert second.data["results"][0]["source_record_id"] == first.data["results"][0]["source_record_id"]


@override_settings(
    AUTHORITY_PROVIDER_ENABLED="viaf",
    AUTHORITY_PROVIDER_VERIFY_DNS=False,
    AI_AUTHORITY_RERANK_ENABLED=False,
)
def test_viaf_null_result_is_an_empty_provider_result(monkeypatch):
    monkeypatch.setattr(service, "_request_json", lambda *args, **kwargs: {"result": None})

    rows, record = service._viaf_candidates("person", "Emile Durkheim")

    assert rows == []
    assert record.provider == "authority:viaf"


@override_settings(
    AUTHORITY_PROVIDER_ENABLED="viaf",
    AUTHORITY_PROVIDER_VERIFY_DNS=False,
    AI_AUTHORITY_RERANK_ENABLED=False,
)
def test_viaf_person_heading_provides_explicit_dates_and_filters_work_titles(monkeypatch):
    monkeypatch.setattr(
        service,
        "_request_json",
        lambda *args, **kwargs: {
            "result": [
                {
                    "viafid": "71387829",
                    "displayForm": "Pierre Bourdieu, 1930-2002",
                    "nametype": "personal",
                },
                {
                    "viafid": "work-1",
                    "displayForm": "Pierre Bourdieu, 1930-2002. Distinction",
                    "nametype": "uniformtitlework",
                },
            ]
        },
    )

    rows, _record = service._viaf_candidates("person", "Pierre Bourdieu parser fixture")

    assert len(rows) == 1
    assert rows[0]["label"] == "Pierre Bourdieu"
    assert rows[0]["birth_year"] == 1930
    assert rows[0]["death_year"] == 2002


@override_settings(
    AUTHORITY_PROVIDER_ENABLED="wikidata,viaf",
    AI_AUTHORITY_RERANK_ENABLED=False,
)
def test_one_provider_parse_failure_preserves_local_and_other_results(
    monkeypatch,
    api_client,
    admin_user,
):
    local = Person.objects.create(preferred_name="埃米尔·杜尔凯姆", original_name="Émile Durkheim")

    def provider(provider, entity_type, query):
        if provider == "viaf":
            raise TypeError("provider returned null result")
        return [{
            "id": "wikidata:Q15948",
            "label": "埃米尔·杜尔凯姆",
            "original_name": "Émile Durkheim",
            "aliases": [],
            "description": "法国社会学家",
            "birth_year": 1858,
            "death_year": 1917,
            "external_ids": {"wikidata": "Q15948"},
            "source": "Wikidata",
            "provider": "wikidata",
            "source_url": "https://www.wikidata.org/wiki/Q15948",
            "source_record_id": "fixture",
            "match_reasons": ["规范名命中"],
            "conflicts": [],
        }]

    monkeypatch.setattr(service, "_fetch_provider_with_policy", provider)
    api_client.force_authenticate(admin_user)
    response = api_client.get(
        "/api/catalog/admin/authority-suggestions/",
        {"entity_type": "person", "q": "埃米尔·杜尔凯姆"},
    )

    assert response.status_code == 200
    identifiers = {row["id"] for row in response.data["results"]}
    assert f"local:person:{local.id}" in identifiers
    assert "wikidata:Q15948" in identifiers
    assert any("viaf" in warning for warning in response.data["warnings"])


def test_authority_suggestions_require_catalog_editor(api_client, reader_user):
    api_client.force_authenticate(reader_user)
    response = api_client.get(
        "/api/catalog/admin/authority-suggestions/",
        {"entity_type": "person", "q": "费孝通"},
    )
    assert response.status_code == 403


@override_settings(AUTHORITY_PROVIDER_ENABLED="", AI_AUTHORITY_RERANK_ENABLED=False)
def test_short_or_unknown_authority_query_is_rejected(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    short = api_client.get(
        "/api/catalog/admin/authority-suggestions/",
        {"entity_type": "person", "q": "费"},
    )
    unknown = api_client.get(
        "/api/catalog/admin/authority-suggestions/",
        {"entity_type": "publisher", "q": "三联"},
    )
    assert short.status_code == 400
    assert unknown.status_code == 400


@override_settings(AI_AUTHORITY_RERANK_ENABLED=True)
def test_ai_filter_cannot_inject_unknown_candidate_ids(monkeypatch):
    rows = [
        {
            "id": "local:person:1",
            "label": "同名人物",
            "original_name": "",
            "aliases": [],
            "description": "",
            "birth_year": None,
            "death_year": None,
            "external_ids": {},
            "source": "馆内人物权威库",
            "match_reasons": [],
            "conflicts": [],
        }
    ]

    class FakeResult:
        data = {
            "ordered_ids": ["forged:person:9", "local:person:1"],
            "decisions": [
                {
                    "id": "forged:person:9",
                    "verdict": "supported",
                    "match_reasons": ["伪造"],
                    "conflicts": [],
                },
                {
                    "id": "local:person:1",
                    "verdict": "ambiguous",
                    "match_reasons": ["缺少年代"],
                    "conflicts": [],
                },
            ],
        }
        provider = "ollama"
        model = "small-model"
        prompt_version = "authority-candidate-reconciliation-v2"

    class FakeConfig:
        enabled = True
        classifier_model = "small-model"
        metadata_model = "fallback"

    class FakeClient:
        config = FakeConfig()

        def generate_json(self, **kwargs):
            return FakeResult()

    monkeypatch.setattr(service, "AIClient", FakeClient)
    filtered, status = service._ai_filter("同名人物", "person", rows)
    assert [row["id"] for row in filtered] == ["local:person:1"]
    assert "缺少年代" in filtered[0]["match_reasons"]
    assert status["status"] == "succeeded"
