"""
Testes da Etapa 3 do Plano Mestre: upload de nota fiscal (XML/PDF) com RN25.
Valida o endpoint importacao:upload_nota e a integração com hash_utils.
"""
import hashlib
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from contratos.models import Contrato, Empresa
from importacao.hash_utils import registrar_hash
from importacao.models import HistoricoHashArquivo
from notas.models import NotaFiscal


@pytest.fixture
def empresa(db):
    return Empresa.objects.create(
        cnpj="11.753.492/0001-02",
        razao_social="Fundo Municipal de Saúde",
    )


@pytest.fixture
def contrato(empresa):
    return Contrato.objects.create(
        numero="TESTE-E3/2026",
        empresa=empresa,
        inicio_vigencia="2026-01-01",
        fim_vigencia="2026-12-31",
    )


@pytest.fixture
def xml_nf_valido():
    """XML mínimo de NF-e para testes de upload."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
  <infNFe Id="NFe35260111753492000102550010000002001000000000" versao="4.00">
    <ide>
      <nNF>200</nNF>
      <serie>1</serie>
      <dhEmi>2026-04-10T10:00:00-03:00</dhEmi>
    </ide>
    <emit>
      <CNPJ>11753492000102</CNPJ>
    </emit>
    <det nItem="1">
      <prod>
        <cProd>001</cProd>
        <xProd>Paracetamol 500mg</xProd>
        <uCom>CP</uCom>
        <qCom>10.0000</qCom>
        <vUnCom>5.0000</vUnCom>
        <vProd>50.00</vProd>
      </prod>
    </det>
    <total>
      <ICMSTot>
        <vNF>50.00</vNF>
      </ICMSTot>
    </total>
  </infNFe>
</NFe>"""


@pytest.mark.django_db
class TestUploadNotaFiscalView:
    """Endpoint importacao:upload_nota — Etapa 3."""

    def test_get_renderiza_formulario(self, client, contrato):
        url = reverse("importacao:upload_nota")
        response = client.get(url)
        assert response.status_code == 200
        assert b"Importar Nota Fiscal" in response.content

    def test_post_xml_cria_nota_com_hash(self, client, contrato, xml_nf_valido):
        arquivo = SimpleUploadedFile(
            "nf200.xml", xml_nf_valido, content_type="application/xml"
        )
        url = reverse("importacao:upload_nota")
        response = client.post(url, {
            "arquivo": arquivo,
            "contrato_id": contrato.pk,
        })
        # Deve redirecionar para nota_detail após sucesso
        assert response.status_code == 302
        assert NotaFiscal.objects.filter(numero="200").exists()
        nota = NotaFiscal.objects.get(numero="200")
        assert nota.hash_sha256 is not None
        assert len(nota.hash_sha256) == 64
        assert nota.origem == "xml"
        assert nota.status == "bloqueada"
        # Hash deve ter sido registrado no histórico
        assert HistoricoHashArquivo.objects.filter(
            hash_sha256=nota.hash_sha256,
            tipo="NOTA_FISCAL",
        ).exists()

    def test_post_xml_duplicado_bloqueia(self, client, contrato, xml_nf_valido):
        """RN25: Segundo upload do mesmo arquivo deve ser bloqueado."""
        # Primeiro upload
        arquivo1 = SimpleUploadedFile(
            "nf200.xml", xml_nf_valido, content_type="application/xml"
        )
        url = reverse("importacao:upload_nota")
        client.post(url, {"arquivo": arquivo1, "contrato_id": contrato.pk})
        assert NotaFiscal.objects.filter(numero="200").count() == 1

        # Segundo upload do mesmo conteúdo
        arquivo2 = SimpleUploadedFile(
            "nf200_copia.xml", xml_nf_valido, content_type="application/xml"
        )
        response = client.post(url, {"arquivo": arquivo2, "contrato_id": contrato.pk})
        # Deve redirecionar de volta ao form com erro
        assert response.status_code == 302
        # Não deve criar segunda nota
        assert NotaFiscal.objects.filter(numero="200").count() == 1

    def test_post_sem_arquivo_retorna_erro(self, client, contrato):
        url = reverse("importacao:upload_nota")
        response = client.post(url, {"contrato_id": contrato.pk})
        assert response.status_code == 302  # Redirect com mensagem de erro

    def test_post_formato_invalido_rejeita(self, client, contrato):
        arquivo = SimpleUploadedFile(
            "nota.txt", b"conteudo invalido", content_type="text/plain"
        )
        url = reverse("importacao:upload_nota")
        response = client.post(url, {
            "arquivo": arquivo,
            "contrato_id": contrato.pk,
        })
        assert response.status_code == 302
        assert not NotaFiscal.objects.exists()

    def test_post_xml_sem_contrato_erro_integridade(self, client, db, xml_nf_valido):
        """Upload sem contrato_id falha porque contrato é obrigatório (PROTECT)."""
        arquivo = SimpleUploadedFile(
            "nf200.xml", xml_nf_valido, content_type="application/xml"
        )
        url = reverse("importacao:upload_nota")
        # O campo contrato é NOT NULL no modelo; upload sem contrato gera erro 500
        # ou redirect com erro dependendo do tratamento na view.
        # Ajuste: a view deve validar e redirecionar com mensagem de erro.
        response = client.post(url, {"arquivo": arquivo})
        # Espera-se redirect de volta ao form com mensagem de erro
        assert response.status_code in (302, 400)
        # Nenhuma nota deve ter sido criada
        assert not NotaFiscal.objects.filter(numero="200").exists()