"""
Views do app importacao — Etapa E2.
Upload, pré-visualização e processamento de planilhas.
"""
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from contratos.models import Contrato
from .forms import UploadPlanilhaForm, ConfirmarImportacaoForm
from .hash_utils import verificar_duplicidade, registrar_hash
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

            # RN25: Verifica duplicidade por hash SHA-256 antes de processar
            filepath = sessao.arquivo_original.path
            eh_duplicado, hash_sha256 = verificar_duplicidade(
                filepath, "PLANILHA", contrato_id
            )
            if eh_duplicado:
                messages.error(
                    request,
                    "Este arquivo já foi importado anteriormente para este contrato. "
                    "Se precisar reimportar, exclua a sessão anterior primeiro.",
                )
                sessao.delete()
                return redirect("importacao:importar")

            # Registra hash para prevenir futuras duplicidades
            registrar_hash(filepath, "PLANILHA", contrato_id, hash_sha256)

            # Detecta cabeçalho e mapeamento
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


def upload_nota_fiscal(request):
    """
    Upload de nota fiscal (XML ou PDF) com verificação de duplicidade SHA-256.
    RN25: Bloqueia reimportação de arquivos idênticos.
    Etapa 3 do Plano Mestre.
    """
    from notas.models import NotaFiscal
    from notas.xml_parser import ler_xml_nota
    from notas.pdf_parser import ler_pdf_nota
    from contratos.models import Empresa

    if request.method == "POST":
        arquivo = request.FILES.get("arquivo")
        contrato_id = request.POST.get("contrato_id")

        if not arquivo:
            messages.error(request, "Selecione um arquivo XML ou PDF.")
            return redirect("importacao:upload_nota")

        # Salva temporariamente para calcular hash
        import tempfile
        import os

        suffix = os.path.splitext(arquivo.name)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in arquivo.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            # RN25: Verifica duplicidade
            eh_duplicado, hash_sha256 = verificar_duplicidade(
                tmp_path, "NOTA_FISCAL", int(contrato_id) if contrato_id else None
            )
            if eh_duplicado:
                messages.error(
                    request,
                    "Esta nota fiscal já foi importada anteriormente. "
                    "Arquivo duplicado detectado por SHA-256.",
                )
                return redirect("importacao:upload_nota")

            # Parse conforme tipo
            if suffix == ".xml":
                dados = ler_xml_nota(tmp_path)
                origem = "xml"
            elif suffix == ".pdf":
                dados = ler_pdf_nota(tmp_path)
                origem = "pdf"
            else:
                messages.error(request, "Formato não suportado. Use XML ou PDF.")
                return redirect("importacao:upload_nota")

            # Valida contrato obrigatório
            if not contrato_id:
                messages.error(request, "Selecione um contrato antes de importar a nota fiscal.")
                return redirect("importacao:upload_nota")

            try:
                contrato = Contrato.objects.get(pk=int(contrato_id))
            except (Contrato.DoesNotExist, ValueError):
                messages.error(request, "Contrato selecionado não encontrado.")
                return redirect("importacao:upload_nota")

            # Busca ou cria empresa
            cnpj = dados.get("cnpj_emitente")
            if not cnpj:
                messages.error(request, "CNPJ do emitente não encontrado no arquivo.")
                return redirect("importacao:upload_nota")

            empresa, _ = Empresa.objects.get_or_create(
                cnpj=cnpj,
                defaults={"razao_social": f"Empresa {cnpj}"},
            )

            # Cria nota com hash
            nota = NotaFiscal.objects.create(
                empresa=empresa,
                contrato=contrato,
                chave_acesso=dados.get("chave_acesso"),
                numero=dados.get("numero") or "",
                serie=dados.get("serie") or "",
                data_emissao=dados.get("data_emissao"),
                valor_total=dados.get("valor_total") or 0,
                origem=origem,
                status="bloqueada",
                hash_sha256=hash_sha256,
            )

            # Registra hash
            registrar_hash(
                tmp_path, "NOTA_FISCAL",
                int(contrato_id) if contrato_id else None,
                hash_sha256,
            )

            messages.success(
                request,
                f"Nota {nota.numero} importada com sucesso. "
                f"Revise os itens antes de confirmar.",
            )
            return redirect("notas:nota_detail", pk=nota.pk)

        finally:
            os.unlink(tmp_path)

    contratos = Contrato.objects.select_related("empresa").all()
    return render(request, "importacao/upload_nota.html", {
        "contratos": contratos,
    })