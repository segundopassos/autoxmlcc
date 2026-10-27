"""
Admin do app importacao — Etapa E2.
"""
from django.contrib import admin
from .models import SessaoImportacao, MapeamentoSalvo


@admin.register(SessaoImportacao)
class SessaoImportacaoAdmin(admin.ModelAdmin):
    list_display = [
        "nome_arquivo",
        "contrato",
        "status",
        "total_itens",
        "itens_importados",
        "criado_em",
    ]
    list_filter = ["status", "criado_em"]
    search_fields = ["nome_arquivo", "empresa_detectada"]
    readonly_fields = [
        "dados_extraidos",
        "avisos",
        "erros",
        "celery_task_id",
    ]


@admin.register(MapeamentoSalvo)
class MapeamentoSalvoAdmin(admin.ModelAdmin):
    list_display = ["nome", "empresa", "linha_cabecalho", "criado_em"]
    list_filter = ["empresa"]
    search_fields = ["nome"]