"""Accurate edition/chapter responsibility; definitions for unified acceptance only."""
from copy import deepcopy
from uuid import uuid4

import pytest

from catalog.models import Contribution, DocumentOutlineRevision, Person
from catalog.services.contribution_scope import (ContributionScopeError, normalize_contribution_scope,
    public_contribution_scope, validate_contribution_scope, whole_edition_contribution)
from catalog.services.citations import _contributors
from catalog.services.knowledge_publication import catalog_snapshot
from catalog.services.publication_commands import prepare_revision
from catalog.services.work_editor import _save_contributors
from catalog.workflow_views import _section_input
from catalog.workflow_serializers import ContributorsSectionSerializer
from .test_reading_paths_20261021 import source

pytestmark = pytest.mark.django_db


def scoped_source():
    _, edition, asset, revision = source()
    ids = [str(uuid4()), str(uuid4())]
    outline = DocumentOutlineRevision.objects.create(asset=asset, document_revision=revision.document_revision,
        revision=1, source_checksum=asset.sha256, is_active=True, reviewed=True,
        nodes=[{"id": ids[i], "parent_id": None, "title": f"合成章节{i + 1}", "pdf_page": i + 1} for i in range(2)])
    scope = {"kind": "chapter", "chapters": [{"title": node["title"], "asset_id": str(asset.pk),
        "document_revision_id": str(revision.document_revision_id), "outline_revision_id": str(outline.pk),
        "outline_node_id": node["id"], "page_start": node["pdf_page"], "page_end": node["pdf_page"]} for node in outline.nodes]}
    return edition, asset, outline, scope


def test_two_chapters_one_contributor_survive_workflow_save_and_snapshot(admin_user):
    edition, _, _, scope = scoped_source()
    person = Person.objects.create(preferred_name="合成章节责任者", authority_status="verified")
    values = _section_input("contributors", {"items": [{"person_id": str(person.pk), "role": "author", "scope": scope}]})
    serializer = ContributorsSectionSerializer(data=values)
    serializer.is_valid(raise_exception=True)
    _save_contributors(edition, serializer.validated_data, admin_user)
    saved = edition.contributions.get()
    assert saved.scope == scope and len(saved.scope["chapters"]) == 2
    snapshot, _ = catalog_snapshot(edition)
    assert snapshot["contributions"][0]["scope"] == scope
    # An older client omitting scope must preserve the explicit chapter responsibility.
    _save_contributors(edition, {"contributors": [{"person_id": person.pk, "role": "author"}]}, admin_user)
    assert edition.contributions.get().scope == scope


@pytest.mark.parametrize("change", ["asset", "document", "outline", "node", "page", "title", "duplicate"])
def test_cross_version_and_invented_chapter_bindings_are_rejected(change):
    edition, _, _, scope = scoped_source()
    altered = deepcopy(scope)
    if change in {"asset", "document", "outline", "node"}:
        field = {"asset": "asset_id", "document": "document_revision_id", "outline": "outline_revision_id", "node": "outline_node_id"}[change]
        altered["chapters"][0][field] = str(uuid4())
    elif change == "page":
        altered["chapters"][0]["page_start"] = 2
    elif change == "title":
        altered["chapters"][0]["title"] = "不存在的章节"
    else:
        altered["chapters"].append(altered["chapters"][0])
    with pytest.raises(ContributionScopeError):
        validate_contribution_scope(edition, altered)


def test_source_withdrawal_masks_chapter_identity_without_whole_book_fallback():
    edition, asset, _, scope = scoped_source()
    data = public_contribution_scope(edition, scope)
    assert data["status"] == "available" and len(data["chapters"]) == 2
    asset.access_status = "restricted"
    asset.save(update_fields=["access_status"])
    masked = public_contribution_scope(edition, scope)
    assert masked["kind"] == "chapter" and masked["status"] == "unavailable" and not masked["chapters"]
    assert "合成章节" not in str(masked) and str(asset.pk) not in str(masked)
    assert not whole_edition_contribution({"scope": scope})


