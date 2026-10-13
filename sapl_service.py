"""
sapl_service.py — Integração com a API do SAPL da Câmara Municipal de Boa Vista.

Autor oficial: Ítalo Otávio (ID 70 no SAPL da CMBV).
Tipo de Matéria: 8 (Indicação).
Endpoint da API: https://sapl.boavista.rr.leg.br/api/materia/materialegislativa/
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Callable, Generator

import requests

from utils import normalizar, BAIRROS_BOA_VISTA

API_BASE = "https://sapl.boavista.rr.leg.br/api/materia/materialegislativa/"
AUTOR_ITALO = 70
TIPO_INDICACAO = 8

HEADERS = {
    "User-Agent": "SIGI-GabineteItaloOtavio/1.0 (Sistema Inteligente de Indicacoes; CMBV/RR)",
    "Accept": "application/json",
}

# Regex para extração de dados da ementa oficial
_RE_BAIRRO = re.compile(
    r"\b(?:no\s+bairro|bairro|no\s+conjunto|conjunto|no\s+loteamento|loteamento|no\s+residencial|residencial)\s+([A-Za-zÀ-ÿ0-9\s\.\-ªº]+?)(?:[\.,;\r\n]|\s+além|\s+bem\s+como|\s+e\s+que|\s+visando|$)",
    re.IGNORECASE,
)

_RE_RUA = re.compile(
    r"\b(rua|avenida|av\.|travessa|alameda|beco|via|estrada|praca|praça)\s+([A-Za-zÀ-ÿ0-9\s\.\-ªº]+?)(?:,\s*(?:em\s+frente|no\s+trecho|entre|localizada|localizado|próximo|situada|situado|no\s+bairro|bairro)|[\.,;\r\n]|\s+no\s+bairro)",
    re.IGNORECASE,
)

_TIPOS_MAPEAMENTO = [
    ("Tapa-Buraco", [r"tapa[- ]buraco", r"operaç[aã]o\s+tapa", r"buraco", r"panelas", r"crateras"]),
    ("Recapeamento Asfáltico", [r"recapeamento", r"pavimentaç[aã]o\s+asf[aá]ltica", r"asfalto", r"asfaltamento"]),
    ("Construção de Calçada", [r"calçada", r"meio[- ]fio", r"passeio\s+p[uú]blico"]),
    ("Limpeza de Terreno", [r"limpeza\s+de\s+terreno", r"terreno\s+baldio", r"roçagem", r"roço", r"entulho", r"lixo"]),
    ("Sinalização", [r"sinalizaç[aã]o", r"placa", r"faixa\s+de\s+pedestre", r"redutor\s+de\s+velocidade", r"lombada"]),
    ("Drenagem Pluvial", [r"drenagem", r"galeria", r"bueiro", r"boca\s+de\s+lobo", r"escoamento"]),
    ("Iluminação Pública", [r"iluminaç[aã]o", r"poste", r"lâmpada", r"luminária"]),
]


def extrair_dados_ementa(ementa: str) -> dict:
    """Extrai rua, bairro e tipo de serviço aproximados a partir do texto oficial da ementa."""
    if not ementa:
        return {"rua": "", "bairro": "", "tipo_servico": "Indicação Geral"}

    # 1. Identificar Tipo de Serviço
    tipo_detectado = "Indicação Geral"
    ementa_norm = unicodedata.normalize("NFKD", ementa)
    for tipo_nome, padroes in _TIPOS_MAPEAMENTO:
        for p in padroes:
            if re.search(p, ementa, re.IGNORECASE):
                tipo_detectado = tipo_nome
                break
        if tipo_detectado != "Indicação Geral":
            break

    # 2. Identificar Bairro
    bairro_detectado = ""
    # Tenta casar primeiro com os bairros conhecidos de Boa Vista
    for b in BAIRROS_BOA_VISTA:
        if re.search(r"\b" + re.escape(b) + r"\b", ementa, re.IGNORECASE):
            bairro_detectado = b
            break

    if not bairro_detectado:
        m_b = _RE_BAIRRO.search(ementa)
        if m_b:
            b_candidato = m_b.group(1).strip()
            # Limpar pontuação e termos extras
            b_candidato = re.split(r"[,;\.]", b_candidato)[0].strip()
            if 3 <= len(b_candidato) <= 40:
                bairro_detectado = b_candidato.title()

    # 3. Identificar Rua
    rua_detectada = ""
    m_r = _RE_RUA.search(ementa)
    if m_r:
        prefixo = m_r.group(1).title()
        if prefixo.lower() in ("av.", "av"):
            prefixo = "Avenida"
        nome_rua = m_r.group(2).strip()
        nome_rua = re.split(r"[,;\.]", nome_rua)[0].strip()
        if 2 <= len(nome_rua) <= 50:
            rua_detectada = f"{prefixo} {nome_rua.title()}"

    return {
        "rua": rua_detectada,
        "bairro": bairro_detectado,
        "tipo_servico": tipo_detectado,
    }


import concurrent.futures


def obter_estatisticas_sapl() -> dict:
    """Retorna contadores gerais do acervo do Ítalo Otávio no SAPL."""
    try:
        url = f"{API_BASE}?tipo={TIPO_INDICACAO}&autores={AUTOR_ITALO}&page_size=1"
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code == 200:
            data = res.json()
            total = data.get("pagination", {}).get("total_entries", 0)
            return {"sucesso": True, "total_geral": total, "erro": None}
        return {"sucesso": False, "total_geral": 0, "erro": f"HTTP {res.status_code}"}
    except Exception as exc:
        return {"sucesso": False, "total_geral": 0, "erro": str(exc)}


def obter_totais_por_ano(anos: Iterable[int] | None = None) -> dict[int, int]:
    """
    Consulta o quantitativo oficial de matérias protocoladas por ano no SAPL
    de forma paralela e ultrarrápida.
    """
    if anos is None:
        ano_atual = datetime.now().year
        anos = range(2017, ano_atual + 1)

    lista_anos = sorted([int(a) for a in anos], reverse=True)

    def _consultar_ano(y: int) -> tuple[int, int]:
        try:
            r = requests.get(
                API_BASE,
                params={"tipo": TIPO_INDICACAO, "autores": AUTOR_ITALO, "ano": y, "page_size": 1},
                headers=HEADERS,
                timeout=12,
            )
            if r.status_code == 200:
                cnt = r.json().get("pagination", {}).get("total_entries", 0)
                return y, cnt
            return y, 0
        except Exception:
            return y, 0

    resultado = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(lista_anos), 8)) as executor:
        for y, total in executor.map(_consultar_ano, lista_anos):
            resultado[y] = total

    return dict(sorted(resultado.items(), key=lambda x: x[0], reverse=True))


def buscar_indicacoes_pagina(ano: int | None = None, pagina: int = 1, page_size: int = 100) -> dict:
    """Busca uma página de matérias na API do SAPL."""
    params = {
        "tipo": TIPO_INDICACAO,
        "autores": AUTOR_ITALO,
        "page": pagina,
        "page_size": page_size,
    }
    if ano:
        params["ano"] = ano

    res = requests.get(API_BASE, params=params, headers=HEADERS, timeout=25)
    if res.status_code != 200:
        raise RuntimeError(f"Erro na API SAPL: HTTP {res.status_code} - {res.text[:200]}")
    return res.json()


def iterar_indicacoes_sapl(ano: int | None = None, limite_paginas: int = 100,
                           progresso: Callable[[int, int, str], None] | None = None
                           ) -> Generator[dict, None, None]:
    """
    Percorre as páginas da API do SAPL trazendo as indicações formatadas.
    """
    pagina_atual = 1
    total_paginas = 1

    while pagina_atual <= total_paginas and pagina_atual <= limite_paginas:
        dados = buscar_indicacoes_pagina(ano=ano, pagina=pagina_atual, page_size=100)
        pagination = dados.get("pagination", {})
        total_paginas = pagination.get("total_pages", 1)
        total_itens = pagination.get("total_entries", 0)
        resultados = dados.get("results", [])

        if progresso:
            progresso(pagina_atual, min(total_paginas, limite_paginas), f"Página {pagina_atual} de {total_paginas} ({total_itens} matérias)")

        for item in resultados:
            ementa = item.get("ementa", "") or ""
            parsed = extrair_dados_ementa(ementa)

            yield {
                "sapl_id": item.get("id"),
                "numero": item.get("numero"),
                "ano": item.get("ano"),
                "numero_protocolo": item.get("numero_protocolo"),
                "data": item.get("data_apresentacao") or datetime.now().strftime("%Y-%m-%d"),
                "ementa": ementa,
                "texto_original": item.get("texto_original") or "",
                "link_sapl": f"https://sapl.boavista.rr.leg.br/materia/{item.get('id')}",
                "rua": parsed["rua"],
                "bairro": parsed["bairro"],
                "tipo_servico": parsed["tipo_servico"],
            }

        if not pagination.get("next_page"):
            break
        pagina_atual += 1

