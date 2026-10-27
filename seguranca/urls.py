from django.urls import path

from . import views

app_name = "seguranca"

urlpatterns = [
    path("status/", views.status_seguranca, name="status"),
]