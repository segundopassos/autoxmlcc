"""
Testes da Etapa 1 do Plano Mestre: recálculo de saldos e deduplicidade por hash.
Cobre RN07 (saldo calculado), RN25 (hash SHA-256) e a lógica cronológica de esgotamento.
"""
from decimal import Decimal

import pytest

from contratos.models import Contrato, Empresa, ItemContrato, recalcular_saldos_contrato
from importacao.models import HistoricoHashArquivo
from notas.models import ItemNota, NotaFiscal


@pytest.fixture
def empresa(db):
    return Empresa.objects.create(
        cnpj="11.753.492/0001-02",
        razao_social="Fundo Municipal de Saúde",
    )


@pytest.fixture
def contrato(empresa):
    return Contrato.objects.create(
        numero="TESTE/2026",
        empresa=empresa,
        inicio_vigencia="2026-01-01",
        fim_vigencia="2026-12-31",
    )


@pytest.fixture
def item_contrato(contrato):
    return ItemContrato.objects.create(
        contrato=contrato,
        numero_item=1,
        descricao="Paracetamol 500mg",
        unidade="CP",
        quantidade_contratada=Decimal("100.0000"),
    )


@pytest.mark.django_db
class TestRecalcularSaldosContrato:
    """RN07: Saldo é sempre calculado, nunca armazenado."""

    def test_recalculo_sem_lancamentos(self, contrato, item_contrato):
        """Sem NFs, qnt_faturada deve ser zero e nota_que_esgotou nulo."""
        recalcular_saldos_contrato(contrato.pk)
        item_contrato.refresh_from_db()
        assert item_contrato.qnt_faturada == Decimal("0")
        assert item_contrato.nota_que_esgotou is None

    def test_recalculo_com_base_inicial(self, contrato, item_contrato):
        """qnt_faturada_base conta como faturado inicial."""
        item_contrato.qnt_faturada_base = Decimal("30.0000")
        item_contrato.save(update_fields=["qnt_faturada_base"])

        recalcular_saldos_contrato(contrato.pk)
        item_contrato.refresh_from_db()
        assert item_contrato.qnt_faturada == Decimal("30.0000")
        assert item_contrato.nota_que_esgotou is None

    def test_recalculo_base_esgota_saldo(self, contrato, item_contrato):
        """Se base já >= limite, nota_que_esgotou = PLANILHA INICIAL."""
        item_contrato.qnt_faturada_base = Decimal("100.0000")
        item_contrato.save(update_fields=["qnt_faturada_base"])

        recalcular_saldos_contrato(contrato.pk)
        item_contrato.refresh_from_db()
        assert item_contrato.qnt_faturada == Decimal("100.0000")
        assert item_contrato.nota_que_esgotou == "PLANILHA INICIAL"

    def test_recalculo_nf_esgota_cronologicamente(self, contrato, item_contrato, empresa):
        """NF que cruza o limite deve ser registrada como nota_que_esgotou."""
        nf1 = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="100",
            data_emissao="2026-03-01",
            valor_total=Decimal("500.00"),
            origem="manual",
            status="conferida",
        )
        ItemNota.objects.create(
            nota=nf1,
            descricao="Paracetamol 500mg",
            unidade="CP",
            quantidade=Decimal("60.0000"),
            valor_unitario=Decimal("5.0000"),
            valor_total=Decimal("300.00"),
            item_contrato=item_contrato,
        )

        nf2 = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="200",
            data_emissao="2026-04-01",
            valor_total=Decimal("500.00"),
            origem="manual",
            status="conferida",
        )
        ItemNota.objects.create(
            nota=nf2,
            descricao="Paracetamol 500mg",
            unidade="CP",
            quantidade=Decimal("50.0000"),
            valor_unitario=Decimal("5.0000"),
            valor_total=Decimal("250.00"),
            item_contrato=item_contrato,
        )

        recalcular_saldos_contrato(contrato.pk)
        item_contrato.refresh_from_db()
        assert item_contrato.qnt_faturada == Decimal("110.0000")
        assert item_contrato.nota_que_esgotou == "NF 200"

    def test_recalculo_ignora_nota_bloqueada(self, contrato, item_contrato, empresa):
        """Notas bloqueadas não entram no cálculo de saldo (RN07)."""
        nf = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="300",
            data_emissao="2026-05-01",
            valor_total=Decimal("200.00"),
            origem="manual",
            status="bloqueada",
        )
        ItemNota.objects.create(
            nota=nf,
            descricao="Paracetamol 500mg",
            unidade="CP",
            quantidade=Decimal("80.0000"),
            valor_unitario=Decimal("5.0000"),
            valor_total=Decimal("400.00"),
            item_contrato=item_contrato,
        )

        recalcular_saldos_contrato(contrato.pk)
        item_contrato.refresh_from_db()
        assert item_contrato.qnt_faturada == Decimal("0")
        assert item_contrato.nota_que_esgotou is None

    def test_recalculo_com_aditivo(self, contrato, item_contrato, empresa):
        """qnt_aditivada aumenta o limite antes de verificar esgotamento."""
        item_contrato.qnt_aditivada = Decimal("50.0000")
        item_contrato.save(update_fields=["qnt_aditivada"])

        nf = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="400",
            data_emissao="2026-06-01",
            valor_total=Decimal("600.00"),
            origem="manual",
            status="conferida",
        )
        ItemNota.objects.create(
            nota=nf,
            descricao="Paracetamol 500mg",
            unidade="CP",
            quantidade=Decimal("120.0000"),
            valor_unitario=Decimal("5.0000"),
            valor_total=Decimal("600.00"),
            item_contrato=item_contrato,
        )

        recalcular_saldos_contrato(contrato.pk)
        item_contrato.refresh_from_db()
        # Limite = 100 + 50 = 150; faturado = 120 → não esgotou
        assert item_contrato.qnt_faturada == Decimal("120.0000")
        assert item_contrato.nota_que_esgotou is None


