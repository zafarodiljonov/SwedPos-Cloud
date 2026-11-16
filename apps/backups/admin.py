from django.contrib import admin, messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.urls import path, reverse

from . import service
from .models import BackupSettings


@admin.register(BackupSettings)
class BackupSettingsAdmin(admin.ModelAdmin):
    """One page: how often, how many to keep, the list of backup files, and a Back up now button. Superusers only."""
    fields = ("frequency", "keep")
    change_form_template = "admin/backups/backupsettings/change_form.html"

    # ---- one row, superuser only ----
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:backups_backupsettings_change", args=[BackupSettings.load().pk]))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        cfg = BackupSettings.load()
        extra = dict(extra_context or {}, cfg=cfg, files=service.list_backups(), folder=service.backup_dir(),
                     due=service.is_due(cfg), run_url=reverse("admin:backups_backupsettings_run"))
        return super().change_view(request, str(cfg.pk), form_url, extra)

    def response_post_save_change(self, request, obj):
        return redirect(reverse("admin:backups_backupsettings_change", args=[obj.pk]))

    # ---- back up now, download ----
    def get_urls(self):
        custom = [
            path("run/", self.admin_site.admin_view(self.run_now), name="backups_backupsettings_run"),
            path("download/<str:name>/", self.admin_site.admin_view(self.download), name="backups_backupsettings_download"),
        ]
        return custom + super().get_urls()

    def run_now(self, request):
        if request.method != "POST" or not request.user.is_superuser:
            raise Http404
        try:
            file = service.run_backup()
            messages.success(request, f"Backup written: {file.name}")
        except service.BackupError as error:
            messages.error(request, f"Backup failed: {error}")
        return redirect(reverse("admin:backups_backupsettings_change", args=[1]))

    def download(self, request, name):
        # Only a name from the backup list: never a path the browser made up.
        if not request.user.is_superuser or not service.NAME.match(name) or name not in {n for n, _, _ in service.list_backups()}:
            raise Http404
        return FileResponse(open(service.backup_dir() / name, "rb"), as_attachment=True, filename=name)
