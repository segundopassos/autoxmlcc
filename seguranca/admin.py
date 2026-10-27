from django.contrib import admin

from .models import SessaoAtiva, TentativaLogin


@admin.register(TentativaLogin)
class TentativaLoginAdmin(admin.ModelAdmin):
    list_display = ("usuario", "ip", "sucesso", "criado_em")
    list_filter = ("sucesso", "criado_em")
    search_fields = ("usuario", "ip")
    readonly_fields = ("usuario", "ip", "sucesso", "criado_em", "user_agent")
    date_hierarchy = "criado_em"


@admin.register(SessaoAtiva)
class SessaoAtivaAdmin(admin.ModelAdmin):
    list_display = ("usuario", "session_key", "ip", "ultimo_acesso", "expira_em")
    list_filter = ("expira_em",)
    search_fields = ("usuario__username", "ip", "session_key")
    readonly_fields = ("usuario", "session_key", "ip", "user_agent", "criada_em", "ultimo_acesso", "expira_em")