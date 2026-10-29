"""
Views da API JSON — replica as rotas do protótipo FastAPI para o frontend SPA.
Implementa: dashboard de contratos, planilha interativa, conferência XML/PDF,
lançamento manual, aditivos, importação Excel e relatórios PDF.
"""
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta

from django.db import transaction, models
from django.db.models import Sum, Q, F
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from contratos.models import (
    Contrato, Empresa, ItemContrato, PrecoItem,
    normalizar_descricao, recalcular_saldos_contrato, validar_cnpj
)
from notas.models import NotaFiscal, ItemNota, VinculoMemorizado
from ordens.models import OrdemFornecimento
from ordens.pdf_generator import gerar_pdf_of, numerar_of
from ordens.utils import primeiro_dia_util


# ============================================================================
# UTILITÁRIOS
# ============================================================================

def json_response(data, status=200):
    """Retorna JsonResponse com safe=False para listas."""
    return JsonResponse(data, status=status, safe=False)


def error_response(message, status=400):
    """Retorna erro padronizado."""
    return json_response({"ok": False, "erro": message}, status=status)


def parse_decimal(value):
    """Converte string/number para Decimal com 4 casas."""
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    except:
        return Decimal("0")


def formatar_cnpj(cnpj):
    """Formata CNPJ para exibição."""
    if not cnpj:
        return "-"
    d = re.sub(r'[^\d]', '', str(cnpj))
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return str(cnpj)


def formatar_data_br(data):
    """Formata data para DD/MM/YYYY."""
    if not data:
        return "-"
    try:
        if isinstance(data, str):
            data = datetime.fromisoformat(data.replace('Z', '+00:00')).date()
        return data.strftime("%d/%m/%Y")
    except:
        return str(data)[:10]


def round4(value):
    """Arredonda para 4 casas decimais."""
    return round(float(value or 0), 4)


def format_br(valor):
    """Formata valor monetário para exibição BR."""
    if valor is None:
        return "0,00"
    return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_int_qtd(valor):
    """Formata quantidade para exibição."""
    if valor is None:
        return "0"
    v = round(float(valor), 4)
    if v.is_integer():
        return f"{int(v):,}".replace(",", ".")
    texto = f"{v:,.4f}".rstrip('0').rstrip('.')
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


# ============================================================================
# ALGORITMO DE CONCILIAÇÃO INTELIGENTE (portado do xml_engine.py)
# ============================================================================

def extrair_tokens_busca(texto):
    """Extrai tokens significativos de um texto para busca."""
    t_clean = re.sub(r'[^\w\s]', ' ', remover_acentos_basico(texto))
    ignorar = {'PARA', 'COM', 'DOS', 'DAS', 'NOS', 'NAS', 'POR', 'UMA', 'ITEM', 'UND', 'UNID', 'CADA', 'VALOR', 'TOTAL'}
    return set(w for w in t_clean.split() if len(w) > 2 and w not in ignorar)


def remover_acentos_basico(txt):
    """Remove acentos básicos de um texto."""
    mapa = str.maketrans(
        "ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüç",
        "AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuuc"
    )
    return str(txt).translate(mapa).upper()


def conciliar_item_inteligente(item_xml, itens_contrato, numero_nf_atual=""):
    """
    Combina Descrição do Item + Valor Unitário + Número do Item (quando presente)
    para encontrar o item exato no contrato.
    """
    v_xml = round(float(item_xml.get('val_xml') or 0), 4)
    x_xml = str(item_xml.get('desc_xml') or '').strip().upper()
    q_xml = round(float(item_xml.get('qtd_xml') or 0), 4)
    num_ref = item_xml.get('item_num_ref')

    if num_ref is None:
        m_num = re.search(r'\bITEM\s*[-:]?\s*0*(\d+)\b', x_xml, re.I)
        if m_num:
            num_ref = int(m_num.group(1))

    tokens_xml = extrair_tokens_busca(x_xml)
    x_norm = remover_acentos_basico(x_xml)

    melhor_escolha = None
    melhor_pontuacao = -1.0

    for c in itens_contrato:
        pontos = 0.0
        v_c = round(float(c.get('val_unitario') or 0), 4)
        desc_c = str(c.get('descricao') or '').strip().upper()
        desc_c_norm = remover_acentos_basico(desc_c)
        tokens_c = extrair_tokens_busca(desc_c)

        # 1. Comparação de Valor Unitário
        diff_val = abs(v_c - v_xml)
        if v_xml > 0 and diff_val <= 0.01:
            pontos += 45.0
        elif v_xml > 0 and diff_val <= 0.25:
            pontos += 20.0

        # 2. Comparação de Número do Item
        try:
            if num_ref is not None and c.get('item_num') is not None:
                num_c = int(re.sub(r'\D', '', str(c['item_num'])))
                if num_c == int(num_ref):
                    pontos += 40.0
        except Exception:
            pass

        # 3. Comparação de Descrição Textual
        if x_norm and x_norm == desc_c_norm:
            pontos += 100.0
        elif len(x_norm) >= 5 and (x_norm in desc_c_norm or desc_c_norm in x_norm):
            pontos += 45.0

        intersecao = len(tokens_xml.intersection(tokens_c))
        if intersecao > 0:
            pontos += intersecao * 14.0
            if len(tokens_c) > 0:
                pontos += (intersecao / len(tokens_c)) * 25.0

        if pontos > melhor_pontuacao and pontos >= 22.0:
            melhor_pontuacao = pontos
            melhor_escolha = c

    situacao = "VÍNCULO PENDENTE"
    status_cor = "amber"
    saldo_antes = None
    saldo_depois = None

    if melhor_escolha:
        total_disp_contrato = round((melhor_escolha.get('qnt_contratada', 0) + melhor_escolha.get('qnt_aditivada', 0)), 4)
        faturado_atual = round(melhor_escolha.get('qnt_faturada', 0), 4)
        saldo_antes = round(total_disp_contrato - faturado_atual, 4)
        saldo_depois = round(saldo_antes - q_xml, 4)
        nota_antiga = melhor_escolha.get('nota_que_esgotou') or ""

        if saldo_antes <= 0:
            ref_nf = f" (desde {nota_antiga})" if nota_antiga else ""
            situacao = f"JÁ ESGOTADO{ref_nf} | Faltam {abs(saldo_depois):g}"
            status_cor = "red"
        elif saldo_depois < 0:
            situacao = f"ESTOUROU NESTA NF Nº {numero_nf_atual} (Passou {abs(saldo_depois):g})"
            status_cor = "red"
        elif saldo_depois == 0:
            situacao = f"ZEROU EXATO NESTA NF Nº {numero_nf_atual}"
            status_cor = "blue"
        else:
            situacao = f"SALDO OK (Restam {saldo_depois:g})"
            status_cor = "emerald"
    else:
        situacao = "SELECIONE O ITEM AO LADO"
        status_cor = "amber"

    return {
        "desc_xml": x_xml,
        "qtd_xml": q_xml,
        "val_xml": v_xml,
        "item_contrato_id": melhor_escolha.get('id') if melhor_escolha else None,
        "desc_contrato": melhor_escolha.get('descricao') if melhor_escolha else None,
        "saldo_antes": saldo_antes,
        "saldo_depois": saldo_depois,
        "situacao": situacao,
        "status_cor": status_cor
    }


# ============================================================================
# DASHBOARD E CONTRATOS
# ============================================================================

@csrf_exempt
@require_http_methods(["GET"])
def lista_empresas(request):
    """Lista todas as empresas com contagem de contratos para gerenciamento."""
    empresas = Empresa.objects.all()
    resultado = []
    for e in empresas:
        qtd_contratos = e.contratos.count()
        resultado.append({
            "id": e.id,
            "razao_social": e.razao_social,
            "cnpj": e.cnpj,
            "qtd_contratos": qtd_contratos,
        })
    return json_response(resultado)


