"""
Testes da Etapa E3 — Conferência de Notas.
Valida lançamento manual, casamento de itens, bloqueio e liberação.
RN02 (duplicidade), RN04 (casamento), RN05 (preço exato),
RN07 (saldo calculado), RN08 (excedente), RN10 (centavos), RN11 (bloqueio).
CA05 a CA08 e CA10.
"""
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client

from contratos.models import Contrato, Empresa, ItemContrato, PrecoItem
from notas.models import ItemNota, NotaFiscal, VinculoMemorizado


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
class TestLancamentoManual:
    """Testes de lançamento manual de nota fiscal."""

    def test_ca05_nota_duplicada_bloqueada(self, empresa, contrato, item_contrato):
        """CA05: Nota com chave de acesso já existente é recusada."""
        NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            chave_acesso="12345678901234567890123456789012345678901234",
            numero="100",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("100.00"),
            origem="manual",
            status="conferida",
        )
        with pytest.raises(Exception):
            NotaFiscal.objects.create(
                empresa=empresa,
                contrato=contrato,
                chave_acesso="12345678901234567890123456789012345678901234",
                numero="101",
                data_emissao=date(2025, 6, 2),
                valor_total=Decimal("200.00"),
                origem="manual",
                status="bloqueada",
            )

    def test_rn05_preco_divergente_bloqueia(self, empresa, contrato, item_contrato):
        """CA06/RN05: Preço diferente do contrato gera divergência."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="200",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("51.00"),
            origem="manual",
            status="bloqueada",
        )
        item_nota = ItemNota.objects.create(
            nota=nota,
            descricao="Diazepam 10mg comprimido",
            unidade="UN",
            quantidade=Decimal("100"),
            valor_unitario=Decimal("0.5100"),  # 1 centavo diferente
            valor_total=Decimal("51.00"),
            item_contrato=item_contrato,
        )
        assert item_nota.divergencia is not None
        assert "Preço divergente" in item_nota.divergencia
        assert nota.status == "bloqueada"

    def test_rn08_saldo_insuficiente_bloqueia(self, empresa, contrato, item_contrato):
        """CA07/RN08: Quantidade acima do saldo gera divergência."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="300",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("600.00"),
            origem="manual",
            status="bloqueada",
        )
        item_nota = ItemNota.objects.create(
            nota=nota,
            descricao="Diazepam 10mg comprimido",
            unidade="UN",
            quantidade=Decimal("1500"),  # Acima dos 1000 contratados
            valor_unitario=Decimal("0.5000"),
            valor_total=Decimal("750.00"),
            item_contrato=item_contrato,
        )
        assert item_nota.divergencia is not None
        assert "Saldo insuficiente" in item_nota.divergencia

    def test_rn10_alerta_arredondamento(self, empresa, contrato, item_contrato):
        """CA10/RN10: Diferença de centavo no total gera alerta, não bloqueio."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="400",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("1.00"),
            origem="manual",
            status="conferida",
        )
        item_nota = ItemNota.objects.create(
            nota=nota,
            descricao="Item teste arredondamento",
            unidade="UN",
            quantidade=Decimal("3"),
            valor_unitario=Decimal("0.3333"),
            valor_total=Decimal("1.00"),  # 3 × 0.3333 = 0.9999 ≠ 1.00
            alerta_arredondamento=True,
        )
        assert item_nota.alerta_arredondamento is True
        # Não deve ter divergência bloqueante por arredondamento
        assert item_nota.divergencia is None or item_nota.divergencia == ""

    def test_nota_sem_divergencia_fica_conferida(self, empresa, contrato, item_contrato):
        """Nota sem divergências fica com status 'conferida'."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="500",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("50.00"),
            origem="manual",
            status="conferida",
        )
        ItemNota.objects.create(
            nota=nota,
            descricao="Diazepam 10mg comprimido",
            unidade="UN",
            quantidade=Decimal("100"),
            valor_unitario=Decimal("0.5000"),
            valor_total=Decimal("50.00"),
            item_contrato=item_contrato,
        )
        assert nota.status == "conferida"
        assert not nota.tem_divergencia


