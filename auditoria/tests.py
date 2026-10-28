"""
Testes da Etapa E8 — Auditoria e Backup.
Valida signals de registro automático (RN20) e comando de backup (RF18).
CA20: Auditoria imutável e backup funcional.
"""
import json
import os
import tempfile
from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import Client

from auditoria.models import RegistroAuditoria
from contratos.models import Contrato, Empresa, ItemContrato, PrecoItem
from notas.models import NotaFiscal


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


@pytest.mark.django_db
class TestSignalsAuditoriaNota:
    """RN20: Signals de auditoria para NotaFiscal."""

    def test_criacao_nota_registra_auditoria(self, empresa, contrato):
        """Criar nota gera registro de auditoria com acao='criacao'."""
        NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="100",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("100.00"),
            origem="manual",
            status="conferida",
        )
        registros = RegistroAuditoria.objects.filter(
            entidade="NotaFiscal",
            acao="criacao",
        )
        assert registros.exists()
        reg = registros.first()
        assert reg.valores_depois is not None
        assert reg.valores_depois.get("numero") == "100"

    def test_edicao_nota_conferida_registra_edicao(self, empresa, contrato):
        """Editar nota com status 'conferida' gera registro de auditoria com acao='edicao'."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="101",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("100.00"),
            origem="manual",
            status="conferida",
        )
        # Limpa registros anteriores para isolar o teste
        RegistroAuditoria.objects.all().delete()

        nota.valor_total = Decimal("200.00")
        nota.save()

        registros = RegistroAuditoria.objects.filter(
            entidade="NotaFiscal",
            objeto_id=nota.pk,
            acao="edicao",
        )
        assert registros.exists()

    def test_salvar_nota_bloqueada_registra_bloqueio(self, empresa, contrato):
        """Salvar nota com status 'bloqueada' registra acao='bloqueio'."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="101b",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("100.00"),
            origem="manual",
            status="conferida",
        )
        RegistroAuditoria.objects.all().delete()

        nota.status = "bloqueada"
        nota.save()

        registros = RegistroAuditoria.objects.filter(
            entidade="NotaFiscal",
            objeto_id=nota.pk,
            acao="bloqueio",
        )
        assert registros.exists()

    def test_liberacao_nota_registra_auditoria(self, empresa, contrato):
        """Liberar nota gera registro com acao='liberacao'."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="102",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("100.00"),
            origem="manual",
            status="bloqueada",
        )
        RegistroAuditoria.objects.all().delete()

        nota.status = "liberada"
        nota.justificativa_liberacao = "Divergência resolvida pelo fiscal."
        nota.save()

        registros = RegistroAuditoria.objects.filter(
            entidade="NotaFiscal",
            objeto_id=nota.pk,
            acao="liberacao",
        )
        assert registros.exists()
        reg = registros.first()
        assert "resolvida" in reg.justificativa.lower() or reg.justificativa != ""

    def test_exclusao_nota_registra_snapshot_antes(self, empresa, contrato):
        """Excluir nota registra snapshot dos valores antes da exclusão."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="103",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("300.00"),
            origem="manual",
            status="conferida",
        )
        nota_pk = nota.pk
        nota.delete()

        registros = RegistroAuditoria.objects.filter(
            entidade="NotaFiscal",
            objeto_id=nota_pk,
            acao="exclusao",
        )
        assert registros.exists()
        reg = registros.first()
        assert reg.valores_antes is not None
        assert reg.valores_antes.get("numero") == "103"


@pytest.mark.django_db
class TestSignalsAuditoriaContrato:
    """RN20: Signals de auditoria para Contrato."""

    def test_criacao_contrato_registra_auditoria(self, empresa):
        """Criar contrato gera registro de auditoria."""
        Contrato.objects.create(
            numero="TESTE-AUD/2025",
            empresa=empresa,
            inicio_vigencia=date(2025, 1, 1),
            fim_vigencia=date(2026, 12, 31),
        )
        registros = RegistroAuditoria.objects.filter(
            entidade="Contrato",
            acao="criacao",
        )
        assert registros.exists()

    def test_exclusao_contrato_registra_auditoria(self, contrato):
        """Excluir contrato registra snapshot anterior."""
        contrato_pk = contrato.pk
        contrato.delete()

        registros = RegistroAuditoria.objects.filter(
            entidade="Contrato",
            objeto_id=contrato_pk,
            acao="exclusao",
        )
        assert registros.exists()
        reg = registros.first()
        assert reg.valores_antes is not None


@pytest.mark.django_db
class TestComandoBackup:
    """RF18: Comando de backup e exportação completa."""

    def test_backup_gera_arquivo_json(self, empresa, contrato):
        """Comando backup_dados gera arquivo JSON válido."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "backup_teste.json")
            call_command("backup_dados", output=output_path)

            assert os.path.exists(output_path)
            with open(output_path, "r", encoding="utf-8") as f:
                dados = json.load(f)

            # Deve conter pelo menos os modelos exportados
            assert isinstance(dados, dict)
            # Verifica que registrou na auditoria
            reg = RegistroAuditoria.objects.filter(acao="backup").last()
            assert reg is not None
            assert "backup" in reg.objeto_repr.lower() or "registros" in reg.objeto_repr.lower()

    def test_backup_com_dados_inclui_entidades(self, empresa, contrato):
        """Backup inclui entidades com dados no JSON."""
        # Cria alguns dados extras
        item = ItemContrato.objects.create(
            contrato=contrato,
            numero_item=1,
            descricao="Item para backup",
            unidade="UN",
            quantidade_contratada=Decimal("100"),
        )
        PrecoItem.objects.create(
            item=item,
            valor_unitario=Decimal("5.0000"),
            vigente_a_partir_de=date(2025, 1, 1),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "backup_dados.json")
            call_command("backup_dados", output=output_path)

            with open(output_path, "r", encoding="utf-8") as f:
                dados = json.load(f)

            # Pelo menos um modelo deve ter dados
            tem_dados = any(len(v) > 0 for v in dados.values())
            assert tem_dados

    def test_backup_registra_auditoria_com_total(self, empresa, contrato):
        """Backup registra na auditoria o total de registros exportados."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "backup_audit.json")
            call_command("backup_dados", output=output_path)

            reg = RegistroAuditoria.objects.filter(acao="backup").last()
            assert reg is not None
            assert reg.valores_depois is not None
            assert "total_registros" in reg.valores_depois
            assert reg.valores_depois["total_registros"] >= 2  # empresa + contrato


@pytest.mark.django_db
class TestModelRegistroAuditoria:
    """Testes do modelo RegistroAuditoria."""

    def test_str_sem_usuario(self):
        """__str__ funciona quando usuario é None."""
        reg = RegistroAuditoria(
            usuario=None,
            acao="criacao",
            entidade="NotaFiscal",
            objeto_repr="NF 100",
        )
        texto = str(reg)
        assert "Sistema" in texto
        assert "Criação" in texto

    def test_ordering_por_criado_em_desc(self):
        """Registros são ordenados por criado_em decrescente."""
        import time
        r1 = RegistroAuditoria.objects.create(
            acao="criacao", entidade="Teste", objeto_repr="1"
        )
        time.sleep(1.1)  # Garante diferença de segundos no SQLite
        r2 = RegistroAuditoria.objects.create(
            acao="edicao", entidade="Teste", objeto_repr="2"
        )
        lista = list(RegistroAuditoria.objects.all())
        # O mais recente vem primeiro
        assert lista[0].pk == r2.pk