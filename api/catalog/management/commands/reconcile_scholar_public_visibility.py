from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import Person, ScholarProfile
from catalog.services.scholar_publication import (
    PUBLICATION_REVIEWABLE_STATUSES,
    ensure_scholar_public_authority,
)


class Command(BaseCommand):
    help = "Inventory and optionally reconcile published Scholar pages whose Person is not public-eligible."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Verify reviewable Person records. Without this flag the command is read-only.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        profiles = list(
            ScholarProfile.objects.select_related("person")
            .filter(editorial_status="published")
            .exclude(person__authority_status=Person.AuthorityStatus.VERIFIED)
            .order_by("person__preferred_name")
        )
        blocked = [
            profile
            for profile in profiles
            if profile.person.authority_status not in PUBLICATION_REVIEWABLE_STATUSES
        ]
        reviewable = [profile for profile in profiles if profile not in blocked]
        self.stdout.write(
            f"published_mismatch={len(profiles)} reviewable={len(reviewable)} blocked={len(blocked)} apply={str(apply_changes).lower()}"
        )
        for profile in profiles:
            action = "blocked" if profile in blocked else "verify" if apply_changes else "would_verify"
            self.stdout.write(
                f"{profile.id}\t{profile.person.preferred_name}\t{profile.person.authority_status}\t{action}"
            )
        if blocked and apply_changes:
            raise CommandError(
                "存在已拒绝、合并或归档的人物记录，未执行任何收敛。请先处理权威身份。"
            )
        if apply_changes:
            for profile in reviewable:
                ensure_scholar_public_authority(profile)
            self.stdout.write(self.style.SUCCESS(f"reconciled={len(reviewable)}"))
        else:
            transaction.set_rollback(True)
