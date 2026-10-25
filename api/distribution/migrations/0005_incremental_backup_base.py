from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('distribution','0004_storagecleanupplan')]
    operations = [
        migrations.AddField(model_name='backupjob', name='incremental_base', field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name='incremental_backups', to='distribution.backupjob')),
        migrations.AddField(model_name='backupschedule', name='incremental_base', field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name='incremental_schedules', to='distribution.backupjob')),
        migrations.AlterField(model_name='backupschedule', name='scope', field=models.CharField(max_length=20, unique=True, choices=[('database','数据库与清单'),('originals','数据库、清单与原件'),('incremental','数据库与增量原件')])),
    ]
