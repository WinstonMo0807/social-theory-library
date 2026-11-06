from datetime import date

import pytest

from catalog.workflow_serializers import BibliographySectionSerializer, WorkSectionSerializer


@pytest.mark.parametrize("serializer_class,field", [
    (WorkSectionSerializer, "first_publication_date"),
    (BibliographySectionSerializer, "publication_date"),
])
def test_optional_date_can_be_cleared_without_inventing_a_day(serializer_class, field):
    for value in ("", None):
        serializer = serializer_class(data={field: value})
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data[field] is None
    omitted = serializer_class(data={})
    assert omitted.is_valid(), omitted.errors
    assert field not in omitted.validated_data
    valid = serializer_class(data={field: "2017-03-01"})
    assert valid.is_valid(), valid.errors
    assert valid.validated_data[field] == date(2017, 3, 1)
    for invalid in ("2017", "2017-03", "2017-02-30", "unknown"):
        serializer = serializer_class(data={field: invalid})
        assert not serializer.is_valid()
        assert field in serializer.errors


def test_year_only_bibliography_and_date_year_consistency():
    year_only = BibliographySectionSerializer(data={"publication_date": "", "publication_year": 2017})
    assert year_only.is_valid(), year_only.errors
    assert year_only.validated_data["publication_date"] is None
    assert year_only.validated_data["publication_year"] == 2017
    mismatch = BibliographySectionSerializer(data={"publication_date": "2015-01-01", "publication_year": 2017})
    assert not mismatch.is_valid()
    assert "publication_date" in mismatch.errors
