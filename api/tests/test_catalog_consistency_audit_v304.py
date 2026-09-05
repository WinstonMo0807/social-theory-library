from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

from accounts.models import User
from catalog.models import (
    Contribution,
    DocumentType,
    Edition,
    Person,
    PublicationState,
    QueryLexiconEntry,
    QueryLexiconState,
    Work,
)
from catalog.services.catalog_consistency_audit import catalog_consistency_report
from catalog.services.query_lexicon.normalization import normalize_term
from catalog.services.query_lexicon.sync import ensure_query_lexicon_state
from ingestion.models import EntityResolutionCandidate, MetadataCandidate, UploadBatch, UploadItem


pytestmark = pytest.mark.django_db


def _user() -> User:
    return User.objects.create_user(
        username="v304-auditor",
        email="v304-auditor@example.org",
        password="test-only-password",
    )


def _intake(user: User) -> tuple[Work, Edition, UploadItem]:
    work = Work.objects.create(document_type=DocumentType.BOOK, title="一致性审计测试")
    edition = Edition.objects.create(work=work)
    batch = UploadBatch.objects.create(created_by=user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        edition=edition,
        source_filename="audit.pdf",
    )
    return work, edition, item


def _check(report: dict, code: str) -> dict:
    return next(row for row in report["checks"] if row["code"] == code)


def test_audit_finds_accepted_candidate_without_formal_author_relation():
    user = _user()
    _work, edition, item = _intake(user)
    person = Person.objects.create(
        preferred_name="陈向明",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    MetadataCandidate.objects.create(
        upload_item=item,
        field_name="authors",
        value=["陈向明"],
        source="pdf",
        lifecycle=MetadataCandidate.Lifecycle.ACCEPTED,
        accepted_by=user,
    )
    EntityResolutionCandidate.objects.create(
        upload_item=item,
        target_type="person",
        source_name="陈向明",
        candidate_entity_type="person",
        candidate_entity_id=str(person.id),
        label="陈向明",
        supporting_properties={"contribution_role": Contribution.Role.AUTHOR},
        status=EntityResolutionCandidate.Status.LINKED,
        reviewed_by=user,
    )
    Contribution.objects.create(
        edition=edition,
        person=person,
        role=Contribution.Role.AUTHOR,
        approved=False,
    )

    report = catalog_consistency_report()

    metadata = _check(report, "accepted_metadata_without_formal_draft")
    relation = _check(report, "accepted_entity_without_formal_relation")
    assert metadata["count"] == 1
    assert metadata["examples"][0]["field"] == "authors"
    assert relation["count"] == 1
    assert relation["examples"][0]["entity_id"] == str(person.id)
    assert report["summary"]["error_count"] >= 2


def test_audit_finds_published_edition_without_active_revision():
    work = Work.objects.create(document_type=DocumentType.BOOK, title="旧馆藏")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
    )

    report = catalog_consistency_report()

    check = _check(report, "published_without_active_revision")
    assert check["count"] == 1
    assert check["examples"][0]["edition_id"] == str(edition.id)


def test_audit_finds_active_lexicon_term_that_v2_cannot_rebuild():
    ensure_query_lexicon_state()
    state = QueryLexiconState.objects.select_related("active_generation").get(key="default")
    draft = Person.objects.create(
        preferred_name="尚未发布的人物",
        authority_status=Person.AuthorityStatus.DRAFT,
    )
    term = draft.preferred_name
    QueryLexiconEntry.objects.create(
        generation=state.active_generation,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=draft.id,
        term=term,
        normalized_term=normalize_term(term),
        language="zh-Hans",
        term_type=QueryLexiconEntry.TermType.CANONICAL,
        source_kind=QueryLexiconEntry.SourceKind.AUTHORITY_FIELD,
        trust_level=QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
        source_ref=f"catalog.Person:{draft.id}:preferred_name",
        source_fingerprint="b" * 64,
        displayable=True,
        public_active=False,
        admin_resolvable=True,
    )

    report = catalog_consistency_report()

    check = _check(report, "query_lexicon_nonformal_entries")
    assert check["count"] == 1
    assert check["examples"][0]["entity_id"] == str(draft.id)


def test_management_command_emits_json_without_mutating_rows():
    user = _user()
    _intake(user)
    before = {
        "works": Work.objects.count(),
        "editions": Edition.objects.count(),
        "people": Person.objects.count(),
        "entries": QueryLexiconEntry.objects.count(),
    }
    output = StringIO()

    call_command("audit_v304_catalog_consistency", stdout=output, limit=5)

    payload = json.loads(output.getvalue())
    after = {
        "works": Work.objects.count(),
        "editions": Edition.objects.count(),
        "people": Person.objects.count(),
        "entries": QueryLexiconEntry.objects.count(),
    }
    assert payload["schema_version"] == "catalog-consistency-audit-v304"
    assert payload["read_only"] is True
    assert payload["safety"]["database_mutated"] is False
    assert after == before
