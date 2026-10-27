"""
Tasks do app auditoria — Etapa E9.
Backup diário automático via Celery Beat (RF18).
"""
import os
from datetime import datetime

from celery import shared_task


@shared_task(name="auditoria.tasks.backup_diario")
def backup_diario():
    """
    RF18: Executa backup completo diário às 02:00.
    Gera arquivo JSON com todos os dados e registra na auditoria.
    """
    from django.core.management import call_command

    backup_dir = os.path.join(os.getcwd(), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(backup_dir, f"backup_{timestamp}.json")

    call_command("backup_dados", f"--output={output_path}")

    return f"Backup concluído: {output_path}"