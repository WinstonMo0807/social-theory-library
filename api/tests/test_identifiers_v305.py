from copy import deepcopy

import pytest
from django.core.exceptions import ValidationError

from catalog.contracts.identifiers import describe_identifier, normalize_identifier, validate_external_identifiers
from catalog.enrichment_serializers import EnrichmentCandidateSerializer
from catalog.models import EnrichmentCandidate, OrganizationAuthority, Person
from catalog.services.field_enrichment.mutations import _person_external_identifier
from catalog.services.field_enrichment.values import normalize_candidate_value


@pytest.mark.parametrize(("scheme", "raw", "expected"), [
    ("isbn_13", "ISBN 978-0-306-40615-7", "9780306406157"),
    ("doi", "https://doi.org/10.1000/ABC", "10.1000/abc"),
    ("issn", "ISSN 0317-8471", "0317-8471"),
    ("issn", "2434561x", "2434-561X"),
    ("orcid", "https://orcid.org/0000-0002-1694-233X", "0000-0002-1694-233X"),
    ("viaf", "https://viaf.org/viaf/49224511/", "49224511"),
    ("oclc", "(OCoLC)ocm00003862", "3862"),
    ("wikidata", "https://www.wikidata.org/wiki/Q42", "Q42"),
    ("openalex", "https://openalex.org/works/w2741809807", "W2741809807"),
    ("url", "https://Example.com/Keep?Case=Yes#Part", "https://example.com/Keep?Case=Yes#Part"),
])
def test_identifier_normalization_and_uri_are_syntax_only(scheme, raw, expected):
    assert normalize_identifier(scheme, raw) == expected
    details = describe_identifier(scheme, raw)
    assert details["value"] == raw and details["normalized_value"] == expected
    assert details["status"] == "syntax_valid" and details["uri"]
    assert details["externally_verified"] is False
    assert details["source"] == {"kind": "unrecorded"}
    assert normalize_identifier(scheme, expected) == expected


@pytest.mark.parametrize(("scheme", "raw"), [
    ("isbn", "9780306406158"), ("issn", "0317-8472"),
    ("orcid", "0000-0002-1825-0098"), ("orcid", "2-1825-0097"),
    ("viaf", "https://viaf.org.evil.test/viaf/49224511"),
    ("wikidata", "Q0"), ("oclc", "ocmnot-a-number"),
    ("openalex", "authors/W2741809807"), ("url", "javascript:alert(1)"),
    ("doi", "doi:"), ("isbn", "ISBN "),
])
def test_invalid_known_identifiers_are_not_linked_or_accepted(scheme, raw):
    with pytest.raises(ValueError):
        normalize_identifier(scheme, raw)
    with pytest.raises(ValueError):
        validate_external_identifiers({scheme: raw})
    assert describe_identifier(scheme, raw)["uri"] is None


def test_unknown_schemes_and_unchanged_legacy_values_are_not_rewritten():
    values = {"orcid": "legacy-invalid", "LocalCode": {"value": " 00042 ", "source": "旧档案"}}
    saved = deepcopy(values)
    assert validate_external_identifiers(values, previous=saved) == saved
    unknown = describe_identifier("LocalCode", values["LocalCode"])
    assert unknown["status"] == "unrecognized" and unknown["uri"] is None
    assert unknown["value"] == values["LocalCode"] and values == saved
    candidate = {"scheme": "LocalCode", "value": " 00042 "}
    assert normalize_candidate_value("person_external_identifier", candidate) == candidate
    with pytest.raises(ValueError):
        validate_external_identifiers({**saved, "orcid": "different-invalid"}, previous=saved)
    with pytest.raises(ValueError):
        validate_external_identifiers({"viaf": True}, previous={"viaf": 1})


@pytest.mark.django_db
@pytest.mark.parametrize("model", (Person, OrganizationAuthority))
def test_model_clean_preserves_history_and_checks_only_changed_identifiers(model):
    row = model.objects.create(preferred_name="历史标识符", external_ids={"orcid": "old", "custom": " 0001 "})
    original = deepcopy(row.external_ids)
    row.preferred_name = "修正名称"
    row.full_clean()
    row.save(update_fields=["preferred_name"])
    row.refresh_from_db()
    assert row.external_ids == original
    row.external_ids = {**original, "orcid": "new-invalid"}
    with pytest.raises(ValidationError):
        row.full_clean()
    row.refresh_from_db()
    assert row.external_ids == original


@pytest.mark.django_db
def test_equivalent_identifier_does_not_replace_original_representation():
    person = Person.objects.create(preferred_name="原始标识符", external_ids={"ORCID": "https://orcid.org/0000-0002-1825-0097", "custom": " 00042 "})
    original = deepcopy(person.external_ids)
    value = normalize_candidate_value("person_external_identifier", {"scheme": "orcid", "value": "0000000218250097"})
    result = _person_external_identifier(target=person, value=value, candidate=None, actor=None)
    assert result.changed is False
    person.refresh_from_db()
    assert person.external_ids == original
    with pytest.raises(ValueError):
        _person_external_identifier(target=person, value={"scheme": "orcid", "value": "0000-0002-1694-233X"}, candidate=None, actor=None)
    person.refresh_from_db()
    assert person.external_ids == original


def test_candidate_serializer_marks_source_and_does_not_claim_verification():
    candidate = EnrichmentCandidate(field_name="external_identifier", proposed_value={"scheme": "orcid", "value": "0000-0002-1825-0097"}, source_class="identifier_registry")
    serializer = EnrichmentCandidateSerializer()
    assert serializer.fields["identifier_details"].read_only
    details = serializer.get_identifier_details(candidate)
    assert details["source"] == {"kind": "candidate", "candidate_id": str(candidate.pk), "source_class": "identifier_registry"}
    assert details["display_value"] == "https://orcid.org/0000-0002-1825-0097"
    assert details["externally_verified"] is False
