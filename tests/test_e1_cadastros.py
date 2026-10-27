"""
Testes da Etapa E1 — Cadastros.
Regras de negócio: RN01 (CNPJ único), RN17 (vencimento).
Critérios de aceite: CA19 (busca por preço e descrição).
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from contratos.models import Empresa, Contrato, ItemContrato, PrecoItem, validar_cnpj


@pytest.mark.django_db
class TestE1Cadastros:
    """Testes de cadastro de empresas, contratos e itens."""

    def test_rn01_empresa_cnpj_unico(self):
        """RN01: Dois CNPJs iguais são recusados."""
        Empresa.objects.create(
            cnpj="11.753.492/0001-02",
            razao_social="Empresa A",
        )
        with pytest.raises(Exception):
            Empresa.objects.create(
                cnpj="11.753.492/0001-02",
                razao_social="Empresa B",
            )

    def test_cnpj_valido(self):
        """CNPJ válido é formatado corretamente."""
        resultado = validar_cnpj("11753492000102")
        assert resultado == "11.753.492/0001-02"

    def test_cnpj_invalido_digito(self):
        """CNPJ com dígito verificador errado levanta ValidationError."""
        with pytest.raises(ValidationError):
            validar_cnpj("11.753.492/0001-99")

    def test_cnpj_invalido_todos_iguais(self):
        """CNPJ com todos os dígitos iguais é inválido."""
        with pytest.raises(ValidationError):
            validar_cnpj("11.111.111/1111-11")

    def test_contrato_numero_unico(self):
        """Número de contrato único."""
        empresa = Empresa.objects.create(
            cnpj="11.753.492/0001-02",
            razao_social="Empresa Teste",
        )
        Contrato.objects.create(
            numero="07.2909/2025",
            empresa=empresa,
            inicio_vigencia=date(2025, 1, 1),
            fim_vigencia=date(2025, 12, 31),
        )
        with pytest.raises(Exception):
            Contrato.objects.create(
                numero="07.2909/2025",
                empresa=empresa,
                inicio_vigencia=date(2026, 1, 1),
                fim_vigencia=date(2026, 12, 31),
            )

    def test_contrato_fim_posterior_inicio(self):
        """Data de fim deve ser posterior à data de início."""
        empresa = Empresa.objects.create(
            cnpj="11.753.492/0001-02",
            razao_social="Empresa Teste",
        )
        contrato = Contrato(
            numero="01.0001/2025",
            empresa=empresa,
            inicio_vigencia=date(2025, 12, 31),
            fim_vigencia=date(2025, 1, 1),
        )
        with pytest.raises(ValidationError):
            contrato.clean()

    def test_rn17_alerta_vencimento(self):
        """RN17: Contrato a 30 dias do fim aparece como 'a_vencer'."""
        empresa = Empresa.objects.create(
            cnpj="11.753.492/0001-02",
            razao_social="Empresa Teste",
        )
        hoje = timezone.now().date()
        contrato = Contrato.objects.create(
            numero="01.0002/2025",
            empresa=empresa,
            inicio_vigencia=hoje - timedelta(days=335),
            fim_vigencia=hoje + timedelta(days=15),
        )
        assert contrato.situacao == "a_vencer"

    def test_contrato_ativo(self):
        """Contrato dentro da vigência é 'ativo'."""
        empresa = Empresa.objects.create(
            cnpj="11.753.492/0001-02",
            razao_social="Empresa Teste",
        )
        hoje = timezone.now().date()
        contrato = Contrato.objects.create(
            numero="01.0003/2025",
            empresa=empresa,
            inicio_vigencia=hoje - timedelta(days=30),
            fim_vigencia=hoje + timedelta(days=335),
        )
        assert contrato.situacao == "ativo"

    def test_contrato_vencido(self):
        """Contrato com fim no passado é 'vencido'."""
        empresa = Empresa.objects.create(
            cnpj="11.753.492/0001-02",
            razao_social="Empresa Teste",
        )
        hoje = timezone.now().date()
        contrato = Contrato.objects.create(
            numero="01.0004/2025",
            empresa=empresa,
            inicio_vigencia=hoje - timedelta(days=400),
            fim_vigencia=hoje - timedelta(days=35),
        )
        assert contrato.situacao == "vencido"

    def test_item_preco_historico(self):
        """Múltiplos preços por item com datas diferentes."""
        empresa = Empresa.objects.create(
            cnpj="11.753.492/0001-02",
            razao_social="Empresa Teste",
        )
        contrato = Contrato.objects.create(
            numero="01.0005/2025",
            empresa=empresa,
            inicio_vigencia=date(2025, 1, 1),
            fim_vigencia=date(2025, 12, 31),
        )
        item = ItemContrato.objects.create(
            contrato=contrato,
            numero_item=1,
            descricao="Diazepam 5mg",
            unidade="CP",
            quantidade_contratada=Decimal("1000.0000"),
        )
        PrecoItem.objects.create(
            item=item,
            valor_unitario=Decimal("0.5000"),
            vigente_a_partir_de=date(2025, 1, 1),
        )
        PrecoItem.objects.create(
            item=item,
            valor_unitario=Decimal("0.5500"),
            vigente_a_partir_de=date(2025, 7, 1),
        )
        assert item.precos.count() == 2
        # Preço mais recente primeiro
        assert item.precos.first().valor_unitario == Decimal("0.5500")

    def test_item_quantidade_positiva(self):
        """Quantidade contratada deve ser maior que zero."""
        empresa = Empresa.objects.create(
            cnpj="11.753.492/0001-02",
            razao_social="Empresa Teste",
        )
        contrato = Contrato.objects.create(
            numero="01.0006/2025",
            empresa=empresa,
            inicio_vigencia=date(2025, 1, 1),
            fim_vigencia=date(2025, 12, 31),
        )
        item = ItemContrato(
            contrato=contrato,
            numero_item=1,
            descricao="Item teste",
            unidade="UN",
            quantidade_contratada=Decimal("0"),
        )
        with pytest.raises(Exception):
            item.full_clean()

    def test_ca19_busca_preco_descricao(self):
        """CA19: Busca 'diazepam' encontra contratos com esse item."""
        empresa = Empresa.objects.create(
            cnpj="11.753.492/0001-02",
            razao_social="Farmácia Teste",
        )
        contrato = Contrato.objects.create(
            numero="07.2909/2025",
            empresa=empresa,
            inicio_vigencia=date(2025, 1, 1),
            fim_vigencia=date(2025, 12, 31),
        )
        ItemContrato.objects.create(
            contrato=contrato,
            numero_item=1,
            descricao="Diazepam 5mg comprimido",
            unidade="CP",
            quantidade_contratada=Decimal("500.0000"),
        )
        # Busca por descrição
        resultados = Contrato.objects.filter(
            itens__descricao__icontains="diazepam"
        ).distinct()
        assert contrato in resultados

    def test_descricao_normalizada(self):
        """Descrição normalizada remove acentos, pontuação e espaços extras."""
        from contratos.models import normalizar_descricao

        texto = "  Diazepam  5mg   comprimido!  "
        resultado = normalizar_descricao(texto)
        assert resultado == "diazepam 5mg comprimido"