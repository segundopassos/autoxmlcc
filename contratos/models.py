"""
Models do app contratos — Etapa E1.
Entidades: Contratante, Empresa, Contrato, ItemContrato, PrecoItem.
Regras de negócio: RN01 (CNPJ único), RN07 (Decimal exato), RN17 (vencimento).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


def validar_cnpj(cnpj: str) -> str:
    """
    Valida e formata um CNPJ. Retorna o CNPJ formatado (XX.XXX.XXX/XXXX-XX).
    Levanta ValidationError se inválido.
    """
    # Remove formatação
    digitos = "".join(c for c in cnpj if c.isdigit())
    if len(digitos) != 14:
        raise ValidationError("CNPJ deve ter 14 dígitos.")

    # Verifica se todos são iguais (ex: 00000000000000)
    if len(set(digitos)) == 1:
        raise ValidationError("CNPJ inválido.")

    # Primeiro dígito verificador
    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(digitos[i]) * pesos_1[i] for i in range(12))
    resto = soma % 11
    dv1 = 0 if resto < 2 else 11 - resto

    if int(digitos[12]) != dv1:
        raise ValidationError("CNPJ inválido (primeiro dígito verificador).")

    # Segundo dígito verificador
    pesos_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(digitos[i]) * pesos_2[i] for i in range(13))
    resto = soma % 11
    dv2 = 0 if resto < 2 else 11 - resto

    if int(digitos[13]) != dv2:
        raise ValidationError("CNPJ inválido (segundo dígito verificador).")

    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


class Contratante(models.Model):
    """
    Configuração única: Fundo Municipal de Saúde de Campo Maior.
    Singleton — só pode existir um registro.
    """
    nome = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, unique=True)
    secretaria = models.CharField(max_length=255, blank=True)
    logo = models.ImageField(upload_to="logos/", blank=True, null=True)

    class Meta:
        verbose_name = "Contratante"
        verbose_name_plural = "Contratante"

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        # Garante singleton: se já existe um registro e este é novo, bloqueia
        if not self.pk and Contratante.objects.exists():
            raise ValidationError("Só pode existir um contratante no sistema.")
        super().save(*args, **kwargs)


class Empresa(models.Model):
    """
    RN01: A empresa é identificada pelo CNPJ do emitente. CNPJ único.
    """
    cnpj = models.CharField(max_length=18, unique=True, verbose_name="CNPJ")
    razao_social = models.CharField(max_length=255, verbose_name="Razão social")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ["razao_social"]

    def __str__(self):
        return f"{self.razao_social} ({self.cnpj})"

    def clean(self):
        self.cnpj = validar_cnpj(self.cnpj)


class Contrato(models.Model):
    """
    Contrato de fornecimento. Número único.
    RN17: Alerta 30 dias antes do fim da vigência.
    """
    numero = models.CharField(
        max_length=50, unique=True, verbose_name="Número do contrato",
        help_text="Ex: 07.2909/2025",
    )
    pregao = models.CharField(max_length=50, blank=True, verbose_name="Pregão")
    empresa = models.ForeignKey(
        Empresa, on_delete=models.PROTECT, related_name="contratos",
        verbose_name="Empresa contratada",
    )
    inicio_vigencia = models.DateField(verbose_name="Início da vigência")
    fim_vigencia = models.DateField(verbose_name="Fim da vigência")
    fiscal = models.CharField(max_length=255, blank=True, verbose_name="Fiscal do contrato")
    solicitante = models.CharField(max_length=255, blank=True)
    ordenador = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Contrato"
        verbose_name_plural = "Contratos"
        ordering = ["-inicio_vigencia", "numero"]

    def __str__(self):
        return f"{self.numero} — {self.empresa.razao_social}"

    def clean(self):
        if self.inicio_vigencia and self.fim_vigencia:
            if self.fim_vigencia <= self.inicio_vigencia:
                raise ValidationError({
                    "fim_vigencia": "A data de fim deve ser posterior à data de início."
                })

    @property
    def situacao(self) -> str:
        """Retorna 'ativo', 'a_vencer' ou 'vencido'."""
        from django.utils import timezone
        hoje = timezone.now().date()
        if hoje > self.fim_vigencia:
            return "vencido"
        from datetime import timedelta
        if hoje >= self.fim_vigencia - timedelta(days=30):
            return "a_vencer"
        return "ativo"

    @property
    def total_contratado(self) -> Decimal:
        """Soma das quantidades contratadas × preço vigente de todos os itens."""
        total = Decimal("0")
        for item in self.itens.all():
            preco = item.precos.order_by("-vigente_a_partir_de").first()
            if preco:
                total += item.quantidade_contratada * preco.valor_unitario
        return total

    @property
    def total_faturado(self) -> Decimal:
        """Soma dos valores faturados (qnt_faturada × preço vigente) de todos os itens."""
        total = Decimal("0")
        for item in self.itens.all():
            preco = item.precos.order_by("-vigente_a_partir_de").first()
            if preco:
                total += item.qnt_faturada * preco.valor_unitario
        return total

    @property
    def saldo_disponivel(self) -> Decimal:
        """Valor global menos o total faturado (RN07: saldo calculado)."""
        return self.total_contratado - self.total_faturado


class ItemContrato(models.Model):
    """
    Item de um contrato. Quantidade em Decimal com 4 casas.
    descricao_normalizada: sem acentos, pontuação e espaços extras (para casamento RN04).
    """
    ORIGEM_CHOICES = [
        ("original", "Original"),
        ("aditivo", "Aditivo"),
    ]

    contrato = models.ForeignKey(
        Contrato, on_delete=models.CASCADE, related_name="itens",
        verbose_name="Contrato",
    )
    lote = models.CharField(max_length=50, blank=True, verbose_name="Lote")
    numero_item = models.PositiveIntegerField(verbose_name="Nº do item")
    descricao = models.TextField(verbose_name="Descrição")
    descricao_normalizada = models.TextField(
        blank=True, verbose_name="Descrição normalizada",
        help_text="Gerada automaticamente para casamento de itens.",
    )
    unidade = models.CharField(max_length=20, verbose_name="Unidade")
    quantidade_contratada = models.DecimalField(
        max_digits=14, decimal_places=4, verbose_name="Quantidade contratada",
    )
    qnt_aditivada = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal("0"),
        verbose_name="Quantidade aditivada",
    )
    qnt_faturada_base = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal("0"),
        verbose_name="Quantidade faturada base (planilha inicial)",
        help_text="Faturado que já veio na planilha inicial de importação.",
    )
    qnt_faturada = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal("0"),
        verbose_name="Quantidade faturada total",
        help_text="Soma de qnt_faturada_base + lançamentos de NF.",
    )
    nota_que_esgotou = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="Nota que esgotou o saldo",
        help_text="Ex: 'PLANILHA INICIAL', 'NF 3432'.",
    )
    ultimo_hash_planilha = models.CharField(
        max_length=64, blank=True, null=True,
        verbose_name="Último hash SHA-256 da planilha",
        help_text="Evita duplicar planilha no modo somar.",
    )
    origem = models.CharField(
        max_length=10, choices=ORIGEM_CHOICES, default="original",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Item do contrato"
        verbose_name_plural = "Itens do contrato"
        constraints = [
            models.UniqueConstraint(
                fields=["contrato", "numero_item", "lote"],
                name="unique_item_contrato_lote",
            ),
            models.CheckConstraint(
                condition=models.Q(quantidade_contratada__gt=0),
                name="item_quantidade_positiva",
            ),
        ]
        ordering = ["numero_item"]

    def __str__(self):
        return f"Item {self.numero_item} — {self.descricao[:50]}"

    @property
    def saldo_restante(self) -> Decimal:
        """Saldo disponível do item (RN07: calculado, nunca armazenado)."""
        limite = self.quantidade_contratada + self.qnt_aditivada
        return limite - self.qnt_faturada

    def save(self, *args, **kwargs):
        # Gera descrição normalizada automaticamente
        if not self.descricao_normalizada:
            self.descricao_normalizada = normalizar_descricao(self.descricao)
        super().save(*args, **kwargs)


class PrecoItem(models.Model):
    """
    Histórico de preços de um item. Cada reajuste cria um novo registro.
    RN05/RN06: Valor unitário com até 4 casas, vigente a partir de uma data.
    """
    item = models.ForeignKey(
        ItemContrato, on_delete=models.CASCADE, related_name="precos",
        verbose_name="Item do contrato",
    )
    valor_unitario = models.DecimalField(
        max_digits=14, decimal_places=4, verbose_name="Valor unitário",
    )
    vigente_a_partir_de = models.DateField(verbose_name="Vigente a partir de")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Preço do item"
        verbose_name_plural = "Preços do item"
        constraints = [
            models.UniqueConstraint(
                fields=["item", "vigente_a_partir_de"],
                name="unique_preco_item_data",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_unitario__gte=Decimal("0")),
                name="preco_nao_negativo",
            ),
        ]
        ordering = ["-vigente_a_partir_de"]

    def __str__(self):
        return f"{self.item} — R$ {self.valor_unitario} (desde {self.vigente_a_partir_de})"


def normalizar_descricao(texto: str) -> str:
    """
    Normaliza descrição para casamento de itens (RN04).
    Remove acentos, pontuação, espaços extras e converte para minúsculas.
    """
    import unicodedata
    import re

    # Remove acentos
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    # Minúsculas
    texto = texto.lower()
    # Remove pontuação e caracteres especiais
    texto = re.sub(r"[^\w\s]", "", texto)
    # Colapsa espaços
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def recalcular_saldos_contrato(contrato_id: int) -> None:
    """
    Recalcula saldos de todos os itens de um contrato dentro de transação atômica.
    Etapa 1.2 do Plano Mestre: determina cronologicamente qual NF esgotou/estourou o saldo.
    """
    from django.db import transaction
    from notas.models import ItemNota, NotaFiscal

    with transaction.atomic():
        itens = ItemContrato.objects.filter(contrato_id=contrato_id).select_for_update()
        for item in itens:
            limite = round(float(item.quantidade_contratada or 0) + float(item.qnt_aditivada or 0), 4)
            acumulado = round(float(item.qnt_faturada_base or 0), 4)
            nota_esgotou = None

            if limite > 0 and acumulado >= limite:
                nota_esgotou = "PLANILHA INICIAL"

            lancamentos = (
                ItemNota.objects.filter(item_contrato=item)
                .exclude(nota__status="bloqueada")
                .select_related("nota")
                .order_by("nota__data_emissao", "nota__id")
            )

            for lanc in lancamentos:
                antes = acumulado
                qtd_l = round(float(lanc.quantidade or 0), 4)
                acumulado = round(acumulado + qtd_l, 4)

                if nota_esgotou is None and limite > 0:
                    if antes < limite and acumulado >= limite:
                        nota_esgotou = f"NF {lanc.nota.numero}"
                    elif acumulado > limite:
                        nota_esgotou = f"NF {lanc.nota.numero}"

            item.qnt_faturada = Decimal(str(acumulado))
            item.nota_que_esgotou = nota_esgotou
            item.save(update_fields=["qnt_faturada", "nota_que_esgotou", "atualizado_em"])