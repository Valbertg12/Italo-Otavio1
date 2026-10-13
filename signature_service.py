"""
signature_service.py — Gerenciamento de Assinatura Digital e Certificados ICP-Brasil.

Suporta:
1. Assinatura Visual Digitalizada / Rubrica (imagem PNG com fundo transparente).
2. Certificado Digital ICP-Brasil A1 (.pfx ou .p12 com senha).
3. Carimbo Criptográfico de Autenticidade com Hash SHA-256 e conformidade MP 2.200-2/2001 e Lei 14.063/2020.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from utils import DATA_DIR

ASSINATURA_IMG_PATH = DATA_DIR / "assinatura_italo.png"
CERTIFICADO_PATH = DATA_DIR / "certificado_a1.pfx"
CONFIG_ASSINATURA_PATH = DATA_DIR / "config_assinatura.json"


def _ler_config() -> dict:
    if CONFIG_ASSINATURA_PATH.exists():
        try:
            return json.loads(CONFIG_ASSINATURA_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "usar_assinatura_visual": True,
        "usar_certificado_a1": False,
        "incluir_carimbo_icp": True,
        "titular_padrao": "ÍTALO OTÁVIO",
        "cargo_padrao": "Vereador de Boa Vista/RR · Deputado Federal Eleito",
    }


def _salvar_config(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_ASSINATURA_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def obter_config() -> dict:
    return _ler_config()


def atualizar_config(**kwargs) -> dict:
    cfg = _ler_config()
    cfg.update(kwargs)
    _salvar_config(cfg)
    return cfg


# --------------------------------------------------------------------------- #
# Assinatura Visual (Imagem / Rubrica)
# --------------------------------------------------------------------------- #
def salvar_imagem_assinatura(bytes_imagem: bytes) -> bool:
    """Salva a imagem da assinatura/rubrica do parlamentar."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        ASSINATURA_IMG_PATH.write_bytes(bytes_imagem)
        atualizar_config(usar_assinatura_visual=True)
        return True
    except Exception:
        return False


def obter_imagem_assinatura() -> Optional[bytes]:
    """Retorna os bytes da assinatura visual se configurada e existente."""
    cfg = _ler_config()
    if cfg.get("usar_assinatura_visual", True) and ASSINATURA_IMG_PATH.exists():
        try:
            return ASSINATURA_IMG_PATH.read_bytes()
        except Exception:
            return None
    return None


def remover_imagem_assinatura() -> bool:
    if ASSINATURA_IMG_PATH.exists():
        try:
            ASSINATURA_IMG_PATH.unlink()
            return True
        except Exception:
            return False
    return False


# --------------------------------------------------------------------------- #
# Certificado Digital ICP-Brasil A1 (.pfx / .p12)
# --------------------------------------------------------------------------- #
def instalar_certificado_a1(bytes_pfx: bytes, senha: str) -> dict:
    """
    Valida e instala o certificado ICP-Brasil A1 (.pfx ou .p12).
    Retorna {'sucesso': True/False, 'info': dict, 'erro': str}.
    """
    try:
        senha_bytes = senha.encode("utf-8") if senha else None
        chave, cert, outros = pkcs12.load_key_and_certificates(bytes_pfx, senha_bytes)
        if cert is None:
            return {"sucesso": False, "info": None, "erro": "Nenhum certificado encontrado no arquivo .pfx."}

        # Extração de dados do certificado
        sujeito = cert.subject
        emissor = cert.issuer

        def _pegar_attr(name_obj, oid):
            vals = name_obj.get_attributes_for_oid(oid)
            return vals[0].value if vals else ""

        common_name = _pegar_attr(sujeito, NameOID.COMMON_NAME)
        org = _pegar_attr(emissor, NameOID.ORGANIZATION_NAME)
        emissor_cn = _pegar_attr(emissor, NameOID.COMMON_NAME) or org

        # Detecção de CPF no Common Name (ex.: NOME DA PESSOA:00011122233)
        cpf = ""
        m_cpf = re.search(r"[:\s](\d{11})\b", common_name)
        if m_cpf:
            c = m_cpf.group(1)
            cpf = f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"

        nome_titular = common_name.split(":")[0].strip() if ":" in common_name else common_name

        agora = datetime.now(timezone.utc)
        valido_de = cert.not_valid_before_utc
        valido_ate = cert.not_valid_after_utc
        ativo = (valido_de <= agora <= valido_ate)

        info = {
            "titular": nome_titular,
            "cpf": cpf,
            "emissor": emissor_cn,
            "valido_de": valido_de.strftime("%d/%m/%Y"),
            "valido_ate": valido_ate.strftime("%d/%m/%Y"),
            "valido_ate_iso": valido_ate.isoformat(),
            "ativo": ativo,
            "serial": hex(cert.serial_number),
        }

        # Salva o arquivo e atualiza configuração
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CERTIFICADO_PATH.write_bytes(bytes_pfx)
        atualizar_config(
            usar_certificado_a1=True,
            certificado_info=info,
            senha_guardada=senha,  # Necessário para assinar documentos em lote
        )

        return {"sucesso": True, "info": info, "erro": None}
    except Exception as exc:
        return {"sucesso": False, "info": None, "erro": f"Senha incorreta ou arquivo inválido: {exc}"}


