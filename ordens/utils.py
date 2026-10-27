"""
Utilitários do app ordens — Etapa E5.
RN16: Cálculo do primeiro dia útil do mês considerando feriados cadastrados.
"""
from datetime import date, timedelta


def primeiro_dia_util(ano: int, mes: int) -> date:
    """
    Retorna o primeiro dia útil do mês/ano informado.
    Desconsidera sábados, domingos e feriados cadastrados no modelo Feriado.
    RN16: Data de assinatura da OF = primeiro dia útil do mês de emissão.
    """
    from .models import Feriado

    dia = date(ano, mes, 1)
    # Busca feriados do mês/ano para evitar queries repetidas
    feriados_mes = set(
        Feriado.objects.filter(
            data__year=ano, data__month=mes
        ).values_list("data", flat=True)
    )

    while True:
        # 0=segunda ... 6=domingo
        if dia.weekday() < 5 and dia not in feriados_mes:
            return dia
        dia += timedelta(days=1)
        # Segurança: se passar do mês, retorna o último dia verificado
        if dia.month != mes:
            return date(ano, mes, 1)