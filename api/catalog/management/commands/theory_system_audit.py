import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError
from django.db.models import Count, Q

from catalog.models import (
    Concept,
    KnowledgeNode,
    LegacyKnowledgeMapping,
    Subdiscipline,
    TheorySchool,
    WorkKnowledgeRelation,
)


class Command(BaseCommand):
    help = "生成理论系统迁移前后统计，识别重复与待人工处理记录。"

    def add_arguments(self, parser):
        parser.add_argument("--output", help="可选 JSON 输出路径")

    def handle(self, *args, **options):
        old_names = [
            *(TheorySchool.objects.values_list("name", flat=True)),
            *(Subdiscipline.objects.values_list("name", flat=True)),
            *(Concept.objects.values_list("name", flat=True)),
        ]
        normalized = [" ".join(str(name).casefold().split()) for name in old_names if name]
        duplicates = sorted(name for name, count in Counter(normalized).items() if count > 1)
        isolated_theories = list(
            TheorySchool.objects.annotate(
                relation_count=Count(
                    "workknowledgerelation",
                    filter=Q(workknowledgerelation__approved=True),
                    distinct=True,
                )
            )
            .filter(relation_count=0)
            .values_list("name", flat=True)
        )
        pending_relations = WorkKnowledgeRelation.objects.filter(
            Q(approved=False) | ~Q(review_status="approved")
        ).count()
        try:
            normalized_report = {
                "available": True,
                "nodes": KnowledgeNode.objects.count(),
                "published_nodes": KnowledgeNode.objects.filter(status="published").count(),
                "mappings": LegacyKnowledgeMapping.objects.count(),
                "nodes_without_legacy_mapping": KnowledgeNode.objects.filter(
                    legacy_mappings__isnull=True
                ).count(),
            }
        except (OperationalError, ProgrammingError):
            normalized_report = {
                "available": False,
                "reason": "规范化知识表尚未迁移",
            }

        report = {
            "legacy": {
                "theory_schools": TheorySchool.objects.count(),
                "subdisciplines": Subdiscipline.objects.count(),
                "concepts": Concept.objects.count(),
                "duplicate_normalized_names": duplicates,
                "duplicate_name_count": len(duplicates),
                "isolated_theories": isolated_theories,
                "isolated_theory_count": len(isolated_theories),
                "pending_work_relations": pending_relations,
            },
            "normalized": normalized_report,
            "manual_review_estimate": len(duplicates) + pending_relations,
        }
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        if options.get("output"):
            output = Path(options["output"]).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"报告已写入 {output}"))
        self.stdout.write(payload)
