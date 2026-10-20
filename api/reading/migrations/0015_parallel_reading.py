"""Private manual alignments and separately reviewed contributions; no backfill."""
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def identity_fields():
    return [
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
    ]


def private_fields():
    return [*identity_fields(),
        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ("revision", models.PositiveIntegerField(default=1)),
        ("data_ciphertext", models.BinaryField(blank=True, default=bytes)),
        ("request_id", models.UUIDField(default=uuid.uuid4)),
    ]


def asset_fields():
    return [(side, models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
             related_name="+", to="catalog.asset")) for side in ("left_asset", "right_asset")]


class Migration(migrations.Migration):
    dependencies = [
        ("reading", "0014_annotation_tags"),
        ("catalog", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name="ParallelReadingTask", fields=[*private_fields(), *asset_fields()],
            options={"ordering": ["-updated_at"], "constraints": [
                models.UniqueConstraint(fields=("user", "request_id"), name="parallel_task_request_unique")],
                "indexes": [models.Index(fields=["user", "left_asset", "-updated_at"], name="parallel_owner_left_idx")]}),
        migrations.CreateModel(name="ParallelReadingReceipt", fields=[
            *identity_fields(),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ("task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="receipts", to="reading.parallelreadingtask")),
            ("request_id", models.UUIDField()),
            ("fingerprint", models.CharField(max_length=64)),
            ("applied_revision", models.PositiveIntegerField()),
        ], options={"constraints": [
            models.UniqueConstraint(fields=("user", "request_id"), name="parallel_receipt_request_unique")]}),
        migrations.CreateModel(name="ParallelCalibration", fields=[*private_fields(), *asset_fields(),
            ("scope", models.CharField(choices=[("bibliography", "Bibliography"), ("passages", "Passages")], max_length=16)),
            ("status", models.CharField(choices=[("submitted", "Submitted"), ("reviewed", "Reviewed"),
                ("published", "Published"), ("rejected", "Rejected")], db_index=True, default="submitted", max_length=16)),
            ("reviewer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-updated_at"], "constraints": [
            models.UniqueConstraint(fields=("user", "request_id"), name="parallel_calib_request_unique")],
            "indexes": [models.Index(fields=["status", "left_asset", "-updated_at"], name="parallel_calib_status_idx")]}),
    ]
