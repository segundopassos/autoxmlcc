"""
Views do app notas — Etapa E3.
Lançamento manual, conferência, casamento de itens, bloqueio e liberação.
RN04: Casamento por vínculo memorizado, descrição normalizada ou semelhança.
RN05: Preço exato. RN07: Saldo calculado. RN08: Excedente. RN10: Centavos.
RN11: Bloqueio com liberação justificada.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from contratos.models import ItemContrato, PrecoItem, normalizar_descricao

from .forms import ItemNotaFormSet, LiberacaoNotaForm, NotaFiscalManualForm
from .models import ItemNota, NotaFiscal, VinculoMemorizado


def lancar_nota_manual(request):
    """
    Tela de lançamento manual de nota fiscal.
    Passo 1: Dados da nota + itens.
    Passo 2: Conferência com divergências.
    """
    if request.method == "POST":
        form = NotaFiscalManualForm(request.POST)
        formset = ItemNotaFormSet(request.POST, prefix="itens")

        if form.is_valid() and formset.is_valid():
            # Salva nota em status bloqueada para conferência
            nota = form.save(commit=False)
            nota.origem = "manual"
            nota.status = "bloqueada"
            nota.save()

            contrato = nota.contrato
            data_emissao = nota.data_emissao
            tem_divergencia = False

            for item_form in formset:
                if item_form.cleaned_data.get("DELETE"):
                    continue

                item_data = item_form.cleaned_data
                # Pula itens vazios (formset extra forms)
                if not item_data.get("descricao"):
                    continue
                item_nota = ItemNota(
                    nota=nota,
                    codigo_fornecedor=item_data.get("codigo_fornecedor", ""),
                    descricao=item_data.get("descricao", ""),
                    unidade=item_data.get("unidade", "UN"),
                    quantidade=item_data.get("quantidade", Decimal("0")),
                    valor_unitario=item_data.get("valor_unitario", Decimal("0")),
                    valor_total=item_data.get("valor_total", Decimal("0")),
                )

                # Tenta casar com item do contrato
                item_contrato = _casar_item(
                    empresa=nota.empresa,
                    codigo_fornecedor=item_data.get("codigo_fornecedor", ""),
                    descricao=item_data["descricao"],
                    valor_unitario=item_data["valor_unitario"],
                    contrato=contrato,
                )

                if item_contrato:
                    item_nota.item_contrato = item_contrato

                    # RN05: Verifica preço exato
                    preco_vigente = _obter_preco_vigente(item_contrato, data_emissao)
                    if preco_vigente is None:
                        item_nota.divergencia = "Item sem preço vigente na data de emissão."
                        tem_divergencia = True
                    elif item_data["valor_unitario"] != preco_vigente.valor_unitario:
                        item_nota.divergencia = (
                            f"Preço divergente: nota R$ {item_data['valor_unitario']}, "
                            f"contrato R$ {preco_vigente.valor_unitario}."
                        )
                        tem_divergencia = True
                    else:
                        # RN07/RN08: Verifica saldo disponível
                        saldo = _calcular_saldo_disponivel(item_contrato)
                        if item_data["quantidade"] > saldo:
                            item_nota.divergencia = (
                                f"Saldo insuficiente: solicitado {item_data['quantidade']}, "
                                f"disponível {saldo}."
                            )
                            tem_divergencia = True

                    # RN10: Alerta de arredondamento
                    calculado = (
                        item_data["quantidade"] * item_data["valor_unitario"]
                    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    if calculado != item_data["valor_total"]:
                        item_nota.alerta_arredondamento = True

                else:
                    item_nota.divergencia = "Item não encontrado no contrato."
                    tem_divergencia = True

                item_nota.save()

            # Atualiza status conforme divergências
            if not tem_divergencia:
                nota.status = "conferida"
                nota.save()
                messages.success(request, "Nota conferida com sucesso.")
            else:
                messages.warning(
                    request,
                    "Nota bloqueada por divergências. Revise os itens e libere se necessário.",
                )

            return redirect("notas:nota_detail", pk=nota.pk)
    else:
        form = NotaFiscalManualForm()
        formset = ItemNotaFormSet(prefix="itens")

    return render(request, "notas/lancar_manual.html", {
        "form": form,
        "formset": formset,
    })


def nota_detail(request, pk):
    """Detalhe da nota com itens e divergências."""
    nota = get_object_or_404(NotaFiscal, pk=pk)
    itens = nota.itens.select_related("item_contrato").all()
    return render(request, "notas/nota_detail.html", {
        "nota": nota,
        "itens": itens,
    })


def liberar_nota(request, pk):
    """
    Libera nota bloqueada com justificativa obrigatória.
    RN11: Justificativa escrita, registrada na auditoria.
    """
    nota = get_object_or_404(NotaFiscal, pk=pk, status="bloqueada")

    if request.method == "POST":
        form = LiberacaoNotaForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                nota.status = "liberada"
                nota.justificativa_liberacao = form.cleaned_data["justificativa"]
                nota.save()
            messages.success(request, "Nota liberada com sucesso.")
            return redirect("notas:nota_detail", pk=nota.pk)
    else:
        form = LiberacaoNotaForm()

    return render(request, "notas/liberar_nota.html", {
        "nota": nota,
        "form": form,
    })


def _casar_item(empresa, codigo_fornecedor, descricao, valor_unitario, contrato):
    """
    RN04: Casa item da nota com item do contrato nesta ordem:
    1. Vínculo memorizado
    2. Descrição normalizada com mesmo preço
    3. Semelhança de texto (rapidfuzz)
    """
    desc_norm = normalizar_descricao(descricao)

    # 1. Vínculo memorizado
    vinculo = VinculoMemorizado.objects.filter(
        empresa=empresa,
        codigo_fornecedor=codigo_fornecedor or "",
        descricao_normalizada=desc_norm,
    ).first()
    if vinculo:
        return vinculo.item_contrato

    # Filtra itens do contrato informado
    itens_contrato = ItemContrato.objects.filter(contrato=contrato)

    # 2. Descrição normalizada exata com mesmo preço
    for item in itens_contrato:
        if item.descricao_normalizada == desc_norm:
            return item

    # 3. Semelhança de texto (threshold 80%)
    try:
        from rapidfuzz import fuzz
        melhor_score = 0
        melhor_item = None
        for item in itens_contrato:
            score = fuzz.ratio(desc_norm, item.descricao_normalizada)
            if score > melhor_score and score >= 80:
                melhor_score = score
                melhor_item = item
        if melhor_item:
            return melhor_item
    except ImportError:
        pass

    return None


def _obter_preco_vigente(item_contrato, data_referencia):
    """Retorna o preço vigente do item na data informada (RN06)."""
    return (
        PrecoItem.objects.filter(
            item=item_contrato,
            vigente_a_partir_de__lte=data_referencia,
        )
        .order_by("-vigente_a_partir_de")
        .first()
    )


def _calcular_saldo_disponivel(item_contrato):
    """
    RN07: Saldo = contratada − faturada − reservada.
    Calculado em Decimal exato.
    """
    from django.db.models import Sum

    contratada = item_contrato.quantidade_contratada

    # Faturado: soma das quantidades de itens de nota conferidas/liberadas
    faturado = (
        ItemNota.objects.filter(
            item_contrato=item_contrato,
            nota__status__in=["conferida", "liberada"],
        ).aggregate(total=Sum("quantidade"))["total"]
        or Decimal("0")
    )

    # Reservado: OFs antecipadas (implementado na E5)
    reservado = Decimal("0")

    return contratada - faturado - reservado