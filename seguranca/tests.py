"""
Testes do módulo de segurança.
RN20: Auditoria de login e sessões.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .models import SessaoAtiva, TentativaLogin


class TentativaLoginModelTest(TestCase):
    def test_str_sucesso(self):
        t = TentativaLogin.objects.create(
            usuario="admin", ip="127.0.0.1", sucesso=True
        )
        self.assertIn("OK", str(t))

    def test_str_falha(self):
        t = TentativaLogin.objects.create(
            usuario="admin", ip="127.0.0.1", sucesso=False
        )
        self.assertIn("FALHA", str(t))


class SessaoAtivaModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teste", password="12345")

    def test_str(self):
        s = SessaoAtiva.objects.create(
            usuario=self.user,
            session_key="abc1234567890",
            ip="10.0.0.1",
            expira_em=timezone.now() + timezone.timedelta(hours=1),
        )
        self.assertIn("abc12345", str(s))