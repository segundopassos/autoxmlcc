"""
Models do app auditoria — Etapa E8.
Entidade: RegistroAuditoria.
Regra de negócio: RN20 (toda liberação, edição e exclusão registra usuário,
data, hora e valores antes e depois).
RF18: Backup automático diário e exportação completa sob demanda.
"""
from django.conf import settings
from django.db import models


class RegistroAuditoria(models.Model):
    """
    RN20: Registro imutável de toda alteração relevante no sistema.
    Captura usuário, data/hora, ação, entidade, valores antes e depois
    e justificativa quando aplicável.
    """

    ACAO_CHOICES = [
        ("criacao", "Criação"),
        ("edicao", "Edição"),
        ("exclusao", "Exclusão"),
        ("liberacao", "Liberação de nota"),
        ("bloqueio", "Bloqueio de nota"),
        ("importacao", "Importação"),
        ("backup", "Backup / Exportação"),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_auditoria",
        verbose_name="Usuário",
    )
    acao = models.CharField(
        max_length=12, choices=ACAO_CHOICES, verbose_name="Ação"
    )
    entidade = models.CharField(
        max_length=100, verbose_name="Entidade",
        help_text="Ex: NotaFiscal, Contrato, Aditivo",
    )
    objeto_id = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="ID do objeto",
    )
    objeto_repr = models.CharField(
        max_length=500, blank=True, verbose_name="Representação do objeto",
        help_text="String representativa do objeto no momento da ação.",
    )
    valores_antes = models.JSONField(
        null=True, blank=True, verbose_name="Valores antes",
        help_text="Snapshot dos campos relevantes antes da alteração.",
    )
    valores_depois = models.JSONField(
        null=True, blank=True, verbose_name="Valores depois",
        help_text="Snapshot dos campos relevantes após a alteração.",
    )
    justificativa = models.TextField(
        blank=True, verbose_name="Justificativa",
        help_text="Obrigatória para liberações e exclusões (RN20).",
    )
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="Data/Hora")

    class Meta:
        verbose_name = "Registro de auditoria"
        verbose_name_plural = "Registros de auditoria"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["entidade", "objeto_id"]),
            models.Index(fields=["-criado_em"]),
            models.Index(fields=["usuario"]),
        ]

    def __str__(self):
        usuario_nome = self.usuario.get_full_name() if self.usuario else "Sistema"
        return f"{self.get_acao_display()} — {self.entidade} ({usuario_nome}, {self.criado_em:%d/%m/%Y %H:%M})"