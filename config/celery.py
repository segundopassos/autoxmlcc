import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# E9 — Backup diário automático às 02:00 (horário local)
app.conf.beat_schedule = {
    "backup-diario-automatico": {
        "task": "auditoria.tasks.backup_diario",
        "schedule": crontab(hour=2, minute=0),
    },
}