"""
Models do app ordens — Etapa E5.
Entidades: Aditivo, ItemAditivo, OrdemFornecimento, Feriado.
Regras de negócio: RN06 (reajuste), RN07 (saldo calculado com reserva),
RN12 (aditivo), RN13 (OF antes da nota/reserva), RN14 (exclusão/edição),
RN15 (numeração OF), RN16 (data OF primeiro dia útil).
"""
from decimal import Decimal

from django.db import models


class Aditivo(models.Model):
    """
    Aditivo contratual. Pode alterar quantidade, valor ou prazo.
    RN12: Quando um item tem saldo original e aditivado com o mesmo preço,
          o usuário escolhe de qual abater.
    RN06: Preço de aditivo de valor vale para notas emitidas na data de
          assinatura ou depois.
    """
    TIPO_CHOICES = [
        ("quantidade", "Quantidade"),
        ("valor", "Valor"),
        ("prazo", "Prazo"),
    ]

    contrato = models.ForeignKey(
        "contratos.Contrato",
        on_delete=models.CASCADE,
        related_name="aditivos",
        verbose_name="Contrato",
    )
    numero = models.CharField(max_length=50, verbose_name="Número do aditivo")
    data_assinatura = models.DateField(verbose_name="Data de assinatura")
    tipo = models.CharField(
        max_length=12, choices=TIPO_CHOICES, verbose_name="Tipo",
    )
    novo_fim_vigencia = models.DateField(
        null=True, blank=True, verbose_name="Novo fim de vigência",
        help_text="Apenas para aditivos de prazo.",
    )
    arquivo_origem = models.FileField(
        upload_to="aditivos/", blank=True, null=True,
    )
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Aditivo"
        verbose_name_plural = "Aditivos"
        ordering = ["-data_assinatura"]
        constraints = [
            models.UniqueConstraint(
                fields=["contrato", "numero"],
                name="unique_aditivo_contrato_numero",
            ),
        ]

    def __str__(self):
        return f"Aditivo {self.numero} — {self.contrato.numero}"


class ItemAditivo(models.Model):
    """
    Item afetado por um aditivo de quantidade ou valor.
    RN12: Saldo aditivado separado do saldo original.
    """
    aditivo = models.ForeignKey(
        Aditivo, on_delete=models.CASCADE, related_name="itens",
        verbose_name="Aditivo",
    )
    item_contrato = models.ForeignKey(
        "contratos.ItemContrato",
        on_delete=models.CASCADE,
        related_name="aditivos",
        verbose_name="Item do contrato",
    )
    quantidade_aditivada = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal("0"),
        verbose_name="Quantidade aditivada",
        help_text="Acréscimo ou decréscimo de quantidade.",
    )
    novo_valor_unitario = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        verbose_name="Novo valor unitário",
        help_text="Apenas para aditivos de valor.",
    )

    class Meta:
        verbose_name = "Item do aditivo"
        verbose_name_plural = "Itens do aditivo"

    def __str__(self):
        return f"{self.item_contrato} — Aditivo {self.aditivo.numero}"


class OrdemFornecimento(models.Model):
    """
    Ordem de Fornecimento vinculada a uma nota fiscal.
    RN13: Pode ser criada antes da nota (reserva de saldo).
    RN15: Numeração automática sequencial por ano a partir de 2027.
    RN16: Data de assinatura = primeiro dia útil do mês de emissão da nota.
    """
    STATUS_CHOICES = [
        ("rascunho", "Rascunho"),
        ("emitida", "Emitida"),
        ("cancelada", "Cancelada"),
    ]

    nota = models.OneToOneField(
        "notas.NotaFiscal",
        on_delete=models.CASCADE,
        related_name="ordem_fornecimento",
        verbose_name="Nota fiscal",
    )
    numero = models.CharField(
        max_length=20, blank=True, verbose_name="Número da OF",
        help_text="Automático a partir de 2027; em branco para 2026.",
    )
    ano = models.PositiveIntegerField(verbose_name="Ano")
    data_assinatura = models.DateField(verbose_name="Data de assinatura")
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default="rascunho",
        verbose_name="Status",
    )
    pdf_gerado = models.FileField(
        upload_to="of/pdf/", blank=True, null=True,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ordem de fornecimento"
        verbose_name_plural = "Ordens de fornecimento"
        ordering = ["-ano", "-numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["ano", "numero"],
                condition=models.Q(numero__gt=""),
                name="unique_of_ano_numero",
            ),
        ]

    def __str__(self):
        if self.numero:
            return f"OF {self.numero}/{self.ano}"
        return f"OF (s/n) — {self.nota}"


class Feriado(models.Model):
    """
    Cadastro de feriados para cálculo do primeiro dia útil (RN16).
    """
    ABRANGENCIA_CHOICES = [
        ("nacional", "Nacional"),
        ("estadual", "Estadual"),
        ("municipal", "Municipal"),
    ]

    data = models.DateField(verbose_name="Data do feriado")
    descricao = models.CharField(max_length=255, verbose_name="Descrição")
    abrangencia = models.CharField(
        max_length=10, choices=ABRANGENCIA_CHOICES, default="nacional",
        verbose_name="Abrangência",
    )

    class Meta:
        verbose_name = "Feriado"
        verbose_name_plural = "Feriados"
        ordering = ["data"]
        constraints = [
            models.UniqueConstraint(
                fields=["data", "abrangencia"],
                name="unique_feriado_data_abrangencia",
            ),
        ]

    def __str__(self):
        return f"{self.data.strftime('%d/%m/%Y')} — {self.descricao}"