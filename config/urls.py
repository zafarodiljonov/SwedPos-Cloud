from django.contrib import admin
from django.urls import path

from apps.sync import views as sync_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/ping", sync_views.ping),
    path("api/sync", sync_views.sync),
]
