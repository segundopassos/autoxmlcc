"""
Testes da Etapa E5 — Aditivos e Reservas.
Valida aditivos de quantidade/valor/prazo, OF antecipada (reserva),
exclusão de nota com devolução de saldo e cálculo do primeiro dia útil.
RN06 (reajuste), RN12 (aditivo), RN13 (reserva), RN14 (exclusão/edição),
RN15 (numeração OF), RN16 (data OF primeiro dia útil).
CA09, CA11, CA14, CA15.
"""
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client

from contratos.models import Contrato, Empresa, ItemContrato, PrecoItem
from notas.models import ItemNota, NotaFiscal
from ordens.models import Aditivo, Feriado, ItemAditivo, OrdemFornecimento
from ordens.utils import primeiro_dia_util


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
class TestAditivoQuantidade:
    """Testes de aditivo de quantidade (RN12)."""

    def test_ca09_aditivo_quantidade_cria_item_aditivo(self, contrato, item_contrato):
        """CA09: Aditivo de quantidade cria ItemAditivo vinculado."""
        aditivo = Aditivo.objects.create(
            contrato=contrato,
            numero="001/2025",
            data_assinatura=date(2025, 6, 1),
            tipo="quantidade",
        )
        item_aditivo = ItemAditivo.objects.create(
            aditivo=aditivo,
            item_contrato=item_contrato,
            quantidade_aditivada=Decimal("500"),
        )
        assert item_aditivo.quantidade_aditivada == Decimal("500")
        assert item_aditivo.aditivo == aditivo

    def test_aditivo_unicidade_contrato_numero(self, contrato):
        """Aditivo com mesmo número no mesmo contrato é recusado."""
        Aditivo.objects.create(
            contrato=contrato,
            numero="002/2025",
            data_assinatura=date(2025, 6, 1),
            tipo="prazo",
        )
        with pytest.raises(Exception):
            Aditivo.objects.create(
                contrato=contrato,
                numero="002/2025",
                data_assinatura=date(2025, 7, 1),
                tipo="quantidade",
            )


@pytest.mark.django_db
class TestAditivoValor:
    """Testes de aditivo de valor (RN06)."""

    def test_rn06_aditivo_valor_cria_novo_preco(self, contrato, item_contrato):
        """RN06: Aditivo de valor cria novo preço vigente a partir da data de assinatura."""
        aditivo = Aditivo.objects.create(
            contrato=contrato,
            numero="003/2025",
            data_assinatura=date(2025, 8, 15),
            tipo="valor",
        )
        novo_preco = Decimal("0.5500")
        ItemAditivo.objects.create(
            aditivo=aditivo,
            item_contrato=item_contrato,
            novo_valor_unitario=novo_preco,
        )
        # Simula o que a view faz: criar PrecoItem
        PrecoItem.objects.create(
            item=item_contrato,
            valor_unitario=novo_preco,
            vigente_a_partir_de=aditivo.data_assinatura,
        )
        # Preço vigente em 2025-09-01 deve ser o novo
        preco_vigente = (
            PrecoItem.objects.filter(
                item=item_contrato,
                vigente_a_partir_de__lte=date(2025, 9, 1),
            )
            .order_by("-vigente_a_partir_de")
            .first()
        )
        assert preco_vigente.valor_unitario == novo_preco

    def test_rn06_preco_anterior_mantido_para_notas_anteriores(
        self, contrato, item_contrato
    ):
        """RN06: Notas emitidas antes do aditivo mantêm o preço antigo."""
        # Preço original: 0.5000 desde 2025-01-01
        # Aditivo de valor em 2025-08-15 → novo preço 0.5500
        PrecoItem.objects.create(
            item=item_contrato,
            valor_unitario=Decimal("0.5500"),
            vigente_a_partir_de=date(2025, 8, 15),
        )
        # Nota emitida em 2025-07-01 deve usar preço antigo
        preco_vigente = (
            PrecoItem.objects.filter(
                item=item_contrato,
                vigente_a_partir_de__lte=date(2025, 7, 1),
            )
            .order_by("-vigente_a_partir_de")
            .first()
        )
        assert preco_vigente.valor_unitario == Decimal("0.5000")


@pytest.mark.django_db
class TestAditivoPrazo:
    """Testes de aditivo de prazo."""

    def test_aditivo_prazo_atualiza_fim_vigencia(self, contrato):
        """Aditivo de prazo pode definir novo fim de vigência."""
        novo_fim = date(2027, 12, 31)
        aditivo = Aditivo.objects.create(
            contrato=contrato,
            numero="004/2025",
            data_assinatura=date(2025, 11, 1),
            tipo="prazo",
            novo_fim_vigencia=novo_fim,
        )
        assert aditivo.novo_fim_vigencia == novo_fim


