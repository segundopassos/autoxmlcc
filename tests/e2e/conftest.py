"""
Configuração do pytest para testes end-to-end com Playwright — Etapa E9.
"""
import os
import pytest

# Permite operações síncronas do Django em contexto async (Playwright)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


@pytest.fixture
def live_server(live_server):
    """Re-exporta o fixture live_server do pytest-django."""
    return live_server