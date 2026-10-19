from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0069_page_text_revision"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AlterField(model_name="publicfeedback", name="category", field=models.CharField(
            choices=[("content", "内容"), ("function", "功能"), ("usage", "使用咨询"), ("suggestion", "改进建议"),
                     ("citation", "引用"), ("accessibility", "无障碍"), ("other", "其他")], db_index=True, default="other", max_length=24)),
        migrations.AddField(model_name="publicfeedback", name="request_id", field=models.UUIDField(blank=True, null=True, unique=True)),
        migrations.AddField(model_name="publicfeedback", name="request_fingerprint", field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name="publicfeedback", name="consent_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="publicfeedback", name="consent_version", field=models.CharField(blank=True, max_length=40)),
        migrations.AddField(model_name="publicfeedback", name="revision", field=models.PositiveIntegerField(default=1)),
        migrations.AddField(model_name="publicfeedback", name="resolution_note", field=models.TextField(blank=True, max_length=2000)),
        migrations.AddField(model_name="publicfeedback", name="follow_up", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="publicfeedback", name="handled_by", field=models.ForeignKey(blank=True, null=True,
            on_delete=django.db.models.deletion.SET_NULL, related_name="handled_public_feedback", to=settings.AUTH_USER_MODEL)),
    ]