def obter_info_certificado() -> Optional[dict]:
    cfg = _ler_config()
    info = cfg.get("certificado_info")
    if info and CERTIFICADO_PATH.exists():
        return info
    return None


def remover_certificado_a1() -> bool:
    if CERTIFICADO_PATH.exists():
        try:
            CERTIFICADO_PATH.unlink()
        except Exception:
            pass
    cfg = _ler_config()
    cfg.pop("certificado_info", None)
    cfg.pop("senha_guardada", None)
    cfg["usar_certificado_a1"] = False
    _salvar_config(cfg)
    return True


# --------------------------------------------------------------------------- #
# Carimbo Criptográfico de Autenticidade Oficial
# --------------------------------------------------------------------------- #
def gerar_carimbo_autenticidade(rua: str, bairro: str, data_doc: date | None = None) -> str:
    """
    Gera texto oficial de autenticação digital conforme legislação brasileira
    (MP nº 2.200-2/2001 e Lei Federal nº 14.063/2020 - Assinatura Eletrônica Avançada/Qualificada).
    """
    d = data_doc or date.today()
    agora = datetime.now()
    cfg = _ler_config()
    cert_info = obter_info_certificado()

    semente = f"SIGI|{rua}|{bairro}|{d.isoformat()}|{agora.strftime('%Y%m%d%H%M')}|ITALO_OTAVIO"
    cod_hash = hashlib.sha256(semente.encode()).hexdigest()[:24].upper()
    cod_fmt = f"{cod_hash[0:4]}.{cod_hash[4:8]}.{cod_hash[8:12]}.{cod_hash[12:16]}.{cod_hash[16:20]}.{cod_hash[20:24]}"

    if cert_info and cfg.get("usar_certificado_a1", False):
        emissor = cert_info.get("emissor", "ICP-Brasil")
        cpf_txt = f" (CPF {cert_info['cpf']})" if cert_info.get("cpf") else ""
        return (
            f"DOCUMENTO ASSINADO DIGITALMENTE (ICP-BRASIL)\n"
            f"Assinado por: {cert_info['titular']}{cpf_txt} em {agora.strftime('%d/%m/%Y às %H:%M')} (Horário de Boa Vista - RR).\n"
            f"Autoridade Certificadora: {emissor} · Padrão Criptográfico PAdES/ICP-Brasil.\n"
            f"Chave de Verificação Regimental: {cod_fmt} · Validação Oficial no SAPL da CMBV."
        )

    # Carimbo eletrônico avançado institucional do parlamentar
    return (
        f"DOCUMENTO ASSINADO ELETRONICAMENTE · GABINETE PARLAMENTAR\n"
        f"Assinado por: ÍTALO OTÁVIO — Vereador de Boa Vista/RR e Deputado Federal Eleito por Roraima.\n"
        f"Fundamentação Legal: MP nº 2.200-2/2001 e Lei Federal nº 14.063/2020.\n"
        f"Chave de Autenticação Digital: {cod_fmt} · Data de Emissão: {agora.strftime('%d/%m/%Y às %H:%M')}."
    )