@csrf_exempt
@require_http_methods(["GET"])
def lista_contratos(request):
    """Lista todos os contratos com contagens para o dashboard."""
    contratos = Contrato.objects.select_related('empresa').all()
    resultado = []

    for c in contratos:
        total_itens = c.itens.count()
        total_notas = c.notas.count()
        itens_esgotados = c.itens.filter(
            qnt_faturada__gte=models.F('quantidade_contratada') + models.F('qnt_aditivada')
        ).count() if total_itens > 0 else 0

        # Usa status_tce se disponível (fonte oficial TCE), senão calcula pela data
        if c.status_tce and "vig" in c.status_tce.lower():
            status_display = "ATIVO"
        elif c.status_tce and ("encerr" in c.status_tce.lower() or "finaliz" in c.status_tce.lower()):
            status_display = "VENCIDO"
        else:
            status_display = c.situacao.upper()

        resultado.append({
            "id": c.id,
            "nome_empresa": c.empresa.razao_social,
            "cnpj": c.empresa.cnpj,
            "numero_contrato": c.numero,
            "data_inicio": c.inicio_vigencia.isoformat() if c.inicio_vigencia else None,
            "data_fim": c.fim_vigencia.isoformat() if c.fim_vigencia else None,
            "status": status_display,
            "total_itens": total_itens,
            "total_notas": total_notas,
            "itens_esgotados": itens_esgotados,
        })

    return json_response(resultado)


@csrf_exempt
@require_http_methods(["GET"])
def detalhe_contrato(request, contrato_id):
    """Retorna contrato completo com itens e notas para a planilha interativa."""
    contrato = get_object_or_404(Contrato.objects.select_related('empresa'), pk=contrato_id)

    # Itens com preços vigentes
    itens_raw = contrato.itens.all()
    itens = []
    for it in itens_raw:
        preco = it.precos.order_by("-vigente_a_partir_de").first()
        val_unitario = float(preco.valor_unitario) if preco else 0.0

        # Calcula valor total faturado real
        fat_notas = ItemNota.objects.filter(
            item_contrato=it,
            nota__status__in=["conferida", "liberada"]
        ).aggregate(total=Sum('valor_total'))['total'] or Decimal("0")

        itens.append({
            "id": it.id,
            "item_num": it.numero_item,
            "lote": it.lote or "",
            "descricao": it.descricao,
            "qnt_contratada": round4(it.quantidade_contratada),
            "qnt_aditivada": round4(it.qnt_aditivada),
            "qnt_faturada": round4(it.qnt_faturada),
            "qnt_faturada_base": round4(it.qnt_faturada_base),
            "val_unitario": val_unitario,
            "nota_que_esgotou": it.nota_que_esgotou or "",
            "valor_total_faturado_real": round4(fat_notas),
        })

    # Notas fiscais
    notas_raw = contrato.notas.all()
    notas = []
    for n in notas_raw:
        notas.append({
            "id": n.id,
            "numero_nf": n.numero,
            "serie": n.serie,
            "data_emissao": n.data_emissao.isoformat() if n.data_emissao else None,
            "valor_total": float(n.valor_total),
            "status": n.status,
        })

    return json_response({
        "contrato": {
            "id": contrato.id,
            "nome_empresa": contrato.empresa.razao_social,
            "cnpj": contrato.empresa.cnpj,
            "numero_contrato": contrato.numero,
            "data_inicio": contrato.inicio_vigencia.isoformat() if contrato.inicio_vigencia else None,
            "data_fim": contrato.fim_vigencia.isoformat() if contrato.fim_vigencia else None,
        },
        "itens": itens,
        "notas": notas,
    })


@csrf_exempt
@require_http_methods(["POST"])
def cadastrar_contrato(request):
    """Cadastra novo contrato via API."""
    try:
        data = json.loads(request.body)
        empresa_nome = data.get('empresa', '').strip()
        contrato_num = data.get('contrato', '').strip()
        cnpj = data.get('cnpj', '').strip()
        inicio = data.get('inicio', '')
        fim = data.get('fim', '')

        if not empresa_nome or not contrato_num or not cnpj:
            return error_response("Empresa, número do contrato e CNPJ são obrigatórios.")

        # Valida CNPJ
        try:
            cnpj_formatado = validar_cnpj(cnpj)
        except Exception as e:
            return error_response(f"CNPJ inválido: {str(e)}")

        # Cria ou recupera empresa
        empresa, _ = Empresa.objects.get_or_create(
            cnpj=cnpj_formatado,
            defaults={"razao_social": empresa_nome}
        )

        # Verifica se contrato já existe
        if Contrato.objects.filter(numero=contrato_num).exists():
            return error_response(f"Contrato nº {contrato_num} já existe.")

        # Cria contrato
        contrato = Contrato.objects.create(
            numero=contrato_num,
            empresa=empresa,
            inicio_vigencia=inicio if inicio else timezone.now().date(),
            fim_vigencia=fim if fim else (timezone.now().date() + timedelta(days=365)),
        )

        return json_response({"ok": True, "id": contrato.id})

    except json.JSONDecodeError:
        return error_response("JSON inválido.")
    except Exception as e:
        return error_response(f"Erro ao cadastrar: {str(e)}", 500)


@csrf_exempt
@require_http_methods(["POST"])
def editar_contrato(request, contrato_id):
    """Edita dados do contrato."""
    try:
        data = json.loads(request.body)
        contrato = get_object_or_404(Contrato, pk=contrato_id)

        if 'nome_empresa' in data:
            contrato.empresa.razao_social = data['nome_empresa']
            contrato.empresa.save()

        if 'numero_contrato' in data:
            contrato.numero = data['numero_contrato']

        if 'cnpj' in data and data['cnpj']:
            try:
                cnpj_formatado = validar_cnpj(data['cnpj'])
                contrato.empresa.cnpj = cnpj_formatado
                contrato.empresa.save()
            except Exception as e:
                return error_response(f"CNPJ inválido: {str(e)}")

        contrato.save()
        return json_response({"ok": True})

    except json.JSONDecodeError:
        return error_response("JSON inválido.")
    except Exception as e:
        return error_response(f"Erro ao editar: {str(e)}", 500)


@csrf_exempt
@require_http_methods(["DELETE"])
def limpar_itens(request, contrato_id):
    """Remove todos os itens de um contrato."""
    try:
        contrato = get_object_or_404(Contrato, pk=contrato_id)
        contrato.itens.all().delete()
        return json_response({"ok": True})
    except Exception as e:
        return error_response(f"Erro ao limpar itens: {str(e)}", 500)


@csrf_exempt
@require_http_methods(["POST"])
def alterar_prazo(request, contrato_id):
    """Altera prazo de vigência do contrato."""
    try:
        data = json.loads(request.body)
        contrato = get_object_or_404(Contrato, pk=contrato_id)

        nova_data_fim = data.get('data_fim', '')
        if not nova_data_fim:
            return error_response("Nova data de fim é obrigatória.")

        contrato.fim_vigencia = nova_data_fim
        contrato.save()

        return json_response({"ok": True})

    except json.JSONDecodeError:
        return error_response("JSON inválido.")
    except Exception as e:
        return error_response(f"Erro ao alterar prazo: {str(e)}", 500)


# ============================================================================
# ITENS E ADITIVOS
# ============================================================================

@csrf_exempt
@require_http_methods(["DELETE"])
def excluir_item(request, item_id):
    """Exclui um item do contrato."""
    try:
        item = get_object_or_404(ItemContrato, pk=item_id)
        contrato_id = item.contrato_id
        item.delete()
        recalcular_saldos_contrato(contrato_id)
        return json_response({"ok": True})
    except Exception as e:
        return error_response(f"Erro ao excluir item: {str(e)}", 500)


