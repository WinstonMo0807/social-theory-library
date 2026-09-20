import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def preserve_site_public_revision(apps, schema_editor):
    Setting = apps.get_model("catalog", "SiteSetting")
    Block = apps.get_model("catalog", "AboutPageBlock")
    Revision = apps.get_model("catalog", "EditorialRevision")
    setting = Setting.objects.filter(key="site_config", public=True).first()
    if setting is None and not Block.objects.exists():
        return
    if setting is None:
        setting = Setting.objects.create(key="site_config", value={}, public=True)
    blocks = list(Block.objects.values("key", "block_type", "title", "body", "icon", "action_label", "action_href", "sort_order", "visible", "configuration"))
    payload = {"config": setting.value, "about_blocks": blocks}
    Revision.objects.get_or_create(target_type="site_content", target_id=setting.pk, revision=1,
        defaults={"base_revision": 0, "patch": payload, "materialized_preview": payload, "changed_fields": [],
                  "status": "published", "published_at": timezone.now(), "change_note": "保留3.0.7前已公开的网站内容",
                  "idempotency_key": f"v307-site-baseline:{setting.pk}"})


class Migration(migrations.Migration):
    dependencies = [("catalog", "0056_v306_taxonomy_media"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AlterField(model_name="editorialrevision", name="target_type", field=models.CharField(max_length=32, db_index=True, choices=[("work", "作品"), ("edition", "版本"), ("knowledge_node", "知识节点"), ("scholar_profile", "学者"), ("discipline", "学科"), ("subdiscipline", "子学科"), ("topic", "主题"), ("publisher", "出版社"), ("reading_path", "阅读路径"), ("knowledge_relation", "理论关系"), ("timeline_event", "时间线事件"), ("recommendation_issue", "书库推荐期"), ("site_content", "网站与关于书库")])),
        migrations.CreateModel(name="RecommendationIssue", fields=[
            ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("slug", models.SlugField(max_length=180, unique=True)), ("title", models.CharField(max_length=600)),
            ("display_from", models.DateTimeField(null=True, blank=True, db_index=True)), ("published_at", models.DateTimeField(null=True, blank=True)),
            ("active_revision", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name="active_recommendation_issues", to="catalog.editorialrevision")),
            ("scheduled_revision", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name="scheduled_recommendation_issues", to="catalog.editorialrevision")),
            ("scheduled_for", models.DateTimeField(null=True, blank=True, db_index=True)),
            ("created_by", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_recommendation_issues", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-display_from", "-created_at"]}),
        migrations.CreateModel(name="RecommendationIssueItem", fields=[
            ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("linked_at", models.DateTimeField(null=True, blank=True)),
            ("issue", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="items", to="catalog.recommendationissue")),
            ("cataloging_session", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name="recommendation_items", to="catalog.catalogingsession")),
            ("planned_work", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name="planned_recommendation_items", to="catalog.work")),
            ("linked_work", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name="linked_recommendation_items", to="catalog.work")),
            ("linked_edition", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name="recommendation_issue_items", to="catalog.edition")),
            ("linked_by", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="linked_recommendation_items", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.RunPython(preserve_site_public_revision, migrations.RunPython.noop),
    ]
