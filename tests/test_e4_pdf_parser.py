"""
Testes para o parser de PDF de notas fiscais — Etapa E4.
CA01-CA04: Leitura de DANFE com múltiplas folhas e páginas extras.
"""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from notas.pdf_parser import (
    extrair_chave_acesso,
    extrair_cnpj_emitente,
    extrair_numero_serie,
    extrair_data_emissao,
    extrair_valor_total,
    parse_valor_br,
    ler_pdf_nota,
)


class TestParseValorBR:
    def test_valor_com_milhar_e_virgula(self):
        assert parse_valor_br("3.742,17") == Decimal("3742.17")

    def test_valor_sem_milhar(self):
        assert parse_valor_br("150,50") == Decimal("150.50")

    def test_valor_com_rs(self):
        assert parse_valor_br("R$ 1.234,56") == Decimal("1234.56")

    def test_valor_inteiro(self):
        assert parse_valor_br("100,00") == Decimal("100.00")

    def test_valor_none(self):
        assert parse_valor_br("") is None
        assert parse_valor_br(None) is None

    def test_valor_invalido(self):
        assert parse_valor_br("abc") is None


class TestExtrairChaveAcesso:
    def test_chave_com_label(self):
        texto = "Chave de Acesso: 12345678901234567890123456789012345678901234"
        assert extrair_chave_acesso(texto) == "12345678901234567890123456789012345678901234"

    def test_chave_44_digitos(self):
        texto = "NF-e 12345678901234567890123456789012345678901234 emitida"
        assert extrair_chave_acesso(texto) == "12345678901234567890123456789012345678901234"

    def test_sem_chave(self):
        assert extrair_chave_acesso("texto sem chave") is None


class TestExtrairCNPJEmitente:
    def test_cnpj_formatado(self):
        texto = "CNPJ: 12.345.678/0001-90 Emitente: Empresa X"
        assert extrair_cnpj_emitente(texto) == "12.345.678/0001-90"

    def test_cnpj_sem_formatacao(self):
        texto = "CNPJ 12345678000190"
        assert extrair_cnpj_emitente(texto) == "12345678000190"

    def test_sem_cnpj(self):
        assert extrair_cnpj_emitente("sem cnpj aqui") is None


class TestExtrairNumeroSerie:
    def test_numero_e_serie(self):
        texto = "Nº. 000123 Série 1"
        num, serie = extrair_numero_serie(texto)
        assert num == "000123"
        assert serie == "1"

    def test_apenas_numero(self):
        texto = "Número 456"
        num, serie = extrair_numero_serie(texto)
        assert num == "456"
        assert serie is None

    def test_sem_dados(self):
        num, serie = extrair_numero_serie("nada aqui")
        assert num is None
        assert serie is None


class TestExtrairDataEmissao:
    def test_data_com_label(self):
        texto = "Data de Emissão: 15/08/2021"
        assert extrair_data_emissao(texto) == "2021-08-15"

    def test_data_com_hifen(self):
        texto = "Data Emissão 15-08-2021"
        assert extrair_data_emissao(texto) == "2021-08-15"

    def test_data_simples(self):
        texto = "10/04/2029"
        assert extrair_data_emissao(texto) == "2029-04-10"

    def test_sem_data(self):
        assert extrair_data_emissao("sem data") is None


class TestExtrairValorTotal:
    def test_valor_total_da_nota(self):
        texto = "VALOR TOTAL DA NOTA: R$ 3.742,17"
        assert extrair_valor_total(texto) == Decimal("3742.17")

    def test_valor_liquido(self):
        texto = "VALOR LÍQUIDO: R$ 3.742,17"
        assert extrair_valor_total(texto) == Decimal("3742.17")

    def test_valor_total_generico(self):
        texto = "Valor Total R$ 1.500,00"
        assert extrair_valor_total(texto) == Decimal("1500.00")

    def test_sem_valor(self):
        assert extrair_valor_total("sem valor") is None


class TestLerPdfNota:
    """Testes de integração do parser completo."""

    @patch("notas.pdf_parser.extrair_texto_pdf")
    @patch("notas.pdf_parser.extrair_itens_danfe")
    def test_leitura_completa(self, mock_itens, mock_texto):
        mock_texto.return_value = """
        Chave de Acesso: 12345678901234567890123456789012345678901234
        CNPJ: 12.345.678/0001-90
        Nº. 000123 Série 1
        Data de Emissão: 15/08/2021
        VALOR TOTAL DA NOTA: R$ 3.742,17
        """
        mock_itens.return_value = [
            {"codigo": "001", "descricao": "Exame sangue", "quantidade": Decimal("1"), "valor_total": Decimal("3742.17")}
        ]

        resultado = ler_pdf_nota("/fake/path.pdf")

        assert resultado["chave_acesso"] == "12345678901234567890123456789012345678901234"
        assert resultado["cnpj_emitente"] == "12.345.678/0001-90"
        assert resultado["numero"] == "000123"
        assert resultado["serie"] == "1"
        assert resultado["data_emissao"] == "2021-08-15"
        assert resultado["valor_total"] == Decimal("3742.17")
        assert len(resultado["itens"]) == 1

    @patch("notas.pdf_parser.extrair_texto_pdf")
    @patch("notas.pdf_parser.extrair_itens_danfe")
    def test_leitura_parial(self, mock_itens, mock_texto):
        """PDF com poucos dados identificáveis."""
        mock_texto.return_value = "Documento simples sem muitos dados"
        mock_itens.return_value = []

        resultado = ler_pdf_nota("/fake/path.pdf")

        assert resultado["chave_acesso"] is None
        assert resultado["cnpj_emitente"] is None
        assert resultado["valor_total"] is None
        assert resultado["itens"] == []