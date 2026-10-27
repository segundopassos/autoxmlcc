"""
Testes da Etapa E9 — Piloto.
Valida configurações de produção, task de backup diário e estrutura E2E.
"""
import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import override_settings

from auditoria.models import RegistroAuditoria
from contratos.models import Contrato, Empresa, ItemContrato, PrecoItem


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


class TestConfiguracoesProducao:
    """Valida arquivos e configurações de deployment da E9."""

    def test_e9_docker_compose_prod_existe(self):
        """E9: docker-compose.prod.yml deve existir."""
        assert os.path.exists("docker-compose.prod.yml")

    def test_e9_env_production_existe(self):
        """E9: .env.production deve existir."""
        assert os.path.exists(".env.production")

    def test_e9_deployment_doc_existe(self):
        """E9: docs/DEPLOYMENT.md deve existir."""
        assert os.path.exists("docs/DEPLOYMENT.md")

    def test_e9_gunicorn_no_requirements(self):
        """E9: gunicorn deve estar no requirements.txt."""
        with open("requirements.txt", "r", encoding="utf-8") as f:
            content = f.read()
        assert "gunicorn" in content

    def test_e9_playwright_no_requirements(self):
        """E9: playwright e pytest-playwright devem estar no requirements.txt."""
        with open("requirements.txt", "r", encoding="utf-8") as f:
            content = f.read()
        assert "playwright" in content
        assert "pytest-playwright" in content

    def test_e9_env_production_debug_false(self):
        """E9: .env.production deve ter DEBUG=False."""
        with open(".env.production", "r", encoding="utf-8") as f:
            content = f.read()
        assert "DEBUG=False" in content

    def test_e9_docker_compose_prod_tem_beat(self):
        """E9: docker-compose.prod.yml deve incluir serviço beat."""
        with open("docker-compose.prod.yml", "r", encoding="utf-8") as f:
            content = f.read()
        assert "beat:" in content
        assert "celery" in content.lower()


class TestTaskBackupDiario:
    """Valida a task de backup diário automático (RF18)."""

    @pytest.mark.django_db
    def test_e9_task_backup_diario_executa(
        self, empresa, contrato, item_contrato, tmp_path
    ):
        """E9: Task backup_diario executa sem erros."""
        from auditoria.tasks import backup_diario

        with patch("auditoria.tasks.os.getcwd", return_value=str(tmp_path)):
            resultado = backup_diario()

        assert "Backup concluído" in resultado
        # Verifica que o arquivo foi criado
        backups_dir = os.path.join(str(tmp_path), "backups")
        assert os.path.exists(backups_dir)
        arquivos = os.listdir(backups_dir)
        assert len(arquivos) == 1
        assert arquivos[0].startswith("backup_")
        assert arquivos[0].endswith(".json")

    @pytest.mark.django_db
    def test_e9_celery_beat_schedule_configurado(self):
        """E9: Celery Beat deve ter schedule de backup diário."""
        from config.celery import app

        schedule = app.conf.beat_schedule
        assert "backup-diario-automatico" in schedule
        task_config = schedule["backup-diario-automatico"]
        assert task_config["task"] == "auditoria.tasks.backup_diario"


class TestEstruturaE2E:
    """Valida estrutura de testes end-to-end com Playwright."""

    def test_e9_teste_fluxo_completo_existe(self):
        """E9: tests/e2e/test_fluxo_completo.py deve existir."""
        assert os.path.exists("tests/e2e/test_fluxo_completo.py")

    def test_e9_conftest_e2e_existe(self):
        """E9: tests/e2e/conftest.py deve existir."""
        assert os.path.exists("tests/e2e/conftest.py")

    def test_e9_init_e2e_existe(self):
        """E9: tests/e2e/__init__.py deve existir."""
        assert os.path.exists("tests/e2e/__init__.py")

    def test_e9_conftest_raiz_integra_playwright(self):
        """E9: conftest.py raiz deve integrar pytest-playwright."""
        with open("conftest.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "pytest_playwright" in content

    def test_e9_pytest_ini_configurado(self):
        """E9: pytest.ini deve estar configurado."""
        assert os.path.exists("pytest.ini")
        with open("pytest.ini", "r", encoding="utf-8") as f:
            content = f.read()
        assert "DJANGO_SETTINGS_MODULE" in content