@pytest.mark.parametrize("target", ["outline", "document"])
def test_stale_outline_or_document_is_not_silently_rebound(target):
    edition, _, outline, scope = scoped_source()
    source_revision = outline if target == "outline" else outline.document_revision
    source_revision.is_active = False
    source_revision.save(update_fields=["is_active"])
    assert public_contribution_scope(edition, scope)["status"] == "unavailable"
    with pytest.raises(ContributionScopeError):
        validate_contribution_scope(edition, scope)


def test_registered_chapter_requires_explicit_viewer_access_set():
    edition, asset, _, scope = scoped_source()
    asset.access_status = "registered"
    asset.save(update_fields=["access_status"])
    with pytest.raises(ContributionScopeError):
        validate_contribution_scope(edition, scope, public=True)
    assert validate_contribution_scope(edition, scope, public=True, allowed_access_statuses={"public", "inherit", "registered"}) == scope
    assert public_contribution_scope(edition, scope)["status"] == "unavailable"


def test_publication_rechecks_saved_chapter_when_outline_changed():
    from ingestion.services.publication import publication_preflight
    edition, _, outline, scope = scoped_source()
    person = Person.objects.create(preferred_name="合成责任范围复核")
    Contribution.objects.create(edition=edition, person=person, role="author", approved=True, scope=scope)
    outline.is_active = False
    outline.save(update_fields=["is_active"])
    assert any("责任者章节范围" in reason for reason in publication_preflight(edition)["blockers"])


@pytest.mark.parametrize("new_relationship", [False, True])
def test_identity_undo_does_not_erase_later_chapter_scope(new_relationship):
    from ingestion.services.entity_resolution_decisions import ResolutionDecisionError, _restore_contribution
    edition, _, _, scope = scoped_source()
    person = Person.objects.create(preferred_name="合成身份撤销")
    row = Contribution.objects.create(edition=edition, person=person, role="author", approved=True)
    previous = {"id": str(row.pk), "person_id": str(person.pk), "role": row.role, "order": row.order,
                "source": row.source, "confidence": row.confidence, "approved": row.approved, "scope": {}}
    row.scope = scope
    row.save(update_fields=["scope"])
    with pytest.raises(ResolutionDecisionError, match="后续修改"):
        _restore_contribution(None if new_relationship else previous, previous)
    row.refresh_from_db()
    assert row.scope == scope


def test_whole_edition_citations_exclude_chapter_authors():
    edition, _, _, scope = scoped_source()
    person = Person.objects.create(preferred_name="章节作者")
    Contribution.objects.create(edition=edition, person=person, role="author", approved=True, scope=scope)
    assert not _contributors(edition)
    assert _contributors(edition, {"contributions": [
        {"role": "author", "name": "章节作者", "scope": scope},
        {"role": "author", "name": "整版作者", "scope": {}},
        {"role": "editor", "name": "编者"}]}) == ["整版作者"]


def test_scope_only_change_invalidates_prepared_publication():
    edition, _, _, scope = scoped_source()
    person = Person.objects.create(preferred_name="责任范围核对")
    row = Contribution.objects.create(edition=edition, person=person, role="author", approved=True)
    before = prepare_revision(edition)
    row.scope = scope
    row.save(update_fields=["scope"])
    edition.refresh_from_db()
    after = prepare_revision(edition)
    assert before["fingerprint"] != after["fingerprint"]
    changed = next(value for value in after["changes"] if value["field"] == "contributor_scopes")
    assert "合成章节1" in changed["after_display"]


@pytest.mark.parametrize("value", [{"kind": "chapter", "chapters": []}, {"kind": "other"}, {"kind": "edition", "chapters": [{}]}, {"kind": "edition", "chapters": {}}, {"kind": "edition", "chapters": 0}])
def test_missing_or_ambiguous_scope_cannot_be_published(value):
    with pytest.raises(ContributionScopeError):
        normalize_contribution_scope(value)