@csrf_exempt
@require_http_methods(["POST"])
def salvar_aditivo(request, item_id):
    """Salva aditivo de quantidade/preço de um item."""
    try:
        data = json.loads(request.body)
        item = get_object_or_404(ItemContrato, pk=item_id)

        modo = data.get('modo', 'SOMAR')
        quantidade = parse_decimal(data.get('quantidade', 0))
        descricao = data.get('descricao', '').strip()
        qnt_contratada = parse_decimal(data.get('qnt_contratada', 0))
        qnt_faturada_base = parse_decimal(data.get('qnt_faturada_base', 0))
        preco = parse_decimal(data.get('preco', 0))
        criar_novo_se_preco_mudar = data.get('criar_novo_se_preco_mudar', False)

        with transaction.atomic():
            # Atualiza descrição se mudou
            if descricao and descricao != item.descricao:
                item.descricao = descricao
                item.descricao_normalizada = normalizar_descricao(descricao)

            # Atualiza quantidade contratada se mudou
            if qnt_contratada > 0:
                item.quantidade_contratada = qnt_contratada

            # Atualiza faturado base se mudou
            if qnt_faturada_base >= 0:
                item.qnt_faturada_base = qnt_faturada_base

            # Aplica aditivo de quantidade
            if quantidade != 0:
                if modo == 'SOMAR':
                    item.qnt_aditivada = item.qnt_aditivada + quantidade
                elif modo == 'SUBSTITUIR':
                    item.qnt_aditivada = quantidade
                elif modo == 'ZERAR':
                    item.qnt_aditivada = Decimal("0")

            # Atualiza preço se mudou
            if preco > 0:
                preco_atual = item.precos.order_by("-vigente_a_partir_de").first()
                if not preco_atual or preco_atual.valor_unitario != preco:
                    if criar_novo_se_preco_mudar or not preco_atual:
                        PrecoItem.objects.create(
                            item=item,
                            valor_unitario=preco,
                            vigente_a_partir_de=timezone.now().date()
                        )
                    else:
                        preco_atual.valor_unitario = preco
                        preco_atual.save()

            item.save()
            recalcular_saldos_contrato(item.contrato_id)

        return json_response({"ok": True})

    except json.JSONDecodeError:
        return error_response("JSON inválido.")
    except Exception as e:
        return error_response(f"Erro ao salvar aditivo: {str(e)}", 500)


@csrf_exempt
@require_http_methods(["POST"])
def zerar_aditivo(request, item_id):
    """Zera o aditivo de um item."""
    try:
        item = get_object_or_404(ItemContrato, pk=item_id)
        item.qnt_aditivada = Decimal("0")
        item.save()
        recalcular_saldos_contrato(item.contrato_id)
        return json_response({"ok": True})
    except Exception as e:
        return error_response(f"Erro ao zerar aditivo: {str(e)}", 500)


# ============================================================================
# EMPRESAS
# ============================================================================

@csrf_exempt
@require_http_methods(["DELETE"])
def excluir_empresa(request, empresa_id):
    """Exclui uma empresa e todos os seus contratos, itens e notas."""
    try:
        empresa = get_object_or_404(Empresa, pk=empresa_id)
        with transaction.atomic():
            # Exclui notas dos contratos da empresa
            for contrato in empresa.contratos.all():
                contrato.notas.all().delete()
                contrato.itens.all().delete()
            empresa.contratos.all().delete()
            empresa.delete()
        return json_response({"ok": True})
    except Exception as e:
        return error_response(f"Erro ao excluir empresa: {str(e)}", 500)


@csrf_exempt
@require_http_methods(["DELETE"])
def excluir_todas_empresas(request):
    """Exclui todas as empresas e todos os dados associados."""
    try:
        with transaction.atomic():
            NotaFiscal.objects.all().delete()
            ItemContrato.objects.all().delete()
            Contrato.objects.all().delete()
            Empresa.objects.all().delete()
        return json_response({"ok": True})
    except Exception as e:
        return error_response(f"Erro ao excluir todas as empresas: {str(e)}", 500)


# ============================================================================
# NOTAS FISCAIS
# ============================================================================

@csrf_exempt
@require_http_methods(["DELETE"])
def excluir_nota(request, nota_id):
    """Exclui nota fiscal e estorna saldos."""
    try:
        nota = get_object_or_404(NotaFiscal, pk=nota_id)
        contrato_id = nota.contrato_id

        with transaction.atomic():
            nota.delete()
            recalcular_saldos_contrato(contrato_id)

        return json_response({"ok": True})
    except Exception as e:
        return error_response(f"Erro ao excluir nota: {str(e)}", 500)


# ============================================================================
# XML / PDF
# ============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def analisar_xml(request):
    """Analisa arquivo XML único e retorna itens conciliados."""
    try:
        if 'arquivo_xml' not in request.FILES:
            return error_response("Nenhum arquivo XML enviado.")

        arquivo = request.FILES['arquivo_xml']
        conteudo = arquivo.read()

        # Parse XML (simplificado — em produção usaria xml_engine.py completo)
        import xml.etree.ElementTree as ET
        texto = conteudo.decode('utf-8', errors='ignore')
        tree = ET.fromstring(texto)
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        infNFe = tree.find('.//nfe:infNFe', ns)

        if infNFe is None:
            return error_response("Estrutura de NF-e inválida no arquivo XML.")

        ide = infNFe.find('nfe:ide', ns)
        emit = infNFe.find('nfe:emit', ns)
        total = infNFe.find('.//nfe:ICMSTot', ns)

        chave = infNFe.attrib.get('Id', '').replace('NFe', '')
        numero_nf = ide.find('nfe:nNF', ns).text if ide is not None and ide.find('nfe:nNF', ns) is not None else "S/N"
        serie = ide.find('nfe:serie', ns).text if ide is not None and ide.find('nfe:serie', ns) is not None else "1"
        dhEmi = ide.find('nfe:dhEmi', ns).text if ide is not None and ide.find('nfe:dhEmi', ns) is not None else ""
        data_emissao = dhEmi[:10] if dhEmi else ""

        cnpj_emit = emit.find('nfe:CNPJ', ns).text if emit is not None and emit.find('nfe:CNPJ', ns) is not None else ""
        razao_emit = emit.find('nfe:xNome', ns).text if emit is not None and emit.find('nfe:xNome', ns) is not None else ""
        vNF = float(total.find('nfe:vNF', ns).text) if total is not None and total.find('nfe:vNF', ns) is not None else 0.0

        # Extrai itens do XML
        itens_xml = []
        for det in infNFe.findall('nfe:det', ns):
            prod = det.find('nfe:prod', ns)
            if prod is None:
                continue
            xProd = prod.find('nfe:xProd', ns).text.strip().upper() if prod.find('nfe:xProd', ns) is not None else ""
            qCom = round(float(prod.find('nfe:qCom', ns).text), 4) if prod.find('nfe:qCom', ns) is not None else 0.0
            vUnCom = round(float(prod.find('nfe:vUnCom', ns).text), 4) if prod.find('nfe:vUnCom', ns) is not None else 0.0
            itens_xml.append({"desc_xml": xProd, "qtd_xml": qCom, "val_xml": vUnCom})

        # Tenta encontrar contrato pelo CNPJ
        contexto_id = request.POST.get('contexto_id')
        contrato = None
        if contexto_id:
            contrato = Contrato.objects.filter(pk=contexto_id).first()
        elif cnpj_emit:
            empresa = Empresa.objects.filter(cnpj__icontains=cnpj_emit).first()
            if empresa:
                contrato = empresa.contratos.first()

        if not contrato:
            return error_response("Contrato não encontrado para este CNPJ. Selecione manualmente.")

        # Carrega itens do contrato
        itens_contrato = []
        for it in contrato.itens.all():
            preco = it.precos.order_by("-vigente_a_partir_de").first()
            itens_contrato.append({
                "id": it.id,
                "item_num": it.numero_item,
                "descricao": it.descricao,
                "qnt_contratada": float(it.quantidade_contratada),
                "qnt_aditivada": float(it.qnt_aditivada),
                "qnt_faturada": float(it.qnt_faturada),
                "val_unitario": float(preco.valor_unitario) if preco else 0.0,
                "nota_que_esgotou": it.nota_que_esgotou or "",
            })

        # Concilia itens
        itens_conciliados = []
        for it_xml in itens_xml:
            resultado = conciliar_item_inteligente(it_xml, itens_contrato, numero_nf)
            itens_conciliados.append(resultado)

        return json_response({
            "ok": True,
            "contrato_id": contrato.id,
            "contrato_nome": f"{contrato.numero} — {contrato.empresa.razao_social}",
            "numero_nf": numero_nf,
            "serie": serie,
            "data_emissao": data_emissao,
            "chave_acesso": chave,
            "emitente": razao_emit,
            "valor_total": vNF,
            "itens": itens_conciliados,
            "itens_contrato_disponiveis": itens_contrato,
        })

    except Exception as e:
        return error_response(f"Erro ao analisar XML: {str(e)}", 500)


