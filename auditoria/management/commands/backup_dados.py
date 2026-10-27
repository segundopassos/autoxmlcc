"""
Comando de backup e exportação completa — Etapa E8.
RF18: Backup automático diário e exportação completa sob demanda.
Gera arquivo JSON com todos os dados do sistema e registra na auditoria.
"""
import json
import os
from datetime import datetime

from django.core.management.base import BaseCommand
from django.core.serializers import serialize

from auditoria.models import RegistroAuditoria


class Command(BaseCommand):
    help = "Exporta todos os dados do sistema em JSON e registra na auditoria."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Caminho do arquivo de saída. Padrão: backups/backup_YYYYMMDD_HHMMSS.json",
        )

    def handle(self, *args, **options):
        from contratos.models import Contrato, Empresa, ItemContrato, PrecoItem
        from notas.models import NotaFiscal, ItemNota, VinculoMemorizado
        from ordens.models import Aditivo, ItemAditivo, OrdemFornecimento, Feriado

        apps_models = [
            Empresa, Contrato, ItemContrato, PrecoItem,
            NotaFiscal, ItemNota, VinculoMemorizado,
            Aditivo, ItemAditivo, OrdemFornecimento, Feriado,
        ]

        dados = {}
        total_registros = 0
        for model in apps_models:
            qs = model.objects.all()
            count = qs.count()
            if count > 0:
                dados[model._meta.label] = json.loads(serialize("json", qs))
                total_registros += count

        output_path = options.get("output")
        if not output_path:
            backup_dir = os.path.join(os.getcwd(), "backups")
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(backup_dir, f"backup_{timestamp}.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)

        RegistroAuditoria.objects.create(
            usuario=None,
            acao="backup",
            entidade="Sistema",
            objeto_repr=f"Backup completo: {total_registros} registros",
            valores_depois={"arquivo": output_path, "total_registros": total_registros},
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Backup concluído: {total_registros} registros em {output_path}"
            )
        )