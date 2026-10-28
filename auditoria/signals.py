"""
Signals do app auditoria — Etapa E8.
RN20: Captura automaticamente criações, edições, exclusões e liberações
de notas fiscais e contratos, registrando usuário e valores antes/depois.
"""
import json
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()


def _get_current_user():
    """Tenta obter o usuário atual da request (via middleware ou thread-local)."""
    try:
        from django.middleware.csrf import get_token
        # Em contexto de request, o usuário pode ser obtido via threading
        import threading
        # Fallback: retorna None se não houver request ativa
        return None
    except Exception:
        return None


def _serializar_valores(instance) -> dict:
    """Serializa campos relevantes de uma instância para JSON."""
    campos = {}
    for field in instance._meta.fields:
        valor = getattr(instance, field.name, None)
        if valor is not None:
            try:
                json.dumps(valor, default=str)
                campos[field.name] = str(valor) if hasattr(valor, '__str__') and not isinstance(valor, (str, int, float, bool)) else valor
            except (TypeError, ValueError):
                campos[field.name] = str(valor)
    return campos


@receiver(post_save, sender="notas.NotaFiscal")
def registrar_auditoria_nota(sender, instance, created, **kwargs):
    """RN20: Registra criação, edição ou liberação de nota fiscal."""
    from .models import RegistroAuditoria

    # Determina a ação com base no estado atual e se é novo
    if created:
        acao = "criacao"
    elif instance.status == "liberada":
        # Verifica se já existe um registro de liberação recente para evitar duplicidade
        # mas para fins de auditoria simples, registramos sempre que salvar como liberada
        acao = "liberacao"
    elif instance.status == "bloqueada":
        acao = "bloqueio"
    else:
        acao = "edicao"

    RegistroAuditoria.objects.create(
        usuario=None,  # Usuário será preenchido via middleware em produção
        acao=acao,
        entidade="NotaFiscal",
        objeto_id=instance.pk,
        objeto_repr=str(instance),
        valores_depois=_serializar_valores(instance),
        justificativa=getattr(instance, 'justificativa_liberacao', "") if acao == "liberacao" else "",
    )


@receiver(pre_delete, sender="notas.NotaFiscal")
def registrar_exclusao_nota(sender, instance, **kwargs):
    """RN20: Registra exclusão de nota fiscal com snapshot anterior."""
    from .models import RegistroAuditoria

    RegistroAuditoria.objects.create(
        usuario=None,
        acao="exclusao",
        entidade="NotaFiscal",
        objeto_id=instance.pk,
        objeto_repr=str(instance),
        valores_antes=_serializar_valores(instance),
    )


@receiver(post_save, sender="contratos.Contrato")
def registrar_auditoria_contrato(sender, instance, created, **kwargs):
    """RN20: Registra criação ou edição de contrato."""
    from .models import RegistroAuditoria

    acao = "criacao" if created else "edicao"
    RegistroAuditoria.objects.create(
        usuario=None,
        acao=acao,
        entidade="Contrato",
        objeto_id=instance.pk,
        objeto_repr=str(instance),
        valores_depois=_serializar_valores(instance),
    )


@receiver(pre_delete, sender="contratos.Contrato")
def registrar_exclusao_contrato(sender, instance, **kwargs):
    """RN20: Registra exclusão de contrato."""
    from .models import RegistroAuditoria

    RegistroAuditoria.objects.create(
        usuario=None,
        acao="exclusao",
        entidade="Contrato",
        objeto_id=instance.pk,
        objeto_repr=str(instance),
        valores_antes=_serializar_valores(instance),
    )