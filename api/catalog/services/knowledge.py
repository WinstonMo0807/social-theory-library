from catalog.models import RelationReviewStatus, Topic


def publish_knowledge_object(target) -> None:
    if target.editorial_status == "published":
        return
    target.editorial_status = "published"
    target.save(update_fields=["editorial_status", "updated_at"])


def demote_orphaned_knowledge_objects(
    *,
    topic_ids: list | tuple | set = (),
) -> None:
    if topic_ids:
        (
            Topic.objects.filter(
                pk__in=topic_ids,
                editorial_status="published",
            )
            .exclude(work_relations__review_status=RelationReviewStatus.APPROVED)
            .exclude(person_relations__review_status=RelationReviewStatus.APPROVED)
            .update(editorial_status="draft")
        )
