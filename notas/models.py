"""
Models do app notas — Etapa E3.
Entidades: NotaFiscal, ItemNota, VinculoMemorizado.
Regras de negócio: RN02 (duplicidade), RN04 (casamento), RN05 (preço exato),
RN07 (saldo calculado), RN08 (excedente), RN10 (centavos), RN11 (bloqueio).
"""
from decimal import Decimal

from django.db import models


class NotaFiscal(models.Model):
    """
    Nota fiscal recebida. Pode ter origem XML, PDF ou manual.
    RN02: Chave de acesso única; sem chave, CNPJ + número + série únicos.
    RN11: Bloqueada quando há divergência; liberada com justificativa.
    """

    ORIGEM_CHOICES = [
        ("xml", "XML"),
        ("pdf", "PDF"),
        ("manual", "Manual"),
        ("importada", "Importada"),
        ("provisoria", "Provisória (OF)"),
    ]

    STATUS_CHOICES = [
        ("conferida", "Conferida"),
        ("bloqueada", "Bloqueada"),
        ("liberada", "Liberada"),
    ]

    empresa = models.ForeignKey(
        "contratos.Empresa",
        on_delete=models.PROTECT,
        related_name="notas",
        verbose_name="Empresa emitente",
    )
    contrato = models.ForeignKey(
        "contratos.Contrato",
        on_delete=models.PROTECT,
        related_name="notas",
        verbose_name="Contrato vinculado",
    )
    chave_acesso = models.CharField(
        max_length=44, blank=True, unique=True, null=True,
        verbose_name="Chave de acesso",
    )
    numero = models.CharField(max_length=20, verbose_name="Número da nota")
    serie = models.CharField(max_length=10, blank=True, verbose_name="Série")
    data_emissao = models.DateField(verbose_name="Data de emissão")
    valor_total = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Valor total da nota",
    )
    origem = models.CharField(
        max_length=10, choices=ORIGEM_CHOICES, verbose_name="Origem",
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default="bloqueada",
        verbose_name="Status",
    )
    justificativa_liberacao = models.TextField(
        blank=True, verbose_name="Justificativa de liberação",
    )
    hash_sha256 = models.CharField(
        max_length=64, blank=True, null=True, db_index=True,
        verbose_name="Hash SHA-256 do arquivo de origem",
        help_text="Usado para bloquear duplicidade de upload (RN25).",
    )
    pdf_anexo = models.FileField(upload_to="notas/pdf/", blank=True, null=True)
    informacoes_complementares = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Nota fiscal"
        verbose_name_plural = "Notas fiscais"
        ordering = ["-data_emissao", "-numero"]
        constraints = [
            # RN02: Sem chave, combinaçãoo CNPJ + número + série é única
            models.UniqueConstraint(
                fields=["empresa", "numero", "serie"],
                condition=models.Q(chave_acesso__isnull=True),
                name="unique_nota_sem_chave",
            ),
        ]

    def __str__(self):
        return f"NF {self.numero} — {self.empresa.razao_social}"

    @property
    def tem_divergencia(self) -> bool:
        """Verifica se algum item tem divergência."""
        return self.itens.filter(divergencia__isnull=False).exists()


