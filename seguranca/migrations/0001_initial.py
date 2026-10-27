"""
Migração inicial do app seguranca.
Modelos: TentativaLogin (throttle) e SessaoAtiva (expiração de sessão).
RN20: Auditoria de login e sessões.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TentativaLogin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("usuario", models.CharField(db_index=True, max_length=150)),
                ("ip", models.GenericIPAddressField(db_index=True)),
                ("sucesso", models.BooleanField()),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user_agent", models.TextField(blank=True, default="")),
            ],
            options={
                "verbose_name": "Tentativa de Login",
                "verbose_name_plural": "Tentativas de Login",
                "ordering": ["-criado_em"],
            },
        ),
        migrations.CreateModel(
            name="SessaoAtiva",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_key", models.CharField(max_length=40, unique=True)),
                ("ip", models.GenericIPAddressField()),
                ("user_agent", models.TextField(blank=True, default="")),
                ("criada_em", models.DateTimeField(auto_now_add=True)),
                ("ultimo_acesso", models.DateTimeField(auto_now=True)),
                ("expira_em", models.DateTimeField(db_index=True)),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessoes_ativas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Sessão Ativa",
                "verbose_name_plural": "Sessões Ativas",
                "ordering": ["-ultimo_acesso"],
            },
        ),
        migrations.AddIndex(
            model_name="tentativalogin",
            index=models.Index(fields=["usuario", "-criado_em"], name="seguranca_t_usuario_7bdf41_idx"),
        ),
        migrations.AddIndex(
            model_name="tentativalogin",
            index=models.Index(fields=["ip", "-criado_em"], name="seguranca_t_ip_cd73bd_idx"),
        ),
    ]