from catalog.models import TheorySchool, Topic


def publish_knowledge_object(target) -> None:
    if target.editorial_status == "published":
        return
    target.editorial_status = "published"
    target.save(update_fields=["editorial_status", "updated_at"])


def demote_orphaned_knowledge_objects(
    *,
    theory_ids: list | tuple | set = (),
    topic_ids: list | tuple | set = (),
) -> None:
    if theory_ids:
        (
            TheorySchool.objects.filter(
                pk__in=theory_ids,
                editorial_status="published",
            )
            .exclude(workknowledgerelation__approved=True)
            .exclude(personknowledgerelation__approved=True)
            .update(editorial_status="draft")
        )
    if topic_ids:
        (
            Topic.objects.filter(
                pk__in=topic_ids,
                editorial_status="published",
            )
            .exclude(workknowledgerelation__approved=True)
            .exclude(personknowledgerelation__approved=True)
            .update(editorial_status="draft")
        )
