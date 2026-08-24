from django.db import migrations, transaction


def backfill_adopted_reading_path_semantics(apps, schema_editor):
    ReadingPath = apps.get_model("catalog", "ReadingPath")
    ReadingPathCandidate = apps.get_model("catalog", "ReadingPathCandidate")
    ReadingPathItem = apps.get_model("catalog", "ReadingPathItem")
    CanonicalObjectRevision = apps.get_model("catalog", "CanonicalObjectRevision")
    DomainChangeEvent = apps.get_model("catalog", "DomainChangeEvent")
    database = schema_editor.connection.alias

    candidates = (
        ReadingPathCandidate.objects.using(database)
        .filter(status="adopted")
        .exclude(adopted_reading_path_id=None)
        .order_by("adopted_reading_path_id", "-created_at", "-id")
    )

    def apply_path_candidates(path_id, path_candidates):
        event_key = f"migration-v301-reading-path-semantics:{path_id}"
        if DomainChangeEvent.objects.using(database).filter(
            idempotency_key=event_key
        ).exists():
            return

        learning_goal = next(
            (
                str(candidate.learning_goal or "").strip()
                for candidate in path_candidates
                if str(candidate.learning_goal or "").strip()
            ),
            "",
        )
        prerequisites_by_work = {}
        # Candidates are newest first. setdefault therefore preserves the most
        # recent human-adopted value while still filling gaps from older rows.
        for candidate in path_candidates:
            for stage in candidate.stages if isinstance(candidate.stages, list) else []:
                if not isinstance(stage, dict):
                    continue
                for source in stage.get("works") or []:
                    if not isinstance(source, dict):
                        continue
                    work_id = str(source.get("work_id") or "")
                    prerequisite = str(source.get("prerequisite") or "").strip()
                    if work_id and prerequisite:
                        prerequisites_by_work.setdefault(work_id, prerequisite)
        with transaction.atomic(using=database):
            path_updated = 0
            if learning_goal:
                path_updated = ReadingPath.objects.using(database).filter(
                    pk=path_id,
                    learning_goal="",
                ).update(learning_goal=learning_goal)
            items = list(
                ReadingPathItem.objects.using(database).filter(
                    reading_path_id=path_id,
                    prerequisite="",
                    work_id__in=prerequisites_by_work,
                )
            )
            for item in items:
                item.prerequisite = prerequisites_by_work.get(str(item.work_id), "")
            items = [item for item in items if item.prerequisite]
            if items:
                ReadingPathItem.objects.using(database).bulk_update(
                    items,
                    ["prerequisite"],
                    batch_size=500,
                )
            if not path_updated and not items:
                return
            revision, _created = CanonicalObjectRevision.objects.using(
                database
            ).get_or_create(
                object_type="reading_path",
                object_id=path_id,
                defaults={"current_revision": 0},
            )
            revision.current_revision += 1
            revision.save(update_fields=["current_revision", "updated_at"], using=database)
            changed_fields = []
            if path_updated:
                changed_fields.append("learning_goal")
            if items:
                changed_fields.append("stage_groups")
            DomainChangeEvent.objects.using(database).create(
                object_type="reading_path",
                object_id=path_id,
                canonical_revision=revision.current_revision,
                change_kind="update",
                changed_fields=changed_fields,
                idempotency_key=event_key,
            )

    current_path_id = None
    path_candidates = []
    for candidate in candidates.iterator(chunk_size=200):
        if current_path_id is not None and candidate.adopted_reading_path_id != current_path_id:
            apply_path_candidates(current_path_id, path_candidates)
            path_candidates = []
        current_path_id = candidate.adopted_reading_path_id
        path_candidates.append(candidate)
    if current_path_id is not None:
        apply_path_candidates(current_path_id, path_candidates)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("catalog", "0037_editorialrevision_discipline"),
    ]

    operations = [
        migrations.RunPython(
            backfill_adopted_reading_path_semantics,
            migrations.RunPython.noop,
        ),
    ]
