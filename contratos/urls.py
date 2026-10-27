"""
URLs do app contratos — Etapa E1.
"""
from django.urls import path
from . import views

app_name = "contratos"

urlpatterns = [
    # Painel de contratos (tela inicial)
    path("", views.painel_contratos, name="painel"),
    # Empresas
    path("empresas/", views.empresa_list, name="empresa_list"),
    path("empresas/nova/", views.empresa_create, name="empresa_create"),
    path("empresas/<int:pk>/editar/", views.empresa_update, name="empresa_update"),
    # Contratos
    path("contratos/novo/", views.contrato_create, name="contrato_create"),
    path("contratos/<int:pk>/", views.contrato_detail, name="contrato_detail"),
    path("contratos/<int:pk>/editar/", views.contrato_update, name="contrato_update"),
]