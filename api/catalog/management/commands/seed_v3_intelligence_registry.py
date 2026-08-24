from __future__ import annotations

import hashlib
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import PromptRegistryEntry, ResearchTaskProfile
from catalog.services.research.task_profiles import BUILTIN_TASK_PROFILES, seed_builtin_task_profiles


class Command(BaseCommand):
    help = "幂等写入 3.0 ResearchTaskProfile 与 evidence-bound Prompt Registry 基线。"

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="只检查缺失或漂移，不写数据库。")

    def handle(self, *args, **options):
        if options["check"]:
            missing_profiles = [
                key
                for key, spec in BUILTIN_TASK_PROFILES.items()
                if not ResearchTaskProfile.objects.filter(key=key, version=spec.version, is_active=True).exists()
            ]
            missing_prompts = [
                spec.prompt_key
                for spec in BUILTIN_TASK_PROFILES.values()
                if not PromptRegistryEntry.objects.filter(
                    key=spec.prompt_key,
                    version=spec.version,
                    status=PromptRegistryEntry.Status.ACTIVE,
                ).exists()
            ]
            payload = {
                "ok": not missing_profiles and not missing_prompts,
                "missing_profiles": missing_profiles,
                "missing_prompts": missing_prompts,
            }
            self.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            if not payload["ok"]:
                raise SystemExit(1)
            return

        with transaction.atomic():
            profile_result = seed_builtin_task_profiles()
            prompt_created = 0
            for spec in BUILTIN_TASK_PROFILES.values():
                content = (
                    f"执行 {spec.name}。只能使用输入的 EvidencePack 与明确给出的知识对象。"
                    "检索结果可以广，但返回内容必须满足 minimum_evidence_policy。"
                    "SearXNG snippet 只可作为线索，不能作为正式证据。"
                    "不得修改 Canonical Knowledge；证据不足时返回 insufficient_evidence。"
                    "输出必须是符合 output_schema 的 JSON。"
                )
                schema_json = json.dumps(spec.output_schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                schema_hash = hashlib.sha256(schema_json.encode("utf-8")).hexdigest()
                PromptRegistryEntry.objects.filter(
                    key=spec.prompt_key,
                    status=PromptRegistryEntry.Status.ACTIVE,
                ).exclude(version=spec.version).update(status=PromptRegistryEntry.Status.RETIRED)
                _, created = PromptRegistryEntry.objects.update_or_create(
                    key=spec.prompt_key,
                    version=spec.version,
                    defaults={
                        "capability": spec.required_capability,
                        "task_profile_key": spec.key,
                        "content": content,
                        "output_schema": spec.output_schema,
                        "provider_guidance": {
                            "evidence_bound": True,
                            "cloud_optional": True,
                            "canonical_write": "forbidden",
                        },
                        "content_hash": content_hash,
                        "schema_hash": schema_hash,
                        "status": PromptRegistryEntry.Status.ACTIVE,
                    },
                )
                prompt_created += int(created)
        self.stdout.write(
            json.dumps(
                {
                    "profiles": profile_result,
                    "prompt_created": prompt_created,
                    "prompt_total": len(BUILTIN_TASK_PROFILES),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

