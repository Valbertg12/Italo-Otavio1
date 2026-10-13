"""
geo_service.py — Integração com a Overpass API (OpenStreetMap).

* listar_bairros()          -> bairros de Boa Vista/RR (polígonos admin_level=10 do OSM)
* buscar_ruas_por_bairro()  -> ruas ("way" com tag "highway" e "name") dentro do bairro

Robustez:
  - vários espelhos da Overpass (o servidor principal costuma responder 429/504);
  - novas tentativas com espera crescente;
  - cache em disco (data/cache_geo.json) para não consultar o OSM a cada clique;
  - se tudo falhar, usa o cache vencido; para bairros, usa a lista estática do utils.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import requests
from PIL import Image, ImageDraw, ImageFont

from utils import BAIRROS_BOA_VISTA, DATA_DIR, normalizar

CACHE_MAPAS_DIR = DATA_DIR / "cache_mapas"

# Município de Boa Vista/RR no OSM: relação 326286 (a 301450 é Boa Vista/PB).
# Em Overpass, id de área = id da relação + 3 600 000 000.
REL_BOA_VISTA_RR = 326286
AREA_BOA_VISTA_RR = 3_600_000_000 + REL_BOA_VISTA_RR

# O alias principal (overpass-api.de) às vezes devolve 504; os espelhos abaixo são
# tentados em ordem e o código passa ao próximo em caso de falha.
ENDPOINTS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "SIGI-CMBV/1.0 (gerador interno de indicacoes; Camara Municipal de Boa Vista-RR)"}

CACHE_PATH = DATA_DIR / "cache_geo.json"
CACHE_TTL = timedelta(days=7)

# Tipos de via considerados "ruas" para indicações de infraestrutura
HIGHWAY_REGEX = "^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|road)$"
SURFACE_SEM_PAVIMENTO = {"unpaved", "dirt", "ground", "earth", "sand", "gravel", "fine_gravel",
                         "compacted", "mud", "grass"}

_MINUSCULAS = {"de", "da", "do", "das", "dos", "e"}


class GeoServiceError(RuntimeError):
    """Falha ao consultar o OpenStreetMap/Overpass."""


# --------------------------------------------------------------------------- #
# Cache em disco
# --------------------------------------------------------------------------- #
def _ler_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gravar_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def _cache_get(chave: str, aceitar_vencido: bool = False):
    item = _ler_cache().get(chave)
    if not item:
        return None
    idade = datetime.now() - datetime.fromisoformat(item["quando"])
    if idade <= CACHE_TTL or aceitar_vencido:
        return item["dados"]
    return None


def _cache_set(chave: str, dados) -> None:
    cache = _ler_cache()
    cache[chave] = {"quando": datetime.now().isoformat(timespec="seconds"), "dados": dados}
    _gravar_cache(cache)


def limpar_cache() -> None:
    if CACHE_PATH.exists():
        CACHE_PATH.unlink()


# --------------------------------------------------------------------------- #
# Núcleo: requisição à Overpass
# --------------------------------------------------------------------------- #
def _consultar_overpass(query: str, tentativas_por_endpoint: int = 1,
                        log: Callable[[str], None] | None = None) -> dict:
    """Envia a query a cada espelho até obter JSON válido."""
    ultimo_erro = "sem resposta"
    for endpoint in ENDPOINTS:
        for tentativa in range(1, tentativas_por_endpoint + 1):
            try:
                resp = requests.post(endpoint, data={"data": query}, headers=HEADERS, timeout=(5, 45))
                if resp.status_code == 200:
                    dados = resp.json()
                    # Overpass devolve 200 com "remark" quando o espelho está com problema
                    # (timeout, memória, banco de áreas ausente...): tenta o próximo espelho.
                    if dados.get("remark") and not dados.get("elements"):
                        ultimo_erro = f"{dados['remark'][:120]} em {endpoint}"
                    else:
                        return dados
                else:
                    ultimo_erro = f"HTTP {resp.status_code} em {endpoint}"
                    if resp.status_code == 400:  # erro de sintaxe: não adianta repetir
                        raise GeoServiceError(f"Consulta inválida: {resp.text[:200]}")
            except GeoServiceError:
                raise
            except (requests.RequestException, ValueError) as exc:
                ultimo_erro = f"{type(exc).__name__} em {endpoint}"
            if log:
                log(f"Overpass: {ultimo_erro} (tentativa {tentativa})")
            time.sleep(1.5 * tentativa)
    raise GeoServiceError(f"Overpass indisponível — {ultimo_erro}")


def _titulo(nome: str) -> str:
    """'31 de março' -> '31 de Março' (mantém preposições em minúsculas)."""
    partes = nome.strip().split(" ")
    saida = []
    for i, p in enumerate(partes):
        if i > 0 and p.lower() in _MINUSCULAS:
            saida.append(p.lower())
        elif p[:1].isalpha() and p == p.lower():
            saida.append(p[:1].upper() + p[1:])
        else:
            saida.append(p)
    return " ".join(saida)


# --------------------------------------------------------------------------- #
# Bairros
# --------------------------------------------------------------------------- #
_AREA_CIDADE = f"area({AREA_BOA_VISTA_RR})->.cidade;"


# Nomes alternativos no OSM -> (chave normalizada, nome de exibição) canônicos.
ALIASES_BAIRRO = {
    "estados": ("bairro dos estados", "Bairro dos Estados"),
    "treze de setembro": ("13 de setembro", "13 de Setembro"),
    "silvio leite": ("doutor silvio leite", "Doutor Sílvio Leite"),
    "distrito industrial governador aquilino mota duarte": ("distrito industrial", "Distrito Industrial"),
}


def _baixar_bairros(log=None) -> dict:
    query = f"""[out:json][timeout:60];
{_AREA_CIDADE}
(
  rel(area.cidade)["boundary"="administrative"]["admin_level"="10"]["name"];
  node(area.cidade)["place"="suburb"]["name"];
);
out tags center;"""
    dados = _consultar_overpass(query, log=log)

    bairros: dict[str, dict] = {}
    for el in dados.get("elements", []):
        nome = el.get("tags", {}).get("name")
        if not nome:
            continue
        chave = normalizar(nome)
        nome_exib = _titulo(nome)
        if chave in ALIASES_BAIRRO:
            chave, nome_exib = ALIASES_BAIRRO[chave]
        b = bairros.setdefault(chave, {"nome": nome_exib, "rel_ids": [], "ponto": None})
        if el["type"] == "relation":
            b["rel_ids"].append(el["id"])
            if not b["ponto"] and "center" in el:
                b["ponto"] = [el["center"]["lat"], el["center"]["lon"]]
        elif el["type"] == "node":
            b["ponto"] = [el["lat"], el["lon"]]
            b["node_id"] = el["id"]
    if not bairros:
        raise GeoServiceError("O OSM não retornou bairros para Boa Vista/RR.")
    return bairros


def listar_bairros(forcar: bool = False, log=None) -> tuple[list[str], str]:
    """
    Retorna (nomes_ordenados, origem) onde origem é 'osm', 'cache' ou 'lista local'.
    """
    if not forcar:
        cache = _cache_get("bairros")
        if cache:
            return sorted((b["nome"] for b in cache.values()), key=normalizar), "cache"
    try:
        bairros = _baixar_bairros(log)
        _cache_set("bairros", bairros)
        return sorted((b["nome"] for b in bairros.values()), key=normalizar), "osm"
    except GeoServiceError:
        velho = _cache_get("bairros", aceitar_vencido=True)
        if velho:
            return sorted((b["nome"] for b in velho.values()), key=normalizar), "cache"
        return list(BAIRROS_BOA_VISTA), "lista local"


def _localizar_bairro(nome: str) -> dict | None:
    cache = _cache_get("bairros", aceitar_vencido=True) or {}
    alvo = normalizar(nome)
    if alvo in cache:
        return cache[alvo]
    # tolerância: "Dr. Silvio Botelho" x "Silvio Botelho", "Bairro dos Estados" x "Estados"
    for chave, b in cache.items():
        if alvo.endswith(chave) or chave.endswith(alvo):
            return b
    return None


# --------------------------------------------------------------------------- #
# Ruas
# --------------------------------------------------------------------------- #
def _consulta_ruas(bairro: dict) -> str:
    filtro = f'["highway"~"{HIGHWAY_REGEX}"]["name"]'
    if bairro.get("rel_ids"):
        rels = "".join(f"rel({i});" for i in bairro["rel_ids"])
        return f"""[out:json][timeout:60];
