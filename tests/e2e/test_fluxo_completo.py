"""
Testes end-to-end com Playwright — Etapa E9 Piloto.
Valida o fluxo completo: login, cadastro, lançamento de nota, conferência e geração de OF.
CA20: Painel com muitos contratos e desempenho.
"""
import re
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import expect, Page

from contratos.models import Contrato, Empresa, ItemContrato, PrecoItem
from notas.models import NotaFiscal

User = get_user_model()


@pytest.fixture
def usuario(db):
    """Cria usuário administrador para testes."""
    return User.objects.create_superuser(
        username="admin",
        email="admin@teste.com",
        password="senha123",
    )


@pytest.fixture
def empresa(db):
    """Cria empresa de teste."""
    return Empresa.objects.create(
        cnpj="11.753.492/0001-02",
        razao_social="Fundo Municipal de Saúde",
    )


@pytest.fixture
def contrato_com_itens(empresa):
    """Cria contrato com itens para teste de fluxo completo."""
    contrato = Contrato.objects.create(
        numero="07.2909/2025",
        empresa=empresa,
        inicio_vigencia="2025-01-01",
        fim_vigencia="2026-12-31",
    )
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
        vigente_a_partir_de="2025-01-01",
    )
    return contrato


@pytest.mark.django_db(transaction=True)
class TestFluxoCompleto:
    """Testes end-to-end do fluxo principal do sistema."""

    def test_e2e_login_e_painel(self, page: Page, live_server, usuario):
        """E2E: Login e acesso ao painel de contratos."""
        page.goto(f"{live_server.url}/admin/login/")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "senha123")
        page.click('input[type="submit"]')

        # Após login, redireciona para o painel
        expect(page).to_have_url(re.compile(r".*/$"))

    def test_e2e_cadastro_empresa(self, page: Page, live_server, usuario):
        """E2E: Cadastro de empresa pela interface."""
        # Login
        page.goto(f"{live_server.url}/admin/login/")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "senha123")
        page.click('input[type="submit"]')

        # Navega para cadastro de empresas (rota real: /empresas/nova/)
        page.goto(f"{live_server.url}/empresas/nova/")

        # Preenche formulário
        page.fill('input[name="cnpj"]', "12.345.678/0001-90")
        page.fill('input[name="razao_social"]', "Empresa Teste E2E Ltda")
        page.click('button[type="submit"]')

        # Verifica que a empresa foi criada (redireciona para lista)
        expect(page).to_have_url(re.compile(r".*/empresas/.*"))
        expect(page.locator("text=Empresa Teste E2E Ltda")).to_be_visible()

    def test_e2e_cadastro_contrato(self, page: Page, live_server, usuario, empresa):
        """E2E: Cadastro de contrato pela interface."""
        # Login
        page.goto(f"{live_server.url}/admin/login/")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "senha123")
        page.click('input[type="submit"]')

        # Navega para novo contrato (rota real: /contratos/novo/)
        page.goto(f"{live_server.url}/contratos/novo/")

        # Preenche formulário
        page.fill('input[name="numero"]', "99.9999/2026")
        page.fill('input[name="inicio_vigencia"]', "2026-01-01")
        page.fill('input[name="fim_vigencia"]', "2026-12-31")
        page.click('button[type="submit"]')

        # Verifica que o contrato foi criado
        expect(page).to_have_url(re.compile(r".*/contratos/\d+/.*"))
        expect(page.locator("text=99.9999/2026")).to_be_visible()

    def test_e2e_lancamento_nota_manual(
        self, page: Page, live_server, usuario, contrato_com_itens
    ):
        """E2E: Lançamento manual de nota fiscal."""
        # Login
        page.goto(f"{live_server.url}/admin/login/")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "senha123")
        page.click('input[type="submit"]')

        # Navega para lançar nota (rota real: /notas/lancar/)
        page.goto(f"{live_server.url}/notas/lancar/")

        # Preenche dados da nota
        page.fill('input[name="numero"]', "999")
        page.fill('input[name="cnpj_emitente"]', "11.753.492/0001-02")
        page.fill('input[name="data_emissao"]', "2025-06-01")

        # Adiciona item
        page.fill('input[name="descricao_0"]', "Diazepam 10mg comprimido")
        page.fill('input[name="quantidade_0"]', "100")
        page.fill('input[name="valor_unitario_0"]', "0.5000")

        page.click('button[type="submit"]')

        # Verifica que a nota foi lançada
        expect(page).to_have_url(re.compile(r".*/notas/\d+/.*"))

    def test_e2e_geracao_of(self, page: Page, live_server, usuario, contrato_com_itens):
        """E2E: Geração de OF a partir de nota conferida."""
        # Cria nota conferida
        nota = NotaFiscal.objects.create(
            empresa=contrato_com_itens.empresa,
            contrato=contrato_com_itens,
            numero="888",
            data_emissao="2025-06-01",
            valor_total=Decimal("50.00"),
            origem="manual",
            status="conferida",
        )

        # Login
        page.goto(f"{live_server.url}/admin/login/")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "senha123")
        page.click('input[type="submit"]')

        # Navega para a nota (rota real: /notas/<pk>/)
        page.goto(f"{live_server.url}/notas/{nota.pk}/")

        # Clica em gerar OF (rota real: /ordens/of/gerar/<nota_pk>/)
        page.click('text=Gerar OF')

        # Verifica que a OF foi gerada
        expect(page).to_have_url(re.compile(r".*/ordens/of/\d+/.*"))


@pytest.mark.django_db(transaction=True)
class TestDesempenhoPainel:
    """CA20: Testes de desempenho do painel com muitos contratos."""

    def test_ca20_painel_com_muitos_contratos(self, page: Page, live_server, usuario):
        """CA20: Painel com 100 contratos abre em tempo aceitável."""
        # Cria 100 empresas e contratos
        for i in range(100):
            emp = Empresa.objects.create(
                cnpj=f"12.345.{i:03d}/0001-90",
                razao_social=f"Empresa Teste {i}",
            )
            Contrato.objects.create(
                numero=f"{i:02d}.0001/2026",
                empresa=emp,
                inicio_vigencia="2026-01-01",
                fim_vigencia="2026-12-31",
            )

        # Login
        page.goto(f"{live_server.url}/admin/login/")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "senha123")
        page.click('input[type="submit"]')

        # Mede tempo de carregamento do painel
        import time
        inicio = time.time()
        page.goto(f"{live_server.url}/")
        duracao = time.time() - inicio

        # Painel deve carregar em menos de 5 segundos
        assert duracao < 5.0, f"Painel demorou {duracao:.2f}s para carregar"

        # Verifica que os contratos aparecem
        expect(page.locator(".contrato-card")).to_have_count(100)