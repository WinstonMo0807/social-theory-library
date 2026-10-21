from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reading", "0019_scholar_source_follows")]

    operations = [
        migrations.AddField(model_name="sourcefollow", name="topic_id", field=models.UUIDField(blank=True, null=True)),
        migrations.RemoveConstraint(model_name="sourcefollow", name="unique_owner_source_follow"),
        migrations.AddConstraint(model_name="sourcefollow", constraint=models.UniqueConstraint(
            fields=("user", "path"), condition=models.Q(scholar_profile_id__isnull=True, topic_id__isnull=True),
            name="unique_owner_source_follow")),
        migrations.AddConstraint(model_name="sourcefollow", constraint=models.UniqueConstraint(
            fields=("user", "topic_id"), condition=models.Q(topic_id__isnull=False), name="unique_owner_topic_follow")),
        migrations.AddConstraint(model_name="sourcefollow", constraint=models.CheckConstraint(
            condition=models.Q(scholar_profile_id__isnull=True) | models.Q(topic_id__isnull=True),
            name="source_follow_single_target")),
    ]