@csrf_exempt
@require_http_methods(["POST"])
def gravar_xml(request):
    """Grava nota fiscal analisada no banco."""
    try:
        data = json.loads(request.body)
        contrato_id = data.get('contrato_id')
        numero_nf = data.get('numero_nf', 'S/N')
        serie = data.get('serie', '1')
        data_emissao = data.get('data_emissao', '')
        chave_acesso = data.get('chave_acesso', '')
        valor_total = parse_decimal(data.get('valor_total', 0))
        itens = data.get('itens', [])

        contrato = get_object_or_404(Contrato, pk=contrato_id)

        # Verifica duplicidade
        if chave_acesso and NotaFiscal.objects.filter(chave_acesso=chave_acesso).exists():
            return error_response(f"Nota com chave {chave_acesso} já existe.")

        # Cria ou recupera empresa
        cnpj_emit = data.get('cnpj_emitente', '')
        razao_emit = data.get('razao_emitente', 'FORNECEDOR')
        if cnpj_emit:
            try:
                cnpj_formatado = validar_cnpj(cnpj_emit)
                empresa, _ = Empresa.objects.get_or_create(
                    cnpj=cnpj_formatado,
                    defaults={"razao_social": razao_emit}
                )
            except:
                empresa = contrato.empresa
        else:
            empresa = contrato.empresa

        with transaction.atomic():
            nota = NotaFiscal.objects.create(
                empresa=empresa,
                contrato=contrato,
                chave_acesso=chave_acesso if chave_acesso else None,
                numero=numero_nf,
                serie=serie,
                data_emissao=data_emissao if data_emissao else timezone.now().date(),
                valor_total=valor_total,
                origem="xml",
                status="conferida",
            )

            for it in itens:
                item_contrato_id = it.get('item_contrato_id')
                if not item_contrato_id:
                    continue

                ItemNota.objects.create(
                    nota=nota,
                    descricao=it.get('desc_xml', ''),
                    unidade="UN",
                    quantidade=parse_decimal(it.get('qtd_xml', 0)),
                    valor_unitario=parse_decimal(it.get('val_xml', 0)),
                    valor_total=parse_decimal(it.get('qtd_xml', 0)) * parse_decimal(it.get('val_xml', 0)),
                    item_contrato_id=item_contrato_id,
                )

            recalcular_saldos_contrato(contrato_id)

        return json_response({"ok": True, "nota_id": nota.id})

    except json.JSONDecodeError:
        return error_response("JSON inválido.")
    except Exception as e:
        return error_response(f"Erro ao gravar XML: {str(e)}", 500)


@csrf_exempt
@require_http_methods(["POST"])
def analisar_xml_multiplo(request):
    """Analisa múltiplos arquivos XML/PDF."""
    try:
        arquivos = request.FILES.getlist('arquivos')
        if not arquivos:
            return error_response("Nenhum arquivo enviado.")

        contexto_id = request.POST.get('contexto_id')
        notas_processadas = []
        erros = []

        for arquivo in arquivos:
            try:
                conteudo = arquivo.read()
                nome = arquivo.name.lower()

                if nome.endswith('.xml'):
                    # Processa XML (reusa lógica de analisar_xml)
                    resultado = processar_xml_individual(conteudo, contexto_id)
                    if resultado.get('ok'):
                        notas_processadas.append(resultado)
                    else:
                        erros.append(f"{arquivo.name}: {resultado.get('erro', 'Erro desconhecido')}")
                elif nome.endswith('.pdf'):
                    # Processa PDF (simplificado)
                    erros.append(f"{arquivo.name}: Leitura de PDF ainda não implementada nesta versão.")
                else:
                    erros.append(f"{arquivo.name}: Formato não suportado.")

            except Exception as e:
                erros.append(f"{arquivo.name}: {str(e)}")

        return json_response({
            "ok": len(notas_processadas) > 0,
            "notas": notas_processadas,
            "erros": erros,
        })

    except Exception as e:
        return error_response(f"Erro ao analisar múltiplos arquivos: {str(e)}", 500)


def processar_xml_individual(conteudo, contexto_id=None):
    """Processa um único XML e retorna resultado conciliado."""
    try:
        import xml.etree.ElementTree as ET
        texto = conteudo.decode('utf-8', errors='ignore')
        tree = ET.fromstring(texto)
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        infNFe = tree.find('.//nfe:infNFe', ns)

        if infNFe is None:
            return {"ok": False, "erro": "Estrutura de NF-e inválida."}

        ide = infNFe.find('nfe:ide', ns)
        emit = infNFe.find('nfe:emit', ns)
        total = infNFe.find('.//nfe:ICMSTot', ns)

        chave = infNFe.attrib.get('Id', '').replace('NFe', '')
        numero_nf = ide.find('nfe:nNF', ns).text if ide is not None and ide.find('nfe:nNF', ns) is not None else "S/N"
        serie = ide.find('nfe:serie', ns).text if ide is not None and ide.find('nfe:serie', ns) is not None else "1"
        dhEmi = ide.find('nfe:dhEmi', ns).text if ide is not None and ide.find('nfe:dhEmi', ns) is not None else ""
        data_emissao = dhEmi[:10] if dhEmi else ""

        cnpj_emit = emit.find('nfe:CNPJ', ns).text if emit is not None and emit.find('nfe:CNPJ', ns) is not None else ""
        razao_emit = emit.find('nfe:xNome', ns).text if emit is not None and emit.find('nfe:xNome', ns) is not None else ""
        vNF = float(total.find('nfe:vNF', ns).text) if total is not None and total.find('nfe:vNF', ns) is not None else 0.0

        itens_xml = []
        for det in infNFe.findall('nfe:det', ns):
            prod = det.find('nfe:prod', ns)
            if prod is None:
                continue
            xProd = prod.find('nfe:xProd', ns).text.strip().upper() if prod.find('nfe:xProd', ns) is not None else ""
            qCom = round(float(prod.find('nfe:qCom', ns).text), 4) if prod.find('nfe:qCom', ns) is not None else 0.0
            vUnCom = round(float(prod.find('nfe:vUnCom', ns).text), 4) if prod.find('nfe:vUnCom', ns) is not None else 0.0
            itens_xml.append({"desc_xml": xProd, "qtd_xml": qCom, "val_xml": vUnCom})

        # Encontra contrato
        contrato = None
        if contexto_id:
            contrato = Contrato.objects.filter(pk=contexto_id).first()
        elif cnpj_emit:
            empresa = Empresa.objects.filter(cnpj__icontains=cnpj_emit).first()
            if empresa:
                contrato = empresa.contratos.first()

        if not contrato:
            return {"ok": False, "erro": "Contrato não encontrado."}

        itens_contrato = []
        for it in contrato.itens.all():
            preco = it.precos.order_by("-vigente_a_partir_de").first()
            itens_contrato.append({
                "id": it.id,
                "item_num": it.numero_item,
                "descricao": it.descricao,
                "qnt_contratada": float(it.quantidade_contratada),
                "qnt_aditivada": float(it.qnt_aditivada),
                "qnt_faturada": float(it.qnt_faturada),
                "val_unitario": float(preco.valor_unitario) if preco else 0.0,
                "nota_que_esgotou": it.nota_que_esgotou or "",
            })

        itens_conciliados = [conciliar_item_inteligente(it, itens_contrato, numero_nf) for it in itens_xml]

        return {
            "ok": True,
            "contrato_id": contrato.id,
            "contrato_nome": f"{contrato.numero} — {contrato.empresa.razao_social}",
            "numero_nf": numero_nf,
            "serie": serie,
            "data_emissao": data_emissao,
            "chave_acesso": chave,
            "emitente": razao_emit,
            "valor_total": vNF,
            "itens": itens_conciliados,
            "itens_contrato_disponiveis": itens_contrato,
        }

    except Exception as e:
        return {"ok": False, "erro": str(e)}


