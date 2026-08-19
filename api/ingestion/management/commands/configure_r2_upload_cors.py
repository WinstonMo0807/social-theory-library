import json

from django.core.management.base import BaseCommand

from ingestion.services.r2_staging import apply_r2_cors_policy, r2_cors_policy


class Command(BaseCommand):
    help = "Configure the temporary R2 upload bucket CORS policy without exposing credentials."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options["dry_run"]:
            policy = r2_cors_policy()
            result = {
                "dry_run": True,
                "allowed_origins": policy["CORSRules"][0]["AllowedOrigins"],
                "allowed_methods": policy["CORSRules"][0]["AllowedMethods"],
                "expose_headers": policy["CORSRules"][0]["ExposeHeaders"],
            }
        else:
            result = {"dry_run": False, **apply_r2_cors_policy()}
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