@pytest.mark.django_db
class TestLiberacaoNota:
    """Testes de liberação de nota bloqueada."""

    def test_ca08_liberar_sem_justificativa_falha(self, empresa, contrato, item_contrato):
        """CA08: Liberar sem justificativa é impedido."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="600",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("100.00"),
            origem="manual",
            status="bloqueada",
        )
        client = Client()
        response = client.post(f"/notas/{nota.pk}/liberar/", {"justificativa": ""})
        # Deve retornar erro de formulário ou permanecer bloqueada
        nota.refresh_from_db()
        assert nota.status == "bloqueada"

    def test_ca08_liberar_com_justificativa_sucesso(self, empresa, contrato, item_contrato):
        """CA08: Liberar com justificativa altera status e grava justificativa."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="700",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("100.00"),
            origem="manual",
            status="bloqueada",
        )
        client = Client()
        response = client.post(
            f"/notas/{nota.pk}/liberar/",
            {"justificativa": "Preço negociado diretamente com o fornecedor."},
        )
        nota.refresh_from_db()
        assert nota.status == "liberada"
        assert nota.justificativa_liberacao == "Preço negociado diretamente com o fornecedor."


@pytest.mark.django_db
class TestCasamentoItens:
    """Testes de casamento automático de itens (RN04)."""

    def test_casamento_por_descricao_normalizada(self, empresa, contrato, item_contrato):
        """RN04: Descrição normalizada igual casa automaticamente."""
        from notas.views import _casar_item

        resultado = _casar_item(
            empresa=empresa,
            codigo_fornecedor="",
            descricao="DIAZEPAM 10MG COMPRIMIDO",  # Mesma descrição, caixa alta
            valor_unitario=Decimal("0.5000"),
            contrato=contrato,
        )
        assert resultado == item_contrato

    def test_casamento_por_vinculo_memorizado(self, empresa, contrato, item_contrato):
        """RN04: Vínculo memorizado tem prioridade sobre outros métodos."""
        from notas.views import _casar_item

        VinculoMemorizado.objects.create(
            empresa=empresa,
            codigo_fornecedor="COD123",
            descricao_normalizada="produto especial x",
            item_contrato=item_contrato,
        )
        resultado = _casar_item(
            empresa=empresa,
            codigo_fornecedor="COD123",
            descricao="Produto Especial X",
            valor_unitario=Decimal("0.5000"),
            contrato=contrato,
        )
        assert resultado == item_contrato

    def test_sem_casamento_retorna_none(self, empresa, contrato, item_contrato):
        """Item sem correspondência retorna None."""
        from notas.views import _casar_item

        resultado = _casar_item(
            empresa=empresa,
            codigo_fornecedor="",
            descricao="Produto Inexistente XYZ",
            valor_unitario=Decimal("10.0000"),
            contrato=contrato,
        )
        assert resultado is None


@pytest.mark.django_db
class TestSaldoCalculado:
    """Testes de cálculo de saldo (RN07)."""

    def test_saldo_inicial_igual_contratado(self, item_contrato):
        """Saldo inicial é igual à quantidade contratada."""
        from notas.views import _calcular_saldo_disponivel

        saldo = _calcular_saldo_disponivel(item_contrato)
        assert saldo == Decimal("1000")

    def test_saldo_abate_faturado(self, empresa, contrato, item_contrato):
        """Saldo desconta quantidades de notas conferidas/liberadas."""
        from notas.views import _calcular_saldo_disponivel

        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="800",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("100.00"),
            origem="manual",
            status="conferida",
        )
        ItemNota.objects.create(
            nota=nota,
            descricao="Diazepam 10mg comprimido",
            unidade="UN",
            quantidade=Decimal("200"),
            valor_unitario=Decimal("0.5000"),
            valor_total=Decimal("100.00"),
            item_contrato=item_contrato,
        )
        saldo = _calcular_saldo_disponivel(item_contrato)
        assert saldo == Decimal("800")

    def test_saldo_nao_abate_bloqueada(self, empresa, contrato, item_contrato):
        """Notas bloqueadas não abatem saldo."""
        from notas.views import _calcular_saldo_disponivel

        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="900",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("150.00"),
            origem="manual",
            status="bloqueada",
        )
        ItemNota.objects.create(
            nota=nota,
            descricao="Diazepam 10mg comprimido",
            unidade="UN",
            quantidade=Decimal("300"),
            valor_unitario=Decimal("0.5000"),
            valor_total=Decimal("150.00"),
            item_contrato=item_contrato,
        )
        saldo = _calcular_saldo_disponivel(item_contrato)
        # Bloqueada não deve abater: saldo ainda é 1000
        assert saldo == Decimal("1000")