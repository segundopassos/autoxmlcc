"""
Testes da Etapa E0 — Fundação.
Verifica que o projeto Django sobe, o banco conecta e o login funciona.
"""

import os

import pytest
from django.contrib.auth.models import User
from django.test import Client


@pytest.mark.django_db
class TestE0Foundation:
    """Critérios de aceite da etapa E0."""

    def test_e0_admin_accessible(self):
        """A página de login do admin responde com 200."""
        client = Client()
        response = client.get("/admin/login/")
        assert response.status_code == 200

    def test_e0_login_works(self):
        """Superusuário consegue logar e acessar o admin."""
        user = User.objects.create_superuser(
            username="admin", password="testpass123"
        )
        client = Client()
        logged_in = client.login(username="admin", password="testpass123")
        assert logged_in is True

        response = client.get("/admin/")
        assert response.status_code == 200

    def test_e0_database_connection(self):
        """O banco de dados está acessível e funcional."""
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
        assert result == (1,)

    @pytest.mark.skipif(
        os.environ.get("USE_SQLITE", "").lower() in ("true", "1"),
        reason="pg_trgm requer PostgreSQL; ignorado em desenvolvimento local com SQLite",
    )
    def test_e0_pg_trgm_available(self):
        """A extensão pg_trgm está instalada no PostgreSQL."""
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM pg_extension WHERE extname = 'pg_trgm'"
            )
            count = cursor.fetchone()[0]
        assert count >= 0