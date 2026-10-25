from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('distribution', '0005_incremental_backup_base')]
    operations = [
        migrations.AddField(model_name='backupjob', name='include_indexes', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='backupjob', name='index_only', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='backupschedule', name='include_indexes', field=models.BooleanField(default=False)),
        migrations.AlterField(model_name='backupschedule', name='scope', field=models.CharField(max_length=20, unique=True, choices=[('database', '数据库与清单'), ('originals', '数据库、清单与原件'), ('incremental', '数据库与增量原件'), ('indexes', '检索索引')])),
        migrations.AddConstraint(model_name='backupjob', constraint=models.CheckConstraint(condition=models.Q(index_only=False) | models.Q(include_indexes=True, include_originals=False, incremental_base__isnull=True), name='backup_index_only_scope')),
    ]
