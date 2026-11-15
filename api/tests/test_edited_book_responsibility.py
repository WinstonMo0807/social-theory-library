import pytest

from catalog.contracts.fields import required_fields
from catalog.models import CatalogFieldDecision, Edition, Person, Work
from catalog.services.admin_queue_query import edition_inventory
from catalog.services.field_decisions import field_readiness
from catalog.services.work_editor import save_workflow_section


@pytest.mark.parametrize("role,field", [("chief_editor", "chief_editors"), ("editor", "editors")])
@pytest.mark.django_db
def test_confirmed_volume_editor_replaces_missing_author_requirement(admin_user, role, field):
    work = Work.objects.create(title="研究论文集", document_type="book", language="zh-CN")
    edition = Edition.objects.create(work=work, publication_mode="bibliographic")
    person = Person.objects.create(preferred_name="论文集主编", sort_name="论文集主编", authority_status="verified")
    save_workflow_section(edition, "work", {
        "title": work.title, "document_type": "book", "language": "zh-CN",
    }, actor=admin_user)
    save_workflow_section(edition, "contributors", {"contributors": [
        {"person_id": str(person.pk), "role": role, "order": 0, "scope": {"kind": "edition"}},
    ]}, actor=admin_user)
    edition.refresh_from_db()
    fields = {row.field_name: row for row in field_readiness(edition)}
    assert not fields["authors"].required
    assert fields["authors"].status == CatalogFieldDecision.Status.NOT_APPLICABLE
    assert fields[field].required
    assert fields[field].status == CatalogFieldDecision.Status.CONFIRMED
    assert not edition_inventory().get(pk=edition.pk).q_incomplete
    assert edition.citation_data["author"] == []
    assert edition.citation_data["editor"] == [{"literal": "论文集主编"}]
    # Removing the only principal contributor restores the author blocker.
    save_workflow_section(edition, "contributors", {"contributors": []}, actor=admin_user)
    edition.refresh_from_db()
    authors = next(row for row in field_readiness(edition) if row.field_name == "authors")
    assert authors.required and authors.status == CatalogFieldDecision.Status.EMPTY


@pytest.mark.parametrize("document_type,role,field,scope", [
    ("book", "translator", "translators", "edition"),
    ("book", "subject", "other_contributors", "edition"),
    ("book", "chief_editor", "chief_editors", "chapter"),
    ("journal_article", "editor", "editors", "edition"),
    ("thesis", "chief_editor", "chief_editors", "edition"),
])
def test_other_roles_and_scopes_do_not_replace_author(document_type, role, field, scope):
    values = {field: ["person"], "contributor_scopes": [
        {"person_id": "person", "role": role, "scope": {"kind": scope}},
    ]}
    assert "authors" in required_fields(document_type, values=values)


def test_author_and_editor_book_still_requires_author_confirmation():
    values = {"authors": ["author"], "editors": ["editor"], "contributor_scopes": [
        {"person_id": "editor", "role": "editor", "scope": {"kind": "edition"}},
    ]}
    assert "authors" in required_fields("book", values=values)
