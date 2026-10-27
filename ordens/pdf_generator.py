"""
Gerador de PDF para Ordens de Fornecimento — Etapa E6.
xhtml2pdf (puro Python) para compatibilidade com Windows sem GTK.
CA18: Cabeçalho repetido em cada página, descrições não cortadas, total igual ao da nota.
RN15: Numeração automática sequencial por ano a partir de 2027.
"""
import io
from decimal import Decimal

from django.template.loader import render_to_string
from xhtml2pdf import pisa


def gerar_pdf_of(of) -> bytes:
    """
    Gera o PDF da Ordem de Fornecimento e retorna como bytes.
    CA18: Layout A4 com cabeçalho de tabela repetido e total igual ao da nota.
    """
    itens = of.nota.itens.select_related("item_contrato").all()
    contratante = _obter_contratante()

    contexto = {
        "of": of,
        "nota": of.nota,
        "contrato": of.nota.contrato,
        "empresa": of.nota.empresa,
        "itens": itens,
        "contratante": contratante,
        "total_geral": of.nota.valor_total,
    }

    html_content = render_to_string("ordens/of_template.html", contexto)
    buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(html_content, dest=buffer, encoding="utf-8")
    if pisa_status.err:
        raise RuntimeError(
            f"Erro ao gerar PDF da OF {of.pk}: {pisa_status.err}"
        )
    return buffer.getvalue()


def _obter_contratante():
    """Retorna o contratante singleton (Fundo Municipal de Saúde)."""
    from contratos.models import Contratante
    return Contratante.objects.first()


def numerar_of(ano: int) -> str:
    """
    RN15: Gera número sequencial para OF do ano informado.
    Em 2026 retorna string vazia (sem numeração).
    A partir de 2027, retorna '001', '002', etc.
    CA17: Primeira de 2027 é 001/2027; primeira de 2028 é 001/2028.
    """
    if ano < 2027:
        return ""

    from .models import OrdemFornecimento
    ultima = (
        OrdemFornecimento.objects.filter(ano=ano)
        .exclude(numero="")
        .order_by("-numero")
        .first()
    )

    if ultima is None:
        return "001"

    try:
        proximo = int(ultima.numero) + 1
        return f"{proximo:03d}"
    except (ValueError, TypeError):
        return "001"