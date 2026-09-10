"""Explicit test-only consumer acknowledgements for catalog API scenarios.

These fixtures exercise the real publication event and activation gate. They
do not execute or establish availability of Meilisearch, embeddings or Celery.
Never use them in production commands or readiness checks.
"""
from catalog.models import KnowledgePublicationEvent, ProjectionState
from catalog.services.knowledge_publication import process_knowledge_event


def confirm_book_identity(edition, actor):
    """Explicit test input, not inferred confirmation from an OCR score."""
    from catalog.models import Contribution, Person
    from catalog.services.field_decisions import record_edition_field_decision

    assert edition.work.document_type == "book"
    if not edition.contributions.filter(role="author", approved=True).exists():
        person = Person.objects.create(
            preferred_name="人工确认测试作者", sort_name="人工确认测试作者", authority_status="verified",
        )
        Contribution.objects.create(
            edition=edition, person=person, role="author", approved=True, source="manual_test_input",
        )
    for name in ("title", "document_type", "language"):
        record_edition_field_decision(
            edition, name, value=getattr(edition.work, name), status="confirmed", actor=actor,
        )
    authors = edition.contributions.filter(role="author", approved=True).values_list("person_id", flat=True)
    record_edition_field_decision(
        edition, "authors", value=[str(pk) for pk in authors], status="confirmed", actor=actor,
    )


def acknowledge_catalog_projections(edition):
    event = KnowledgePublicationEvent.objects.filter(
        catalog_revision__edition=edition,
    ).select_related("catalog_revision", "domain_event").order_by("-catalog_revision__revision").first()
    assert event is not None, "Publication must create a durable event before test acknowledgement."
    assert event.event_type in {"catalog_published", "catalog_updated"}
    assert event.catalog_revision.metadata_ready
    requirements = {
        name for delivery in event.deliveries.exclude(status="skipped")
        for name in delivery.result.get("required_projections", [])
    }
    states = ProjectionState.objects.filter(object_type=event.object_type, object_id=event.object_id, projection_type__in=requirements)
    assert set(states.values_list("projection_type", flat=True)) == requirements, "Do not invent missing projection registrations."
    assert not states.filter(source_revision__lt=event.domain_event.canonical_revision).exists()
    states.update(status="current", projected_revision=event.domain_event.canonical_revision)
    completed = process_knowledge_event(event.pk)
    assert completed.status == "completed", completed.last_error_message
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == event.catalog_revision_id
    assert edition.active_catalog_revision.status == "active"
    return completed
