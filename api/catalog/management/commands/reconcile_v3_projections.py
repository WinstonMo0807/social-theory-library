from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.db.models import F

from catalog.models import CapabilityDemand, ProjectionState
from catalog.services.projection_refresh import reconcile_projection_runtime


class Command(BaseCommand):
    help = "有界恢复 3.0 Projection lease、capability demand 与遗漏调度。"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        limit = max(1, min(int(options["limit"]), 100))
        before = {
            "stale_projection_states": ProjectionState.objects.filter(
                source_revision__gt=F("projected_revision"),
            ).exclude(status=ProjectionState.Status.CURRENT).count(),
            "waiting_projection_demands": CapabilityDemand.objects.filter(
                capability="projection",
                state__in=[
                    CapabilityDemand.State.WAITING_FOR_CAPABILITY,
                    CapabilityDemand.State.READY,
                    CapabilityDemand.State.CLAIMED,
                ],
            ).count(),
        }
        if options["dry_run"]:
            result = {"dry_run": True, "limit": limit, "before": before}
        else:
            runtime = reconcile_projection_runtime(limit=limit)
            result = {
                "dry_run": False,
                "limit": limit,
                "before": before,
                "runtime": runtime,
                "after": {
                    "stale_projection_states": ProjectionState.objects.filter(
                        source_revision__gt=F("projected_revision"),
                    ).exclude(status=ProjectionState.Status.CURRENT).count(),
                    "waiting_projection_demands": CapabilityDemand.objects.filter(
                        capability="projection",
                        state__in=[
                            CapabilityDemand.State.WAITING_FOR_CAPABILITY,
                            CapabilityDemand.State.READY,
                            CapabilityDemand.State.CLAIMED,
                        ],
                    ).count(),
                },
            }
        self.stdout.write(json.dumps(result, ensure_ascii=False, default=str))
