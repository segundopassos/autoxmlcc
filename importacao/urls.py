"""
URLs do app importacao — Etapa E2.
"""
from django.urls import path
from . import views

app_name = "importacao"

urlpatterns = [
    path("", views.importar_planilha, name="importar"),
    path("nota/", views.upload_nota_fiscal, name="upload_nota"),
    path("<int:pk>/previsualizar/", views.previsualizar, name="previsualizar"),
    path("<int:pk>/resultado/", views.resultado, name="resultado"),
]