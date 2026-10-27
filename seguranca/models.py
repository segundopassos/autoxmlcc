"""
Modelos de segurança — CLAUDE.md §Segurança.
- TentativaLogin: throttle de login com bloqueio temporário (RN20).
- SessaoAtiva: expiração por inatividade e auditoria de sessão.
"""
from django.conf import settings
from django.db import models


class TentativaLogin(models.Model):
    """
    Registra tentativas de login para throttle e auditoria.
    CLAUDE.md: 'Limite de tentativas de login com bloqueio temporário.'
    RN20: 'Toda alteração relevante gera auditoria, inclusive login e falha de login.'
    """
    usuario = models.CharField(max_length=150, db_index=True)
    ip = models.GenericIPAddressField(db_index=True)
    sucesso = models.BooleanField()
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    user_agent = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["usuario", "-criado_em"]),
            models.Index(fields=["ip", "-criado_em"]),
        ]
        verbose_name = "Tentativa de Login"
        verbose_name_plural = "Tentativas de Login"

    def __str__(self):
        status = "OK" if self.sucesso else "FALHA"
        return f"{self.usuario} @ {self.ip} [{status}] {self.criado_em:%Y-%m-%d %H:%M}"


class SessaoAtiva(models.Model):
    """
    Rastreia sessões ativas para expiração por inatividade e logout forçado.
    CLAUDE.md: 'Sessão com expiração por inatividade.'
    """
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sessoes_ativas",
    )
    session_key = models.CharField(max_length=40, unique=True)
    ip = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, default="")
    criada_em = models.DateTimeField(auto_now_add=True)
    ultimo_acesso = models.DateTimeField(auto_now=True)
    expira_em = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-ultimo_acesso"]
        verbose_name = "Sessão Ativa"
        verbose_name_plural = "Sessões Ativas"

    def __str__(self):
        return f"{self.usuario} ({self.session_key[:8]}…) expira {self.expira_em:%Y-%m-%d %H:%M}"