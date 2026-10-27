"""
URLs do app notas — Etapa E3.
"""
from django.urls import path

from . import views

app_name = "notas"

urlpatterns = [
    path("lancar/", views.lancar_nota_manual, name="lancar_manual"),
    path("<int:pk>/", views.nota_detail, name="nota_detail"),
    path("<int:pk>/liberar/", views.liberar_nota, name="liberar_nota"),
]