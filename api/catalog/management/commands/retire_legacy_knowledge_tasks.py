from django.core.management.base import BaseCommand, CommandError
from catalog.models import CapabilityDemand, CuratedClaim, KnowledgeLegacyMapping
from catalog.services.knowledge_retirement import RETIRED_TASKS, cancel_legacy_demand


class Command(BaseCommand):
    help="停止旧claim/library_synthesis任务并撤销租约；保留历史行、其他任务和搜索索引。默认只列范围。"

    def add_arguments(self,parser):
        parser.add_argument("--apply",action="store_true")
        parser.add_argument("--batch-size",type=int,default=100)

    def handle(self,*args,**options):
        size=options["batch_size"]
        if not 1<=size<=500:raise CommandError("batch-size须为1至500")
        migrated=KnowledgeLegacyMapping.objects.filter(source_type="catalog.curatedclaim",target_type="assertion",
            provenance__migration_version=2).values("source_id")
        missing=CuratedClaim.objects.exclude(pk__in=migrated).count()
        if options["apply"] and missing:
            raise CommandError(f"仍有{missing}条人工观点未迁移，请先运行backfill_knowledge_core --claims。")
        rows=CapabilityDemand.objects.filter(payload__task_kind__in=RETIRED_TASKS).exclude(state__in=["completed","canceled"])
        self.stdout.write(str({"eligible":rows.count(),"unmigrated_human_claims":missing,"apply":options["apply"]}))
        if options["apply"]:
            count=sum(cancel_legacy_demand(key) for key in list(rows.order_by("id").values_list("id",flat=True)[:size]))
            self.stdout.write(str({"canceled":count,"remaining":rows.count(),"history_retained":True}))
