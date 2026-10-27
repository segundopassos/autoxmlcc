"""
Configuração do pytest para testes end-to-end com Playwright — Etapa E9.
"""
import pytest


@pytest.fixture
def live_server(live_server):
    """Re-exporta o fixture live_server do pytest-django."""
    return live_server