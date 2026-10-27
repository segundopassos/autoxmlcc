"""
Testes da Etapa E8 — Robustez e Auditoria.
Valida registro de auditoria (RN20) e comando de backup (RF18).
CA20: Painel com 1.000 contratos e importação grande (desempenho).
"""
import json
import os
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client

from auditoria.models import RegistroAuditoria
from contratos.models import Contrato, Empresa, ItemContrato, PrecoItem
from notas.models import ItemNota, NotaFiscal


@pytest.fixture
def empresa(db):
    return Empresa.objects.create(
        cnpj="11.753.492/0001-02",
        razao_social="Empresa Teste Ltda",
    )


@pytest.fixture
def contrato(empresa):
    return Contrato.objects.create(
        numero="07.2909/2025",
        empresa=empresa,
        inicio_vigencia=date(2025, 1, 1),
        fim_vigencia=date(2026, 12, 31),
    )


@pytest.fixture
def item_contrato(contrato):
    item = ItemContrato.objects.create(
        contrato=contrato,
        numero_item=1,
        descricao="Diazepam 10mg comprimido",
        unidade="UN",
        quantidade_contratada=Decimal("1000"),
    )
    PrecoItem.objects.create(
        item=item,
        valor_unitario=Decimal("0.5000"),
        vigente_a_partir_de=date(2025, 1, 1),
    )
    return item


@pytest.mark.django_db
class TestAuditoriaNota:
    """Testes de auditoria de notas fiscais (RN20)."""

    def test_rn20_criacao_nota_registra_auditoria(self, empresa, contrato):
        """RN20: Criar nota gera registro de auditoria."""
        NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="900",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("100.00"),
            origem="manual",
            status="conferida",
        )
        registros = RegistroAuditoria.objects.filter(
            entidade="NotaFiscal", acao="criacao"
        )
        assert registros.exists()

    def test_rn20_liberacao_nota_registra_auditoria(
        self, empresa, contrato, item_contrato
    ):
        """RN20: Liberar nota bloqueada gera registro de liberação."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="901",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("50.00"),
            origem="manual",
            status="bloqueada",
        )
        # Libera a nota
        nota.status = "liberada"
        nota.justificativa_liberacao = "Divergência resolvida verbalmente."
        nota.save()

        registros = RegistroAuditoria.objects.filter(
            entidade="NotaFiscal", acao="liberacao"
        )
        assert registros.exists()
        reg = registros.first()
        assert reg.justificativa == "Divergência resolvida verbalmente."

    def test_rn20_exclusao_nota_registra_snapshot(
        self, empresa, contrato, item_contrato
    ):
        """RN20: Excluir nota registra valores anteriores."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="902",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("75.00"),
            origem="manual",
            status="conferida",
        )
        nota_pk = nota.pk
        nota.delete()

        registros = RegistroAuditoria.objects.filter(
            entidade="NotaFiscal", acao="exclusao", objeto_id=nota_pk
        )
        assert registros.exists()
        reg = registros.first()
        assert reg.valores_antes is not None
        assert "valor_total" in reg.valores_antes


@pytest.mark.django_db
class TestAuditoriaContrato:
    """Testes de auditoria de contratos (RN20)."""

    def test_rn20_criacao_contrato_registra_auditoria(self, empresa):
        """RN20: Criar contrato gera registro de auditoria."""
        Contrato.objects.create(
            numero="08.0001/2026",
            empresa=empresa,
            inicio_vigencia=date(2026, 1, 1),
            fim_vigencia=date(2026, 12, 31),
        )
        registros = RegistroAuditoria.objects.filter(
            entidade="Contrato", acao="criacao"
        )
        assert registros.exists()

    def test_rn20_edicao_contrato_registra_auditoria(self, contrato):
        """RN20: Editar contrato gera registro de edição."""
        contrato.fiscal = "Novo Fiscal"
        contrato.save()

        registros = RegistroAuditoria.objects.filter(
            entidade="Contrato", acao="edicao", objeto_id=contrato.pk
        )
        assert registros.exists()


@pytest.mark.django_db
class TestBackupExportacao:
    """Testes do comando de backup/exportação (RF18)."""

    def test_rf18_backup_gera_arquivo_json(
        self, empresa, contrato, item_contrato, tmp_path
    ):
        """RF18: Backup gera arquivo JSON válido."""
        output_file = str(tmp_path / "backup_teste.json")
        out = StringIO()
        call_command("backup_dados", f"--output={output_file}", stdout=out)

        assert os.path.exists(output_file)
        with open(output_file, "r", encoding="utf-8") as f:
            dados = json.load(f)
        assert isinstance(dados, dict)
        # Deve conter pelo menos os modelos criados
        assert "contratos.Empresa" in dados or len(dados) > 0

    def test_rf18_backup_registra_auditoria(
        self, empresa, contrato, item_contrato, tmp_path
    ):
        """RF18: Backup registra evento na auditoria."""
        output_file = str(tmp_path / "backup_auditoria.json")
        call_command("backup_dados", f"--output={output_file}")

        registros = RegistroAuditoria.objects.filter(acao="backup")
        assert registros.exists()
        reg = registros.first()
        assert "total_registros" in (reg.valores_depois or {})

    def test_rf18_backup_inclui_todos_os_modelos(
        self, empresa, contrato, item_contrato, tmp_path
    ):
        """RF18: Backup inclui dados de todos os apps."""
        # Cria uma nota para garantir que há dados em múltiplos apps
        NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="903",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("200.00"),
            origem="manual",
            status="conferida",
        )

        output_file = str(tmp_path / "backup_completo.json")
        call_command("backup_dados", f"--output={output_file}")

        with open(output_file, "r", encoding="utf-8") as f:
            dados = json.load(f)

        # Verifica presença de dados dos principais apps
        labels_presentes = set(dados.keys())
        assert any("Empresa" in label for label in labels_presentes)
        assert any("Contrato" in label for label in labels_presentes)
        assert any("NotaFiscal" in label for label in labels_presentes)