@pytest.mark.django_db
class TestReservaOF:
    """Testes de OF antecipada / reserva de saldo (RN13)."""

    def test_ca11_of_reserva_cria_nota_provisoria(self, empresa, contrato):
        """CA11/RN13: OF antecipada cria nota provisória com origem='provisoria'."""
        nota_provisoria = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="RESERVA-20250601",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("0"),
            origem="provisoria",
            status="conferida",
        )
        of = OrdemFornecimento.objects.create(
            nota=nota_provisoria,
            ano=2025,
            data_assinatura=date(2025, 6, 2),
            status="rascunho",
        )
        assert of.nota.origem == "provisoria"
        assert of.status == "rascunho"

    def test_of_unicidade_ano_numero(self, empresa, contrato):
        """OF com mesmo ano e número não pode duplicar."""
        nota1 = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="100",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("100"),
            origem="manual",
            status="conferida",
        )
        OrdemFornecimento.objects.create(
            nota=nota1,
            numero="001",
            ano=2027,
            data_assinatura=date(2027, 1, 2),
            status="emitida",
        )
        nota2 = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="101",
            data_emissao=date(2025, 7, 1),
            valor_total=Decimal("200"),
            origem="manual",
            status="conferida",
        )
        with pytest.raises(Exception):
            OrdemFornecimento.objects.create(
                nota=nota2,
                numero="001",
                ano=2027,
                data_assinatura=date(2027, 2, 3),
                status="emitida",
            )


@pytest.mark.django_db
class TestExclusaoNota:
    """Testes de exclusão de nota (RN14)."""

    def test_ca14_excluir_nota_devolve_saldo(self, empresa, contrato, item_contrato):
        """CA14/RN14: Excluir nota devolve saldo ao contrato."""
        from notas.views import _calcular_saldo_disponivel

        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="500",
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
        # Saldo antes: 1000 - 200 = 800
        assert _calcular_saldo_disponivel(item_contrato) == Decimal("800")

        # Exclui a nota
        nota.delete()

        # Saldo depois: volta para 1000
        assert _calcular_saldo_disponivel(item_contrato) == Decimal("1000")

    def test_ca14_excluir_nota_remove_of_vinculada(self, empresa, contrato, item_contrato):
        """CA14/RN14: Excluir nota remove a OF vinculada."""
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="501",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("50.00"),
            origem="manual",
            status="conferida",
        )
        of = OrdemFornecimento.objects.create(
            nota=nota,
            ano=2025,
            data_assinatura=date(2025, 6, 2),
            status="emitida",
        )
        of_pk = of.pk
        nota.delete()
        assert not OrdemFornecimento.objects.filter(pk=of_pk).exists()


@pytest.mark.django_db
class TestPrimeiroDiaUtil:
    """Testes do cálculo do primeiro dia útil (RN16)."""

    def test_primeiro_dia_util_sem_feriado(self):
        """Janeiro de 2025: dia 1 é quarta-feira → primeiro dia útil = 01/01."""
        # 01/01/2025 é quarta-feira
        resultado = primeiro_dia_util(2025, 1)
        assert resultado == date(2025, 1, 1)

    def test_primeiro_dia_util_fim_de_semana(self):
        """Junho de 2025: dia 1 é domingo → primeiro dia útil = 02/06 (segunda)."""
        resultado = primeiro_dia_util(2025, 6)
        assert resultado == date(2025, 6, 2)

    def test_primeiro_dia_util_com_feriado(self, db):
        """Se dia 1 for feriado, pula para o próximo dia útil."""
        # Janeiro de 2025: dia 1 é quarta
        Feriado.objects.create(
            data=date(2025, 1, 1),
            descricao="Confraternização Universal",
            abrangencia="nacional",
        )
        resultado = primeiro_dia_util(2025, 1)
        # Dia 1 é feriado → pula para dia 2 (quinta)
        assert resultado == date(2025, 1, 2)

    def test_primeiro_dia_util_feriado_e_fim_de_semana(self, db):
        """Se dia 1 for sábado e dia 3 for feriado, retorna dia 4."""
        # Novembro de 2025: dia 1 é sábado, dia 3 é segunda
        Feriado.objects.create(
            data=date(2025, 11, 3),
            descricao="Feriado municipal",
            abrangencia="municipal",
        )
        resultado = primeiro_dia_util(2025, 11)
        # Sábado(1) → Domingo(2) → Segunda(3) feriado → Terça(4)
        assert resultado == date(2025, 11, 4)


@pytest.mark.django_db
class TestFeriado:
    """Testes do modelo Feriado."""

    def test_feriado_unicidade_data_abrangencia(self):
        """Mesma data + abrangência não pode duplicar."""
        Feriado.objects.create(
            data=date(2025, 12, 25),
            descricao="Natal",
            abrangencia="nacional",
        )
        with pytest.raises(Exception):
            Feriado.objects.create(
                data=date(2025, 12, 25),
                descricao="Natal duplicado",
                abrangencia="nacional",
            )

    def test_feriado_mesma_data_abrangencias_diferentes(self):
        """Mesma data com abrangências diferentes é permitido."""
        Feriado.objects.create(
            data=date(2025, 8, 16),
            descricao="Dia Estadual",
            abrangencia="estadual",
        )
        f2 = Feriado.objects.create(
            data=date(2025, 8, 16),
            descricao="Dia Municipal",
            abrangencia="municipal",
        )
        assert f2.pk is not None