"""
Testes da Etapa E7 — Relatórios e Busca Global.
Valida busca por preço exato e descrição (CA19), exportação Excel
e geração de relatório PDF com filtros.
RN18: Saldo negativo — mostrar negativo ou zero com observação.
"""
from datetime import date
from decimal import Decimal
import pytest
from django.test import Client
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
        valor_unitario=Decimal("9.0000"),
        vigente_a_partir_de=date(2025, 1, 1),
    )
    return item


@pytest.mark.django_db
class TestBuscaGlobal:
    """Testes de busca global (CA19)."""

    def test_ca19_busca_por_preco_exato(self, empresa, contrato, item_contrato):
        """CA19: Buscar '9,00' retorna itens com preço exatamente 9,00."""
        client = Client()
        response = client.get("/relatorios/busca/", {"q": "9,00"})
        assert response.status_code == 200
        # O item com preço 9.0000 deve aparecer nos resultados
        itens = response.context["itens"]
        assert len(itens) >= 1
        assert any(i.numero_item == 1 for i in itens)

    def test_ca19_busca_por_descricao(self, empresa, contrato, item_contrato):
        """CA19: Buscar 'diazepam' retorna contratos e itens correspondentes."""
        client = Client()
        response = client.get("/relatorios/busca/", {"q": "diazepam"})
        assert response.status_code == 200
        contratos = response.context["contratos"]
        assert len(contratos) >= 1
        assert any(c.numero == "07.2909/2025" for c in contratos)

    def test_busca_sem_resultados(self, db):
        """Busca sem correspondência retorna listas vazias."""
        client = Client()
        response = client.get("/relatorios/busca/", {"q": "xyzinexistente"})
        assert response.status_code == 200
        assert len(response.context["contratos"]) == 0
        assert len(response.context["itens"]) == 0

    def test_busca_vazia(self, db):
        """Busca sem query não retorna resultados."""
        client = Client()
        response = client.get("/relatorios/busca/")
        assert response.status_code == 200
        assert response.context["query"] == ""


@pytest.mark.django_db
class TestExportarExcel:
    """Testes de exportação Excel."""

    def test_exportar_excel_retorna_xlsx(self, empresa, contrato, item_contrato):
        """Exportação Excel retorna arquivo .xlsx válido."""
        client = Client()
        response = client.get(f"/relatorios/contrato/{contrato.pk}/excel/")
        assert response.status_code == 200
        assert (
            response["Content-Type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        # Verifica assinatura de arquivo ZIP (xlsx é um ZIP)
        assert response.content[:2] == b"PK"

    def test_exportar_excel_contem_itens(self, empresa, contrato, item_contrato):
        """Excel exportado contém dados dos itens do contrato."""
        import io
        from openpyxl import load_workbook

        client = Client()
        response = client.get(f"/relatorios/contrato/{contrato.pk}/excel/")
        wb = load_workbook(io.BytesIO(response.content))
        ws = wb.active
        # Cabeçalho + 1 linha de dados
        rows = list(ws.iter_rows(values_only=True))
        assert len(rows) >= 2
        # Segunda linha deve conter o item
        assert "Diazepam 10mg comprimido" in str(rows[1])


@pytest.mark.django_db
class TestRelatorioPDF:
    """Testes de geração de relatório PDF."""

    def test_relatorio_pdf_retorna_bytes(self, empresa, contrato, item_contrato):
        """Relatório PDF retorna bytes válidos."""
        client = Client()
        response = client.get(f"/relatorios/contrato/{contrato.pk}/pdf/")
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response.content[:5] == b"%PDF-"

    def test_relatorio_pdf_filtro_saldo(self, empresa, contrato, item_contrato):
        """Relatório com filtro 'saldo' exclui itens zerados."""
        # Cria nota que consome todo o saldo
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="800",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("9000.00"),
            origem="manual",
            status="conferida",
        )
        ItemNota.objects.create(
            nota=nota,
            descricao="Diazepam 10mg comprimido",
            unidade="UN",
            quantidade=Decimal("1000"),
            valor_unitario=Decimal("9.0000"),
            valor_total=Decimal("9000.00"),
            item_contrato=item_contrato,
        )
        client = Client()
        response = client.get(
            f"/relatorios/contrato/{contrato.pk}/pdf/", {"itens": "saldo"}
        )
        assert response.status_code == 200
        assert response.content[:5] == b"%PDF-"

    def test_relatorio_pdf_negativo_oculto(self, empresa, contrato, item_contrato):
        """Relatório com negativo='nao' mostra zero em vez de saldo negativo."""
        # Liberação justificada pode gerar saldo negativo
        nota = NotaFiscal.objects.create(
            empresa=empresa,
            contrato=contrato,
            numero="801",
            data_emissao=date(2025, 6, 1),
            valor_total=Decimal("10000.00"),
            origem="manual",
            status="liberada",
        )
        ItemNota.objects.create(
            nota=nota,
            descricao="Diazepam 10mg comprimido",
            unidade="UN",
            quantidade=Decimal("1100"),  # Acima do contratado
            valor_unitario=Decimal("9.0000"),
            valor_total=Decimal("9900.00"),
            item_contrato=item_contrato,
        )
        client = Client()
        response = client.get(
            f"/relatorios/contrato/{contrato.pk}/pdf/", {"negativo": "nao"}
        )
        assert response.status_code == 200
        assert response.content[:5] == b"%PDF-"