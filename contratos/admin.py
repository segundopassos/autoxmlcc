"""
Admin do app contratos — Etapa E1.
"""
from django.contrib import admin
from .models import Contratante, Empresa, Contrato, ItemContrato, PrecoItem


@admin.register(Contratante)
class ContratanteAdmin(admin.ModelAdmin):
    list_display = ["nome", "cnpj", "secretaria"]


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ["razao_social", "cnpj"]
    search_fields = ["razao_social", "cnpj"]


class ItemContratoInline(admin.TabularInline):
    model = ItemContrato
    extra = 0
    fields = ["numero_item", "lote", "descricao", "unidade", "quantidade_contratada", "origem"]


@admin.register(Contrato)
class ContratoAdmin(admin.ModelAdmin):
    list_display = ["numero", "empresa", "inicio_vigencia", "fim_vigencia", "situacao"]
    list_filter = ["inicio_vigencia", "fim_vigencia"]
    search_fields = ["numero", "empresa__razao_social", "empresa__cnpj"]
    inlines = [ItemContratoInline]


@admin.register(ItemContrato)
class ItemContratoAdmin(admin.ModelAdmin):
    list_display = ["numero_item", "descricao", "contrato", "quantidade_contratada"]
    search_fields = ["descricao", "contrato__numero"]


@admin.register(PrecoItem)
class PrecoItemAdmin(admin.ModelAdmin):
    list_display = ["item", "valor_unitario", "vigente_a_partir_de"]
    list_filter = ["vigente_a_partir_de"]