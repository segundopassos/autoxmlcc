"""
Parsers de planilhas Excel para importação de contratos — Etapa E2.
RN19: Valores digitados são respeitados como estão.
CA12/CA13: Lê totais digitados à mão e valores em texto.
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import openpyxl


def detectar_cabecalho(ws) -> tuple[int, dict[str, str]]:
    """
    Detecta a linha de cabeçalho e mapeia colunas por palavras-chave.
    Retorna (linha_cabecalho, mapeamento).
    """
    # Palavras-chave para cada papel de coluna
    padroes = {
        "item": [r"\bitem\b", r"\bn[ºo]?\s*item"],
        "descricao": [r"descri[cç][aã]o", r"\bobjeto\b", r"\bespecifica"],
        "unidade": [r"\bund\b", r"unidade", r"\bmedida\b"],
        "valor_unitario": [
            r"vlr?\s*unt",
            r"valor\s*unit",
            r"pre[cç]o\s*unit",
            r"^valor$",  # Cabeçalho simples "VALOR"
        ],
        "quantidade_contratada": [
            r"qnt?\s*licitad",
            r"quantidade\s*contrat",
            r"\bqtd\b",
            r"^quantidade$",  # Cabeçalho simples "QUANTIDADE"
        ],
        "marca": [r"\bmarca\b"],
        "lote": [r"\blote\b"],
    }

    # Busca nas primeiras 20 linhas
    for row_idx in range(1, min(21, ws.max_row + 1)):
        row_values = []
        for cell in ws[row_idx]:
            val = cell.value
            if val is not None:
                row_values.append((cell.column_letter, str(val).strip()))

        if not row_values:
            continue

        # Tenta casar pelo menos 3 colunas
        mapeamento = {}
        for papel, regexes in padroes.items():
            for col_letter, texto in row_values:
                for regex in regexes:
                    if re.search(regex, texto, re.IGNORECASE):
                        mapeamento[papel] = col_letter
                        break
                if papel in mapeamento:
                    break

        if len(mapeamento) >= 3 and "descricao" in mapeamento:
            return row_idx, mapeamento

    return 0, {}


def detectar_colunas_notas(ws, linha_cabecalho: int) -> list[dict]:
    """
    Detecta colunas de notas fiscais históricas no cabeçalho.
    Retorna lista de {'coluna': 'N', 'numero_nfe': '266', 'data': ...}.
    """
    notas = []
    header_row = ws[linha_cabecalho]
    for cell in header_row:
        val = cell.value
        if val is None:
            continue
        texto = str(val).strip()
        match = re.search(r"NFE?\s*(\d+)", texto, re.IGNORECASE)
        if match:
            notas.append({
                "coluna": cell.column_letter,
                "numero_nfe": match.group(1),
                "cabecalho": texto,
            })
    return notas


def parse_valor(valor: Any) -> Decimal | None:
    """
    Converte valor da célula para Decimal.
    Trata números, strings com formatação brasileira e texto puro.
    CA13: Lê valores gravados como texto ("R$16.752,00").
    """
    if valor is None:
        return None

    if isinstance(valor, (int, float)):
        return Decimal(str(valor))

    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None
        # Remove R$, espaços e caracteres extras
        texto = re.sub(r"[R$\s]", "", texto)
        # Formato brasileiro: 1.234,56 -> 1234.56
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            return Decimal(texto)
        except InvalidOperation:
            return None

    return None


def extrair_itens_planilha(
    filepath: str,
    mapeamento: dict[str, str],
    linha_inicio: int,
) -> tuple[list[dict], list[str]]:
    """
    Extrai itens da planilha usando o mapeamento de colunas.
    Retorna (lista_de_itens, lista_de_avisos).
    RN19: Totais digitados são respeitados.
    """
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active

    itens = []
    avisos = []

    col_item = mapeamento.get("item")
    col_descricao = mapeamento.get("descricao")
    col_unidade = mapeamento.get("unidade")
    col_valor = mapeamento.get("valor_unitario")
    col_qtd = mapeamento.get("quantidade_contratada")
    col_lote = mapeamento.get("lote")
    col_marca = mapeamento.get("marca")

    for row_idx in range(linha_inicio, ws.max_row + 1):
        row = ws[row_idx]

        def get_cell(col_letter):
            if not col_letter:
                return None
            idx = ord(col_letter.upper()) - ord("A")
            if idx < len(row):
                return row[idx].value
            return None

        descricao = get_cell(col_descricao)
        if not descricao or str(descricao).strip() == "":
            continue

        item_data = {
            "linha": row_idx,
            "numero_item": get_cell(col_item),
            "descricao": str(descricao).strip(),
            "unidade": str(get_cell(col_unidade) or "UN").strip(),
            "valor_unitario": parse_valor(get_cell(col_valor)),
            "quantidade_contratada": parse_valor(get_cell(col_qtd)),
            "lote": str(get_cell(col_lote) or "").strip(),
            "marca": str(get_cell(col_marca) or "").strip(),
        }

        # Aviso se quantidade ou valor não puderam ser lidos
        if item_data["quantidade_contratada"] is None:
            avisos.append(
                f"Linha {row_idx}: quantidade não lida para '{item_data['descricao'][:40]}'"
            )
        if item_data["valor_unitario"] is None:
            avisos.append(
                f"Linha {row_idx}: valor unitário não lido para '{item_data['descricao'][:40]}'"
            )

        itens.append(item_data)

    wb.close()
    return itens, avisos


def extrair_notas_historicas(
    filepath: str,
    colunas_notas: list[dict],
    linha_inicio: int,
    itens_linhas: list[int],
) -> list[dict]:
    """
    Extrai notas fiscais históricas das colunas detectadas.
    Retorna lista de {'numero_nfe': ..., 'itens': [{'linha': ..., 'valor': ...}]}.
    """
    if not colunas_notas:
        return []

    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active

    notas = []
    for nota_info in colunas_notas:
        col = nota_info["coluna"]
        numero = nota_info["numero_nfe"]
        itens_nota = []

        for row_idx in itens_linhas:
            idx = ord(col.upper()) - ord("A")
            row = ws[row_idx]
            if idx < len(row):
                valor = parse_valor(row[idx].value)
                if valor is not None and valor > 0:
                    itens_nota.append({"linha": row_idx, "valor": valor})

        if itens_nota:
            notas.append({
                "numero_nfe": numero,
                "itens": itens_nota,
            })

    wb.close()
    return notas