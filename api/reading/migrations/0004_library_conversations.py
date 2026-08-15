import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0023_search_evaluation_task_tracking"),
        ("reading", "0003_backfill_saved_item_progress"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LibraryConversation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(blank=True, max_length=240)),
                ("assist_mode", models.CharField(choices=[("auto", "自动判断"), ("on", "只依据书库"), ("off", "不检索书库")], default="auto", max_length=12)),
                ("scope", models.JSONField(blank=True, default=dict)),
                ("archived", models.BooleanField(db_index=True, default=False)),
                ("last_message_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="library_conversations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-last_message_at", "-updated_at"]},
        ),
        migrations.CreateModel(
            name="LibraryMessage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("role", models.CharField(choices=[("user", "读者"), ("assistant", "书库助手")], max_length=16)),
                ("body_ciphertext", models.BinaryField(blank=True, default=bytes)),
                ("status", models.CharField(choices=[("pending", "等待生成"), ("streaming", "正在生成"), ("completed", "已完成"), ("failed", "生成失败"), ("canceled", "已取消")], db_index=True, default="completed", max_length=16)),
                ("retrieval_used", models.BooleanField(default=False)),
                ("model_provider", models.CharField(blank=True, max_length=40)),
                ("model_name", models.CharField(blank=True, max_length=240)),
                ("prompt_version", models.CharField(blank=True, max_length=80)),
                ("error_code", models.CharField(blank=True, max_length=80)),
                ("error_message", models.TextField(blank=True)),
                ("usage", models.JSONField(blank=True, default=dict)),
                ("cancel_requested_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="reading.libraryconversation")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="LibraryMessageSource",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_key", models.CharField(max_length=24)),
                ("ordinal", models.PositiveSmallIntegerField()),
                ("source_chunk_id", models.CharField(blank=True, max_length=120)),
                ("title_snapshot", models.CharField(max_length=500)),
                ("authors_snapshot", models.JSONField(blank=True, default=list)),
                ("page_index", models.PositiveIntegerField(blank=True, null=True)),
                ("printed_label", models.CharField(blank=True, max_length=80)),
                ("chapter_title", models.CharField(blank=True, max_length=500)),
                ("quote_ciphertext", models.BinaryField(blank=True, default=bytes)),
                ("cited", models.BooleanField(db_index=True, default=False)),
                ("asset", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="library_answer_sources", to="catalog.asset")),
                ("edition", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="library_answer_sources", to="catalog.edition")),
                ("message", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sources", to="reading.librarymessage")),
                ("work", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="library_answer_sources", to="catalog.work")),
            ],
            options={"ordering": ["ordinal"]},
        ),
        migrations.AddIndex(
            model_name="libraryconversation",
            index=models.Index(fields=["user", "archived", "last_message_at"], name="reading_lib_user_id_f2299a_idx"),
        ),
        migrations.AddIndex(
            model_name="librarymessage",
            index=models.Index(fields=["conversation", "created_at"], name="reading_lib_convers_bf7dee_idx"),
        ),
        migrations.AddConstraint(
            model_name="librarymessagesource",
            constraint=models.UniqueConstraint(fields=("message", "source_key"), name="unique_library_message_source_key"),
        ),
        migrations.AddIndex(
            model_name="librarymessagesource",
            index=models.Index(fields=["message", "cited", "ordinal"], name="reading_lib_message_51f66f_idx"),
        ),
    ]
