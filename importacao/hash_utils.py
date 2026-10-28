"""
Utilitários de hash SHA-256 para deduplicidade de arquivos — Etapa E2.
RN25: Bloqueia reimportação de planilhas ou notas fiscais idênticas.
"""
import hashlib
from pathlib import Path

from importacao.models import HistoricoHashArquivo


def calcular_hash_sha256(filepath: str | Path) -> str:
    """
    Calcula o hash SHA-256 de um arquivo.
    Lê em chunks de 8KB para evitar sobrecarga de memória em arquivos grandes.
    """
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def verificar_duplicidade(
    filepath: str | Path,
    tipo: str,
    contrato_id: int | None = None,
) -> tuple[bool, str]:
    """
    Verifica se um arquivo já foi importado anteriormente.
    Retorna (eh_duplicado, hash_sha256).
    Se eh_duplicado=True, o arquivo NÃO deve ser processado novamente.
    """
    file_hash = calcular_hash_sha256(filepath)
    nome_arquivo = Path(filepath).name

    qs = HistoricoHashArquivo.objects.filter(
        hash_sha256=file_hash,
        tipo=tipo,
    )
    if contrato_id is not None:
        qs = qs.filter(contrato_id=contrato_id)
    else:
        qs = qs.filter(contrato__isnull=True)

    if qs.exists():
        return True, file_hash

    return False, file_hash


def registrar_hash(
    filepath: str | Path,
    tipo: str,
    contrato_id: int | None = None,
    hash_sha256: str | None = None,
) -> HistoricoHashArquivo:
    """
    Registra o hash de um arquivo processado para prevenir duplicidade futura.
    Se hash_sha256 não for fornecido, calcula automaticamente.
    """
    if hash_sha256 is None:
        hash_sha256 = calcular_hash_sha256(filepath)

    nome_arquivo = Path(filepath).name

    return HistoricoHashArquivo.objects.create(
        contrato_id=contrato_id,
        tipo=tipo,
        nome_arquivo=nome_arquivo,
        hash_sha256=hash_sha256,
    )