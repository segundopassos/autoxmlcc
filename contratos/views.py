"""
Views do app contratos — Etapa E1.
Painel de contratos, CRUD de empresas e contratos.
CA20: Paginação para suportar 1.000+ contratos com desempenho.
"""
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Sum, DecimalField
from django.db.models.functions import Coalesce
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone

from .models import Empresa, Contrato, ItemContrato, PrecoItem
from .forms import EmpresaForm, ContratoForm


def painel_contratos(request):
    """
    Painel principal com cartões de contratos.
    Abas: Geral, Ativos, A vencer em 30 dias, Vencidos.
    Busca por empresa, nº do contrato, CNPJ ou item.
    """
    hoje = timezone.now().date()
    limite_vencer = hoje + timedelta(days=30)

    # Filtro por aba
    aba = request.GET.get("aba", "geral")
    queryset = Contrato.objects.select_related("empresa").all()

    if aba == "ativos":
        queryset = queryset.filter(
            inicio_vigencia__lte=hoje,
            fim_vigencia__gte=hoje,
        )
    elif aba == "a_vencer":
        queryset = queryset.filter(
            fim_vigencia__gt=hoje,
            fim_vigencia__lte=limite_vencer,
        )
    elif aba == "vencidos":
        queryset = queryset.filter(fim_vigencia__lt=hoje)

    # Busca
    busca = request.GET.get("q", "").strip()
    if busca:
        queryset = queryset.filter(
            Q(numero__icontains=busca)
            | Q(empresa__razao_social__icontains=busca)
            | Q(empresa__cnpj__icontains=busca)
            | Q(itens__descricao__icontains=busca)
        ).distinct()

    # Filtro por ano do contrato
    ano = request.GET.get("ano", "").strip()
    if ano:
        queryset = queryset.filter(numero__endswith=f"/{ano}")

    # Contagens para as abas
    contagens = {
        "geral": Contrato.objects.count(),
        "ativos": Contrato.objects.filter(
            inicio_vigencia__lte=hoje, fim_vigencia__gte=hoje
        ).count(),
        "a_vencer": Contrato.objects.filter(
            fim_vigencia__gt=hoje, fim_vigencia__lte=limite_vencer
        ).count(),
        "vencidos": Contrato.objects.filter(fim_vigencia__lt=hoje).count(),
    }

    # Lista de abas para o template (contagens embutidas para evitar acesso dinâmico a dict no DTL)
    abas = [
        {"key": "geral", "label": "Geral", "count": contagens["geral"]},
        {"key": "ativos", "label": "Ativos", "count": contagens["ativos"]},
        {"key": "a_vencer", "label": "A vencer em 30 dias", "count": contagens["a_vencer"]},
        {"key": "vencidos", "label": "Vencidos", "count": contagens["vencidos"]},
    ]

    # CA20: Paginação para suportar 1.000+ contratos com desempenho < 2s
    paginator = Paginator(queryset, 50)  # 50 contratos por página
    page_number = request.GET.get("page")
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "contratos": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "aba": aba,
        "busca": busca,
        "ano": ano,
        "contagens": contagens,
        "abas": abas,
    }
    return render(request, "contratos/painel.html", context)


def empresa_list(request):
    """Lista de empresas cadastradas."""
    empresas = Empresa.objects.all()
    busca = request.GET.get("q", "").strip()
    if busca:
        empresas = empresas.filter(
            Q(razao_social__icontains=busca) | Q(cnpj__icontains=busca)
        )
    return render(request, "contratos/empresa_list.html", {
        "empresas": empresas,
        "busca": busca,
    })


def empresa_create(request):
    """Cadastro de nova empresa."""
    if request.method == "POST":
        form = EmpresaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Empresa cadastrada com sucesso.")
            return redirect("contratos:empresa_list")
    else:
        form = EmpresaForm()
    return render(request, "contratos/empresa_form.html", {"form": form})


def empresa_update(request, pk):
    """Edição de empresa existente."""
    empresa = get_object_or_404(Empresa, pk=pk)
    if request.method == "POST":
        form = EmpresaForm(request.POST, instance=empresa)
        if form.is_valid():
            form.save()
            messages.success(request, "Empresa atualizada com sucesso.")
            return redirect("contratos:empresa_list")
    else:
        form = EmpresaForm(instance=empresa)
    return render(request, "contratos/empresa_form.html", {
        "form": form,
        "empresa": empresa,
    })


def contrato_create(request):
    """Cadastro de novo contrato."""
    if request.method == "POST":
        form = ContratoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Contrato cadastrado com sucesso.")
            return redirect("contratos:painel")
    else:
        form = ContratoForm()
    return render(request, "contratos/contrato_form.html", {"form": form})


def contrato_detail(request, pk):
    """
    Tela do contrato com abas Itens, Notas e OF, Aditivos.
    Mostra totais e tabela de itens.
    """
    from notas.models import NotaFiscal

    contrato = get_object_or_404(
        Contrato.objects.select_related("empresa"), pk=pk
    )
    itens = contrato.itens.prefetch_related("precos").order_by("numero_item")
    notas = NotaFiscal.objects.filter(contrato=contrato).order_by("-data_emissao")

    # Aba ativa via query param
    aba = request.GET.get("aba", "itens")

    context = {
        "contrato": contrato,
        "itens": itens,
        "notas": notas,
        "aba": aba,
    }
    return render(request, "contratos/contrato_detail.html", context)


def contrato_update(request, pk):
    """Edição de contrato existente."""
    contrato = get_object_or_404(Contrato, pk=pk)
    if request.method == "POST":
        form = ContratoForm(request.POST, instance=contrato)
        if form.is_valid():
            form.save()
            messages.success(request, "Contrato atualizado com sucesso.")
            return redirect("contratos:contrato_detail", pk=contrato.pk)
    else:
        form = ContratoForm(instance=contrato)
    return render(request, "contratos/contrato_form.html", {
        "form": form,
        "contrato": contrato,
    })