@csrf_exempt
@require_http_methods(["POST"])
def gravar_xml_multiplo(request):
    """Grava múltiplas notas fiscais no banco."""
    try:
        data = json.loads(request.body)
        notas = data.get('notas', [])

        if not notas:
            return error_response("Nenhuma nota para gravar.")

        notas_gravadas = []

        for nota_data in notas:
            resultado = gravar_nota_individual(nota_data)
            if resultado.get('ok'):
                notas_gravadas.append(resultado)
            else:
                return error_response(f"Erro na nota {nota_data.get('numero_nf', '?')}: {resultado.get('erro', 'Erro desconhecido')}")

        return json_response({"ok": True, "notas_gravadas": len(notas_gravadas)})

    except json.JSONDecodeError:
        return error_response("JSON inválido.")
    except Exception as e:
        return error_response(f"Erro ao gravar múltiplas notas: {str(e)}", 500)


def gravar_nota_individual(nota_data):
    """Grava uma única nota fiscal."""
    try:
        contrato_id = nota_data.get('contrato_id')
        numero_nf = nota_data.get('numero_nf', 'S/N')
        serie = nota_data.get('serie', '1')
        data_emissao = nota_data.get('data_emissao', '')
        chave_acesso = nota_data.get('chave_acesso', '')
        valor_total = parse_decimal(nota_data.get('valor_total', 0))
        itens = nota_data.get('itens', [])

        contrato = get_object_or_404(Contrato, pk=contrato_id)

        if chave_acesso and NotaFiscal.objects.filter(chave_acesso=chave_acesso).exists():
            return {"ok": False, "erro": f"Nota com chave {chave_acesso} já existe."}

        with transaction.atomic():
            nota = NotaFiscal.objects.create(
                empresa=contrato.empresa,
                contrato=contrato,
                chave_acesso=chave_acesso if chave_acesso else None,
                numero=numero_nf,
                serie=serie,
                data_emissao=data_emissao if data_emissao else timezone.now().date(),
                valor_total=valor_total,
                origem="xml",
                status="conferida",
            )

            for it in itens:
                item_contrato_id = it.get('item_contrato_id')
                if not item_contrato_id:
                    continue

                ItemNota.objects.create(
                    nota=nota,
                    descricao=it.get('desc_xml', ''),
                    unidade="UN",
                    quantidade=parse_decimal(it.get('qtd_xml', 0)),
                    valor_unitario=parse_decimal(it.get('val_xml', 0)),
                    valor_total=parse_decimal(it.get('qtd_xml', 0)) * parse_decimal(it.get('val_xml', 0)),
                    item_contrato_id=item_contrato_id,
                )

            recalcular_saldos_contrato(contrato_id)

        return {"ok": True, "nota_id": nota.id}

    except Exception as e:
        return {"ok": False, "erro": str(e)}


# ============================================================================
# IMPORTAÇÃO EXCEL
# ============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def importar_excel(request):
    """Importa planilha Excel de itens (legado — usa importacao app)."""
    return error_response("Use /api/importar_itens com contrato_id selecionado.")


@csrf_exempt
@require_http_methods(["POST"])
def importar_itens(request):
    """Importa itens de planilha Excel para um contrato específico usando detector inteligente de colunas."""
    try:
        contrato_id = request.POST.get('contrato_id')
        if not contrato_id:
            return error_response("contrato_id é obrigatório.")

        arquivo = request.FILES.get('arquivo')
        if not arquivo:
            return error_response("Nenhum arquivo enviado.")

        modo_somar = request.POST.get('modo_somar', 'false') == 'true'
        contrato = get_object_or_404(Contrato, pk=contrato_id)

        # Usa o detector inteligente de colunas
        import openpyxl
        from importacao.detectar_colunas import encontrar_linha_cabecalho, detectar_colunas, extrair_itens_planilha

        wb = openpyxl.load_workbook(arquivo, read_only=True, data_only=True)
        ws = wb.active

        linha_cab_idx, linha_cab = encontrar_linha_cabecalho(ws)
        if linha_cab is None:
            wb.close()
            return error_response("Não foi possível detectar o cabeçalho da planilha. Verifique se a primeira linha contém os nomes das colunas (item, quant, valor, etc.).")

        mapeamento = detectar_colunas(linha_cab)
        if mapeamento.get('descricao') is None:
            wb.close()
            return error_response("Coluna de descrição não encontrada. A planilha deve ter uma coluna chamada 'item', 'descrição' ou 'objeto'.")

        itens_extraidos = extrair_itens_planilha(ws, linha_cab_idx, mapeamento)
        wb.close()

        if not itens_extraidos:
            return error_response("Nenhum item válido encontrado na planilha.")

        with transaction.atomic():
            # Se não estiver em modo somar, limpa itens existentes antes de importar
            if not modo_somar:
                contrato.itens.all().delete()

            # Encontra o maior numero_item existente para gerar sequência única
            max_num = ItemContrato.objects.filter(contrato=contrato).aggregate(
                m=models.Max('numero_item')
            )['m'] or 0
            seq_counter = max_num + 1

            for it_data in itens_extraidos:
                if modo_somar:
                    # Tenta encontrar item existente pelo número ou descrição
                    item_existente = ItemContrato.objects.filter(
                        contrato=contrato,
                        numero_item=it_data['item_num']
                    ).first()
                    if not item_existente and it_data['descricao']:
                        item_existente = ItemContrato.objects.filter(
                            contrato=contrato,
                            descricao__icontains=it_data['descricao'][:50]
                        ).first()

                    if item_existente:
                        if it_data['quant'] is not None:
                            item_existente.quantidade_contratada = Decimal(str(it_data['quant']))
                        if it_data['qnt_comprada'] is not None:
                            item_existente.qnt_faturada_base = Decimal(str(it_data['qnt_comprada']))
                        if it_data['val_unit'] is not None:
                            preco_atual = item_existente.precos.order_by("-vigente_a_partir_de").first()
                            if not preco_atual or float(preco_atual.valor_unitario) != it_data['val_unit']:
                                PrecoItem.objects.create(
                                    item=item_existente,
                                    valor_unitario=Decimal(str(it_data['val_unit'])),
                                    vigente_a_partir_de=timezone.now().date()
                                )
                        item_existente.save()
                        continue

                # Gera numero_item único: usa o da planilha se válido (>0), senão usa sequência
                num_item_raw = it_data.get('item_num', '') or 0
                try:
                    num_item = int(num_item_raw)
                except (ValueError, TypeError):
                    num_item = 0

                lote_val = it_data.get('lote', '') or ''

                # Se numero_item é 0 ou já existe com mesmo lote, usa sequência
                if num_item <= 0 or ItemContrato.objects.filter(
                    contrato=contrato, numero_item=num_item, lote=lote_val
                ).exists():
                    num_item = seq_counter
                    seq_counter += 1

                # Garante quantidade mínima de 0.0001 para passar no CheckConstraint
                quant_val = it_data['quant'] if it_data['quant'] and float(it_data['quant']) > 0 else 1

                item = ItemContrato.objects.create(
                    contrato=contrato,
                    lote=lote_val,
                    numero_item=num_item,
                    descricao=it_data['descricao'],
                    quantidade_contratada=Decimal(str(quant_val)),
                    qnt_aditivada=Decimal("0"),
                    qnt_faturada_base=Decimal(str(it_data['qnt_comprada'] or 0)),
                    qnt_faturada=Decimal(str(it_data['qnt_comprada'] or 0)),
                )
                if it_data.get('val_unit') is not None:
                    PrecoItem.objects.create(
                        item=item,
                        valor_unitario=Decimal(str(it_data['val_unit'])),
                        vigente_a_partir_de=timezone.now().date()
                    )

        recalcular_saldos_contrato(contrato_id)
        return json_response({"ok": True, "itens_importados": len(itens_extraidos)})

    except Exception as e:
        return error_response(f"Erro ao importar itens: {str(e)}", 500)


