"""
URLs do app relatorios — Etapa E7.
Relatórios PDF, exportação Excel e busca global.
CA19: Busca por preço exato e descrição com saldo.
"""
from django.urls import path
from . import views

app_name = "relatorios"

urlpatterns = [
    path("busca/", views.busca_global, name="busca_global"),
    path(
        "contrato/<int:pk>/pdf/",
        views.relatorio_contrato_pdf,
        name="relatorio_contrato_pdf",
    ),
    path(
        "contrato/<int:pk>/excel/",
        views.exportar_excel,
        name="exportar_excel",
    ),
]