import json

from django.core.management.base import BaseCommand, CommandError

from catalog.services.public_knowledge_control import public_management_coverage


class Command(BaseCommand):
    help = "Audit public Scholar, Theory and Topic pages against admin and preview contracts."

    def handle(self, *args, **options):
        report = public_management_coverage()
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=list))
        if report["errors"]:
            raise CommandError("Public management coverage has blocking gaps.")