@pytest.mark.django_db
class TestHistoricoHashArquivo:
    """RN25: Bloqueia reimportação de arquivos idênticos via SHA-256."""

    def test_cria_hash_planilha(self, contrato):
        obj = HistoricoHashArquivo.objects.create(
            contrato=contrato,
            tipo="PLANILHA",
            nome_arquivo="itens.xlsx",
            hash_sha256="a" * 64,
        )
        assert obj.pk is not None
        assert str(obj).startswith("PLANILHA")

    def test_hash_duplicado_mesmo_tipo_contrato_bloqueia(self, contrato):
        HistoricoHashArquivo.objects.create(
            contrato=contrato,
            tipo="NOTA_FISCAL",
            nome_arquivo="nf.xml",
            hash_sha256="b" * 64,
        )
        with pytest.raises(Exception):
            HistoricoHashArquivo.objects.create(
                contrato=contrato,
                tipo="NOTA_FISCAL",
                nome_arquivo="nf_copia.xml",
                hash_sha256="b" * 64,
            )

    def test_hash_mesmo_valor_tipos_diferentes_permitido(self, contrato):
        """Mesmo hash em tipos diferentes não viola a constraint."""
        HistoricoHashArquivo.objects.create(
            contrato=contrato,
            tipo="PLANILHA",
            nome_arquivo="itens.xlsx",
            hash_sha256="c" * 64,
        )
        obj = HistoricoHashArquivo.objects.create(
            contrato=contrato,
            tipo="MESTRE",
            nome_arquivo="mestre.xlsx",
            hash_sha256="c" * 64,
        )
        assert obj.pk is not None

    def test_hash_mesmo_valor_contratos_diferentes_permitido(self, contrato, empresa):
        """Mesmo hash em contratos diferentes não viola a constraint."""
        contrato2 = Contrato.objects.create(
            numero="OUTRO/2026",
            empresa=empresa,
            inicio_vigencia="2026-01-01",
            fim_vigencia="2026-12-31",
        )
        HistoricoHashArquivo.objects.create(
            contrato=contrato,
            tipo="PLANILHA",
            nome_arquivo="itens.xlsx",
            hash_sha256="d" * 64,
        )
        obj = HistoricoHashArquivo.objects.create(
            contrato=contrato2,
            tipo="PLANILHA",
            nome_arquivo="itens.xlsx",
            hash_sha256="d" * 64,
        )
        assert obj.pk is not None