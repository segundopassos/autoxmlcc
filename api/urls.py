"""
URLs da API JSON — replica as rotas do protótipo FastAPI para o frontend SPA.
"""
from django.urls import path
from . import views

app_name = "api"

urlpatterns = [
    # Dashboard
    path("contratos", views.lista_contratos, name="lista_contratos"),
    path("contrato/<int:contrato_id>", views.detalhe_contrato, name="detalhe_contrato"),
    path("contrato/cadastrar", views.cadastrar_contrato, name="cadastrar_contrato"),
    path("contrato/<int:contrato_id>/prazo", views.alterar_prazo, name="alterar_prazo"),
    path("contrato/<int:contrato_id>", views.editar_contrato, name="editar_contrato"),
    path("contrato/<int:contrato_id>/itens", views.limpar_itens, name="limpar_itens"),
    path("contrato/<int:contrato_id>/transferir_itens", views.transferir_itens, name="transferir_itens"),
    path("contrato/mestre", views.importar_mestre, name="importar_mestre"),

    # Itens e aditivos
    path("item/<int:item_id>", views.excluir_item, name="excluir_item"),
    path("aditivo/<int:item_id>", views.salvar_aditivo, name="salvar_aditivo"),
    path("aditivo/<int:item_id>/zerar", views.zerar_aditivo, name="zerar_aditivo"),

    # Notas fiscais
    path("nota/<int:nota_id>", views.excluir_nota, name="excluir_nota"),

    # XML / PDF
    path("analisar-xml", views.analisar_xml, name="analisar_xml"),
    path("gravar-xml", views.gravar_xml, name="gravar_xml"),
    path("xml/analisar_multiplo", views.analisar_xml_multiplo, name="analisar_xml_multiplo"),
    path("xml/gravar_multiplo", views.gravar_xml_multiplo, name="gravar_xml_multiplo"),

    # Importação Excel
    path("importar-excel", views.importar_excel, name="importar_excel"),
    path("importar_itens", views.importar_itens, name="importar_itens"),
    path("verificar_planilha_contrato", views.verificar_planilha, name="verificar_planilha"),
    path("importar_lista_mestra", views.importar_lista_mestra, name="importar_lista_mestra"),
    path("empresas", views.lista_empresas, name="lista_empresas"),
    path("empresa/<int:empresa_id>", views.excluir_empresa, name="excluir_empresa"),
    path("empresas/todas", views.excluir_todas_empresas, name="excluir_todas_empresas"),

    # Lançamento manual / texto IA
    path("nfse/analisar_texto", views.analisar_texto_ia, name="analisar_texto_ia"),

    # Relatórios PDF
    path("pdf/relatorio_contrato", views.pdf_relatorio_contrato, name="pdf_relatorio_contrato"),
    path("pdf/of_lote", views.pdf_of_lote, name="pdf_of_lote"),

    # Exportação
    path("exportar_xls", views.exportar_xls, name="exportar_xls"),
]