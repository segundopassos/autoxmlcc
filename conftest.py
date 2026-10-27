import django
from django.conf import settings


def pytest_configure():
    """Garante que o Django seja configurado antes dos testes."""
    settings.DJANGO_SETTINGS_MODULE = "config.settings"
    django.setup()


# Integração com pytest-playwright para testes E2E
pytest_plugins = ["pytest_playwright"]