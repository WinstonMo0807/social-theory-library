import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0041_v304_asset_text_revisions")]

    operations = [
        migrations.CreateModel(
            name="JournalIssueArticle",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=600)),
                ("author_display", models.CharField(blank=True, max_length=600)),
                ("page_range", models.CharField(blank=True, max_length=80)),
                ("position", models.PositiveIntegerField(default=0)),
                ("issue", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="journal_articles", to="catalog.edition")),
                ("article_work", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="journal_issue_entries", to="catalog.work")),
            ],
            options={
                "ordering": ["position", "created_at", "id"],
                "constraints": [models.UniqueConstraint(condition=models.Q(article_work__isnull=False), fields=("issue", "article_work"), name="unique_issue_article_work")],
            },
        ),
    ]
