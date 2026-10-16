"""Add private research state; no data backfill, external calls or public writes."""
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def identity_fields():
    return [
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("revision", models.PositiveIntegerField(default=1)),
        ("data_ciphertext", models.BinaryField(blank=True, default=bytes)),
    ]


def owner_field():
    return ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL))


def project_field(related_name):
    return ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
        related_name=related_name, to="reading.researchproject"))


class Migration(migrations.Migration):
    dependencies = [
        ("reading", "0007_reader_ai_connection"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(name="ResearchProject", fields=[
            *identity_fields(), owner_field(),
            ("request_id", models.UUIDField(default=uuid.uuid4)),
            ("archived", models.BooleanField(default=False)),
            ("conversation", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="research", to="reading.libraryconversation")),
        ], options={"ordering": ["-updated_at"], "indexes": [models.Index(
            fields=["user", "archived", "-updated_at"], name="research_owner_archive_idx")],
            "constraints": [models.UniqueConstraint(fields=("user", "request_id"), name="research_project_request_unique")]}),
        migrations.CreateModel(name="ResearchTurn", fields=[
            *identity_fields(),
            ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="turns", to="reading.researchproject")),
            ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="branches", to="reading.researchturn")),
            ("request_id", models.UUIDField(default=uuid.uuid4)),
            ("discovery_session_id", models.UUIDField(blank=True, null=True)),
            ("status", models.CharField(db_index=True, default="queued", max_length=16)),
            ("generation", models.PositiveIntegerField(default=1)),
            ("task_id", models.CharField(blank=True, max_length=64)),
            ("error_code", models.CharField(blank=True, max_length=80)),
            ("finished_at", models.DateTimeField(blank=True, null=True)),
        ], options={"ordering": ["created_at"], "constraints": [models.UniqueConstraint(
            fields=("project", "request_id"), name="research_turn_request_unique")]}),
        migrations.CreateModel(name="CitationAudit", fields=[
            *identity_fields(), owner_field(), project_field("audits"),
            ("request_id", models.UUIDField(default=uuid.uuid4)),
            ("original_ciphertext", models.BinaryField(default=bytes)),
            ("content_hash", models.CharField(max_length=64)),
            ("status", models.CharField(db_index=True, default="queued", max_length=16)),
            ("generation", models.PositiveIntegerField(default=1)),
            ("task_id", models.CharField(blank=True, max_length=64)),
            ("error_code", models.CharField(blank=True, max_length=80)),
            ("completed_units", models.PositiveIntegerField(default=0)),
            ("total_units", models.PositiveIntegerField(default=0)),
            ("finished_at", models.DateTimeField(blank=True, null=True)),
        ], options={"ordering": ["-updated_at"], "constraints": [models.UniqueConstraint(
            fields=("user", "request_id"), name="citation_audit_request_unique")]}),
        migrations.CreateModel(name="PersonalReadingPlan", fields=[
            *identity_fields(), owner_field(), project_field("plans"),
            ("request_id", models.UUIDField(default=uuid.uuid4)),
        ], options={"ordering": ["-updated_at"], "constraints": [models.UniqueConstraint(
            fields=("user", "request_id"), name="reading_plan_request_unique")]}),
        migrations.CreateModel(name="ResearchMemory", fields=[
            *identity_fields(), owner_field(), project_field("memories"),
            ("request_id", models.UUIDField(default=uuid.uuid4)),
            ("state", models.CharField(default="proposed", max_length=16)),
            ("embedding_ciphertext", models.BinaryField(blank=True, default=bytes)),
            ("embedding_artifact", models.CharField(blank=True, max_length=160)),
        ], options={"ordering": ["-updated_at"], "indexes": [models.Index(
            fields=["user", "state"], name="memory_owner_state_idx")], "constraints": [models.UniqueConstraint(
            fields=("user", "request_id"), name="research_memory_request_unique")]}),
    ]
