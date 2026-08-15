from django.contrib import admin

from .models import BackupJob, CloudBudgetPolicy, CloudObject, CloudProvider, CloudUsageSnapshot

admin.site.register(CloudProvider)
admin.site.register(CloudObject)
admin.site.register(CloudBudgetPolicy)
admin.site.register(CloudUsageSnapshot)
admin.site.register(BackupJob)
