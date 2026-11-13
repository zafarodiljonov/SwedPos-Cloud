from django.urls import path

from . import views

app_name = "help"

urlpatterns = [
    path("", views.index, name="index"),
    path("<slug:topic_id>/", views.index, name="topic"),
]
