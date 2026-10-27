"""
Parser de PDF para notas fiscais (DANFE) — Etapa E4.
Extrai chave de acesso, emitente, data, itens e totais de PDFs de NF-e/NFS-e.
CA01 a CA04: L DANFE com vrias folhas e pginas extras.
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Any
import pdfplumber


def extrair_texto_pdf(filepath: str) -> str:
    """Extrai todo o texto de um PDF, pgina por pgina."""
    with pdfplumber.open(filepath) as pdf:
        textos = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                textos.append(text)
        return "\n".join(textos)


def extrair_chave_acesso(texto: str) -> str | None:
    """
    Extrai chave de acesso da NF-e (44 dgitos).
    Padres comuns: 'Chave de Acesso', 'CHAVE DE ACESSO DA NF-E', ou 44 dgitos sequenciais.
    """
    # Procura padro explcito
    padroes = [
        r"[Cc]have\s+de\s+[Aa]cesso[:\s]*([0-9]{44})",
        r"CHAVE\s+DE\s+ACESSO[^0-9]*([0-9]{44})",
        r"([0-9]{44})",  # 44 dgitos consecutivos
    ]
    for padrao in padroes:
        match = re.search(padrao, texto)
        if match:
            return match.group(1)
    return None


def extrair_cnpj_emitente(texto: str) -> str | None:
    """
    Extrai CNPJ do emitente da nota.
    Geralmente aparece como 'CNPJ/CPF' perto do cabealho.
    """
    padroes = [
        r"CNPJ[:\s]*([0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2})",
        r"CNPJ[:\s]*([0-9]{14})",
        r"CNPJ/CPF[:\s]*([0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2})",
    ]
    for padrao in padroes:
        match = re.search(padrao, texto)
        if match:
            return match.group(1)
    return None


def extrair_numero_serie(texto: str) -> tuple[str | None, str | None]:
    """
    Extrai nmero e srie da nota fiscal.
    Padres: 'Nm.', 'Nmero', 'Srie'.
    """
    numero = None
    serie = None

    # Nmero da nota
    match_num = re.search(r"N[úu]m(?:ero)?\.?[\s:]*([0-9]{1,9})", texto, re.IGNORECASE)
    if not match_num:
        match_num = re.search(r"N[mº]\.?[\s:]*([0-9]{1,9})", texto)
    if match_num:
        numero = match_num.group(1)

    # Srie
    match_ser = re.search(r"S[eé]rie[\s:]*([0-9]{1,3})", texto, re.IGNORECASE)
    if match_ser:
        serie = match_ser.group(1)

    return numero, serie


def extrair_data_emissao(texto: str) -> str | None:
    """
    Extrai data de emisso. Formatos: dd/mm/aaaa, dd-mm-aaaa.
    """
    padroes = [
        r"[Dd]ata\s+[Ee]miss.{0,3}o?[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})",
        r"[Dd]ata\s+[Ee]miss.{0,3}o?[:\s]*([0-9]{2}-[0-9]{2}-[0-9]{4})",
        r"([0-9]{2}/[0-9]{2}/[0-9]{4})",
    ]
    for padrao in padroes:
        match = re.search(padrao, texto)
        if match:
            data_str = match.group(1)
            # Converte dd/mm/aaaa ou dd-mm-aaaa para aaaa-mm-dd
            if "/" in data_str:
                partes = data_str.split("/")
                return f"{partes[2]}-{partes[1]}-{partes[0]}"
            elif "-" in data_str:
                partes = data_str.split("-")
                if len(partes) == 3 and len(partes[2]) == 4:
                    return f"{partes[2]}-{partes[1]}-{partes[0]}"
            return data_str
    return None


def extrair_valor_total(texto: str) -> Decimal | None:
    """
    Extrai valor total da nota.
    Padres: 'Valor Total', 'VALOR TOTAL DA NOTA', 'R$ X.XXX,XX'.
    """
    # Procura valor total explcito
    padroes = [
        r"[Vv]alor\s+[Tt]otal[^0-9]*R?\$?\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})",
        r"VALOR\s+TOTAL\s+DA\s+NOTA[:\s]*R?\$?\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})",
        r"VALOR\s+L[IÍ]QUIDO[:\s]*R?\$?\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})",
    ]
    for padrao in padroes:
        match = re.search(padrao, texto)
        if match:
            valor_str = match.group(1)
            return parse_valor_br(valor_str)
    return None


def parse_valor_br(valor_str: str) -> Decimal | None:
    """Converte string de valor brasileiro (1.234,56) para Decimal."""
    if not valor_str:
        return None
    texto = valor_str.strip()
    # Remove R$, espaos
    texto = re.sub(r"[R$\s]", "", texto)
    # Formato brasileiro: remove separador de milhar, troca vrgula por ponto
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def extrair_itens_danfe(filepath: str) -> list[dict]:
    """
    Extrai itens da DANFE de um PDF.
    Retorna lista de dicts com: codigo, descricao, unidade, quantidade, valor_unitario, valor_total.
    CA01-CA04: Lida com mltiplas folhas e layouts variados.
    """
    itens = []

    with pdfplumber.open(filepath) as pdf:
        for page_num, page in enumerate(pdf.pages):
            # Tenta extrair tabelas
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    itens_page = _processar_tabela(table, page_num)
                    if itens_page:
                        itens.extend(itens_page)

            # Se no encontrou em tabelas, tenta extrair por regex do texto
            if not itens:
                text = page.extract_text()
                if text:
                    itens_texto = _extrair_itens_por_regex(text)
                    if itens_texto:
                        itens.extend(itens_texto)

    return itens


def _processar_tabela(table: list[list], page_num: int) -> list[dict]:
    """
    Processa uma tabela extrada do PDF tentando identificar colunas de itens.
    """
    itens = []
    if not table or len(table) < 2:
        return []

    # Identifica cabealho
    cabecalho = table[0]
    colunas_mapeadas = _mapear_colunas(cabecalho)

    if not colunas_mapeadas:
        return []

    # Processa linhas de dados
    for row in table[1:]:
        if not row or len(row) < len(colunas_mapeadas):
            continue

        item = {}
        for papel, col_idx in colunas_mapeadas.items():
            if col_idx < len(row) and row[col_idx]:
                valor = str(row[col_idx]).strip()
                if papel == "quantidade":
                    item[papel] = parse_valor_br(valor)
                elif papel in ("valor_unitario", "valor_total"):
                    item[papel] = parse_valor_br(valor)
                else:
                    item[papel] = valor

        if item.get("descricao"):
            itens.append(item)

    return itens


def _mapear_colunas(cabecalho: list) -> dict[str, int]:
    """
    Mapeia colunas do cabealho da tabela para papis conhecidos.
    """
    padroes = {
        "codigo": [r"c[oó]digo", r"c[oó]d\.", r"^cod"],
        "descricao": [r"descri[cç][aã]o", r"objeto", r"produto", r"servi[cç]o"],
        "unidade": [r"und", r"unidade", r"u\.?m\."],
        "quantidade": [r"qnt?", r"quantidade", r"qtde?"],
        "valor_unitario": [r"vlr?\s*unt", r"pre[cç]o\s*unit", r"valor\s*unit"],
        "valor_total": [r"valor\s*total", r"vt", r"total"],
    }

    mapeamento = {}
    for col_idx, texto in enumerate(cabecalho):
        if not texto:
            continue
        texto_lower = str(texto).lower().strip()

        for papel, regexes in padroes.items():
            for regex in regexes:
                if re.search(regex, texto_lower):
                    mapeamento[papel] = col_idx
                    break
            if papel in mapeamento:
                break

    # Precisa pelo menos descrio
    if "descricao" not in mapeamento:
        return {}

    return mapeamento


def _extrair_itens_por_regex(texto: str) -> list[dict]:
    """
    Extrai itens por regex quando no h tabelas estruturadas.
    Fallback para layouts complexos.
    """
    itens = []
    # Padro genrico: cdigo + descrio + unidade + qtd + vl_unit + vl_total
    # Este  um fallback; parsers especficos por layout so preferveis
    padrao_item = r"(\d+)\s+(.+?)\s+(UN|KG|LT|CX|PC)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)"

    for match in re.finditer(padrao_item, texto, re.DOTALL):
        itens.append({
            "codigo": match.group(1),
            "descricao": match.group(2).strip(),
            "unidade": match.group(3),
            "quantidade": parse_valor_br(match.group(4)),
            "valor_unitario": parse_valor_br(match.group(5)),
            "valor_total": parse_valor_br(match.group(6)),
        })

    return itens


def ler_pdf_nota(filepath: str) -> dict[str, Any]:
    """
    Funo principal: l um PDF de nota fiscal e retorna todos os dados extrados.
    Retorna dict com: chave_acesso, cnpj_emitente, numero, serie, data_emissao,
    valor_total, itens (lista).
    """
    texto = extrair_texto_pdf(filepath)

    resultado = {
        "texto_completo": texto,
        "chave_acesso": extrair_chave_acesso(texto),
        "cnpj_emitente": extrair_cnpj_emitente(texto),
        "data_emissao": extrair_data_emissao(texto),
        "valor_total": extrair_valor_total(texto),
        "itens": extrair_itens_danfe(filepath),
    }

    numero, serie = extrair_numero_serie(texto)
    resultado["numero"] = numero
    resultado["serie"] = serie

    return resultado