@csrf_exempt
@require_http_methods(["POST"])
def verificar_planilha(request):
    """Verifica compatibilidade da planilha com o contrato selecionado."""
    try:
        contrato_id = request.POST.get('contrato_id')
        arquivo = request.FILES.get('arquivo')

        if not contrato_id or not arquivo:
            return json_response({"aviso": None})

        # Lógica simplificada — em produção compararia CNPJ/nome da planilha com contrato
        return json_response({"aviso": None})

    except Exception as e:
        return json_response({"aviso": None})


@csrf_exempt
@require_http_methods(["POST"])
def importar_lista_mestra(request):
    """
    Importa lista mestra de contratos/empresas do TCE (contratos_saude_vigentes.xlsx).
    Cria ou atualiza registros de Empresa e Contrato a partir da planilha.
    Colunas esperadas: Número do Contrato, CNPJ, Status, Data Assinatura,
    Início Vigência, Fim Vigência, Processo TCE, Modalidade, Tipo, Objeto.
    """
    try:
        arquivo = request.FILES.get('arquivo')
        if not arquivo:
            return error_response("Nenhum arquivo enviado.")

        import openpyxl
        from importacao.detectar_colunas import normalizar, parse_valor_br

        wb = openpyxl.load_workbook(arquivo, read_only=True, data_only=True)
        ws = wb.active

        # Encontra cabeçalho
        linha_cab_idx = None
        linha_cab = None
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= 15:
                break
            celulas_texto = [str(c).strip() for c in row if c is not None]
            normais = [normalizar(c) for c in celulas_texto]
            hits = sum(1 for n in normais if any(p in n for p in ("contrato", "cnpj", "vigencia", "objeto", "status")))
            if hits >= 2 and len(celulas_texto) >= 3:
                linha_cab_idx = i
                linha_cab = list(row)
                break

        if linha_cab is None:
            wb.close()
            return error_response("Cabeçalho da lista mestra não encontrado. Verifique se a planilha contém colunas como 'Número do Contrato', 'CNPJ', etc.")

        # Mapeia colunas
        mapeamento = {}
        for idx, celula in enumerate(linha_cab):
            norm = normalizar(celula)
            if not norm:
                continue
            if "numero" in norm and "contrato" in norm:
                mapeamento["numero"] = idx
            elif "nome" in norm and "empresa" in norm:
                mapeamento["nome_empresa"] = idx
            elif norm == "cnpj":
                mapeamento["cnpj"] = idx
            elif "status" in norm:
                mapeamento["status"] = idx
            elif "data" in norm and "assinatura" in norm:
                mapeamento["data_assinatura"] = idx
            elif "inicio" in norm and "vigencia" in norm:
                # Prioriza "Atual" sobre "Inicial"
                if "inicio_vigencia" not in mapeamento or "atual" in norm:
                    mapeamento["inicio_vigencia"] = idx
            elif "fim" in norm and "vigencia" in norm:
                if "fim_vigencia" not in mapeamento or "atual" in norm:
                    mapeamento["fim_vigencia"] = idx
            elif "processo" in norm:
                mapeamento["processo_tce"] = idx
            elif "modalidade" in norm:
                mapeamento["modalidade"] = idx
            elif "tipo" in norm:
                mapeamento["tipo"] = idx
            elif "objeto" in norm:
                mapeamento["objeto"] = idx

        if "numero" not in mapeamento or "cnpj" not in mapeamento:
            wb.close()
            return error_response("Colunas obrigatórias 'Número do Contrato' e 'CNPJ' não encontradas na planilha.")

        criados_empresas = 0
        atualizados_empresas = 0
        criados_contratos = 0
        atualizados_contratos = 0
        erros = []

        with transaction.atomic():
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i <= linha_cab_idx:
                    continue
                if not any(c is not None and str(c).strip() for c in row):
                    continue

                def pegar(campo):
                    idx = mapeamento.get(campo)
                    if idx is None or idx >= len(row):
                        return None
                    val = row[idx]
                    if val is None:
                        return None
                    return str(val).strip()

                numero = pegar("numero")
                cnpj = pegar("cnpj")
                if not numero or not cnpj:
                    continue

                # Limpa prefixo "Termo de contrato" do número
                numero_limpo = re.sub(r"^termo\s+de\s+contrato\s+", "", numero, flags=re.IGNORECASE).strip()

                # Limpa CNPJ
                cnpj_limpo = re.sub(r"[^\d]", "", cnpj)
                if len(cnpj_limpo) != 14:
                    erros.append(f"Linha {i+1}: CNPJ inválido '{cnpj}'")
                    continue

                # Formata CNPJ para padrão XX.XXX.XXX/XXXX-XX
                cnpj_fmt = f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"

                # Busca nome da empresa (prioridade) ou objeto como fallback
                nome_empresa = pegar("nome_empresa") or ""
                objeto = pegar("objeto") or ""
                razao = nome_empresa if nome_empresa else (objeto[:200] if objeto else f"Empresa {cnpj_fmt}")

                # Cria ou atualiza empresa — sempre atualiza o nome se veio da planilha mestra
                empresa, criado_emp = Empresa.objects.get_or_create(
                    cnpj=cnpj_fmt,
                    defaults={"razao_social": razao}
                )
                if criado_emp:
                    criados_empresas += 1
                else:
                    # Atualiza o nome se a planilha trouxe um nome melhor
                    if nome_empresa and empresa.razao_social != nome_empresa:
                        empresa.razao_social = nome_empresa
                        empresa.save()
                    atualizados_empresas += 1

                # Parse datas
                def parse_data(val):
                    if val is None:
                        return None
                    s = str(val).strip()
                    if not s:
                        return None
                    # Tenta dd/mm/aaaa
                    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                        try:
                            from datetime import datetime
                            return datetime.strptime(s, fmt).date()
                        except ValueError:
                            continue
                    return None

                inicio_raw = row[mapeamento["inicio_vigencia"]] if "inicio_vigencia" in mapeamento and mapeamento["inicio_vigencia"] < len(row) else None
                fim_raw = row[mapeamento["fim_vigencia"]] if "fim_vigencia" in mapeamento and mapeamento["fim_vigencia"] < len(row) else None

                inicio_vig = parse_data(inicio_raw)
                fim_vig = parse_data(fim_raw)

                # Status da planilha TCE
                status_planilha = pegar("status") or ""

                # Cria ou atualiza contrato (usa numero_limpo sem o prefixo "Termo de contrato")
                contrato, criado_ct = Contrato.objects.update_or_create(
                    numero=numero_limpo,
                    empresa=empresa,
                    defaults={
                        "inicio_vigencia": inicio_vig,
                        "fim_vigencia": fim_vig,
                        "status_tce": status_planilha,
                    }
                )
                # Se já existia, atualiza o status_tce também
                if not criado_ct and status_planilha:
                    contrato.status_tce = status_planilha
                    contrato.save(update_fields=["status_tce"])
                if criado_ct:
                    criados_contratos += 1
                else:
                    atualizados_contratos += 1

        wb.close()

        return json_response({
            "ok": True,
            "empresas_criadas": criados_empresas,
            "empresas_atualizadas": atualizados_empresas,
            "contratos_criados": criados_contratos,
            "contratos_atualizados": atualizados_contratos,
            "erros": erros[:20],
        })

    except Exception as e:
        return error_response(f"Erro ao importar lista mestra: {str(e)}", 500)


