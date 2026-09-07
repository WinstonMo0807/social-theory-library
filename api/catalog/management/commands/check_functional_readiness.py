import json

from django.core.management.base import BaseCommand, CommandError

from catalog.services.system_health import HEALTH_CHECKS, ProbeResult


class Command(BaseCommand):
    help = "Read-only functional release checks; no canonical mutations or automatic recovery."

    def add_arguments(self, parser):
        parser.add_argument("--external", action="store_true", help="Also probe the configured public origin.")

    def handle(self, *args, **options):
        keys = ["database", "migrations", "catalog_workbench", "active_publication", "storage_reader"]
        if options["external"]:
            keys.append("external_public")
        checks = []
        for key in keys:
            probe = HEALTH_CHECKS.get(key)
            try:
                result = probe.runner()
            except Exception as error:
                result = ProbeResult(True, False, False, False, "功能检查失败。", error_code="probe_failed", error_category=error.__class__.__name__)
            passed = result.reachable is True and result.functional is True and result.productive is True
            failed = result.reachable is False or result.functional is False or result.productive is False
            checks.append({"probe": key, "layer": probe.layer, "status": "PASS" if passed else "FAIL" if failed else "SKIPPED",
                           "reason": result.summary, "code": result.error_code, "details": result.details})
        self.stdout.write(json.dumps({"checks": checks, "canonical_mutated": False, "automatic_recovery": False,
                                     "scope": "functional_source_smoke", "full_release_acceptance": False}, ensure_ascii=False))
        if any(row["status"] != "PASS" for row in checks):
            raise CommandError("功能门槛尚未全部验证通过；区分应用与公网结果，不自动回退应用。")
