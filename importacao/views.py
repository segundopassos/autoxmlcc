"""
Views do app importacao — Etapa E2.
Upload, pré-visualização e processamento de planilhas.
"""
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from contratos.models import Contrato
from .forms import UploadPlanilhaForm, ConfirmarImportacaoForm
from .models import SessaoImportacao
from .parsers import detectar_cabecalho, extrair_itens_planilha, detectar_colunas_notas
from .tasks import processar_importacao


def importar_planilha(request):
    """
    Passo 1: Upload da planilha e detecção automática de colunas.
    """
    if request.method == "POST":
        form = UploadPlanilhaForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo = request.FILES["arquivo"]
            contrato_id = form.cleaned_data.get("contrato_id")

            # Cria sessão de importação
            sessao = SessaoImportacao.objects.create(
                arquivo_original=arquivo,
                nome_arquivo=arquivo.name,
                usuario=request.user if request.user.is_authenticated else None,
                status=SessaoImportacao.Status.ENVIADO,
            )

            if contrato_id:
                try:
                    sessao.contrato = Contrato.objects.get(pk=contrato_id)
                    sessao.save()
                except Contrato.DoesNotExist:
                    pass

            # Detecta cabeçalho e mapeamento
            filepath = sessao.arquivo_original.path
            linha_cabecalho, mapeamento = detectar_cabecalho(
                __import__("openpyxl").load_workbook(filepath, data_only=True).active
            )

            if not mapeamento or "descricao" not in mapeamento:
                messages.error(
                    request,
                    "Não foi possível detectar as colunas automaticamente. "
                    "Verifique se a planilha tem cabeçalhos reconhecíveis.",
                )
                return redirect("importacao:importar")

            sessao.mapeamento_colunas = mapeamento
            sessao.save()

            # Extrai itens para pré-visualização
            itens, avisos = extrair_itens_planilha(
                filepath, mapeamento, linha_cabecalho + 1
            )

            # Detecta notas históricas
            wb = __import__("openpyxl").load_workbook(filepath, data_only=True)
            colunas_notas = detectar_colunas_notas(wb.active, linha_cabecalho)
            wb.close()

            linhas_itens = [item["linha"] for item in itens]
            notas = []
            if colunas_notas:
                from .parsers import extrair_notas_historicas
                notas = extrair_notas_historicas(
                    filepath, colunas_notas, linha_cabecalho + 1, linhas_itens
                )

            sessao.dados_extraidos = itens
            sessao.avisos = avisos
            sessao.total_itens = len(itens)
            sessao.total_notas_historicas = len(notas)
            sessao.status = SessaoImportacao.Status.PREVISUALIZACAO
            sessao.save()

            return redirect("importacao:previsualizar", pk=sessao.pk)
    else:
        form = UploadPlanilhaForm()

    contratos = Contrato.objects.select_related("empresa").all()
    return render(request, "importacao/upload.html", {
        "form": form,
        "contratos": contratos,
    })


def previsualizar(request, pk):
    """
    Passo 2: Pré-visualização dos dados extraídos antes de confirmar.
    """
    sessao = get_object_or_404(SessaoImportacao, pk=pk)

    if request.method == "POST":
        form = ConfirmarImportacaoForm(request.POST)
        if form.is_valid():
            # Dispara task Celery (ou executa síncrono se Celery não estiver rodando)
            try:
                result = processar_importacao.delay(sessao.pk)
                sessao.celery_task_id = result.id
                sessao.status = SessaoImportacao.Status.PROCESSANDO
                sessao.save()
                messages.success(
                    request,
                    f"Importação iniciada! {sessao.total_itens} itens sendo processados.",
                )
            except Exception:
                # Fallback síncrono se Celery não estiver disponível
                resultado = processar_importacao(sessao.pk)
                if isinstance(resultado, dict) and "erro" not in resultado:
                    messages.success(
                        request,
                        f"Importação concluída! {resultado.get('itens_criados', 0)} itens criados.",
                    )
                else:
                    messages.warning(
                        request,
                        f"Importação concluída com avisos. Verifique o relatório.",
                    )

            return redirect("importacao:resultado", pk=sessao.pk)
    else:
        form = ConfirmarImportacaoForm(initial={"sessao_id": sessao.pk})

    return render(request, "importacao/previsualizar.html", {
        "sessao": sessao,
        "itens": sessao.dados_extraidos[:50],  # Limita preview
        "total_itens": sessao.total_itens,
        "avisos": sessao.avisos,
        "form": form,
    })


def resultado(request, pk):
    """
    Passo 3: Resultado da importação.
    """
    sessao = get_object_or_404(SessaoImportacao, pk=pk)
    return render(request, "importacao/resultado.html", {
        "sessao": sessao,
    })