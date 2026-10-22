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

try:
    from utils import obter_centroide_bairro
except ImportError:
    _CENTROIDES_FALLBACK: dict[str, tuple[float, float]] = {
        "13 de setembro": (2.7985268, -60.6859828),
        "31 de marco": (2.8382857, -60.6707996),
        "aeroporto": (2.8412095, -60.7081436),
        "alvorada": (2.8193735, -60.7518051),
        "asa branca": (2.8133925, -60.7214194),
        "bairro dos estados": (2.8456344, -60.6700971),
        "bela vista": (2.7708789, -60.72384),
        "buritis": (2.8149517, -60.7091259),
        "cacari": (2.849888, -60.6514545),
        "caimbe": (2.8226526, -60.7168106),
        "calunga": (2.8054308, -60.6765191),
        "cambara": (2.8136037, -60.7310263),
        "canarinho": (2.8345, -60.6582439),
        "carana": (2.839746, -60.721722),
        "cauame": (2.8485289, -60.7120887),
        "centenario": (2.7960596, -60.7124904),
        "centro": (2.819611, -60.6711632),
        "cidade satelite": (2.8444229, -60.7465232),
        "cinturao verde": (2.8039145, -60.7088478),
        "distrito industrial": (2.7635135, -60.7144414),
        "doutor airton rocha": (2.7674016, -60.7572412),
        "doutor silvio leite": (2.8215119, -60.7416242),
        "dr airton rocha": (2.7674016, -60.7572412),
        "dr silvio botelho": (2.8013255, -60.7424217),
        "dr silvio leite": (2.8215119, -60.7416242),
        "equatorial": (2.8184254, -60.7664732),
        "estados": (2.8456052, -60.669641),
        "jardim floresta": (2.8301981, -60.7100944),
        "jardim primavera": (2.8245869, -60.7344581),
        "jardim tropical": (2.7946992, -60.7334586),
        "joquei clube": (2.8046491, -60.7264193),
        "laura moreira": (2.8005162, -60.7872681),
        "liberdade": (2.8192364, -60.7005652),
        "mecejana": (2.8243788, -60.6876267),
        "nova canaa": (2.8150202, -60.7407219),
        "nova cidade": (2.7650202, -60.730845),
        "olimpico": (2.8022024, -60.7347069),
        "operario": (2.7786593, -60.7455088),
        "paraviana": (2.856586, -60.6591133),
        "pedra pintada": (2.8822767, -60.6866022),
        "pintolandia": (2.8067035, -60.7485165),
        "piscicultura": (2.8351304, -60.735663),
        "pricuma": (2.8102035, -60.6976568),
        "professora araceli souto maior": (2.7875362, -60.7242869),
        "raiar do sol": (2.7741627, -60.7193381),
        "santa luzia": (2.8076877, -60.7546758),
        "santa tereza": (2.8275784, -60.73056),
        "sao bento": (2.7815558, -60.7151151),
        "sao francisco": (2.831568, -60.6755466),
        "sao pedro": (2.8269956, -60.6637205),
        "sao vicente": (2.8103919, -60.6828635),
        "senador helio campos": (2.7928175, -60.7533669),
        "silvio botelho": (2.8013255, -60.7424217),
        "silvio leite": (2.8256714, -60.740009),
        "tancredo neves": (2.8232436, -60.7252115),
        "treze de setembro": (2.7984266, -60.6830477),
        "uniao": (2.8454504, -60.7292707),
    }

    def obter_centroide_bairro(nome: str) -> tuple[float, float]:
        alvo = normalizar(nome)
        if alvo in _CENTROIDES_FALLBACK:
            return _CENTROIDES_FALLBACK[alvo]
        for k, v in _CENTROIDES_FALLBACK.items():
            if alvo.endswith(k) or k.endswith(alvo) or (len(k) > 4 and k in alvo):
                return v
        return (2.819611, -60.6711632)