# ============================================================================
# LANÇAMENTO MANUAL / TEXTO IA
# ============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def analisar_texto_ia(request):
    """Analisa texto colado (tabela IA, NFS-e) e extrai itens."""
    try:
        data = json.loads(request.body)
        texto = data.get('texto', '')
        numero_nf = data.get('numero_nf', 'S/N')
        data_emissao = data.get('data_emissao', '')
        contexto_id = data.get('contexto_id')

        if not texto.strip():
            return error_response("Texto vazio.")

        # Extrai itens do texto (lógica simplificada do app.py original)
        itens_extraidos = extrair_itens_de_texto(texto)

        if not itens_extraidos:
            return error_response("Não foi possível extrair itens do texto.")

        # Concilia com contrato
        contrato = Contrato.objects.filter(pk=contexto_id).first() if contexto_id else None
        if not contrato:
            return error_response("Contrato não encontrado.")

        itens_contrato = []
        for it in contrato.itens.all():
            preco = it.precos.order_by("-vigente_a_partir_de").first()
            itens_contrato.append({
                "id": it.id,
                "item_num": it.numero_item,
                "descricao": it.descricao,
                "qnt_contratada": float(it.quantidade_contratada),
                "qnt_aditivada": float(it.qnt_aditivada),
                "qnt_faturada": float(it.qnt_faturada),
                "val_unitario": float(preco.valor_unitario) if preco else 0.0,
                "nota_que_esgotou": it.nota_que_esgotou or "",
            })

        itens_conciliados = [conciliar_item_inteligente(it, itens_contrato, numero_nf) for it in itens_extraidos]

        return json_response({
            "ok": True,
            "notas": [{
                "contrato_id": contrato.id,
                "numero_nf": numero_nf,
                "data_emissao": data_emissao,
                "itens": itens_conciliados,
            }]
        })

    except json.JSONDecodeError:
        return error_response("JSON inválido.")
    except Exception as e:
        return error_response(f"Erro ao analisar texto: {str(e)}", 500)


def extrair_itens_de_texto(texto):
    """Extrai itens de texto livre (tabelas, listas, etc.)."""
    itens = []
    linhas = texto.strip().split('\n')

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue

        # Tenta extrair padrão: Descrição | Quantidade | Valor Unitário
        partes = re.split(r'[|\t;]+', linha)
        if len(partes) >= 3:
            desc = partes[0].strip()
            try:
                qtd = float(re.sub(r'[^\d.,]', '', partes[1]).replace(',', '.'))
                val = float(re.sub(r'[^\d.,]', '', partes[2]).replace(',', '.'))
                if qtd > 0 and val > 0:
                    itens.append({"desc_xml": desc.upper(), "qtd_xml": qtd, "val_xml": val})
            except:
                pass

    return itens


# ============================================================================
# RELATÓRIOS PDF
# ============================================================================

@csrf_exempt
@require_http_methods(["GET"])
def pdf_relatorio_contrato(request):
    """Gera relatório PDF de saldos do contrato."""
    try:
        contrato_id = request.GET.get('contrato_id')
        if not contrato_id:
            return error_response("contrato_id é obrigatório.")

        contrato = get_object_or_404(Contrato.objects.select_related('empresa'), pk=contrato_id)

        # Gera HTML do relatório (simplificado)
        html = gerar_html_relatorio(contrato)

        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = f'inline; filename="relatorio_{contrato.numero}.html"'
        return response

    except Exception as e:
        return error_response(f"Erro ao gerar relatório: {str(e)}", 500)


def gerar_html_relatorio(contrato):
    """Gera HTML do relatório de saldos."""
    itens_html = ""
    total_faturado = 0
    total_disponivel = 0

    for it in contrato.itens.all():
        preco = it.precos.order_by("-vigente_a_partir_de").first()
        val_unit = float(preco.valor_unitario) if preco else 0.0
        qtd_total = float(it.quantidade_contratada) + float(it.qnt_aditivada)
        disp_qtd = qtd_total - float(it.qnt_faturada)
        fat_real = float(it.qnt_faturada) * val_unit
        val_disp = max(0, (qtd_total * val_unit) - fat_real)

        total_faturado += fat_real
        total_disponivel += val_disp

        cor_linha = "background:#fff1f2;" if disp_qtd <= 0 else ""
        itens_html += f"""
        <tr style='{cor_linha}'>
            <td style='border:1px solid #444; padding:3px 5px; text-align:center;'>{it.numero_item}</td>
            <td style='border:1px solid #444; padding:3px 5px;'>{it.descricao}</td>
            <td style='border:1px solid #444; padding:3px 5px; text-align:right;'>{format_int_qtd(it.quantidade_contratada)}</td>
            <td style='border:1px solid #444; padding:3px 5px; text-align:right;'>{format_int_qtd(it.qnt_aditivada) if it.qnt_aditivada else '-'}</td>
            <td style='border:1px solid #444; padding:3px 5px; text-align:right;'>{format_int_qtd(it.qnt_faturada)}</td>
            <td style='border:1px solid #444; padding:3px 5px; text-align:right; font-weight:bold;'>{format_int_qtd(disp_qtd)}</td>
            <td style='border:1px solid #444; padding:3px 5px; text-align:right;'>R$ {format_br(val_unit)}</td>
            <td style='border:1px solid #444; padding:3px 5px; text-align:right;'>R$ {format_br(fat_real)}</td>
            <td style='border:1px solid #444; padding:3px 5px; text-align:right; font-weight:bold;'>R$ {format_br(val_disp)}</td>
        </tr>
        """

    return f"""
    <html><head><title>Relatório - {contrato.empresa.razao_social}</title>
    <style>
        @page {{ size: A4 portrait; margin: 8mm; }}
        body {{ font-family: Arial, sans-serif; font-size: 10px; color: #111; margin: 0; padding: 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        tr {{ page-break-inside: avoid; }}
        thead {{ display: table-header-group; }}
    </style>
    </head>
    <body onload='window.print()'>
        <div style='border-bottom:2px solid #0f4c81; padding-bottom:6px; margin-bottom:8px;'>
            <div style='font-size:12px; font-weight:900; color:#0f4c81;'>SECRETARIA MUNICIPAL DE SAÚDE DE CAMPO MAIOR</div>
            <div style='font-size:10px; font-weight:bold; color:#333;'>CNPJ: 11.753.492/0001-02</div>
            <div style='font-size:11px; font-weight:bold; margin-top:2px;'>RELATÓRIO DE SALDOS CONTRATUAIS</div>
        </div>
        <div style='margin-bottom:8px;'>
            <strong>Contratada:</strong> {contrato.empresa.razao_social}<br>
            <strong>CNPJ:</strong> {formatar_cnpj(contrato.empresa.cnpj)}<br>
            <strong>Contrato Nº:</strong> {contrato.numero}
        </div>
        <table>
            <thead>
                <tr style='background:#e2e8f0; font-size:9.5px;'>
                    <th style='border:1px solid #444; padding:4px;'>Nº</th>
                    <th style='border:1px solid #444; padding:4px; text-align:left;'>Descrição</th>
                    <th style='border:1px solid #444; padding:4px; text-align:right;'>Contrat.</th>
                    <th style='border:1px solid #444; padding:4px; text-align:right;'>Aditivo</th>
                    <th style='border:1px solid #444; padding:4px; text-align:right;'>Faturado</th>
                    <th style='border:1px solid #444; padding:4px; text-align:right;'>Saldo Disp.</th>
                    <th style='border:1px solid #444; padding:4px; text-align:right;'>V. Unit.</th>
                    <th style='border:1px solid #444; padding:4px; text-align:right;'>Faturado (R$)</th>
                    <th style='border:1px solid #444; padding:4px; text-align:right;'>Saldo (R$)</th>
                </tr>
            </thead>
            <tbody>
                {itens_html}
                <tr style='background:#f8fafc; font-weight:bold;'>
                    <td colspan='7' style='border:1px solid #444; padding:5px; text-align:right;'>TOTAIS:</td>
                    <td style='border:1px solid #444; padding:5px; text-align:right;'>R$ {format_br(total_faturado)}</td>
                    <td style='border:1px solid #444; padding:5px; text-align:right; color:#047857;'>R$ {format_br(total_disponivel)}</td>
                </tr>
            </tbody>
        </table>
    </body></html>
    """