({rels})->.r;
.r map_to_area->.b;
way(area.b){filtro};
out tags center;"""
    # Bairro mapeado só como ponto (sem polígono): raio de 900 m ao redor do ponto
    lat, lon = bairro["ponto"]
    return f"""[out:json][timeout:60];
way(around:900,{lat},{lon}){filtro};
out tags center;"""


def _agrupar_ruas(elementos: list[dict]) -> list[dict]:
    """Une os trechos (ways) de mesmo nome numa única rua, preservando coordenadas centrais."""
    ruas: dict[str, dict] = {}
    for el in elementos:
        tags = el.get("tags", {})
        nome = (tags.get("name") or "").strip()
        if not nome:
            continue
        chave = normalizar(nome)
        ponto = None
        if "center" in el:
            ponto = [el["center"]["lat"], el["center"]["lon"]]
        elif "lat" in el and "lon" in el:
            ponto = [el["lat"], el["lon"]]

        r = ruas.setdefault(chave, {"nome": nome, "highway": tags.get("highway", ""),
                                    "sem_pavimento": False, "trechos": 0, "ponto": ponto})
        if not r.get("ponto") and ponto:
            r["ponto"] = ponto
        r["trechos"] += 1
        if tags.get("surface") in SURFACE_SEM_PAVIMENTO:
            r["sem_pavimento"] = True
    return sorted(ruas.values(), key=lambda r: normalizar(r["nome"]))


def buscar_ruas_por_bairro(bairro: str, forcar: bool = False, log=None) -> list[dict]:
    """
    Recebe o nome do bairro (ex.: 'Cauamé', 'Pintolândia', 'Centro') e devolve as ruas
    contidas nele, como [{'nome', 'highway', 'sem_pavimento', 'trechos', 'ponto'}], em ordem alfabética.

    Lança GeoServiceError se o OSM estiver inacessível e não houver cache.
    """
    chave_cache = f"ruas::{normalizar(bairro)}"
    if not forcar:
        cache = _cache_get(chave_cache)
        if cache is not None:
            return cache

    try:
        info = _localizar_bairro(bairro)
        if info is None:  # lista de bairros ainda não baixada
            try:
                _cache_set("bairros", _baixar_bairros(log))
            except GeoServiceError:
                pass
            info = _localizar_bairro(bairro)
        if info is None:
            raise GeoServiceError(f"Bairro '{bairro}' não encontrado no OSM.")

        dados = _consultar_overpass(_consulta_ruas(info), log=log)
        ruas = _agrupar_ruas(dados.get("elements", []))
        _cache_set(chave_cache, ruas)
        return ruas
    except GeoServiceError:
        velho = _cache_get(chave_cache, aceitar_vencido=True)
        if velho is not None:
            return velho
        raise


def nomes_ruas(bairro: str, **kw) -> list[str]:
    return [r["nome"] for r in buscar_ruas_por_bairro(bairro, **kw)]


# --------------------------------------------------------------------------- #
# Geração de Mapas & Croquis Oficiais com Pins Georreferenciados
# --------------------------------------------------------------------------- #
def _latlon_para_tile(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    lat_r = math.radians(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return x, y


def _criar_croqui_esquematico(largura: int, altura: int, titulo: str, subtitulo: str, lat: float, lon: float) -> Image.Image:
    """Croqui vetorial elegante de contingência quando azulejos de satélite/mapa estiverem sem conexão."""
    img = Image.new("RGB", (largura, altura), color="#0F172A")
    draw = ImageDraw.Draw(img)

    # Grade técnica
    for x in range(0, largura, 40):
        draw.line([(x, 0), (x, altura)], fill="#1E293B", width=1)
    for y in range(0, altura, 40):
        draw.line([(0, y), (largura, y)], fill="#1E293B", width=1)

    # Vias simuladas em cruz
    cx, cy = largura // 2, (altura - 48) // 2
    draw.rectangle([0, cy - 14, largura, cy + 14], fill="#1E2E50")
    draw.line([0, cy, largura, cy], fill="#38BDF8", width=2)
    draw.rectangle([cx - 14, 0, cx + 14, altura - 48], fill="#1E2E50")
    draw.line([cx, 0, cx, altura - 48], fill="#38BDF8", width=2)

    # Rosa dos ventos simplificada
    draw.text((largura - 45, 12), "N ↑", fill="#94A3B8")

    # Marcador central (Pin GPS)
    px, py = cx, cy
    draw.ellipse([px - 10, py + 12, px + 10, py + 18], fill=(0, 0, 0, 160))
    draw.polygon([(px - 12, py), (px + 12, py), (px, py + 16)], fill="#DC2626")
    draw.ellipse([px - 14, py - 24, px + 14, py + 4], fill="#DC2626", outline="#991B1B", width=2)
    draw.ellipse([px - 6, py - 16, px + 6, py - 4], fill="#FFFFFF")

    # Rodapé institucional
    banner_h = 48
    draw.rectangle([0, altura - banner_h, largura, altura], fill="#080D1A")
    draw.line([0, altura - banner_h, largura, altura - banner_h], fill="#F59E0B", width=2)
    draw.text((14, altura - banner_h + 6), (titulo or "INDICAÇÃO DE INFRAESTRUTURA")[:80], fill="#F8FAFC")
    draw.text((14, altura - banner_h + 26), f"{subtitulo} · Coords: {lat:.5f}, {lon:.5f}", fill="#94A3B8")

    return img


def gerar_imagem_mapa(lat: float, lon: float, titulo: str = "", subtitulo: str = "",
                      largura: int = 650, altura: int = 360, zoom: int = 16) -> bytes:
    """
    Gera print institucional do mapa centrado em (lat, lon) com pin GPS e cabeçalho/rodapé oficial.
    Utiliza azulejos OpenStreetMap / CartoDB com cache e contingência esquemática.
    """
    CACHE_MAPAS_DIR.mkdir(parents=True, exist_ok=True)
    chave_md5 = hashlib.md5(f"{lat:.5f}_{lon:.5f}_{zoom}_{titulo}_{subtitulo}_{largura}_{altura}".encode()).hexdigest()
    arquivo_cache = CACHE_MAPAS_DIR / f"mapa_{chave_md5}.png"
    if arquivo_cache.exists():
        return arquivo_cache.read_bytes()

    x, y = _latlon_para_tile(lat, lon, zoom)
    tile_x, tile_y = int(x), int(y)
    offset_x = int((x - tile_x) * 256)
    offset_y = int((y - tile_y) * 256)

    canvas = Image.new("RGB", (3 * 256, 3 * 256), color="#E2E8F0")
    headers = {"User-Agent": "SIGI-CMBV/1.0 (Camara Municipal de Boa Vista - RR)"}

    def _baixar_tile(dx: int, dy: int):
        tx, ty = tile_x + dx, tile_y + dy
        url = f"https://tile.openstreetmap.org/{zoom}/{tx}/{ty}.png"
        try:
            resp = requests.get(url, headers=headers, timeout=2.0)
            if resp.status_code == 200:
                return (dx, dy), Image.open(io.BytesIO(resp.content)).convert("RGB")
        except Exception:
            pass
        return (dx, dy), None

    sucesso_tiles = 0
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=9) as executor:
        tarefas = [executor.submit(_baixar_tile, dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        for f in concurrent.futures.as_completed(tarefas):
            (dx, dy), img_tile = f.result()
            if img_tile is not None:
                canvas.paste(img_tile, ((dx + 1) * 256, (dy + 1) * 256))
                sucesso_tiles += 1

    if sucesso_tiles < 3:
        # Se não conseguiu baixar azulejos, gera croqui institucional estilizado
        final_img = _criar_croqui_esquematico(largura, altura, titulo, subtitulo, lat, lon)
    else:
        # Recorta área central de (largura x altura)
        cx = 256 + offset_x
        cy = 256 + offset_y
        box = (cx - largura // 2, cy - altura // 2, cx + largura // 2, cy + altura // 2)
        final_img = canvas.crop(box)
        draw = ImageDraw.Draw(final_img)

        # Desenha o Marcador GPS (Pin) no centro exato da rua
        px, py = largura // 2, altura // 2
        draw.ellipse([px - 10, py + 12, px + 10, py + 18], fill=(50, 50, 50, 120))
        draw.polygon([(px - 12, py), (px + 12, py), (px, py + 16)], fill="#DC2626")
        draw.ellipse([px - 14, py - 24, px + 14, py + 4], fill="#DC2626", outline="#991B1B", width=2)
        draw.ellipse([px - 6, py - 16, px + 6, py - 4], fill="#FFFFFF")

        # Faixa institucional inferior
        banner_h = 44
        draw.rectangle([0, altura - banner_h, largura, altura], fill="#0D1629")
        draw.line([0, altura - banner_h, largura, altura - banner_h], fill="#F59E0B", width=2)
        txt_tit = (titulo or "DEMANDA LEGISLATIVA").upper()[:75]
        txt_sub = (subtitulo or "Boa Vista / RR")[:85]
        draw.text((12, altura - banner_h + 5), txt_tit, fill="#F8FAFC")
        draw.text((12, altura - banner_h + 23), f"{txt_sub} · Coordenadas: {lat:.4f}, {lon:.4f}", fill="#94A3B8")

    buf = io.BytesIO()
    final_img.save(buf, format="PNG")
    conteudo = buf.getvalue()
    try:
        arquivo_cache.write_bytes(conteudo)
    except Exception:
        pass
    return conteudo


def obter_coordenadas_rua(rua: str, bairro: str) -> tuple[float, float]:
    """Retorna (lat, lon) de uma rua ou cai de volta para as coordenadas do bairro / Boa Vista."""
    # 1. Tenta buscar no cache de ruas do bairro
    chave_b = normalizar(bairro)
    cache_ruas = _cache_get(f"ruas::{chave_b}") or []
    chave_r = normalizar(rua)
    for r in cache_ruas:
        if normalizar(r.get("nome", "")) == chave_r and r.get("ponto"):
            return float(r["ponto"][0]), float(r["ponto"][1])

    # 2. Tenta buscar nas coordenadas do bairro
    cache_bairros = _cache_get("bairros") or {}
    if chave_b in cache_bairros and cache_bairros[chave_b].get("ponto"):
        p = cache_bairros[chave_b]["ponto"]
        return float(p[0]), float(p[1])

    # 3. Padrão: Centro de Boa Vista - RR
    return 2.8235, -60.6758


def obter_mapa_rua(rua: str, bairro: str, tipo_servico: str = "") -> bytes:
    """Gera o print oficial do mapa para inclusão direta no documento da indicação."""
    lat, lon = obter_coordenadas_rua(rua, bairro)
    tit = f"Demanda: {tipo_servico} · {rua}" if tipo_servico else rua
    sub = f"Bairro {bairro} — Boa Vista/RR"
    return gerar_imagem_mapa(lat, lon, titulo=tit, subtitulo=sub)