CACHE_MAPAS_DIR = DATA_DIR / "cache_mapas"

# Município de Boa Vista/RR no OSM: relação 326286 (a 301450 é Boa Vista/PB).
# Em Overpass, id de área = id da relação + 3 600 000 000.
REL_BOA_VISTA_RR = 326286
AREA_BOA_VISTA_RR = 3_600_000_000 + REL_BOA_VISTA_RR

# Espelhos rápidos da Overpass API
ENDPOINTS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
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
# Núcleo: requisição à Overpass (com timeout rápido e proteção contra congelamento)
# --------------------------------------------------------------------------- #
def _consultar_overpass(query: str, tentativas_por_endpoint: int = 1,
                        log: Callable[[str], None] | None = None) -> dict:
    """Envia a query a cada espelho com timeout curto para não travar a aplicação."""
    ultimo_erro = "sem resposta"
    for endpoint in ENDPOINTS:
        for tentativa in range(1, tentativas_por_endpoint + 1):
            try:
                resp = requests.post(endpoint, data={"data": query}, headers=HEADERS, timeout=(2, 6))
                if resp.status_code == 200:
                    dados = resp.json()
                    if dados.get("remark") and not dados.get("elements"):
                        ultimo_erro = f"{dados['remark'][:100]} em {endpoint}"
                    else:
                        return dados
                else:
                    ultimo_erro = f"HTTP {resp.status_code} em {endpoint}"
                    if resp.status_code == 400:
                        raise GeoServiceError(f"Consulta inválida: {resp.text[:200]}")
            except GeoServiceError:
                raise
            except (requests.RequestException, ValueError) as exc:
                ultimo_erro = f"{type(exc).__name__} em {endpoint}"
            if log:
                log(f"Overpass: {ultimo_erro} (tentativa {tentativa})")
            time.sleep(0.3 * tentativa)
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
    Abre instantaneamente (< 0.05s) sem travar a interface do Streamlit.
    """
    if not forcar:
        cache = _cache_get("bairros", aceitar_vencido=True)
        if cache:
            return sorted((b["nome"] for b in cache.values()), key=normalizar), "cache"
        # Se cache não existir ainda, retorna a lista local imediatamente para inicialização instantânea
        return list(BAIRROS_BOA_VISTA), "lista local"

    try:
        bairros = _baixar_bairros(log)
        _cache_set("bairros", bairros)
        return sorted((b["nome"] for b in bairros.values()), key=normalizar), "osm"
    except Exception:
        velho = _cache_get("bairros", aceitar_vencido=True)
        if velho:
            return sorted((b["nome"] for b in velho.values()), key=normalizar), "cache"
        return list(BAIRROS_BOA_VISTA), "lista local"


def _localizar_bairro(nome: str) -> dict:
    """Retorna os metadados do bairro garantindo coordenadas válidas mesmo offline."""
    cache = _cache_get("bairros", aceitar_vencido=True) or {}
    alvo = normalizar(nome)
    if alvo in cache:
        return cache[alvo]
    # tolerância: "Dr. Silvio Botelho" x "Silvio Botelho", "Bairro dos Estados" x "Estados"
    for chave, b in cache.items():
        if alvo == chave or alvo.endswith(chave) or chave.endswith(alvo):
            return b
    for chave, b in cache.items():
        if len(chave) > 3 and (chave in alvo or alvo in chave):
            return b
    # Ponto de referência oficial do centroide consolidado do bairro específico
    pt = list(obter_centroide_bairro(nome))
    return {"nome": nome, "rel_ids": [], "ponto": pt}


# --------------------------------------------------------------------------- #
# Ruas
# --------------------------------------------------------------------------- #
def _consulta_ruas(bairro: dict) -> str:
    filtro = f'["highway"~"{HIGHWAY_REGEX}"]["name"]'
    if bairro.get("rel_ids"):
        rels = "".join(f"rel({i});" for i in bairro["rel_ids"])
        return f"""[out:json][timeout:15];
