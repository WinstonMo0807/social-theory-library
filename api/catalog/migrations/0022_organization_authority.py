from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0021_asset_registered_access"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationAuthority",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("preferred_name", models.CharField(db_index=True, max_length=300)),
                ("original_name", models.CharField(blank=True, max_length=300)),
                ("aliases", models.JSONField(blank=True, default=list)),
                ("organization_type", models.CharField(choices=[("university", "高校"), ("research_institute", "研究机构"), ("association", "学会或协会"), ("government", "政府机构"), ("archive", "档案或收藏机构"), ("other", "其他机构")], db_index=True, default="other", max_length=32)),
                ("country", models.CharField(blank=True, max_length=120)),
                ("external_ids", models.JSONField(blank=True, default=dict)),
                ("description", models.TextField(blank=True)),
                ("authority_status", models.CharField(choices=[("draft", "草稿"), ("needs_review", "待消歧"), ("verified", "已核验"), ("rejected", "已拒绝"), ("merged", "已合并"), ("archived", "已归档")], db_index=True, default="draft", max_length=20)),
            ],
            options={"ordering": ["preferred_name"]},
        ),
        migrations.CreateModel(
            name="OrganizationContribution",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("role", models.CharField(choices=[("degree_granting", "学位授予单位"), ("report_issuer", "报告发布机构"), ("sponsor", "主办机构"), ("issuing_body", "责任机构"), ("archive", "收藏机构")], max_length=32)),
                ("verbatim_name", models.CharField(blank=True, max_length=300)),
                ("source", models.CharField(blank=True, max_length=120)),
                ("confidence", models.FloatField(default=1)),
                ("approved", models.BooleanField(default=False)),
                ("edition", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="organization_contributions", to="catalog.edition")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="contributions", to="catalog.organizationauthority")),
            ],
            options={"ordering": ["role", "created_at"]},
        ),
        migrations.AddConstraint(
            model_name="organizationauthority",
            constraint=models.UniqueConstraint(fields=("preferred_name", "organization_type"), name="unique_organization_authority_name_type"),
        ),
        migrations.AddConstraint(
            model_name="organizationcontribution",
            constraint=models.UniqueConstraint(fields=("edition", "organization", "role"), name="unique_organization_contribution"),
        ),
    ]
