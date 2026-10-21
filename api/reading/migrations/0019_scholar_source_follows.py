from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("reading", "0018_public_path_plans")]

    operations = [
        migrations.AddField(model_name="sourcefollow", name="scholar_profile_id", field=models.UUIDField(null=True, blank=True)),
        migrations.RemoveConstraint(model_name="sourcefollow", name="unique_owner_source_follow"),
        migrations.AddConstraint(model_name="sourcefollow", constraint=models.UniqueConstraint(fields=("user", "path"),
            condition=models.Q(scholar_profile_id__isnull=True), name="unique_owner_source_follow")),
        migrations.AddConstraint(model_name="sourcefollow", constraint=models.UniqueConstraint(fields=("user", "scholar_profile_id"),
            condition=models.Q(scholar_profile_id__isnull=False), name="unique_owner_scholar_follow")),
        migrations.AlterField(model_name="sourcefollowevent", name="follow", field=models.ForeignKey(to="reading.sourcefollow",
            null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="events")),
    ]
