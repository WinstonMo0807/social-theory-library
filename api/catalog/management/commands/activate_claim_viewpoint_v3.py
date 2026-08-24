from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from catalog.services.claim_benchmark import activate_claim_viewpoint_ranking


class Command(BaseCommand):
    help = "用已通过的 PostgreSQL benchmark run 激活 Claim Viewpoint Ranking。"

    def add_arguments(self, parser):
        parser.add_argument("--report-hash", required=True)
        parser.add_argument("--actor-email", required=True)

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(
            email__iexact=str(options["actor_email"] or "").strip()
        ).first()
        if actor is None:
            raise CommandError("找不到激活操作人。")
        try:
            result = activate_claim_viewpoint_ranking(
                str(options["report_hash"] or ""),
                actor=actor,
            )
        except (PermissionError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
