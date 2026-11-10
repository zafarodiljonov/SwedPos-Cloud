from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.accounts.forms import PhoneLoginForm
from apps.sync import views as sync_views

admin.site.site_header = "SwedPos Cloud"
admin.site.site_title = "SwedPos Cloud"

urlpatterns = [
    path("admin/", admin.site.urls),
    # The restaurant's server PC sends here (SwedPos › Settings › SwedPos Cloud).
    path("api/ping", sync_views.ping),
    path("api/sync", sync_views.sync),
    path("login/", auth_views.LoginView.as_view(authentication_form=PhoneLoginForm, redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("apps.reports.urls")),
]
