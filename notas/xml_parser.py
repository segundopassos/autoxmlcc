"""
Parser de XML para notas fiscais eletrônicas (NF-e / NFC-e) — Etapa E2.
Extrai chave de acesso, emitente, data, itens e totais do XML padrão SEFAZ.
Usa lxml conforme pilha definida no CLAUDE.md.
"""
from decimal import Decimal, InvalidOperation
from typing import Any

from lxml import etree


# Namespace padrão da NF-e 4.0
NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}


def _texto(elemento, xpath: str, namespaces: dict | None = None) -> str | None:
    """Extrai texto de um elemento filho via XPath. Retorna None se não existir."""
    if elemento is None:
        return None
    ns = namespaces or NS
    node = elemento.find(xpath, ns)
    if node is not None and node.text:
        return node.text.strip()
    return None


def _decimal(texto: str | None) -> Decimal | None:
    """Converte string numérica do XML para Decimal. Retorna None se inválido."""
    if not texto:
        return None
    try:
        return Decimal(texto.strip())
    except InvalidOperation:
        return None


def ler_xml_nota(filepath: str) -> dict[str, Any]:
    """
    Lê um XML de NF-e e retorna todos os dados extraídos.
    Retorna dict com: chave_acesso, cnpj_emitente, numero, serie, data_emissao,
    valor_total, itens (lista), hash_sha256 (calculado pelo caller).
    """
    tree = etree.parse(filepath)
    root = tree.getroot()

    # Detecta namespace dinamicamente (XML pode ou não ter prefixo)
    nsmap = root.nsmap
    ns_uri = None
    for prefix, uri in nsmap.items():
        if "portalfiscal" in uri:
            ns_uri = uri
            break

    if ns_uri:
        ns = {"nfe": ns_uri}
    else:
        ns = {}

    # InfNFe contém todos os dados
    inf_nfe = root.find(".//nfe:infNFe", ns) if ns else root.find(".//infNFe")
    if inf_nfe is None:
        # Tenta sem namespace
        inf_nfe = root.find(".//{*}infNFe")
    if inf_nfe is None:
        raise ValueError("XML não contém elemento infNFe válido.")

    # Chave de acesso (atributo Id de infNFe)
    chave_acesso = None
    id_attr = inf_nfe.get("Id", "")
    if id_attr.startswith("NFe") and len(id_attr) == 47:
        chave_acesso = id_attr[3:]  # Remove prefixo "NFe"
    elif len(id_attr) == 44:
        chave_acesso = id_attr

    # Ide (identificação da nota)
    ide = inf_nfe.find("nfe:ide", ns) if ns else inf_nfe.find("ide")
    if ide is None:
        ide = inf_nfe.find("{*}ide")

    numero = _texto(ide, "nfe:nNF", ns) if ns and ide is not None else None
    if not numero and ide is not None:
        numero = _texto(ide, "{*}nNF")
    serie = _texto(ide, "nfe:serie", ns) if ns and ide is not None else None
    if not serie and ide is not None:
        serie = _texto(ide, "{*}serie")
    data_emissao = _texto(ide, "nfe:dhEmi", ns) if ns and ide is not None else None
    if not data_emissao and ide is not None:
        data_emissao = _texto(ide, "{*}dhEmi")
    # Extrai apenas a data (YYYY-MM-DD) do datetime completo
    if data_emissao and len(data_emissao) >= 10:
        data_emissao = data_emissao[:10]

    # Emitente
    emit = inf_nfe.find("nfe:emit", ns) if ns else inf_nfe.find("emit")
    if emit is None:
        emit = inf_nfe.find("{*}emit")
    cnpj_emitente = _texto(emit, "nfe:CNPJ", ns) if ns and emit is not None else None
    if not cnpj_emitente and emit is not None:
        cnpj_emitente = _texto(emit, "{*}CNPJ")

    # Totais
    total_node = inf_nfe.find("nfe:total", ns) if ns else inf_nfe.find("total")
    if total_node is None:
        total_node = inf_nfe.find("{*}total")
    icms_total = None
    if total_node is not None:
        icms = total_node.find("nfe:ICMSTot", ns) if ns else total_node.find("ICMSTot")
        if icms is None:
            icms = total_node.find("{*}ICMSTot")
        v_nf = _texto(icms, "nfe:vNF", ns) if ns and icms is not None else None
        if not v_nf and icms is not None:
            v_nf = _texto(icms, "{*}vNF")
        valor_total = _decimal(v_nf)
    else:
        valor_total = None

    # Itens (det)
    itens = []
    dets = inf_nfe.findall("nfe:det", ns) if ns else inf_nfe.findall("det")
    if not dets:
        dets = inf_nfe.findall("{*}det")

    for det in dets:
        prod = det.find("nfe:prod", ns) if ns else det.find("prod")
        if prod is None:
            prod = det.find("{*}prod")
        if prod is None:
            continue

        codigo = _texto(prod, "nfe:cProd", ns) if ns else _texto(prod, "{*}cProd")
        descricao = _texto(prod, "nfe:xProd", ns) if ns else _texto(prod, "{*}xProd")
        unidade = _texto(prod, "nfe:uCom", ns) if ns else _texto(prod, "{*}uCom")
        qtd = _decimal(_texto(prod, "nfe:qCom", ns) if ns else _texto(prod, "{*}qCom"))
        vl_unit = _decimal(_texto(prod, "nfe:vUnCom", ns) if ns else _texto(prod, "{*}vUnCom"))
        vl_total = _decimal(_texto(prod, "nfe:vProd", ns) if ns else _texto(prod, "{*}vProd"))

        if descricao:
            itens.append({
                "codigo": codigo or "",
                "descricao": descricao,
                "unidade": unidade or "UN",
                "quantidade": qtd,
                "valor_unitario": vl_unit,
                "valor_total": vl_total,
            })

    return {
        "chave_acesso": chave_acesso,
        "cnpj_emitente": cnpj_emitente,
        "numero": numero,
        "serie": serie,
        "data_emissao": data_emissao,
        "valor_total": valor_total,
        "itens": itens,
    }