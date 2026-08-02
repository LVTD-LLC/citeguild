from django.contrib import admin

from apps.core.models import EmailSent, Project, ProjectStateTransition, ProjectSyncRequest

admin.site.register(EmailSent)
admin.site.register(Project)
admin.site.register(ProjectStateTransition)
admin.site.register(ProjectSyncRequest)
