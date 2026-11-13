"""A name correction must not publish other pending catalog edits."""
from copy import deepcopy
from uuid import uuid4
import pytest
from catalog.models import Contribution, Person
from catalog.services.knowledge_publication import create_catalog_publication_event
from tests.test_discovery_sessions_v308 import fixture_source


@pytest.mark.django_db
def test_citation_name_publication_preserves_formal_book_and_document(monkeypatch):
    edition, asset, _, _ = fixture_source(count=1)
    person = Person.objects.create(preferred_name='布罗尼斯拉夫·马林诺夫斯基', citation_name='马林诺夫斯基', authority_status='verified')
    Contribution.objects.create(edition=edition, person=person, role='author', approved=True)
    formal = edition.active_catalog_revision
    formal.status = 'superseded'
    formal.save(update_fields=['status'])
    original = deepcopy(formal.snapshot)
    original.setdefault('document', {})
    original['contributions'] = [{'role': 'author', 'person': {'id': str(person.pk), 'preferred_name': person.preferred_name}}]
    formal.snapshot = original
    formal.status = 'active'
    formal.pk = uuid4()
    formal.revision += 1
    formal._state.adding = True
    formal.save(force_insert=True)
    edition.active_catalog_revision = formal
    edition.save(update_fields=['active_catalog_revision'])
    edition.work.title = '尚未发布的书名改动'
    edition.work.save(update_fields=['title'])
    edition.publisher = '尚未发布的出版社'
    edition.save(update_fields=['publisher'])
    def unexpected(*args, **kwargs):
        pytest.fail('A citation correction must not prepare or publish unrelated bundles')
    monkeypatch.setattr('catalog.services.knowledge_publication.ensure_publication_bundle', unexpected)
    event = create_catalog_publication_event(edition, event_type='catalog_updated', changed_fields=['contributors'],
        idempotency_key=f'citation-name:{uuid4()}', provenance={'source': 'person_citation_name', 'person_id': str(person.pk)})
    result = deepcopy(event.catalog_revision.snapshot)
    assert result['contributions'][0]['person'].pop('citation_name') == '马林诺夫斯基'
    assert result == original
    assert event.catalog_revision.reader_asset_id == formal.reader_asset_id
    assert event.catalog_revision.document_revision_id == formal.document_revision_id