({rels})->.r;
.r map_to_area->.b;
way(area.b){filtro};
out tags center;"""
    # Bairro mapeado só como ponto (sem polígono): raio de 900 m ao redor do ponto
    lat, lon = bairro["ponto"]
    return f"""[out:json][timeout:15];
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


def _buscar_ruas_locais_db(bairro: str) -> list[dict]:
    """Busca vias no acervo histórico local do SIGI/SAPL quando o OSM estiver inacessível."""
    try:
        from database import _conn
        b_norm = normalizar(bairro)
        ponto_bairro = list(obter_centroide_bairro(bairro))
        with _conn() as con:
            rows = con.execute(
                "SELECT DISTINCT rua FROM sapl_materias WHERE (bairro_norm = ? OR bairro_norm LIKE ?) AND rua != ''",
                (b_norm, f"%{b_norm}%")
            ).fetchall()
            saida = []
            for r in rows:
                nome_r = r[0].strip()
                if len(nome_r) >= 3 and not nome_r.lower().startswith("sn") and not nome_r.lower().startswith("s/n"):
                    saida.append({
                        "nome": nome_r,
                        "highway": "residential",
                        "sem_pavimento": False,
                        "trechos": 1,
                        "ponto": None
                    })
            saida.sort(key=lambda x: normalizar(x["nome"]))
            return saida
    except Exception:
        return []


def buscar_ruas_por_bairro(bairro: str, forcar: bool = False, log=None) -> list[dict]:
    """
    Recebe o nome do bairro (ex.: 'Centro', 'Cauamé', 'Pintolândia') e devolve as ruas
    contidas nele. Nunca trava a tela e utiliza múltiplas camadas de contingência.
    """
    chave_cache = f"ruas::{normalizar(bairro)}"
    if not forcar:
        cache = _cache_get(chave_cache, aceitar_vencido=True)
        if cache:
            return cache

    # Tenta consultar o OpenStreetMap via Overpass API com timeout rápido
    try:
        info = _localizar_bairro(bairro)
        dados = _consultar_overpass(_consulta_ruas(info), log=log)
        ruas = _agrupar_ruas(dados.get("elements", []))
        if ruas:
            _cache_set(chave_cache, ruas)
            return ruas
    except Exception:
        pass

    # 1º Fallback: cache existente (mesmo que antigo)
    velho = _cache_get(chave_cache, aceitar_vencido=True)
    if velho:
        return velho

    # 2º Fallback: vias já catalogadas no banco de matérias legislativas locais
    ruas_db = _buscar_ruas_locais_db(bairro)
    if ruas_db:
        _cache_set(chave_cache, ruas_db)
        return ruas_db

    return []


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
        # Prioriza azulejos oficiais do Google Maps (Roadmap oficial) com fallback
        urls = [
            f"https://mt1.google.com/vt/lyrs=m&x={tx}&y={ty}&z={zoom}",
            f"https://mt0.google.com/vt/lyrs=m&x={tx}&y={ty}&z={zoom}",
            f"https://mt2.google.com/vt/lyrs=m&x={tx}&y={ty}&z={zoom}",
            f"https://mt3.google.com/vt/lyrs=m&x={tx}&y={ty}&z={zoom}",
            f"https://a.basemaps.cartocdn.com/rastertiles/voyager/{zoom}/{tx}/{ty}.png",
            f"https://tile.openstreetmap.org/{zoom}/{tx}/{ty}.png",
        ]
        for u in urls:
            try:
                resp = requests.get(u, headers=headers, timeout=2.0)
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


