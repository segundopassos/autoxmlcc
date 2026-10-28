"""
Models do app importacao — Etapa E2.
Rastreia sessões de importação de planilhas e mapeamentos de colunas.
RN19: Valores digitados são respeitados como estão.
"""
from django.db import models
from django.conf import settings


class SessaoImportacao(models.Model):
    """
    Representa uma tentativa de importação de planilha.
    Guarda o arquivo original, status e resultado do processamento.
    """

    class Status(models.TextChoices):
        ENVIADO = "enviado", "Enviado"
        PROCESSANDO = "processando", "Processando"
        PREVISUALIZACAO = "previsualizacao", "Pré-visualização"
        CONFIRMADO = "confirmado", "Confirmado"
        CONCLUIDO = "concluido", "Concluído"
        ERRO = "erro", "Erro"

    arquivo_original = models.FileField(
        upload_to="importacoes/%Y/%m/",
        verbose_name="Arquivo da planilha",
    )
    nome_arquivo = models.CharField(max_length=255, verbose_name="Nome do arquivo")
    contrato = models.ForeignKey(
        "contratos.Contrato",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessoes_importacao",
        verbose_name="Contrato associado",
    )
    empresa_detectada = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Empresa detectada no arquivo",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ENVIADO,
    )
    # Mapeamento de colunas detectado/salvo como JSON
    mapeamento_colunas = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Mapeamento de colunas",
        help_text="Ex: {'item': 'A', 'descricao': 'B', 'valor_unitario': 'E', ...}",
    )
    # Dados extraídos na pré-visualização (lista de dicts)
    dados_extraidos = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Dados extraídos (pré-visualização)",
    )
    # Avisos e erros encontrados durante a extração
    avisos = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Avisos de importação",
        help_text="Lista de mensagens informativas (RN19: totais digitados, etc.)",
    )
    erros = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Erros de importação",
    )
    # Estatísticas
    total_itens = models.PositiveIntegerField(default=0)
    total_notas_historicas = models.PositiveIntegerField(default=0)
    itens_importados = models.PositiveIntegerField(default=0)
    notas_importadas = models.PositiveIntegerField(default=0)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessoes_importacao",
    )
    celery_task_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="ID da task Celery",
    )

    class Meta:
        verbose_name = "Sessão de importação"
        verbose_name_plural = "Sessões de importação"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.nome_arquivo} — {self.get_status_display()}"


class MapeamentoSalvo(models.Model):
    """
    Mapeamento de colunas salvo para reutilização em futuras importações
    da mesma empresa ou layout de planilha.
    """

    nome = models.CharField(max_length=255, verbose_name="Nome do mapeamento")
    empresa = models.ForeignKey(
        "contratos.Empresa",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mapeamentos_importacao",
        verbose_name="Empresa (opcional)",
    )
    colunas = models.JSONField(
        verbose_name="Mapeamento de colunas",
        help_text="Dict com papel -> letra da coluna",
    )
    linha_cabecalho = models.PositiveIntegerField(
        default=1,
        verbose_name="Linha do cabeçalho",
    )
    linha_inicio_dados = models.PositiveIntegerField(
        default=2,
        verbose_name="Linha de início dos dados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mapeamento salvo"
        verbose_name_plural = "Mapeamentos salvos"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class HistoricoHashArquivo(models.Model):
    """
    Registro de hashes SHA-256 de arquivos importados para prevenção de duplicidade.
    RN25: Bloqueia reimportação de planilhas ou notas fiscais idênticas.
    """

    TIPO_CHOICES = [
        ("PLANILHA", "Planilha de Itens"),
        ("NOTA_FISCAL", "Nota Fiscal (XML/PDF)"),
        ("MESTRE", "Planilha Mestre"),
    ]

    contrato = models.ForeignKey(
        "contratos.Contrato",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="historico_hashes",
        verbose_name="Contrato associado",
    )
    tipo = models.CharField(
        max_length=15,
        choices=TIPO_CHOICES,
        verbose_name="Tipo de arquivo",
    )
    nome_arquivo = models.CharField(max_length=255, verbose_name="Nome do arquivo")
    hash_sha256 = models.CharField(
        max_length=64, db_index=True, verbose_name="Hash SHA-256"
    )
    data_upload = models.DateTimeField(auto_now_add=True, verbose_name="Data de upload")

    class Meta:
        verbose_name = "Histórico de Hash de Arquivo"
        verbose_name_plural = "Históricos de Hash de Arquivos"
        ordering = ["-data_upload"]
        constraints = [
            models.UniqueConstraint(
                fields=["hash_sha256", "tipo", "contrato"],
                name="unique_hash_tipo_contrato",
            ),
        ]

    def __str__(self):
        return f"{self.tipo} — {self.nome_arquivo[:30]} ({self.hash_sha256[:8]}...)"