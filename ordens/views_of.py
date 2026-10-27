"""
Views de geração de Ordem de Fornecimento em PDF — Etapa E6.
RN15: Numeração automática a partir de 2027.
RN16: Data de assinatura = primeiro dia útil.
CA16-CA18: Geração de PDF com WeasyPrint.
"""
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from notas.models import NotaFiscal
from .models import OrdemFornecimento
from .pdf_generator import gerar_pdf_of, numerar_of
from .utils import primeiro_dia_util


def gerar_of_para_nota(request, nota_pk):
    """
    Cria ou recupera OF para uma nota e gera o PDF.
    RN15: Numeração automática se ano >= 2027.
    RN16: Data de assinatura = primeiro dia útil do mês de emissão.
    """
    nota = get_object_or_404(NotaFiscal, pk=nota_pk)

    with transaction.atomic():
        of, created = OrdemFornecimento.objects.get_or_create(
            nota=nota,
            defaults={
                "ano": nota.data_emissao.year,
                "data_assinatura": primeiro_dia_util(
                    nota.data_emissao.year, nota.data_emissao.month
                ),
                "status": "emitida",
            },
        )

        if created or not of.numero:
            numero = numerar_of(of.ano)
            if numero and not of.numero:
                of.numero = numero
                of.save(update_fields=["numero"])

        if of.status == "rascunho":
            of.status = "emitida"
            of.save(update_fields=["status"])

    pdf_bytes = gerar_pdf_of(of)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    nome_arquivo = f"OF_{of.numero or 'sn'}_{of.ano}.pdf"
    response["Content-Disposition"] = f'inline; filename="{nome_arquivo}"'
    return response


def gerar_of_lote(request):
    """
    Gera OFs em lote para notas selecionadas.
    Retorna um ZIP com todos os PDFs ou redireciona com mensagem.
    """
    if request.method != "POST":
        return redirect("contratos:painel")

    nota_ids = request.POST.getlist("nota_ids")
    if not nota_ids:
        messages.warning(request, "Nenhuma nota selecionada.")
        return redirect("contratos:painel")

    notas = NotaFiscal.objects.filter(pk__in=nota_ids).select_related(
        "contrato", "empresa"
    )
    ofs_geradas = []

    for nota in notas:
        with transaction.atomic():
            of, created = OrdemFornecimento.objects.get_or_create(
                nota=nota,
                defaults={
                    "ano": nota.data_emissao.year,
                    "data_assinatura": primeiro_dia_util(
                        nota.data_emissao.year, nota.data_emissao.month
                    ),
                    "status": "emitida",
                },
            )
            if created or not of.numero:
                numero = numerar_of(of.ano)
                if numero and not of.numero:
                    of.numero = numero
                    of.save(update_fields=["numero"])
            if of.status == "rascunho":
                of.status = "emitida"
                of.save(update_fields=["status"])

        ofs_geradas.append(of)

    if len(ofs_geradas) == 1:
        return gerar_of_para_nota(request, ofs_geradas[0].nota_id)

    # Múltiplas OFs: gera ZIP
    import io
    import zipfile

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for of in ofs_geradas:
            pdf_bytes = gerar_pdf_of(of)
            nome = f"OF_{of.numero or 'sn'}_{of.ano}.pdf"
            zf.writestr(nome, pdf_bytes)

    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="OFs_lote.zip"'
    return response