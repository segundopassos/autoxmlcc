"""
Views do app ordens — Etapa E5.
Aditivos, OF antecipada (reserva), exclusão e edição de nota.
RN06: Reajuste. RN12: Aditivo. RN13: Reserva. RN14: Exclusão/edição.
RN15: Numeração OF. RN16: Data OF primeiro dia útil.
"""
from decimal import Decimal
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from contratos.models import ItemContrato, PrecoItem
from notas.models import ItemNota, NotaFiscal
from .forms import (
    AditivoForm,
    ExcluirNotaForm,
    ItemAditivoFormSet,
    OrdemFornecimentoForm,
)
from .models import Aditivo, ItemAditivo, OrdemFornecimento
from .utils import primeiro_dia_util


def criar_aditivo(request):
    """
    Tela para lançamento de aditivo contratual.
    RN12: Aditivo de quantidade ou valor.
    RN06: Preço de aditivo vale para notas a partir da data de assinatura.
    """
    if request.method == "POST":
        form = AditivoForm(request.POST, request.FILES)
        formset = ItemAditivoFormSet(request.POST, prefix="itens_aditivo")

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                aditivo = form.save()

                for item_form in formset:
                    if item_form.cleaned_data.get("DELETE"):
                        continue
                    dados = item_form.cleaned_data
                    if not dados.get("item_contrato_id"):
                        continue

                    item_contrato = get_object_or_404(
                        ItemContrato, pk=dados["item_contrato_id"]
                    )

                    ItemAditivo.objects.create(
                        aditivo=aditivo,
                        item_contrato=item_contrato,
                        quantidade_aditivada=dados.get("quantidade_aditivada")
                        or Decimal("0"),
                        novo_valor_unitario=dados.get("novo_valor_unitario"),
                    )

                    # RN06: Se aditivo de valor, cria novo preço vigente
                    if (
                        aditivo.tipo == "valor"
                        and dados.get("novo_valor_unitario") is not None
                    ):
                        PrecoItem.objects.create(
                            item=item_contrato,
                            valor_unitario=dados["novo_valor_unitario"],
                            vigente_a_partir_de=aditivo.data_assinatura,
                        )

            messages.success(request, "Aditivo criado com sucesso.")
            return redirect("contratos:contrato_detail", pk=aditivo.contrato.pk)
    else:
        form = AditivoForm()
        formset = ItemAditivoFormSet(prefix="itens_aditivo")

    return render(
        request,
        "ordens/criar_aditivo.html",
        {"form": form, "formset": formset},
    )


def criar_of_reserva(request, contrato_pk):
    """
    Cria OF antecipada (reserva de saldo) sem nota fiscal vinculada.
    RN13: OF antes da nota reserva saldo até a nota real chegar.
    """
    from contratos.models import Contrato

    contrato = get_object_or_404(Contrato, pk=contrato_pk)

    if request.method == "POST":
        # Cria nota provisória para vincular à OF
        with transaction.atomic():
            nota_provisoria = NotaFiscal.objects.create(
                empresa=contrato.empresa,
                contrato=contrato,
                numero=f"RESERVA-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                data_emissao=timezone.now().date(),
                valor_total=Decimal("0"),
                origem="provisoria",
                status="conferida",
            )

            of = OrdemFornecimento.objects.create(
                nota=nota_provisoria,
                ano=timezone.now().year,
                data_assinatura=primeiro_dia_util(
                    timezone.now().year, timezone.now().month
                ),
                status="rascunho",
            )

        messages.success(
            request,
            "OF de reserva criada. Adicione itens para reservar saldo.",
        )
        return redirect("ordens:of_detail", pk=of.pk)

    return render(
        request,
        "ordens/criar_of_reserva.html",
        {"contrato": contrato},
    )


def excluir_nota(request, pk):
    """
    Exclui nota fiscal e devolve saldo.
    RN14: Excluir devolve saldo e exclui OF vinculada.
    """
    nota = get_object_or_404(NotaFiscal, pk=pk)

    if request.method == "POST":
        form = ExcluirNotaForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Exclui OF vinculada se existir
                OrdemFornecimento.objects.filter(nota=nota).delete()
                # Exclui a nota (itens são deletados em cascata)
                nota.delete()

            messages.success(request, "Nota excluída e saldo devolvido.")
            return redirect("contratos:painel")
    else:
        form = ExcluirNotaForm()

    return render(
        request,
        "ordens/excluir_nota.html",
        {"nota": nota, "form": form},
    )


def of_detail(request, pk):
    """Detalhe da ordem de fornecimento."""
    of = get_object_or_404(
        OrdemFornecimento.objects.select_related("nota", "nota__contrato"),
        pk=pk,
    )
    itens = of.nota.itens.select_related("item_contrato").all()

    return render(
        request,
        "ordens/of_detail.html",
        {"of": of, "itens": itens},
    )