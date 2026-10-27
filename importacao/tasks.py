"""
Tasks Celery do app importacao — Etapa E2.
Processamento assíncrono de planilhas em segundo plano.
"""
from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3)
def processar_importacao(self, sessao_id: int):
    """
    Processa uma sessão de importação confirmada.
    Cria/atualiza itens e preços no contrato associado.
    """
    from .models import SessaoImportacao
    from contratos.models import ItemContrato, PrecoItem, normalizar_descricao

    try:
        sessao = SessaoImportacao.objects.get(pk=sessao_id)
    except SessaoImportacao.DoesNotExist:
        return {"erro": f"Sessão {sessao_id} não encontrada"}

    if not sessao.contrato:
        sessao.status = SessaoImportacao.Status.ERRO
        sessao.erros = ["Contrato não associado à sessão."]
        sessao.save()
        return {"erro": "Contrato não associado"}

    sessao.status = SessaoImportacao.Status.PROCESSANDO
    sessao.save()

    erros = []
    itens_criados = 0
    precos_criados = 0

    dados = sessao.dados_extraidos or []
    for item_data in dados:
        try:
            # Busca ou cria o item pelo número + lote
            numero_item = item_data.get("numero_item")
            if numero_item is None:
                erros.append(
                    f"Linha {item_data.get('linha')}: número do item ausente"
                )
                continue

            item, criado = ItemContrato.objects.update_or_create(
                contrato=sessao.contrato,
                numero_item=int(numero_item),
                lote=item_data.get("lote", ""),
                defaults={
                    "descricao": item_data["descricao"],
                    "descricao_normalizada": normalizar_descricao(
                        item_data["descricao"]
                    ),
                    "unidade": item_data.get("unidade", "UN"),
                    "quantidade_contratada": item_data.get(
                        "quantidade_contratada", 0
                    ),
                    "origem": "original",
                },
            )
            if criado:
                itens_criados += 1

            # Cria preço se valor unitário foi fornecido
            valor = item_data.get("valor_unitario")
            if valor is not None and valor > 0:
                _, preco_criado = PrecoItem.objects.update_or_create(
                    item=item,
                    vigente_a_partir_de=sessao.contrato.inicio_vigencia,
                    defaults={"valor_unitario": valor},
                )
                if preco_criado:
                    precos_criados += 1

        except Exception as exc:
            erros.append(
                f"Linha {item_data.get('linha')}: {str(exc)}"
            )

    sessao.itens_importados = itens_criados
    sessao.erros = erros
    sessao.status = (
        SessaoImportacao.Status.CONCLUIDO
        if not erros
        else SessaoImportacao.Status.ERRO
    )
    sessao.save()

    return {
        "itens_criados": itens_criados,
        "precos_criados": precos_criados,
        "erros": len(erros),
    }