def geocodificar_rua_precisa(rua: str, bairro: str = "") -> tuple[float, float] | None:
    """
    Geocodificação multi-motor com precisão métrica para Boa Vista/RR:
    1. Google Maps Geocoding API (se chave configurada ou no ambiente)
    2. Photon (Komoot / OSM) centrado nas coordenadas de Boa Vista/RR (2.82, -60.67)
    3. Nominatim (OpenStreetMap) estruturado com parâmetros de logradouro
    """
    chave_cache = f"geo_precisa::{normalizar(rua)}::{normalizar(bairro)}"
    cached = _cache_get(chave_cache, aceitar_vencido=True)
    if cached and isinstance(cached, list) and len(cached) == 2:
        return float(cached[0]), float(cached[1])

    # 1. Google Maps Geocoding API (se GOOGLE_MAPS_API_KEY configurada)
    import os
    g_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not g_key:
        try:
            cfg_p = DATA_DIR / "config_maps.json"
            if cfg_p.exists():
                import json
                g_key = json.loads(cfg_p.read_text(encoding="utf-8")).get("google_maps_api_key")
        except Exception:
            pass

    if g_key:
        try:
            q_g = f"{rua}, {bairro}, Boa Vista - RR, Brasil"
            resp_g = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": q_g, "key": g_key},
                timeout=3.0
            )
            if resp_g.status_code == 200:
                res = resp_g.json().get("results", [])
                if res:
                    loc = res[0]["geometry"]["location"]
                    lat, lon = float(loc["lat"]), float(loc["lng"])
                    if 2.5 <= lat <= 3.2 and -61.1 <= lon <= -60.4:
                        _cache_set(chave_cache, [lat, lon])
                        return lat, lon
        except Exception:
            pass

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SIGI-CMBV/1.0"}
    consultas = [
        f"{rua}, {bairro}, Boa Vista",
        f"{rua}, Boa Vista, Roraima",
        f"{rua}, Boa Vista",
    ]

    # 2. Photon (Komoot / OSM) com viés geográfico em Boa Vista (2.8196, -60.6711)
    for q in consultas:
        try:
            resp_p = requests.get(
                "https://photon.komoot.io/api/",
                params={"q": q, "lat": 2.8196, "lon": -60.6711, "limit": 3},
                headers=headers,
                timeout=3.0
            )
            if resp_p.status_code == 200:
                features = resp_p.json().get("features", [])
                for feat in features:
                    props = feat.get("properties", {})
                    city = str(props.get("city", "") or props.get("state", "")).lower()
                    if "boa vista" in city or "roraima" in city or not props.get("city"):
                        coords = feat.get("geometry", {}).get("coordinates", [])
                        if len(coords) == 2:
                            lon, lat = float(coords[0]), float(coords[1])
                            if 2.5 <= lat <= 3.2 and -61.1 <= lon <= -60.4:
                                _cache_set(chave_cache, [lat, lon])
                                return lat, lon
        except Exception:
            pass

    # 3. Nominatim (OpenStreetMap) estruturado
    for q in consultas:
        try:
            resp_n = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": q, "format": "json", "limit": 2, "countrycodes": "br"},
                headers={"User-Agent": "SIGI-CMBV-Gabinete/1.0 (gab.italootavio@cmbv.rr.gov.br)"},
                timeout=3.0
            )
            if resp_n.status_code == 200:
                dados = resp_n.json()
                if dados:
                    lat = float(dados[0]["lat"])
                    lon = float(dados[0]["lon"])
                    if 2.5 <= lat <= 3.2 and -61.1 <= lon <= -60.4:
                        _cache_set(chave_cache, [lat, lon])
                        return lat, lon
        except Exception:
            pass

    return None


