"""
Detector inteligente de colunas de planilhas de contratos.

Analisa os cabeçalhos de qualquer planilha .xlsx e mapeia automaticamente
as colunas para os campos padrão do sistema, independente do formato usado
pela empresa (TIAGO MACHADO, ICCOSTA, POTY MED, LOTUS, VITORIA, DINAMICA,
CLEMILTON, DRC, etc.).

Padrões detectados (todos case-insensitive, com normalização de acentos):
- lote:        "nº lote", "lote", "lot"
- item_num:    "nº item", "item", "cod", "codigo", "código"
- descricao:   "item" (quando texto longo), "descricao", "descrição",
               "objeto", "produto", "serviço"
- quant:       "quant", "qnt", "qtd", "quantidade", "qtde"
- qnt_comprada:"qnt comprada", "comprada", "faturada", "consumida"
- qnt_disponivel: "qnt disponivel", "disponivel", "saldo", "restante"
- val_unit:    "val unit", "valor unit", "unitário", "unitario", "v.unit"
- val_total:   "val total", "valor total", "total"
- notas_nf:    qualquer coluna cujo cabeçalho comece com "nf", "nfe", "nfs"
               (essas viram colunas dinâmicas de histórico de NFs)
"""
import re
import unicodedata
from typing import Optional


def normalizar(texto: str) -> str:
    """Remove acentos, lowercase, colapsa espaços."""
    if texto is None:
        return ""
    texto = str(texto)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower().strip()
    texto = re.sub(r"\s+", " ", texto)
    return texto


def eh_coluna_nf(cabecalho_norm: str) -> bool:
    """Detecta se uma coluna é de histórico de NF (ex: 'Nfe 180 20-08-26')."""
    if not cabecalho_norm:
        return False
    # Padrão: começa com nf/nfe/nfs seguido de número ou espaço
    return bool(re.match(r"^nf[e|s]?\s*\d*", cabecalho_norm))


def detectar_colunas(linha_cabecalho: list) -> dict:
    """
    Recebe a linha de cabeçalho (lista de valores) e retorna um dict
    mapeando campo_padrao -> indice_da_coluna.

    Campos possíveis: lote, item_num, descricao, quant, qnt_comprada,
    qnt_disponivel, val_unit, val_total.
    Campo especial: notas_nf -> lista de índices de colunas de NF.
    """
    resultado = {
        "lote": None,
        "item_num": None,
        "descricao": None,
        "quant": None,
        "qnt_comprada": None,
        "qnt_disponivel": None,
        "val_unit": None,
        "val_total": None,
        "notas_nf": [],
    }

    candidatos_descricao = []  # (indice, score)

    for idx, celula in enumerate(linha_cabecalho):
        norm = normalizar(celula)
        if not norm:
            continue

        # Colunas de NF (histórico)
        if eh_coluna_nf(norm):
            resultado["notas_nf"].append(idx)
            continue

        # Lote
        if resultado["lote"] is None and norm in ("n lote", "lote", "lot", "numero lote", "número lote"):
            resultado["lote"] = idx
            continue

        # Item num
        if resultado["item_num"] is None and norm in ("n item", "item", "cod", "codigo", "código", "numero item", "número item", "cod item"):
            # "item" sozinho pode ser descrição — guarda como candidato fraco
            if norm == "item":
                candidatos_descricao.append((idx, 1))  # score baixo
                resultado["item_num"] = idx  # mas também marca como item_num por enquanto
            else:
                resultado["item_num"] = idx
            continue

        # Descrição
        if norm in ("descricao", "descrição", "objeto", "descricao do objeto", "descrição do objeto", "produto", "serviço", "servico", "especificação", "especificacao"):
            resultado["descricao"] = idx
            continue

        # Quantidade contratada
        if resultado["quant"] is None and norm in ("quant", "qnt", "qtd", "qtde", "quantidade", "quantidade contratada", "qnt contratada"):
            resultado["quant"] = idx
            continue

        # Qnt comprada / faturada
        if resultado["qnt_comprada"] is None and norm in ("qnt comprada", "comprada", "faturada", "consumida", "quantidade comprada", "qtd comprada"):
            resultado["qnt_comprada"] = idx
            continue

        # Qnt disponível / saldo
        if resultado["qnt_disponivel"] is None and norm in ("qnt disponivel", "qnt disponível", "disponivel", "disponível", "saldo", "restante", "quantidade disponivel"):
            resultado["qnt_disponivel"] = idx
            continue

        # Valor unitário
        if resultado["val_unit"] is None and norm in ("val unit", "valor unit", "valor unitário", "valor unitario", "v.unit", "v unit", "preço unitário", "preco unitario", "valor unit. (r$)", "valor unitário (r$)"):
            resultado["val_unit"] = idx
            continue
        if resultado["val_unit"] is None and ("unit" in norm and "total" not in norm):
            resultado["val_unit"] = idx
            continue

        # Valor total
        if resultado["val_total"] is None and norm in ("val total (r$)", "valor total (r$)", "val total", "valor total", "total (r$)", "total"):
            resultado["val_total"] = idx
            continue

        # Val disponível (DRC usa isso)
        if norm in ("val disponivel", "val disponível", "valor disponivel"):
            # Não mapeamos para campo padrão, mas registramos
            pass

    # Se não achou descrição explícita, usa o candidato "item"
    if resultado["descricao"] is None and candidatos_descricao:
        # Pega o de maior score
        candidatos_descricao.sort(key=lambda x: -x[1])
        resultado["descricao"] = candidatos_descricao[0][0]
        # Se esse índice estava marcado como item_num, limpa item_num
        if resultado["item_num"] == resultado["descricao"]:
            resultado["item_num"] = None

    return resultado


