"""
Testes da Etapa 2 do Plano Mestre: parsers XML/PDF/Excel e deduplicidade SHA-256.
Cobre RN25 (anti-duplicidade), parser XML de NF-e e utilitários de hash.
"""
import hashlib
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree

from importacao.hash_utils import calcular_hash_sha256, verificar_duplicidade, registrar_hash
from importacao.models import HistoricoHashArquivo
from notas.xml_parser import ler_xml_nota


@pytest.fixture
def contrato(db):
    from contratos.models import Empresa, Contrato
    empresa = Empresa.objects.create(
        cnpj="11.753.492/0001-02",
        razao_social="Fundo Municipal de Saúde",
    )
    return Contrato.objects.create(
        numero="TESTE-E2/2026",
        empresa=empresa,
        inicio_vigencia="2026-01-01",
        fim_vigencia="2026-12-31",
    )


@pytest.fixture
def xml_nf_simples(tmp_path):
    """Gera um XML de NF-e mínimo válido para testes."""
    xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
  <infNFe Id="NFe35260111753492000102550010000001001000000000" versao="4.00">
    <ide>
      <nNF>100</nNF>
      <serie>1</serie>
      <dhEmi>2026-03-15T10:00:00-03:00</dhEmi>
    </ide>
    <emit>
      <CNPJ>11753492000102</CNPJ>
    </emit>
    <det nItem="1">
      <prod>
        <cProd>001</cProd>
        <xProd>Paracetamol 500mg</xProd>
        <uCom>CP</uCom>
        <qCom>50.0000</qCom>
        <vUnCom>5.0000</vUnCom>
        <vProd>250.00</vProd>
      </prod>
    </det>
    <det nItem="2">
      <prod>
        <cProd>002</cProd>
        <xProd>Dipirona 1g</xProd>
        <uCom>CP</uCom>
        <qCom>30.0000</qCom>
        <vUnCom>8.5000</vUnCom>
        <vProd>255.00</vProd>
      </prod>
    </det>
    <total>
      <ICMSTot>
        <vNF>505.00</vNF>
      </ICMSTot>
    </total>
  </infNFe>
</NFe>"""
    filepath = tmp_path / "nf_teste.xml"
    filepath.write_bytes(xml_content)
    return str(filepath)


@pytest.mark.django_db
class TestXmlParser:
    """Parser XML de NF-e — Etapa E2."""

    def test_extrai_chave_acesso(self, xml_nf_simples):
        resultado = ler_xml_nota(xml_nf_simples)
        assert resultado["chave_acesso"] == "35260111753492000102550010000001001000000000"

    def test_extrai_numero_serie(self, xml_nf_simples):
        resultado = ler_xml_nota(xml_nf_simples)
        assert resultado["numero"] == "100"
        assert resultado["serie"] == "1"

    def test_extrai_data_emissao(self, xml_nf_simples):
        resultado = ler_xml_nota(xml_nf_simples)
        assert resultado["data_emissao"] == "2026-03-15"

    def test_extrai_cnpj_emitente(self, xml_nf_simples):
        resultado = ler_xml_nota(xml_nf_simples)
        assert resultado["cnpj_emitente"] == "11753492000102"

    def test_extrai_valor_total(self, xml_nf_simples):
        resultado = ler_xml_nota(xml_nf_simples)
        assert resultado["valor_total"] == Decimal("505.00")

    def test_extrai_itens_completos(self, xml_nf_simples):
        resultado = ler_xml_nota(xml_nf_simples)
        assert len(resultado["itens"]) == 2

        item1 = resultado["itens"][0]
        assert item1["codigo"] == "001"
        assert item1["descricao"] == "Paracetamol 500mg"
        assert item1["unidade"] == "CP"
        assert item1["quantidade"] == Decimal("50.0000")
        assert item1["valor_unitario"] == Decimal("5.0000")
        assert item1["valor_total"] == Decimal("250.00")

        item2 = resultado["itens"][1]
        assert item2["descricao"] == "Dipirona 1g"
        assert item2["quantidade"] == Decimal("30.0000")

    def test_xml_invalido_levanta_excecao(self, tmp_path):
        filepath = tmp_path / "invalido.xml"
        filepath.write_text("<root><foo>bar</foo></root>")
        with pytest.raises(ValueError, match="infNFe"):
            ler_xml_nota(str(filepath))


@pytest.mark.django_db
class TestHashUtils:
    """Utilitários de hash SHA-256 — RN25."""

    def test_calcular_hash_sha256(self, tmp_path):
        filepath = tmp_path / "teste.txt"
        conteudo = b"conteudo de teste para hash"
        filepath.write_bytes(conteudo)

        esperado = hashlib.sha256(conteudo).hexdigest()
        resultado = calcular_hash_sha256(str(filepath))
        assert resultado == esperado

    def test_verificar_duplicidade_primeiro_upload(self, contrato, tmp_path):
        filepath = tmp_path / "planilha.xlsx"
        filepath.write_bytes(b"dados da planilha")

        eh_dup, hash_val = verificar_duplicidade(
            str(filepath), "PLANILHA", contrato.pk
        )
        assert eh_dup is False
        assert len(hash_val) == 64

    def test_verificar_duplicidade_segundo_upload_bloqueia(self, contrato, tmp_path):
        filepath = tmp_path / "planilha.xlsx"
        filepath.write_bytes(b"dados da planilha")

        # Primeiro registro
        registrar_hash(str(filepath), "PLANILHA", contrato.pk)

        # Segunda verificação deve detectar duplicidade
        eh_dup, hash_val = verificar_duplicidade(
            str(filepath), "PLANILHA", contrato.pk
        )
        assert eh_dup is True

    def test_registrar_hash_cria_registro(self, contrato, tmp_path):
        filepath = tmp_path / "nf.xml"
        filepath.write_bytes(b"<nfe>dados</nfe>")

        obj = registrar_hash(str(filepath), "NOTA_FISCAL", contrato.pk)
        assert obj.pk is not None
        assert obj.tipo == "NOTA_FISCAL"
        assert obj.nome_arquivo == "nf.xml"
        assert obj.contrato_id == contrato.pk

    def test_mesmo_hash_tipos_diferentes_nao_duplica(self, contrato, tmp_path):
        filepath = tmp_path / "arquivo.bin"
        filepath.write_bytes(b"mesmo conteudo")

        registrar_hash(str(filepath), "PLANILHA", contrato.pk)

        # Mesmo conteúdo, tipo diferente → não é duplicado
        eh_dup, _ = verificar_duplicidade(
            str(filepath), "NOTA_FISCAL", contrato.pk
        )
        assert eh_dup is False

    def test_hash_arquivo_vazio(self, tmp_path):
        filepath = tmp_path / "vazio.txt"
        filepath.write_bytes(b"")

        esperado = hashlib.sha256(b"").hexdigest()
        resultado = calcular_hash_sha256(str(filepath))
        assert resultado == esperado