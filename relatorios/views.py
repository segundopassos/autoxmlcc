"""
Views do app relatorios — Etapa E7.
Relatórios em PDF, exportação Excel e busca global avançada.
CA19: Busca por preço exato e descrição com saldo.
RN18: Saldo negativo — mostrar negativo ou zero com observação.
"""
import io
from decimal import Decimal

from django.contrib import messages
from django.db.models import Q, Sum, DecimalField, Value, CharField
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from openpyxl import Workbook

from contratos.models import Contrato, ItemContrato, PrecoItem
from notas.models import NotaFiscal, ItemNota
from ordens.models import OrdemFornecimento


def busca_global(request):
    """
    CA19: Buscar '9,00' num contrato e 'diazepam' no painel.
    Itens com preço exatamente 9,00; contratos que têm diazepam, com saldo.
    """
    query = request.GET.get("q", "").strip()
    resultados_contratos = []
    resultados_itens = []

    if query:
        # Tenta interpretar como preço exato
        preco_busca = _parse_preco_busca(query)

        # Busca contratos por nome, número, CNPJ ou item
        resultados_contratos = (
            Contrato.objects.select_related("empresa")
            .filter(
                Q(numero__icontains=query)
                | Q(empresa__razao_social__icontains=query)
                | Q(empresa__cnpj__icontains=query)
                | Q(itens__descricao__icontains=query)
            )
            .distinct()
        )

        # Se for preço, busca itens com esse preço vigente
        if preco_busca is not None:
            itens_com_preco = []
            for item in ItemContrato.objects.filter(
                precos__valor_unitario=preco_busca
            ).select_related("contrato", "contrato__empresa"):
                preco_vigente = (
                    item.precos.order_by("-vigente_a_partir_de").first()
                )
                if preco_vigente and preco_vigente.valor_unitario == preco_busca:
                    itens_com_preco.append(item)
            resultados_itens = itens_com_preco
        else:
            # Busca por descrição normalizada
            from contratos.models import normalizar_descricao

            desc_norm = normalizar_descricao(query)
            resultados_itens = list(
                ItemContrato.objects.filter(
                    descricao_normalizada__icontains=desc_norm
                ).select_related("contrato", "contrato__empresa")
            )

    context = {
        "query": query,
        "contratos": resultados_contratos,
        "itens": resultados_itens,
    }
    return render(request, "relatorios/busca_global.html", context)


def relatorio_contrato_pdf(request, pk):
    """
    Gera relatório em PDF de um contrato com filtros.
    Opções: itens exibidos, formato, aditivos, período, saldo negativo.
    """
    from xhtml2pdf import pisa

    contrato = Contrato.objects.select_related("empresa").get(pk=pk)
    itens = contrato.itens.prefetch_related("precos").order_by("numero_item")

    # Filtros via GET
    filtro_itens = request.GET.get("itens", "todos")  # todos, saldo, zerados
    mostrar_aditivos = request.GET.get("aditivos", "sim") == "sim"
    mostrar_negativo = request.GET.get("negativo", "sim") == "sim"

    itens_filtrados = []
    for item in itens:
        saldo = _calcular_saldo_item(item)
        if filtro_itens == "saldo" and saldo <= 0:
            continue
        if filtro_itens == "zerados" and saldo > 0:
            continue
        itens_filtrados.append({
            "item": item,
            "saldo": saldo,
            "faturado": _calcular_faturado_item(item),
        })

    context = {
        "contrato": contrato,
        "itens": itens_filtrados,
        "mostrar_aditivos": mostrar_aditivos,
        "mostrar_negativo": mostrar_negativo,
        "data_geracao": timezone.now(),
    }
    html_content = render(request, "relatorios/relatorio_contrato.html", context).content.decode("utf-8")

    buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(html_content, dest=buffer, encoding="utf-8")
    if pisa_status.err:
        messages.error(request, "Erro ao gerar PDF do relatório.")
        return HttpResponse("Erro ao gerar PDF", status=500)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Relatorio_{contrato.numero}.pdf"'
    return response


def exportar_excel(request, pk):
    """
    Exporta dados do contrato em Excel.
    """
    contrato = Contrato.objects.select_related("empresa").get(pk=pk)
    itens = contrato.itens.prefetch_related("precos").order_by("numero_item")

    wb = Workbook()
    ws = wb.active
    ws.title = "Itens do Contrato"

    # Cabeçalho
    ws.append([
        "Nº Item", "Descrição", "Unidade", "Qtd. Contratada",
        "Qtd. Faturada", "Saldo", "Preço Unitário", "Valor Total",
    ])

    for item in itens:
        preco = item.precos.order_by("-vigente_a_partir_de").first()
        valor_unitario = preco.valor_unitario if preco else Decimal("0")
        faturado = _calcular_faturado_item(item)
        saldo = _calcular_saldo_item(item)
        ws.append([
            item.numero_item,
            item.descricao,
            item.unidade,
            float(item.quantidade_contratada),
            float(faturado),
            float(saldo),
            float(valor_unitario),
            float(item.quantidade_contratada * valor_unitario),
        ])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="Contrato_{contrato.numero}.xlsx"'
    return response


def _parse_preco_busca(query: str) -> Decimal | None:
    """Tenta interpretar a query como preço exato (ex: '9,00' ou '9.00')."""
    try:
        texto = query.replace(".", "").replace(",", ".")
        valor = Decimal(texto)
        return valor
    except Exception:
        return None


def _calcular_saldo_item(item: ItemContrato) -> Decimal:
    """Calcula saldo disponível de um item."""
    faturado = _calcular_faturado_item(item)
    return item.quantidade_contratada - faturado


def _calcular_faturado_item(item: ItemContrato) -> Decimal:
    """Soma quantidades faturadas (notas conferidas/liberadas)."""
    resultado = ItemNota.objects.filter(
        item_contrato=item,
        nota__status__in=["conferida", "liberada"],
    ).aggregate(total=Sum("quantidade"))
    return resultado["total"] or Decimal("0")