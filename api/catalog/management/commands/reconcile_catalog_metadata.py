import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from catalog.models import KnowledgePublicationEvent
from catalog.services.knowledge_publication import metadata_activation_preflight, recover_catalog_metadata


class Command(BaseCommand):
    help = "Inspect or explicitly recover one approved metadata-only first publication; retain pending jobs and files."

    def add_arguments(self, parser):
        parser.add_argument("--event-id", type=UUID, required=True)
        parser.add_argument("--edition-id", type=UUID, required=True)
        parser.add_argument("--apply", action="store_true", help="Activate only if all read-only checks still pass.")

    def handle(self, *args, **options):
        try:
            event = KnowledgePublicationEvent.objects.select_related(
                "catalog_revision__edition", "catalog_revision__reader_asset", "domain_event",
            ).get(pk=options["event_id"])
        except KnowledgePublicationEvent.DoesNotExist as exc:
            raise CommandError("找不到指定的发布事件。") from exc
        if event.catalog_revision is None or event.catalog_revision.edition_id != options["edition_id"]:
            raise CommandError("事件不属于明确指定的馆藏版本。")
        if options["apply"]:
            try:
                result = recover_catalog_metadata(event.pk, expected_edition_id=options["edition_id"])
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
        else:
            result = {
                "dry_run": True,
                "event_id": str(event.pk),
                "edition_id": str(event.catalog_revision.edition_id),
                "catalog_revision_id": str(event.catalog_revision_id),
                "event_status": event.status,
                "event_attempts": event.attempts,
                **metadata_activation_preflight(event, require_idle=True),
                "deliveries": list(event.deliveries.values("consumer", "status")),
            }
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
