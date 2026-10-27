"""
URLs do app ordens — Etapa E5/E6.
Aditivos, OF antecipada (reserva), exclusão de nota, detalhe da OF,
geração de PDF individual e em lote.
"""
from django.urls import path
from . import views
from . import views_of

app_name = "ordens"

urlpatterns = [
    path("aditivo/criar/", views.criar_aditivo, name="criar_aditivo"),
    path(
        "of/reserva/<int:contrato_pk>/",
        views.criar_of_reserva,
        name="criar_of_reserva",
    ),
    path("nota/<int:pk>/excluir/", views.excluir_nota, name="excluir_nota"),
    path("of/<int:pk>/", views.of_detail, name="of_detail"),
    # E6 — Geração de OF em PDF
    path(
        "of/gerar/<int:nota_pk>/",
        views_of.gerar_of_para_nota,
        name="gerar_of_pdf",
    ),
    path("of/lote/", views_of.gerar_of_lote, name="gerar_of_lote"),
]