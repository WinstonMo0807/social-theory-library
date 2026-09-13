import inspect

from catalog.services import knowledge_publication


def test_nullable_publication_revision_joins_lock_only_event_rows():
    """PostgreSQL rejects locking the nullable joined revision side.

    Event rows remain locked; revision and Edition locks are acquired explicitly
    by activation. The runtime PostgreSQL recovery check exercises the query.
    """
    source = inspect.getsource(knowledge_publication)
    assert 'KnowledgePublicationEvent.objects.select_for_update()\n        .select_related("catalog_revision")' not in source
    assert 'KnowledgePublicationEvent.objects.select_for_update()\n            .select_related("catalog_revision")' not in source
    assert 'KnowledgePublicationEvent.objects.select_for_update(of=("self",))' in inspect.getsource(knowledge_publication._finish_event)