class ItemNota(models.Model):
    """
    Item individual de uma nota fiscal.
    RN05: Valor unitário deve ser exatamente igual ao preço vigente.
    RN07: Saldo calculado como contratada − faturada − reservada.
    RN10: Valor total gravado exatamente como na nota.
    """

    nota = models.ForeignKey(
        NotaFiscal, on_delete=models.CASCADE, related_name="itens",
        verbose_name="Nota fiscal",
    )
    codigo_fornecedor = models.CharField(
        max_length=50, blank=True, verbose_name="Código do fornecedor",
    )
    descricao = models.TextField(verbose_name="Descrição do item")
    unidade = models.CharField(max_length=20, verbose_name="Unidade")
    quantidade = models.DecimalField(
        max_digits=14, decimal_places=4, verbose_name="Quantidade",
    )
    valor_unitario = models.DecimalField(
        max_digits=14, decimal_places=4, verbose_name="Valor unitário",
    )
    valor_total = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Valor total da linha",
    )
    item_contrato = models.ForeignKey(
        "contratos.ItemContrato",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="itens_nota",
        verbose_name="Item do contrato vinculado",
    )
    divergencia = models.TextField(
        blank=True, null=True,
        verbose_name="Divergência detectada",
        help_text="Descrição da divergência, se houver.",
    )
    alerta_arredondamento = models.BooleanField(
        default=False,
        verbose_name="Alerta de arredondamento",
        help_text="RN10: Quantidade × preço difere do total da linha.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Item da nota"
        verbose_name_plural = "Itens da nota"
        ordering = ["id"]

    def __str__(self):
        return f"{self.descricao[:50]} — R$ {self.valor_total}"

    def save(self, *args, **kwargs):
        """
        Calcula divergências automaticamente ao salvar.
        RN05: Preço exato. RN08: Saldo suficiente. RN10: Alerta de arredondamento.
        """
        from decimal import ROUND_HALF_UP

        if self.item_contrato_id and not self.divergencia:
            from contratos.models import PrecoItem

            # RN05: Verifica preço vigente na data de emissão da nota
            preco_vigente = (
                PrecoItem.objects.filter(
                    item=self.item_contrato,
                    vigente_a_partir_de__lte=self.nota.data_emissao,
                )
                .order_by("-vigente_a_partir_de")
                .first()
            )

            if preco_vigente is None:
                self.divergencia = "Item sem preço vigente na data de emissão."
            elif self.valor_unitario != preco_vigente.valor_unitario:
                self.divergencia = (
                    f"Preço divergente: nota R$ {self.valor_unitario}, "
                    f"contrato R$ {preco_vigente.valor_unitario}."
                )
            else:
                # RN08: Verifica saldo disponível
                from django.db.models import Sum

                contratada = self.item_contrato.quantidade_contratada
                faturado = (
                    ItemNota.objects.filter(
                        item_contrato=self.item_contrato,
                        nota__status__in=["conferida", "liberada"],
                    ).exclude(pk=self.pk).aggregate(total=Sum("quantidade"))["total"]
                    or Decimal("0")
                )
                saldo = contratada - faturado

                if self.quantidade > saldo:
                    self.divergencia = (
                        f"Saldo insuficiente: solicitado {self.quantidade}, "
                        f"disponível {saldo}."
                    )

        # RN10: Alerta de arredondamento (não bloqueia)
        if not self.alerta_arredondamento:
            calculado = (self.quantidade * self.valor_unitario).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if calculado != self.valor_total:
                self.alerta_arredondamento = True

        super().save(*args, **kwargs)


class VinculoMemorizado(models.Model):
    """
    Vínculo memorizado entre item da nota e item do contrato.
    RN04: Todo casamento confirmado vira vínculo memorizado.
    Usado para sugerir automaticamente o item do contrato em lançamentos futuros.
    """

    empresa = models.ForeignKey(
        "contratos.Empresa",
        on_delete=models.CASCADE,
        related_name="vinculos_memorizados",
        verbose_name="Empresa",
    )
    codigo_fornecedor = models.CharField(
        max_length=50, blank=True, verbose_name="Código do fornecedor",
    )
    descricao_normalizada = models.TextField(
        verbose_name="Descrição normalizada",
        help_text="Descrição da nota normalizada para busca.",
    )
    item_contrato = models.ForeignKey(
        "contratos.ItemContrato",
        on_delete=models.CASCADE,
        related_name="vinculos_memorizados",
        verbose_name="Item do contrato",
    )
    fator_conversao = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal("1"),
        verbose_name="Fator de conversão",
        help_text="Fase 2: conversão de unidades.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vínculo memorizado"
        verbose_name_plural = "Vínculos memorizados"
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "codigo_fornecedor", "descricao_normalizada"],
                name="unique_vinculo_empresa_codigo_desc",
            ),
        ]

    def __str__(self):
        return f"{self.descricao_normalizada[:40]} → {self.item_contrato}"