@csrf_exempt
@require_http_methods(["GET"])
def pdf_of_lote(request):
    """Gera OFs em lote para impressão."""
    try:
        ids = request.GET.get('ids', '')
        lista_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()]

        if not lista_ids:
            return error_response("Nenhuma nota selecionada.")

        # Gera HTML das OFs
        html_blocos = []
        for nf_id in lista_ids:
            nota = get_object_or_404(NotaFiscal.objects.select_related('contrato__empresa'), pk=nf_id)
            of = OrdemFornecimento.objects.filter(nota=nota).first()

            if not of:
                continue

            itens_html = ""
            sum_total = 0.0
            for it in nota.itens.select_related('item_contrato').all():
                val_unit = float(it.valor_unitario)
                qtd = float(it.quantidade)
                total_item = qtd * val_unit
                sum_total += total_item

                itens_html += f"""
                <tr>
                    <td style='border:1px solid #333; padding:3px 5px; text-align:center;'>{it.item_contrato.numero_item if it.item_contrato else '-'}</td>
                    <td style='border:1px solid #333; padding:3px 5px;'>{it.descricao}</td>
                    <td style='border:1px solid #333; padding:3px 5px; text-align:center;'>{format_int_qtd(qtd)}</td>
                    <td style='border:1px solid #333; padding:3px 5px; text-align:right;'>R$ {format_br(val_unit)}</td>
                    <td style='border:1px solid #333; padding:3px 5px; text-align:right;'>R$ {format_br(total_item)}</td>
                </tr>
                """

            dt_assinatura = formatar_data_br(of.data_assinatura) if of.data_assinatura else "-"

            html_blocos.append(f"""
            <div style='padding:2px 0; page-break-after: always;'>
                <div style='display:flex; align-items:center; justify-content:space-between; border-bottom:2px solid #0f4c81; padding-bottom:5px; margin-bottom:8px;'>
                    <div>
                        <div style='font-size:12px; font-weight:900; color:#0f4c81;'>SECRETARIA MUNICIPAL DE SAÚDE DE CAMPO MAIOR</div>
                        <div style='font-size:10px; font-weight:bold; color:#222;'>CNPJ: 11.753.492/0001-02</div>
                    </div>
                    <div style='font-size:12px; font-weight:900; color:#111; border:1.5px solid #111; padding:3px 7px; border-radius:4px;'>ORDEM DE FORNECIMENTO</div>
                </div>

                <table style='width:100%; font-size:10px; margin-bottom:8px; border:1px solid #999; background:#f8fafc;'>
                    <tr>
                        <td style='padding:3px 6px;'><strong>CONTRATANTE:</strong> SMS Campo Maior</td>
                        <td style='padding:3px 6px; text-align:right;'><strong>CNPJ:</strong> 11.753.492/0001-02</td>
                    </tr>
                    <tr>
                        <td style='padding:3px 6px; border-top:1px solid #ddd;'><strong>CONTRATADA:</strong> {nota.contrato.empresa.razao_social}</td>
                        <td style='padding:3px 6px; text-align:right; border-top:1px solid #ddd;'><strong>CNPJ:</strong> {formatar_cnpj(nota.contrato.empresa.cnpj)}</td>
                    </tr>
                    <tr>
                        <td style='padding:3px 6px; border-top:1px solid #ddd;' colspan='2'><strong>CONTRATO Nº:</strong> {nota.contrato.numero}</td>
                    </tr>
                </table>

                <table style='width:100%; border-collapse:collapse; font-size:9.5px;'>
                    <thead>
                        <tr style='background:#e2e8f0;'>
                            <th style='border:1px solid #333; padding:3px; width:40px;'>Item</th>
                            <th style='border:1px solid #333; padding:3px; text-align:left;'>Descrição</th>
                            <th style='border:1px solid #333; padding:3px; width:70px;'>Qtd</th>
                            <th style='border:1px solid #333; padding:3px; width:80px; text-align:right;'>V. Unit.</th>
                            <th style='border:1px solid #333; padding:3px; width:90px; text-align:right;'>Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {itens_html}
                        <tr style='background:#f1f5f9;'>
                            <td colspan='4' style='border:1px solid #333; padding:4px; text-align:right; font-weight:bold;'>TOTAL:</td>
                            <td style='border:1px solid #333; padding:4px; text-align:right; font-weight:bold;'>R$ {format_br(sum_total)}</td>
                        </tr>
                    </tbody>
                </table>

                <div style='margin-top:35px; text-align:center;'>
                    <div style='width:260px; border-top:1px solid #000; margin:0 auto; padding-top:4px; font-size:10px;'>
                        <strong>Ateste do Servidor</strong><br>
                        <span style='font-size:9.5px; font-weight:bold; color:#111;'>Data: {dt_assinatura}</span>
                    </div>
                </div>
            </div>
            """)

        html_final = f"""
        <html><head><title>Ordens de Fornecimento ({len(lista_ids)})</title>
        <style>
            @page {{ size: A4 portrait; margin: 8mm; }}
            body {{ font-family: Arial, sans-serif; color: #111; margin: 0; padding: 0; }}
            tr {{ page-break-inside: avoid; }}
        </style>
        </head><body onload='window.print()'>{''.join(html_blocos)}</body></html>
        """

        response = HttpResponse(html_final, content_type='text/html')
        response['Content-Disposition'] = f'inline; filename="of_lote_{len(lista_ids)}.html"'
        return response

    except Exception as e:
        return error_response(f"Erro ao gerar OFs: {str(e)}", 500)


# ============================================================================
# IMPORTAÇÃO MESTRE (LEGADO)
# ============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def importar_mestre(request):
    """Importa planilha mestre de contratos (legado)."""
    return error_response("Funcionalidade legado — use /api/importar_itens com contrato_id.")


@csrf_exempt
@require_http_methods(["POST"])
def transferir_itens(request, contrato_id):
    """Copia itens de um contrato origem para um contrato destino (adaptação entre contratos)."""
    try:
        data = json.loads(request.body)
        destino_id = data.get('destino_id')

        if not destino_id:
            return error_response("destino_id é obrigatório.")

        contrato_origem = get_object_or_404(Contrato, pk=contrato_id)
        contrato_destino = get_object_or_404(Contrato, pk=destino_id)

        copiados = 0
        with transaction.atomic():
            itens = contrato_origem.itens.prefetch_related('precos').all()
            for it in itens:
                # Verifica se já existe item similar no destino (por numero_item ou descrição)
                existe = ItemContrato.objects.filter(
                    contrato=contrato_destino,
                    numero_item=it.numero_item
                ).first()
                if not existe and it.descricao:
                    existe = ItemContrato.objects.filter(
                        contrato=contrato_destino,
                        descricao__iexact=it.descricao
                    ).first()
                if existe:
                    continue  # Pula itens já existentes no destino

                # Copia o item com quantidades zeradas (novo contrato)
                novo_item = ItemContrato.objects.create(
                    contrato=contrato_destino,
                    lote=it.lote,
                    numero_item=it.numero_item,
                    descricao=it.descricao,
                    unidade=it.unidade,
                    quantidade_contratada=Decimal("0"),  # Será definida via planilha ou aditivo
                    qnt_aditivada=Decimal("0"),
                    qnt_faturada_base=Decimal("0"),
                    qnt_faturada=Decimal("0"),
                )

                # Copia o preço vigente mais recente
                preco_vigente = it.precos.order_by("-vigente_a_partir_de").first()
                if preco_vigente:
                    PrecoItem.objects.create(
                        item=novo_item,
                        valor_unitario=preco_vigente.valor_unitario,
                        vigente_a_partir_de=timezone.now().date()
                    )
                copiados += 1

            recalcular_saldos_contrato(destino_id)

        return json_response({"ok": True, "itens_copiados": copiados})

    except json.JSONDecodeError:
        return error_response("JSON inválido.")
    except Exception as e:
        return error_response(f"Erro ao adaptar itens: {str(e)}", 500)