def obter_coordenadas_rua(rua: str, bairro: str) -> tuple[float, float]:
    """
    Retorna (lat, lon) georreferenciados precisos para a rua e bairro em Boa Vista/RR.
    1. Geometria real no cache (apenas se for ponto verificado e diferente do centroide genérico).
    2. Geocodificação multi-motor de alta precisão (Google Maps / Photon / Nominatim).
    3. Fallback inteligente: Centroide do bairro somente se a rua não for encontrada em nenhum mapa.
    """
    chave_b = normalizar(bairro)
    chave_r = normalizar(rua)
    cb_lat, cb_lon = obter_centroide_bairro(bairro)

    # 1. Verifica no cache se há ponto real verificado
    cache_ruas = _cache_get(f"ruas::{chave_b}", aceitar_vencido=True) or []
    for r in cache_ruas:
        if normalizar(r.get("nome", "")) == chave_r and r.get("ponto"):
            pt = r["ponto"]
            # Descarta se o ponto for idêntico ao centroide genérico do bairro
            if abs(float(pt[0]) - cb_lat) > 0.0001 or abs(float(pt[1]) - cb_lon) > 0.0001:
                return float(pt[0]), float(pt[1])

    # 2. Geocodificação multi-motor em tempo real (Google Maps + Photon + Nominatim)
    pt_geo = geocodificar_rua_precisa(rua, bairro)
    if pt_geo:
        # Atualiza no cache de ruas para futuras consultas serem instantâneas
        for r in cache_ruas:
            if normalizar(r.get("nome", "")) == chave_r:
                r["ponto"] = list(pt_geo)
                _cache_set(f"ruas::{chave_b}", cache_ruas)
                break
        return pt_geo

    # 3. Fallback: Centroide exato do bairro
    return cb_lat, cb_lon


def validar_rua(rua: str, bairro: str) -> dict:
    """
    Verifica a precisão cartográfica da rua e suas coordenadas em Boa Vista/RR.
    Retorna dict com status de validação, nível de precisão, fonte e coordenadas.
    """
    chave_b = normalizar(bairro)
    chave_r = normalizar(rua)
    cache_ruas = _cache_get(f"ruas::{chave_b}", aceitar_vencido=True) or []

    # 1. Correspondência exata no bairro
    for r in cache_ruas:
        if normalizar(r.get("nome", "")) == chave_r and r.get("ponto"):
            return {
                "valida": True,
                "precisao": "Alta (Ponto Exato OSM)",
                "fonte": "Malha Viária OpenStreetMap",
                "coordenadas": (float(r["ponto"][0]), float(r["ponto"][1])),
                "icone": "🟢",
            }

    # 2. Correspondência aproximada no bairro
    for r in cache_ruas:
        nome_norm = normalizar(r.get("nome", ""))
        if (chave_r in nome_norm or nome_norm in chave_r) and r.get("ponto"):
            return {
                "valida": True,
                "precisao": "Alta (Aproximada OSM)",
                "fonte": f"OpenStreetMap ({r['nome']})",
                "coordenadas": (float(r["ponto"][0]), float(r["ponto"][1])),
                "icone": "🟢",
            }

    # 3. Geocodificação Nominatim
    pt_nom = _geocodificar_nominatim(rua, bairro)
    if pt_nom:
        return {
            "valida": True,
            "precisao": "Boa (GPS Nominatim)",
            "fonte": "OpenStreetMap Nominatim",
            "coordenadas": pt_nom,
            "icone": "🟡",
        }

    # 4. Centroide oficial do Bairro
    pt_b = obter_centroide_bairro(bairro)
    return {
        "valida": False,
        "precisao": "Média (Centroide do Bairro)",
        "fonte": f"Centroide Oficial ({bairro})",
        "coordenadas": pt_b,
        "icone": "🟠",
    }


def obter_mapa_rua(rua: str, bairro: str, tipo_servico: str = "") -> bytes:
    """Gera o print oficial do mapa para inclusão direta no documento da indicação."""
    lat, lon = obter_coordenadas_rua(rua, bairro)
    tit = f"Demanda: {tipo_servico} · {rua}" if tipo_servico else rua
    sub = f"Bairro {bairro} — Boa Vista/RR"
    return gerar_imagem_mapa(lat, lon, titulo=tit, subtitulo=sub)