def encontrar_linha_cabecalho(ws, max_linhas: int = 15) -> tuple:
    """
    Procura a linha de cabeçalho na planilha.
    Retorna (indice_linha_0based, lista_de_valores) ou (None, None).

    Heurística: a linha de cabeçalho é a primeira linha que contém pelo menos
    3 células com texto reconhecível (não-numérico curto) e pelo menos uma
    palavra-chave conhecida (item, quant, valor, nf, etc.).
    """
    palavras_chave = {"item", "quant", "qnt", "qtd", "valor", "val", "nf", "nfe", "lote", "descricao", "descrição", "objeto", "disponivel", "disponível", "comprada", "unit"}

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= max_linhas:
            break
        celulas_texto = []
        for c in row:
            if c is None:
                continue
            s = str(c).strip()
            if s and not s.replace(".", "").replace(",", "").replace("-", "").isdigit():
                celulas_texto.append(s)
        if len(celulas_texto) < 3:
            continue
        # Verifica se alguma célula bate com palavra-chave
        normais = [normalizar(c) for c in celulas_texto]
        hits = sum(1 for n in normais if any(p in n for p in palavras_chave))
        if hits >= 2:
            return (i, list(row))

    return (None, None)


def parse_valor_br(valor) -> Optional[float]:
    """
    Converte valor em formato BR (1.234,56 ou R$ 1.234,56 ou 1234.56) para float.
    Retorna None se não conseguir.
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip()
    if not s:
        return None
    # Remove R$, espaços, pontos de milhar BR
    s = s.replace("R$", "").replace("r$", "").strip()
    # Detecta formato: se tem vírgula e ponto, decide qual é decimal
    if "," in s and "." in s:
        # Formato BR: 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # Só vírgula: 1234,56
        s = s.replace(",", ".")
    # Remove quaisquer outros caracteres não numéricos exceto ponto e menos
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def extrair_itens_planilha(ws, linha_cabecalho_idx: int, mapeamento: dict) -> list:
    """
    Extrai os itens da planilha usando o mapeamento de colunas detectado.
    Retorna lista de dicts com campos padronizados.
    """
    itens = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i <= linha_cabecalho_idx:
            continue
        # Linha vazia?
        if not any(c is not None and str(c).strip() for c in row):
            continue

        def pegar(campo):
            idx = mapeamento.get(campo)
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        descricao = pegar("descricao")
        if descricao is None or not str(descricao).strip():
            continue

        item = {
            "lote": str(pegar("lote") or "").strip(),
            "item_num": str(pegar("item_num") or "").strip(),
            "descricao": str(descricao).strip(),
            "quant": parse_valor_br(pegar("quant")),
            "qnt_comprada": parse_valor_br(pegar("qnt_comprada")),
            "qnt_disponivel": parse_valor_br(pegar("qnt_disponivel")),
            "val_unit": parse_valor_br(pegar("val_unit")),
            "val_total": parse_valor_br(pegar("val_total")),
            "historico_nfs": [],
        }

        # Extrai histórico de NFs
        for nf_idx in mapeamento.get("notas_nf", []):
            if nf_idx < len(row):
                v = parse_valor_br(row[nf_idx])
                if v is not None and v > 0:
                    cabecalho_nf = str(row[nf_idx]) if False else ""
                    # Pegar o cabeçalho da coluna NF
                    item["historico_nfs"].append({
                        "coluna_idx": nf_idx,
                        "quantidade": v,
                    })

        itens.append(item)

    return itens