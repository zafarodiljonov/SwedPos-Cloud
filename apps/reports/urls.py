from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.home, name="home"),
    path("r/<int:rid>/<str:page>/", views.page, name="page"),
    path("r/<int:rid>/<str:page>/export/", views.export, name="export"),
    path("r/<int:rid>/detail/<str:kind>/<int:key>/", views.detail, name="detail"),
    path("lang/<str:code>/", views.language, name="language"),
]
