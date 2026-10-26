from catalog.workflow_serializers import BibliographySectionSerializer


def test_full_isbn_pair_replaces_stale_legacy_value_and_still_validates():
    corrected = BibliographySectionSerializer(data={
        "isbn": "0120025265", "isbn10": "", "isbn13": "9787301214268",
    })
    assert corrected.is_valid(), corrected.errors
    assert corrected.validated_data["isbn"] == "9787301214268"
    cleared = BibliographySectionSerializer(data={"isbn": "0120025265", "isbn10": "", "isbn13": ""})
    assert cleared.is_valid(), cleared.errors
    assert cleared.validated_data["isbn"] == ""
    invalid = BibliographySectionSerializer(data={"isbn10": "", "isbn13": "9787301214260"})
    assert not invalid.is_valid()
    legacy_only = BibliographySectionSerializer(data={"isbn": "0120025265"})
    assert not legacy_only.is_valid()


def test_bibliography_preserves_explicit_publication_mode():
    serializer = BibliographySectionSerializer(data={"publication_mode": "document"})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["publication_mode"] == "document"
    invalid = BibliographySectionSerializer(data={"publication_mode": "invalid"})
    assert not invalid.is_valid()
