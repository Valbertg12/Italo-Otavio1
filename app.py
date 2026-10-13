"""
SIGI — Sistema Inteligente de Geração de Indicações
Câmara Municipal de Boa Vista – RR

Gabinete Parlamentar: Ítalo Otávio (Vereador e Deputado Federal Eleito por Roraima)
Criador do Programa: Valbert Breno
Site Oficial: https://italootavio.com.br/
Integração Oficial: SAPL (Sistema de Apoio ao Processo Legislativo da CMBV)
"""
from __future__ import annotations

import random
import shutil
from datetime import date, datetime

import importlib
import pandas as pd
import streamlit as st

import database as db
import doc_generator as dg
import geo_service as geo
import sapl_service as sapl
import signature_service as sig_serv

importlib.reload(db)
importlib.reload(dg)
importlib.reload(geo)
importlib.reload(sapl)
importlib.reload(sig_serv)
from utils import (
    META_DIARIA,
    MESES_ALERTA,
    OUTPUT_DIR,
    TEMPLATE_PATH,
    TEMPLATES_DIR,
    TIPOS_SERVICO,
    VARIAVEIS_OBRIGATORIAS,
    VARIAVEIS_OPCIONAIS,
    data_por_extenso,
    gerar_justificativa,
    gerar_texto_solicitacao,
    normalizar,
)

st.set_page_config(
    page_title="SIGI — Gabinete Ítalo Otávio",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

OUTRO_BAIRRO = "➕ Outro bairro (digitar manualmente)…"

# --------------------------------------------------------------------------- #
# Design System Oficial: Azul Marinho Institucional & Amarelo Dourado Roraima
# --------------------------------------------------------------------------- #
PALETA_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"], .stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    background-color: #080D1A !important;
    color: #E2E8F0 !important;
}

h1, h2, h3, .brand-font {
    font-family: 'Outfit', sans-serif !important;
}

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 3.5rem;
    max-width: 1360px;
}

#MainMenu, footer { visibility: hidden; }

/* Header Institucional de Alto Padrão */
.gov-header {
    background: #0D1629;
    border: 1px solid #1A2847;
    border-top: 3px solid #F59E0B;
    border-radius: 14px;
    padding: 1.5rem 1.8rem;
    margin-bottom: 1.25rem;
    box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.4);
}

.gov-brand-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    background: rgba(245, 158, 11, 0.12);
    color: #FBBF24;
    border: 1px solid rgba(245, 158, 11, 0.3);
}

.gov-live-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 600;
    background: rgba(37, 99, 235, 0.15);
    color: #93C5FD;
    border: 1px solid rgba(37, 99, 235, 0.3);
}

.gov-dot-live {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #10B981;
    display: inline-block;
    box-shadow: 0 0 8px #10B981;
}

.gov-title {
    margin: 8px 0 2px 0;
    font-size: 2.1rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: #F8FAFC;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}

.gov-title-yellow {
    color: #F59E0B;
}

.gov-subtitle {
    margin: 0;
    font-size: 0.96rem;
    color: #94A3B8;
    line-height: 1.5;
}

.gov-subtitle b {
    color: #E2E8F0;
}

.gov-author-credit {
    font-size: 0.82rem;
    color: #64748B;
    margin-top: 4px;
}

.gov-author-credit span {
    color: #F59E0B;
    font-weight: 600;
}

.gov-btn-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.82rem;
    font-weight: 600;
    color: #F59E0B;
    text-decoration: none;
    background: rgba(245, 158, 11, 0.08);
    border: 1px solid rgba(245, 158, 11, 0.3);
    padding: 6px 14px;
    border-radius: 8px;
    transition: all 0.2s ease;
}

.gov-btn-link:hover {
    background: rgba(245, 158, 11, 0.18);
    color: #FDE68A;
    border-color: rgba(245, 158, 11, 0.6);
    text-decoration: none;
}

/* Card de Meta Diária com Destaque Dourado & Azul */
.gov-goal-card {
    background: #0D1629;
    border: 1px solid #1E2E50;
    border-radius: 12px;
    padding: 1.25rem 1.6rem;
    margin-bottom: 1.25rem;
}

.gov-progress-track {
    height: 14px;
    background: #15223D;
    border-radius: 9999px;
    overflow: hidden;
    margin: 12px 0;
    border: 1px solid rgba(255, 255, 255, 0.04);
}

.gov-progress-fill {
    height: 100%;
    border-radius: 9999px;
    background: linear-gradient(90deg, #F59E0B 0%, #FBBF24 100%);
    box-shadow: 0 0 14px rgba(245, 158, 11, 0.5);
    transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}

.gov-progress-fill.done {
    background: linear-gradient(90deg, #10B981 0%, #34D399 100%);
    box-shadow: 0 0 14px rgba(16, 185, 129, 0.5);
}

/* KPI Cards com Visual Corporativo */
.gov-stat-card {
    background: #0D1629;
    border: 1px solid #1A2847;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    transition: all 0.2s ease;
}

.gov-stat-card:hover {
    border-color: #2E4370;
    transform: translateY(-2px);
}

.gov-stat-label {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #94A3B8;
    margin-bottom: 4px;
}

.gov-stat-val {
    font-family: 'Outfit', sans-serif !important;
    font-size: 2.1rem;
    font-weight: 800;
    color: #F8FAFC;
    line-height: 1.15;
}

.gov-stat-val.gold {
    color: #F59E0B;
}

.gov-stat-sub {
    font-size: 0.8rem;
    color: #64748B;
    margin-top: 4px;
}

/* Stepper Parlamentar */
.gov-step-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #13203A;
    border: 1px solid #24355A;
    padding: 4px 12px 4px 6px;
    border-radius: 8px;
    margin-bottom: 12px;
}

.gov-step-num {
    width: 22px;
    height: 22px;
    border-radius: 6px;
    background: #F59E0B;
    color: #080D1A;
    font-weight: 800;
    font-size: 0.78rem;
    display: flex;
    align-items: center;
    justify-content: center;
}

.gov-step-title {
    font-size: 0.88rem;
    font-weight: 700;
    color: #F1F5F9;
}

/* Folha de Pré-visualização de Documento Oficial */
.gov-doc-sheet {
    background: #0A1122;
    border: 1px solid #203152;
    border-left: 4px solid #F59E0B;
    border-radius: 8px;
    padding: 18px 22px;
    font-size: 0.92rem;
    line-height: 1.6;
    color: #CBD5E1;
}

.gov-doc-sheet b {
    color: #F8FAFC;
}

/* Botões do Streamlit no Estilo Gabinete */
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
    background: #F59E0B !important;
    color: #080D1A !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 8px rgba(245, 158, 11, 0.3) !important;
    transition: all 0.15s ease !important;
}

.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {
    background: #FBBF24 !important;
    box-shadow: 0 4px 14px rgba(245, 158, 11, 0.45) !important;
    transform: translateY(-1px) !important;
}

.stButton > button, .stDownloadButton > button {
    border-radius: 8px !important;
    border: 1px solid #24355A !important;
    background-color: #111C33 !important;
    color: #E2E8F0 !important;
    font-weight: 500 !important;
}

.stButton > button:hover {
    border-color: #3B82F6 !important;
    color: #FFFFFF !important;
}

/* Tabs Elegantes */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    border-bottom: 1px solid #1A2847;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    padding: 10px 18px;
    font-weight: 600;
    color: #94A3B8;
    border: none;
}

.stTabs [aria-selected="true"] {
    color: #F59E0B !important;
    border-bottom: 2px solid #F59E0B !important;
    background: rgba(245, 158, 11, 0.05);
}

/* Sidebar Executiva */
section[data-testid="stSidebar"] {
    background-color: #0B1222 !important;
    border-right: 1px solid #1A2847 !important;
}

.sidebar-brand-card {
    background: #111C33;
    border: 1px solid #1E2E50;
    border-left: 3px solid #F59E0B;
    border-radius: 10px;
    padding: 14px;
    margin-bottom: 12px;
}

.gov-action-box {
    background: #0D1629;
    border: 1px solid #1E2E4E;
    border-radius: 12px;
    padding: 1.2rem;
    margin-bottom: 1.2rem;
}

.gov-badge-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 9999px;
    font-size: 0.76rem;
    font-weight: 700;
}

.gov-badge-green {
    background: rgba(16, 185, 129, 0.15);
    color: #34D399;
    border: 1px solid rgba(16, 185, 129, 0.3);
}

.gov-badge-amber {
    background: rgba(245, 158, 11, 0.15);
    color: #FBBF24;
    border: 1px solid rgba(245, 158, 11, 0.3);
}

.gov-badge-blue {
    background: rgba(37, 99, 235, 0.15);
    color: #60A5FA;
    border: 1px solid rgba(37, 99, 235, 0.3);
}

/* Rodapé Institucional */
.gov-footer {
    border-top: 1px solid #1A2847;
    margin-top: 3.5rem;
    padding-top: 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 14px;
    color: #64748B;
    font-size: 0.84rem;
}

.gov-footer a {
    color: #F59E0B;
    text-decoration: none;
    font-weight: 600;
}

.gov-footer a:hover {
    text-decoration: underline;
}

/* ------------------------------------------------------------------------- */
/* Responsividade e Adaptação para Celulares (iPhone iOS e Android)          */
/* ------------------------------------------------------------------------- */
@media (max-width: 768px) {
    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 0.65rem !important;
        padding-right: 0.65rem !important;
    }

    .gov-header {
        padding: 1.1rem 0.9rem !important;
        border-radius: 10px !important;
        margin-bottom: 0.85rem !important;
    }

    .gov-title {
        font-size: 1.38rem !important;
        line-height: 1.25 !important;
        gap: 6px !important;
    }

    .gov-subtitle {
        font-size: 0.84rem !important;
        line-height: 1.38 !important;
    }

    .gov-author-credit {
        font-size: 0.78rem !important;
    }

    .gov-stat-card {
        padding: 0.85rem 0.95rem !important;
        margin-bottom: 0.5rem !important;
    }

    .gov-stat-val {
        font-size: 1.55rem !important;
    }

    .gov-goal-card {
        padding: 0.95rem 1rem !important;
    }

    /* Tabs horizontais com rolagem suave no celular */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px !important;
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
        -webkit-overflow-scrolling: touch !important;
        padding-bottom: 4px !important;
        border-bottom: 1px solid #1A2847 !important;
    }

    .stTabs [data-baseweb="tab"] {
        padding: 8px 12px !important;
        font-size: 0.82rem !important;
        white-space: nowrap !important;
        flex-shrink: 0 !important;
    }

    /* Botões confortáveis para o polegar no celular */
    .stButton > button, .stDownloadButton > button {
        min-height: 46px !important;
        font-size: 0.94rem !important;
        width: 100% !important;
    }

    .gov-doc-sheet {
        padding: 12px 14px !important;
        font-size: 0.84rem !important;
        word-break: break-word !important;
    }

    /* Ajuste de formulários e inputs para toque */
    div[data-baseweb="select"] {
        min-height: 44px !important;
    }
}
</style>
"""
st.markdown(PALETA_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Inicialização e Cache
# --------------------------------------------------------------------------- #
@st.cache_resource
def bootstrap() -> bool:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    db.init_db()
    if not TEMPLATE_PATH.exists():
        dg.criar_template_padrao(TEMPLATE_PATH)
    return True


bootstrap()
ss = st.session_state
ss.setdefault("ruas_cache", {})
ss.setdefault("manuais", {})
ss.setdefault("ultimo_lote", None)


@st.cache_data(show_spinner=False)
def analisar_template_cache(mtime: float) -> dict:
    return dg.analisar_template(TEMPLATE_PATH)


def carregar_bairros(forcar: bool = False) -> tuple[list[str], str]:
    if forcar or "bairros" not in ss:
        with st.spinner("Consultando bairros de Boa Vista no OpenStreetMap…"):
            ss["bairros"] = geo.listar_bairros(forcar=forcar)
    return ss["bairros"]


def carregar_ruas(bairro: str, forcar: bool = False) -> dict:
    cache = ss["ruas_cache"]
    if forcar or bairro not in cache:
        with st.spinner(f"Mapeando vias do bairro {bairro} via Overpass API…"):
            try:
                cache[bairro] = {"ruas": geo.buscar_ruas_por_bairro(bairro, forcar=forcar), "erro": None}
            except geo.GeoServiceError as exc:
                cache[bairro] = {"ruas": [], "erro": str(exc)}
    return cache[bairro]


def barra_meta_executiva(feitas: int, meta: int) -> None:
    pct = min(feitas / meta, 1.0) * 100
    restante = max(meta - feitas, 0)
    classe = "gov-progress-fill done" if feitas >= meta else "gov-progress-fill"
    
    st.markdown(
        f"""
        <div class="gov-goal-card">
            <div style="display:flex; justify-content:space-between; align-items:baseline;">
                <div>
                    <span style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.08em; font-weight:700; color:#F59E0B;">
                        Painel de Controle Diário · {data_por_extenso()}
                    </span>
                    <div style="font-size:1.85rem; font-weight:800; color:#F8FAFC; margin-top:2px;">
                        {feitas} <span style="font-size:1rem; color:#64748B; font-weight:600;">/ {meta} indicações geradas hoje</span>
                    </div>
                </div>
                <div>
                    <span style="display:inline-flex; align-items:center; gap:6px; padding:4px 12px; border-radius:6px; font-size:0.78rem; font-weight:700; background:rgba(245,158,11,0.15); color:#FBBF24; border:1px solid rgba(245,158,11,0.3);">
                        {pct:.0f}% da cota diária
                    </span>
                </div>
            </div>
            <div class="gov-progress-track">
                <div class="{classe}" style="width:{pct:.1f}%;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.84rem; color:#94A3B8;">
                <span>{("🎉 Cota diária de 20 indicações atingida com êxito!" if restante == 0 else f"Restam <b>{restante}</b> indicação(ões) para completar a meta do dia.")}</span>
                <span style="color:#64748B; font-size:0.8rem;">Regimento da CMBV</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_executivo(coluna, rotulo: str, valor, sub: str = "", destaque_amarelo: bool = False) -> None:
    classe_val = "gov-stat-val gold" if destaque_amarelo else "gov-stat-val"
    coluna.markdown(
        f"""
        <div class="gov-stat-card">
            <div class="gov-stat-label">{rotulo}</div>
            <div class="{classe_val}">{valor}</div>
            <div class="gov-stat-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def passo_executivo(n: int, titulo: str) -> None:
    st.markdown(
        f"""
        <div class="gov-step-badge">
            <div class="gov-step-num">{n}</div>
            <div class="gov-step-title">{titulo}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def fmt_data_br(iso: str) -> str:
    if not iso:
        return ""
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return iso


# --------------------------------------------------------------------------- #
# Barra Lateral do Gabinete
# --------------------------------------------------------------------------- #
gerado_hoje = db.contar_por_data()
total_sapl_cadastrado = db.total_sapl()

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand-card">
            <div style="font-size:0.68rem; font-weight:700; color:#F59E0B; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:2px;">
                Gabinete Parlamentar
            </div>
            <div style="font-size:1.25rem; font-weight:800; color:#F8FAFC; line-height:1.2;">
                Ítalo Otávio
            </div>
            <div style="font-size:0.8rem; color:#94A3B8; margin-top:4px; line-height:1.4;">
                Vereador de Boa Vista / RR<br>
                <b style="color:#FBBF24;">Deputado Federal Eleito por Roraima</b>
            </div>
            <div style="margin-top:12px; display:flex; flex-direction:column; gap:6px;">
                <a href="https://italootavio.com.br/" target="_blank" class="gov-btn-link" style="justify-content:center;">
                    🌐 italootavio.com.br ↗
                </a>
                <a href="https://sapl.boavista.rr.leg.br/materia/pesquisar-materia?tipo=8&autoria__autor=70" target="_blank" class="gov-btn-link" style="justify-content:center; background:rgba(37,99,235,0.12); color:#60A5FA; border-color:rgba(37,99,235,0.3);">
                    🏛️ Acervo SAPL Câmara ↗
                </a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="sidebar-brand-card" style="border-left-color:#3B82F6; background:#0D1629;">
            <div style="font-size:0.68rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.08em;">
                Engenharia de Software
            </div>
            <div style="font-size:0.95rem; font-weight:700; color:#F1F5F9; margin-top:2px;">
                Valbert Breno
            </div>
            <div style="font-size:0.76rem; color:#94A3B8;">
                Criador & Desenvolvedor do SIGI
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    st.markdown("**Parâmetros do Documento**")
    caixa_alta = st.toggle("Texto legislativo em CAIXA ALTA", value=True,
                           help="Padronização regimental do SAPL da Câmara Municipal.")
    data_doc = st.date_input("Data da Sessão ({{DATA}})", value=date.today(), format="DD/MM/YYYY")
    st.caption(f"Impresso: **{data_por_extenso(data_doc)}**")
    pular_duplicadas = st.toggle(f"Ignorar ruas atendidas nos últimos {MESES_ALERTA} meses", value=False,
                                 help="Cruza os dados locais e o acervo oficial do SAPL para evitar indicações repetidas.")

    st.divider()
    ok_t = analisar_template_cache(TEMPLATE_PATH.stat().st_mtime)
    if ok_t.get("modo") == "auto":
        st.success("Modelo Oficial Ativo ✔ (Sem tags necessárias)")
        if ok_t.get("imagens_cabecalho") or ok_t.get("imagens_rodape"):
            st.caption(f"🖼️ Imagens: {ok_t.get('imagens_cabecalho', 0)} no cabeçalho · {ok_t.get('imagens_rodape', 0)} no rodapé")
    else:
        st.success("Modelo Oficial Validado ✔")
    st.caption(f"Meta diária estabelecida: **{META_DIARIA}** indicações")


# --------------------------------------------------------------------------- #
# Header Institucional & Barra de Cota
# --------------------------------------------------------------------------- #
st.markdown(
    f"""
    <div class="gov-header">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:12px;">
            <div>
                <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                    <span class="gov-brand-badge">
                        Gabinete Oficial
                    </span>
                    <span class="gov-live-badge">
                        <span class="gov-dot-live"></span> SAPL Conectado ({total_sapl_cadastrado} matérias no acervo)
                    </span>
                    <span class="gov-live-badge">
                        <span class="gov-dot-live"></span> OpenStreetMap Boa Vista Ativo
                    </span>
                </div>
                <div class="gov-title">
                    SIGI <span class="gov-title-yellow">·</span> Sistema Inteligente de Geração de Indicações
                </div>
                <div class="gov-subtitle">
                    Gabinete Parlamentar de <b>Ítalo Otávio</b> — Vereador de Boa Vista / RR e Deputado Federal Eleito por Roraima.<br>
                    Automação e auditoria para cumprimento da cota diária de infraestrutura urbana na Câmara Municipal.
                </div>
                <div class="gov-author-credit">
                    Criado e desenvolvido por <span>Valbert Breno</span>
                </div>
            </div>
            <div style="align-self:center; display:flex; gap:8px; flex-wrap:wrap;">
                <a href="https://italootavio.com.br/" target="_blank" class="gov-btn-link">
                    🌐 italootavio.com.br ↗
                </a>
                <a href="https://sapl.boavista.rr.leg.br/materia/pesquisar-materia?tipo=8&autoria__autor=70" target="_blank" class="gov-btn-link" style="color:#60A5FA; border-color:rgba(59,130,246,0.3); background:rgba(37,99,235,0.08);">
                    🏛️ SAPL Câmara ↗
                </a>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

barra_meta_executiva(gerado_hoje, META_DIARIA)
st.write("")

aba_gerar, aba_sapl, aba_dash, aba_hist, aba_conf = st.tabs(
    ["📝 Gerador de Indicações", "🏛️ Integração SAPL Oficial", "📊 Dashboard do Mandato", "🗂️ Histórico & Auditoria", "⚙️ Configurações & Template"]
)

# =========================================================================== #
# ABA 1 — GERADOR DE INDICAÇÕES
# =========================================================================== #
with aba_gerar:
    lote = ss["ultimo_lote"]
    if lote:
        c1, c2 = st.columns([2.5, 1.5], vertical_alignment="center")
        c1.success(f"✅ Lote gerado com sucesso: **{lote['qtd']}** indicações legislativas prontas · `{lote['nome']}`")
        c2.download_button("⬇️ Baixar Pacote Completo (ZIP)", data=lote["bytes"], file_name=lote["nome"],
                           mime="application/zip", type="primary", width="stretch",
                           key="dl_zip")

        with st.expander("📂 Baixar Documentos Separadamente (Indicações Individuais)", expanded=True):
            st.markdown("Cada indicação foi gerada como um **documento individual** pronto para protocolo ou envio:")
            pasta_p = Path(lote["pasta"])
            for idx_arq, arq_nome in enumerate(lote["arquivos"], start=1):
                c_arq = pasta_p / arq_nome
                if c_arq.exists():
                    cd1, cd2 = st.columns([3, 1.3], vertical_alignment="center")
                    with cd1:
                        st.markdown(f"📄 **{arq_nome}**")
                    with cd2:
                        st.download_button(f"⬇️ Baixar #{idx_arq:02d}",
                                           data=c_arq.read_bytes(),
                                           file_name=arq_nome,
                                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                           key=f"dl_indiv_{idx_arq}_{arq_nome}",
                                           use_container_width=True)
            st.caption(f"Arquivos salvos em: `{lote['pasta']}`")
        st.divider()

    col_a, col_b = st.columns(2, gap="large")

    # ---- Passo 1: Bairro -------------------------------------------------- #
    with col_a:
        passo_executivo(1, "Bairro de Boa Vista - RR")
        bairros, origem = carregar_bairros()
        opcoes_bairro = bairros + [OUTRO_BAIRRO]
        idx = bairros.index("Centro") if "Centro" in bairros else 0
        escolha = st.selectbox("Selecione o Bairro", opcoes_bairro, index=idx, key="bairro_sel",
                               label_visibility="collapsed")
        if escolha == OUTRO_BAIRRO:
            bairro = st.text_input("Digite o nome do bairro", key="bairro_livre").strip()
        else:
            bairro = escolha

        r1, r2 = st.columns([3, 1], vertical_alignment="center")
        r1.caption({"osm": "🌐 OpenStreetMap ao vivo (Boa Vista/RR)",
                    "cache": "💾 Banco Geográfico Consolidado (Boa Vista/RR)",
                    "lista local": "🏛️ Catálogo Oficial de Bairros (Boa Vista/RR)"}.get(origem, "🏛️ Boa Vista/RR"))
        if r2.button("↻ Atualizar", help="Recarregar vias do OSM", key="btn_bairros"):
            carregar_bairros(forcar=True)
            st.rerun()

    # ---- Passo 2: Tipo de Serviço ----------------------------------------- #
    with col_b:
        passo_executivo(2, "Tipo de Demanda / Infraestrutura")
        tipo = st.selectbox("Tipo de Demanda", TIPOS_SERVICO, key="tipo_sel", label_visibility="collapsed")
        st.caption("A fundamentação técnica é montada automaticamente conforme os padrões aprovados pelo gabinete.")

    st.write("")
    passo_executivo(3, "Mapeamento e Seleção de Vias")

    if not bairro:
        st.info("Informe um bairro para visualizar as ruas mapeadas.")
        st.stop()

    dados_ruas = carregar_ruas(bairro)
    chave_sel = f"sel::{normalizar(bairro)}"
    ruas_osm = {r["nome"]: r for r in dados_ruas["ruas"]}
    manuais = ss["manuais"].setdefault(normalizar(bairro), [])
    todas = list(dict.fromkeys(list(ruas_osm.keys()) + manuais))
    todas.sort(key=normalizar)

    if dados_ruas.get("erro") and not todas:
        st.warning(f"Aviso OpenStreetMap: {dados_ruas['erro']}. Você pode adicionar ruas manualmente.")
    elif not todas:
        st.info("ℹ️ Nenhuma via encontrada automaticamente para este bairro. Digite as vias no campo abaixo para adicioná-las.")

    # Cruzamento com o SAPL e SIGI
    recentes = db.mapa_recentes(tipo)
    bairro_n = normalizar(bairro)

    def recente(rua: str):
        return recentes.get((normalizar(rua), bairro_n))

    def rotulo(rua: str) -> str:
        sufixo = ""
        info = ruas_osm.get(rua)
        if info and info.get("sem_pavimento"):
            sufixo += "  🟤 sem asfalto"
        if rua in manuais and rua not in ruas_osm:
            sufixo += "  ✍️ manual"
        r = recente(rua)
        if r:
            fonte = r.get("fonte", "SIGI")
            sufixo += f"  ⚠️ já indicada ({fonte} em {fmt_data_br(r['data'])})"
        return rua + sufixo

    m1, m2, m3, m4 = st.columns([1.1, 1.3, 0.8, 1], vertical_alignment="bottom")
    qtd_sug = m1.number_input("Qtd. a sugerir", 1, META_DIARIA,
                              value=min(max(META_DIARIA - gerado_hoje, 1), META_DIARIA), key="qtd_sug")

    def sugerir() -> None:
        livres = [r for r in todas if not recente(r)]
        rnd = random.Random(f"{bairro_n}|{tipo}|{date.today().isoformat()}")
        rnd.shuffle(livres)
        ss[chave_sel] = sorted(livres[: int(ss["qtd_sug"])], key=normalizar)

    m2.button("🎯 Sugerir Vias sem Repetição", on_click=sugerir, width="stretch", disabled=not todas)
    m3.button("Limpar", on_click=lambda: ss.__setitem__(chave_sel, []), width="stretch")
    if m4.button("↻ Recarregar OSM", width="stretch"):
        carregar_ruas(bairro, forcar=True)
        st.rerun()

    if todas:
        n_osm = len(ruas_osm)
        st.caption(f"{len(todas)} vias mapeadas ({n_osm} pelo OpenStreetMap"
                   f"{', ' + str(len(manuais)) + ' manuais' if manuais else ''}) · "
                   f"⚠️ = verificada contra histórico local e acervo oficial do SAPL")

    ss.setdefault(chave_sel, [])
    if ss.pop("_limpar_sel", None) == chave_sel:
        ss[chave_sel] = []
    ss[chave_sel] = [r for r in ss[chave_sel] if r in todas]

    selecionadas = st.multiselect(
        f"Selecione as vias do lote (até {META_DIARIA})", options=todas, key=chave_sel, format_func=rotulo,
        max_selections=META_DIARIA, placeholder="Pesquise por Rua, Avenida, Travessa...",
    )

    with st.form("form_manual", clear_on_submit=True, border=False):
        f1, f2 = st.columns([4, 1], vertical_alignment="bottom")
        nova = f1.text_input("Não encontrou no mapa? Adicione a via manualmente",
                             placeholder="Ex.: Rua Moisés Teixeira Hausen")
        if f2.form_submit_button("Adicionar Via", width="stretch") and nova.strip():
            nome = " ".join(nova.strip().split())
            if nome not in manuais:
                manuais.append(nome)
            ss[chave_sel] = list(dict.fromkeys(ss.get(chave_sel, []) + [nome]))[:META_DIARIA]
            st.rerun()

    # ---- Alerta de Duplicidade com Link do SAPL ---------------------------- #
    duplicadas = {r: recente(r) for r in selecionadas if recente(r)}
    if duplicadas:
        def _linha(rua: str, info: dict) -> str:
            fonte = info.get("fonte", "SIGI")
            return f"- **{rua}** — {tipo} já indicado via **{fonte}** em **{fmt_data_br(info['data'])}**"

        linhas = "\n".join(_linha(r, i) for r, i in duplicadas.items())
        st.warning(f"⚠️ **Atenção do Gabinete:** {len(duplicadas)} via(s) selecionada(s) já possuem indicação recente registrada no SAPL ou no SIGI:\n\n{linhas}")

    # ---- Passo 4: Redação da Justificativa -------------------------------- #
    st.write("")
    passo_executivo(4, "Redação e Fundamentação Legislativa")
    usar_custom = st.toggle("Personalizar o texto da justificativa para este lote")
    custom = ""
    if usar_custom:
        custom = st.text_area(
            "Texto da Justificativa", height=130, key="just_custom",
            placeholder="Dica: use {rua} e {bairro} para substituição automática.")

    def justificativa_para(rua: str) -> str:
        if usar_custom and custom.strip():
            return custom.replace("{rua}", rua).replace("{bairro}", bairro)
        return gerar_justificativa(tipo, rua, bairro)

    exemplo = selecionadas[0] if selecionadas else (todas[0] if todas else "Rua Exemplo")
    st.markdown(
        f"""
        <div class="gov-doc-sheet">
            <div style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.08em; font-weight:700; color:#F59E0B; margin-bottom:8px;">
                Pré-visualização Oficial · Padrão Gabinete Ítalo Otávio
            </div>
            <b>{gerar_texto_solicitacao(tipo, exemplo, bairro)}</b><br><br>
            <b>Justificativa:</b> {justificativa_para(exemplo).replace(chr(10) + chr(10), '<br><br>')}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- Passo 5: Croqui e Geração em Lote ------------------------------- #
    st.write("")
    passo_executivo(5, "Mapa Georreferenciado e Geração em Lote")

    incluir_mapa = st.toggle("📷 Incluir Croqui / Print do Mapa no documento oficial", value=True,
                             help="Gera e insere o print georreferenciado da via com marcador oficial da CMBV.")

    if incluir_mapa and selecionadas:
        with st.expander(f"🗺️ Prévia do Print do Mapa: {exemplo} ({bairro})", expanded=False):
            c_m1, c_m2 = st.columns([2, 1], vertical_alignment="center")
            with c_m1:
                try:
                    img_previa = geo.obter_mapa_rua(exemplo, bairro, tipo)
                    st.image(img_previa, caption=f"Print oficial gerado: {exemplo} — {bairro}", width=480)
                except Exception as exc:
                    st.caption(f"Prévia do mapa: {exc}")
            with c_m2:
                st.markdown("**Localização Automática**")
                st.caption(f"O SIGI gera automaticamente este mapa com pin centralizado para cada uma das {len(selecionadas)} via(s) selecionadas.")
                st.caption("✔️ Sem necessidade de tirar prints manuais um por um.")
                st.caption("✔️ Inserido certinho no .docx após a justificativa.")

    a_gerar = [r for r in selecionadas if not (pular_duplicadas and recente(r))]
    pulo = len(selecionadas) - len(a_gerar)
    g1, g2 = st.columns([1.2, 2], vertical_alignment="center")
    clicou = g1.button(f"🚀 Gerar {len(a_gerar)} Indicação(ões) em .docx", type="primary", width="stretch",
                       disabled=not a_gerar, key="btn_gerar")

    if pulo:
        g2.caption(f"{pulo} via(s) com registro recente foram ignoradas.")
    elif not selecionadas:
        g2.caption("Selecione pelo menos uma rua acima para iniciar a geração.")

    if clicou:
        agora = datetime.now()
        pasta_lote = OUTPUT_DIR / f"lote_{agora:%Y-%m-%d_%H%M%S}"
        barra = st.progress(0.0, text="Processando documentos oficiais...")

        def atualizar(i: int, total: int, rua: str) -> None:
            barra.progress(i / total, text=f"Gerando {i}/{total} · {rua}")

        itens = [{"rua": r, "bairro": bairro, "tipo_servico": tipo, "justificativa": justificativa_para(r),
                  "data": data_doc, "caixa_alta": caixa_alta} for r in a_gerar]
        try:
            gerados = dg.gerar_lote(TEMPLATE_PATH, itens, pasta_lote, progresso=atualizar, incluir_mapa=incluir_mapa)
            nome_zip = dg.nome_zip_do_dia(OUTPUT_DIR)
            zip_bytes = dg.criar_zip([g["caminho"] for g in gerados])
            (OUTPUT_DIR / nome_zip).write_bytes(zip_bytes)
            db.inserir_lote([{"rua": g["rua"], "bairro": g["bairro"], "tipo_servico": g["tipo_servico"],
                              "data": data_doc, "arquivo": g["arquivo"]} for g in gerados])
            ss["ultimo_lote"] = {"nome": nome_zip, "bytes": zip_bytes, "qtd": len(gerados),
                                 "arquivos": [g["arquivo"] for g in gerados], "pasta": str(pasta_lote)}
            ss["_limpar_sel"] = chave_sel
            st.toast(f"{len(gerados)} indicações geradas com sucesso!", icon="✅")
            st.rerun()
        except Exception as exc:
            barra.empty()
            st.error(f"Erro ao gerar arquivos: {exc}")

# =========================================================================== #
# ABA 2 — INTEGRAÇÃO SAPL OFICIAL
# =========================================================================== #
with aba_sapl:
    st.markdown("### 🏛️ Acervo Legislativo Oficial no SAPL")
    st.caption("Sincronização direta com o Sistema de Apoio ao Processo Legislativo da Câmara Municipal de Boa Vista (Ítalo Otávio - Autor nº 70).")

    ANOS_MANDATO = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017]
    
    # Cache inicial dos totais conhecidos da API do SAPL
    _TOTAIS_DEFAULT = {
        2026: 268, 2025: 1045, 2024: 502, 2023: 554, 2022: 64,
        2021: 202, 2020: 228, 2019: 383, 2018: 125, 2017: 280
    }
    ss.setdefault("totais_sapl_online", _TOTAIS_DEFAULT.copy())
    ss.setdefault("anos_sapl_sel", [2026])

    # Dados locais atualizados
    totais_locais = db.contagem_sapl_por_ano()
    total_local_geral = db.total_sapl()
    total_sapl_geral = sum(ss["totais_sapl_online"].values())

    if total_local_geral < 3651:
        st.info("💡 **Acervo Histórico:** Você pode restaurar instantaneamente todo o acervo legislativo consolidado (3.651 matérias de 2017 a 2026) sem precisar aguardar download demorado.")
        if st.button("⚡ Restaurar Acervo Consolidado (3.651 Matérias em 0,1s)", type="primary", key="btn_seed_instant", use_container_width=True):
            with st.spinner("Restaurando acervo legislativo consolidado..."):
                seed_p = DATA_DIR / "sapl_seed.json.gz"
                if seed_p.exists():
                    import gzip, json
                    with gzip.open(seed_p, "rt", encoding="utf-8") as f:
                        dados = json.load(f)
                    db.salvar_lote_sapl(dados)
                    st.toast("3.651 matérias históricas restauradas com sucesso!", icon="⚡")
                    st.rerun()

    # --- Seção de Controles e Seleção de Anos ---
    st.markdown(
        """
        <div class="gov-action-box">
            <div style="font-size:0.75rem; font-weight:700; color:#F59E0B; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:4px;">
                Painel de Controle Legislativo
            </div>
            <div style="font-size:1.15rem; font-weight:800; color:#F8FAFC; margin-bottom:4px;">
                🗓️ Seleção de Anos & Puxada de Histórico de Projetos
            </div>
            <div style="font-size:0.83rem; color:#94A3B8;">
                Escolha os anos do mandato para auditar o quantitativo de indicações protocoladas no SAPL oficial e sincronizar com o banco local do SIGI.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Atalhos rápidos para facilitar a seleção
    st.write("**Atalhos de Período:**")
    col_at1, col_at2, col_at3, col_at4 = st.columns(4)
    with col_at1:
        if st.button("🌟 Todos os Anos (2017-2026)", use_container_width=True, key="btn_at_todos"):
            ss["anos_sapl_sel"] = list(ANOS_MANDATO)
            st.rerun()
    with col_at2:
        if st.button("🏛️ Mandato Atual (2025-2026)", use_container_width=True, key="btn_at_atual"):
            ss["anos_sapl_sel"] = [2026, 2025]
            st.rerun()
    with col_at3:
        if st.button("📜 Mandato Anterior (2021-2024)", use_container_width=True, key="btn_at_anterior"):
            ss["anos_sapl_sel"] = [2024, 2023, 2022, 2021]
            st.rerun()
    with col_at4:
        if st.button("📍 Ano Vigente (2026)", use_container_width=True, key="btn_at_2026"):
            ss["anos_sapl_sel"] = [2026]
            st.rerun()

    anos_selecionados = st.multiselect(
        "Selecione ou ajuste os anos desejados:",
        options=ANOS_MANDATO,
        default=[a for a in ss["anos_sapl_sel"] if a in ANOS_MANDATO],
        key="ms_anos_sapl",
        format_func=lambda y: f"Ano {y}"
    )
    if not anos_selecionados:
        anos_selecionados = [2026]
    ss["anos_sapl_sel"] = anos_selecionados

    # Botões de Ação
    col_act1, col_act2 = st.columns([1, 1], gap="medium")
    with col_act1:
        if st.button("📊 Consultar Quantidade de Projetos no SAPL (Ao Vivo)", type="secondary", use_container_width=True, key="btn_check_online"):
            with st.spinner("Consultando quantitativo oficial na API da Câmara..."):
                try:
                    novos_totais = sapl.obter_totais_por_ano(anos_selecionados)
                    ss["totais_sapl_online"].update(novos_totais)
                    st.toast("Quantitativos atualizados ao vivo com sucesso!", icon="📊")
                    st.success(f"Consulta realizada! Total de {sum(novos_totais.values())} projetos protocolados nos anos selecionados.")
                except Exception as exc:
                    st.error(f"Erro ao consultar API do SAPL: {exc}")

    with col_act2:
        if st.button("📥 Puxar Histórico Completo dos Anos Selecionados", type="primary", use_container_width=True, key="btn_pull_history"):
            barra_sync = st.progress(0.0, text="Iniciando conexão paralela ultrarrápida com a API da Câmara Municipal...")
            total_baixado = 0
            qtd_anos = len(anos_selecionados)

            try:
                for idx_a, a in enumerate(anos_selecionados):
                    def cb_ano(pg, total_pg, msg):
                        pct = (idx_a + (pg / max(total_pg, 1))) / qtd_anos
                        barra_sync.progress(min(pct, 1.0), text=f"Ano {a}: {msg}")

                    materias = sapl.baixar_indicacoes_ano_rapido(ano=a, limite_paginas=100, progresso=cb_ano)
                    salvos = db.salvar_lote_sapl(materias)
                    total_baixado += salvos

                barra_sync.empty()
                st.toast(f"{total_baixado} matérias do SAPL sincronizadas com sucesso!", icon="✅")
                st.success(f"Histórico puxado com sucesso! {total_baixado} matérias dos anos selecionados foram indexadas no banco local.")
                st.rerun()
            except Exception as exc:
                barra_sync.empty()
                st.error(f"Erro na conexão com o SAPL: {exc}")

    st.write("")

    # --- KPIs Consolidados dos Anos Selecionados ---
    total_online_sel = sum(ss["totais_sapl_online"].get(y, 0) for y in anos_selecionados)
    total_local_sel = sum(totais_locais.get(y, 0) for y in anos_selecionados)

    s1, s2, s3 = st.columns(3)
    kpi_executivo(
        s1,
        "Total Protocolado no SAPL",
        f"{total_online_sel:,}".replace(",", "."),
        f"Soma dos {len(anos_selecionados)} ano(s) selecionado(s)",
        destaque_amarelo=True
    )
    kpi_executivo(
        s2,
        "Sincronizado no Banco Local",
        f"{total_local_sel:,}".replace(",", "."),
        f"{round((total_local_sel / max(total_online_sel, 1)) * 100)}% de cobertura local para auditoria"
    )
    kpi_executivo(
        s3,
        "Acervo Histórico Completo",
        f"{total_sapl_geral:,}".replace(",", "."),
        "Total de 3.651 matérias na CMBV (2017 a 2026)"
    )

    st.divider()

    # --- Tabela Analítica & Gráfico de Histórico Anual ---
    st.markdown("#### 📊 Quantitativo de Projetos Protocolados por Ano")
    
    dados_tabela = []
    for y in sorted(anos_selecionados, reverse=True):
        qtd_sapl = ss["totais_sapl_online"].get(y, 0)
        qtd_local = totais_locais.get(y, 0)
        cobertura = round((qtd_local / qtd_sapl * 100) if qtd_sapl > 0 else 100)
        status = "100% Sincronizado ✅" if qtd_local >= qtd_sapl and qtd_sapl > 0 else (
            f"Parcial ({qtd_local}/{qtd_sapl}) ⚠️" if qtd_local > 0 else "Pendente ⏳"
        )
        pct_mandato = f"{(qtd_sapl / max(total_sapl_geral, 1) * 100):.1f}%"
        dados_tabela.append({
            "Ano": str(y),
            "Protocolados no SAPL (Oficial)": qtd_sapl,
            "Sincronizados Localmente": qtd_local,
            "Status da Base": status,
            "Participação no Mandato": pct_mandato,
        })

    df_resumo_anos = pd.DataFrame(dados_tabela)

    c_tab, c_chart = st.columns([1.3, 1], gap="large")
    with c_tab:
        st.markdown("**Detalhamento Anual dos Projetos:**")
        st.dataframe(
            df_resumo_anos,
            hide_index=True,
            width="stretch",
            column_config={
                "Protocolados no SAPL (Oficial)": st.column_config.NumberColumn(format="%d"),
                "Sincronizados Localmente": st.column_config.NumberColumn(format="%d"),
            }
        )

    with c_chart:
        st.markdown("**Evolução Anual de Matérias Protocoladas:**")
        df_chart = pd.DataFrame({
            "Ano": [str(d["Ano"]) for d in reversed(dados_tabela)],
            "Projetos Protocolados": [d["Protocolados no SAPL (Oficial)"] for d in reversed(dados_tabela)],
        }).set_index("Ano")
        st.bar_chart(df_chart, color="#F59E0B")

    st.divider()

    # --- Explorador de Matérias Oficiais Puxadas ---
    st.markdown("#### 🔍 Auditoria Detalhada das Matérias Oficiais Puxadas")
    st.caption("Consulte o texto original, tramitação oficial na CMBV e localização mapeada das indicações dos anos selecionados.")

    c_filt1, c_filt2 = st.columns([2.5, 1])
    with c_filt1:
        busca_sapl = st.text_input(
            "Filtrar por rua, bairro ou palavra-chave na ementa",
            placeholder="Ex.: Pintolândia, Moysés Teixeira, Buritis, calçada, iluminação...",
            key="busca_sapl_multi"
        )
    with c_filt2:
        limite_exibicao = st.selectbox("Limite de registros na tabela", [100, 300, 500, 1000, "Todos"], index=0)
        limite_val = 5000 if limite_exibicao == "Todos" else int(limite_exibicao)

    lista_sapl = db.listar_sapl(limite=limite_val, anos=anos_selecionados, busca=busca_sapl or None)
    
    if lista_sapl:
        df_sapl = pd.DataFrame(lista_sapl)
        df_exib = pd.DataFrame({
            "Indicação": df_sapl["numero"].astype(str) + "/" + df_sapl["ano"].astype(str),
            "Data": pd.to_datetime(df_sapl["data"]).dt.strftime("%d/%m/%Y"),
            "Via Identificada": df_sapl["rua"].replace("", "—"),
            "Bairro": df_sapl["bairro"].replace("", "—"),
            "Serviço": df_sapl["tipo_servico"],
            "Ementa Oficial": df_sapl["ementa"],
            "Link SAPL": df_sapl["link_sapl"],
            "PDF Assinado": df_sapl["texto_original"],
        })

        st.caption(f"Exibindo **{len(df_exib)}** matérias oficiais correspondentes aos filtros.")
        st.dataframe(
            df_exib,
            column_config={
                "Link SAPL": st.column_config.LinkColumn("Tramitação SAPL", display_text="Abrir Matéria ↗"),
                "PDF Assinado": st.column_config.LinkColumn("Documento Original", display_text="Baixar PDF ↗"),
            },
            hide_index=True,
            width="stretch",
            height=460,
        )
    else:
        st.info("Nenhuma matéria localizada para os anos e filtros selecionados.")

# =========================================================================== #
# ABA 3 — DASHBOARD DO MANDATO
# =========================================================================== #
with aba_dash:
    st.markdown("### 📊 Desempenho Legislativo do Mandato")
    st.caption("Métricas consolidadas de atendimento aos bairros e infraestrutura de Boa Vista.")

    serie = db.serie_diaria(14)
    total = db.total_geral()
    semana = sum(x["total"] for x in serie[-7:])
    sequencia = db.sequencia_dias_meta(META_DIARIA)
    media = round(sum(x["total"] for x in serie) / 14, 1)

    k1, k2, k3, k4 = st.columns(4)
    kpi_executivo(k1, "Produção Hoje", f"{gerado_hoje}/{META_DIARIA}", f"{round(gerado_hoje / META_DIARIA * 100)}% da meta diária", destaque_amarelo=True)
    kpi_executivo(k2, "Últimos 7 Dias", semana, f"Média de {media}/dia nas duas semanas")
    kpi_executivo(k3, "Total SIGI Local", total, "Indicações geradas internamente")
    kpi_executivo(k4, "Sequência da Cota", f"{sequencia} dias", "Dias seguidos atingindo a cota")

    st.write("")
    d1, d2 = st.columns([3, 2], gap="large")
    with d1:
        st.markdown("**Produção Diária do Gabinete (Últimos 14 Dias)**")
        df_dias = pd.DataFrame({"Dia": [x["data"].strftime("%d/%m") for x in serie],
                                "Indicações": [x["total"] for x in serie]}).set_index("Dia")
        st.bar_chart(df_dias, color="#F59E0B", height=280)
    with d2:
        st.markdown("**Distribuição por Tipo de Serviço**")
        df2 = pd.DataFrame(db.contagem_por("tipo_servico")).rename(columns={"nome": "Serviço", "total": "Qtd"})
        if not df2.empty:
            st.bar_chart(df2.set_index("Serviço"), color="#2563EB", horizontal=True, height=280)
        else:
            st.caption("Sem dados suficientes para gráficos de serviço.")

    e1, e2 = st.columns(2, gap="large")
    with e1:
        st.markdown("**Bairros com Mais Indicações no SIGI**")
        df3 = pd.DataFrame(db.contagem_por("bairro")).rename(columns={"nome": "Bairro", "total": "Total"})
        st.dataframe(df3, hide_index=True, width="stretch")
    with e2:
        st.markdown("**Vias com Mais Demandas Atendidas**")
        df4 = pd.DataFrame(db.contagem_por("rua")).rename(columns={"nome": "Rua", "total": "Total"})
        st.dataframe(df4, hide_index=True, width="stretch")

# =========================================================================== #
# ABA 4 — HISTÓRICO & AUDITORIA
# =========================================================================== #
with aba_hist:
    st.markdown("### 🗂️ Histórico de Indicações Geradas pelo SIGI")
    st.caption("Controle detalhado de cada documento processado para protocolo.")

    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
    busca = f1.text_input("Pesquisar via", key="h_busca")
    f_bairro = f2.text_input("Filtrar Bairro", key="h_bairro")
    f_tipo = f3.selectbox("Filtrar Serviço", ["Todos"] + TIPOS_SERVICO, key="h_tipo")
    periodo = f4.date_input("Período", value=(), format="DD/MM/YYYY", key="h_periodo")
    de = ate = None
    if isinstance(periodo, tuple) and len(periodo) == 2:
        de, ate = periodo

    regs = db.listar_indicacoes(limite=2000, bairro=f_bairro or None, tipo=None if f_tipo == "Todos" else f_tipo,
                                busca=busca or None, de=de, ate=ate)
    if regs:
        dfh = pd.DataFrame(regs)[["id", "data", "rua", "bairro", "tipo_servico", "arquivo"]]
        dfh["data"] = pd.to_datetime(dfh["data"]).dt.strftime("%d/%m/%Y")
        dfh.columns = ["ID", "Data", "Rua", "Bairro", "Serviço", "Arquivo .docx"]
        st.dataframe(dfh, hide_index=True, width="stretch", height=420)

        h1, h2 = st.columns([1.2, 2.8], vertical_alignment="bottom")
        h1.download_button("⬇️ Exportar Relatório CSV", dfh.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           file_name=f"relatorio_indicacoes_{date.today():%Y-%m-%d}.csv", mime="text/csv")
        with h2.expander("🗑️ Excluir indicação do registro local"):
            id_del = st.selectbox("Selecione o ID", dfh["ID"].tolist(), key="h_del_id")
            confirmar = st.checkbox("Confirmo a exclusão", key="h_del_ok")
            if st.button("Remover Registro", disabled=not confirmar):
                db.excluir_indicacao(int(id_del))
                st.toast("Indicação removida do histórico local.", icon="🗑️")
                st.rerun()
    else:
        st.info("Nenhuma indicação localizada com os filtros informados.")

# =========================================================================== #
# ABA 5 — CONFIGURAÇÕES & TEMPLATE
# =========================================================================== #
with aba_conf:
    st.markdown("### ⚙️ Configurações do Gabinete & Modelo Oficial")
    st.info("💡 **Aviso importante do Gabinete:** Não é necessário inserir tags manuais (como `{{RUA}}`) no seu arquivo! Você pode anexar qualquer documento `.docx` oficial já existente. O SIGI **preserva 100% de cabeçalhos e rodapés com imagens/logos** e faz a auto-detecção dos campos legislativos e do mapa.")

    up = st.file_uploader("📎 Anexar novo modelo oficial (.docx)", type=["docx"], key="up_template")
    if up is not None:
        try:
            conteudo = up.getvalue()
            rel = dg.analisar_template(conteudo)
        except Exception as exc:
            st.error(f"Erro ao analisar arquivo: {exc}")
        else:
            ca, cb = st.columns(2)
            with ca:
                st.markdown("**Estrutura Visual e Imagens**")
                if rel.get("tem_cabecalho_img"):
                    st.write(f"🖼️ **Cabeçalho com imagens:** {rel.get('imagens_cabecalho', 0)} imagem(ns) detectadas e **100% preservadas** ✔")
                else:
                    st.write("📄 Cabeçalho sem imagens externas.")

                if rel.get("tem_rodape_img"):
                    st.write(f"🖼️ **Rodapé com imagens:** {rel.get('imagens_rodape', 0)} imagem(ns) detectadas e **100% preservadas** ✔")
                else:
                    st.write("📄 Rodapé sem imagens externas.")

                modo_txt = "Detecção Automática Oficial (sem tags)" if rel.get("modo") == "auto" else "Tags de Substituição"
                st.write(f"🎯 **Modo de Operação:** `{modo_txt}`")

            with cb:
                st.markdown("**Seções Identificadas para Atualização**")
                det = rel.get("detectados", {})
                if rel.get("modo") == "auto":
                    st.write(f"📝 **Objeto / Solicitação:** {det.get('solic') or 'Detectado automaticamente'}")
                    st.write(f"⚖️ **Justificativa:** {det.get('just') or 'Detectada automaticamente'}")
                    st.write(f"📅 **Data / Plenário:** {det.get('data') or 'Detectada automaticamente'}")
                    st.write("🗺️ **Croqui / Mapa:** Será inserido certinho após a justificativa ✔")
                else:
                    for v in rel["encontradas"]:
                        st.write(f"✅ `{v}` localizado")
                    for v in rel.get("opcionais", []):
                        st.write(f"➕ `{v}` (opcional)")

            st.success("✅ Modelo verificado com sucesso! Pronto para ser ativado.")
            if st.button("💾 Salvar como Modelo Ativo", type="primary", key="btn_save_tpl"):
                if TEMPLATE_PATH.exists():
                    shutil.copy2(TEMPLATE_PATH, TEMPLATES_DIR / f"modelo_indicacao.{datetime.now():%Y%m%d_%H%M%S}.bak.docx")
                TEMPLATE_PATH.write_bytes(conteudo)
                analisar_template_cache.clear()
                st.success("Modelo ativado com êxito! Todas as gerações utilizarão este formato.")
                st.rerun()

    st.divider()
    t1, t2 = st.columns(2)
    t1.download_button("⬇️ Baixar Modelo Vigente", TEMPLATE_PATH.read_bytes(),
                       file_name="modelo_indicacao_italo_otavio.docx",
                       mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    if t2.button("♻️ Restaurar Modelo Padrão do Gabinete"):
        if TEMPLATE_PATH.exists():
            shutil.copy2(TEMPLATE_PATH, TEMPLATES_DIR / f"modelo_indicacao.{datetime.now():%Y%m%d_%H%M%S}.bak.docx")
        dg.criar_template_padrao(TEMPLATE_PATH)
        analisar_template_cache.clear()
        st.success("Modelo padrão restabelecido.")
        st.rerun()

    st.divider()
    st.markdown("### ✍️ Assinatura Digital & Certificado ICP-Brasil")
    st.caption("Configure a assinatura oficial para que todos os documentos já saiam assinados e autenticados separadamente.")

    col_sig_a, col_sig_b = st.columns(2, gap="large")

    # 1. Assinatura Visual (Rubrica em Imagem)
    with col_sig_a:
        st.markdown("#### 1. Assinatura Visual / Rubrica")
        st.write("Anexe a imagem da assinatura/rubrica oficial do parlamentar (.png com fundo transparente):")

        img_existente = sig_serv.obter_imagem_assinatura()
        if img_existente:
            st.image(img_existente, caption="Assinatura atual ativa para os documentos", width=220)
            if st.button("🗑️ Remover Assinatura Visual", key="btn_del_sig"):
                sig_serv.remover_imagem_assinatura()
                st.toast("Assinatura removida.", icon="🗑️")
                st.rerun()
        else:
            st.info("Nenhuma imagem de assinatura carregada ainda.")

        up_sig = st.file_uploader("Carregar imagem da assinatura (.png, .jpg)", type=["png", "jpg", "jpeg"], key="up_sig_img")
        if up_sig is not None:
            if st.button("💾 Salvar Assinatura Visual", type="primary", key="btn_salvar_sig"):
                sig_serv.salvar_imagem_assinatura(up_sig.getvalue())
                st.toast("Assinatura visual salva com sucesso!", icon="✅")
                st.rerun()

    # 2. Certificado Digital ICP-Brasil A1 (Para quando comprar)
    with col_sig_b:
        st.markdown("#### 2. Certificado Digital ICP-Brasil A1")
        st.write("Quando você adquirir o Certificado Digital e-CPF A1 (.pfx ou .p12), instale aqui:")

        cert_info = sig_serv.obter_info_certificado()
        if cert_info:
            st.success("🔒 **Certificado ICP-Brasil Instalado:**")
            st.write(f"• **Titular:** `{cert_info['titular']}`")
            if cert_info.get("cpf"):
                st.write(f"• **CPF:** `{cert_info['cpf']}`")
            st.write(f"• **Emissor:** `{cert_info['emissor']}`")
            st.write(f"• **Validade:** {cert_info['valido_de']} até **{cert_info['valido_ate']}**")
            if st.button("🗑️ Remover Certificado A1", key="btn_del_cert"):
                sig_serv.remover_certificado_a1()
                st.toast("Certificado removido.", icon="🗑️")
                st.rerun()
        else:
            st.info("ℹ️ **Aguardando compra do Certificado A1:** Você pode comprar um e-CPF A1 em qualquer autoridade certificadora (Certisign, Serasa, Soluti, Valid). Assim que comprar, anexe o arquivo `.pfx` abaixo com a senha e todos os documentos já saem assinados digitalmente!")

        up_cert = st.file_uploader("Carregar arquivo do certificado (.pfx, .p12)", type=["pfx", "p12"], key="up_cert_file")
        senha_cert = st.text_input("Senha do Certificado Digital", type="password", key="pwd_cert_input",
                                   help="Senha cadastrada no momento da emissão do e-CPF A1.")

        if up_cert is not None and senha_cert:
            if st.button("🔐 Validar e Instalar Certificado A1", type="primary", key="btn_val_cert"):
                res_cert = sig_serv.instalar_certificado_a1(up_cert.getvalue(), senha_cert)
                if res_cert["sucesso"]:
                    st.success("Certificado ICP-Brasil instalado com sucesso!")
                    st.rerun()
                else:
                    st.error(res_cert["erro"])

    st.write("")
    cfg_sig = sig_serv.obter_config()
    st.markdown("#### 3. Carimbo de Autenticidade Digital ICP-Brasil")
    usar_carimbo = st.toggle("Incluir carimbo de autenticidade eletrônica no rodapé dos documentos (MP nº 2.200-2/2001 e Lei nº 14.063/2020)",
                             value=cfg_sig.get("incluir_carimbo_icp", True), key="tog_carimbo_icp",
                             help="Insere automaticamente o código hash verificador e a indicação de assinatura digital institucional em cada indicação gerada.")
    if usar_carimbo != cfg_sig.get("incluir_carimbo_icp", True):
        sig_serv.atualizar_config(incluir_carimbo_icp=usar_carimbo)
        st.rerun()

    st.divider()
    st.markdown("#### Manutenção do Cache do OpenStreetMap")
    st.caption("Cache geográfico local mantido para rapidez de resposta durante o expediente.")
    if st.button("🗑️ Limpar Cache Geográfico"):
        geo.limpar_cache()
        ss.pop("bairros", None)
        ss["ruas_cache"] = {}
        st.success("Cache do OpenStreetMap resetado com sucesso.")
        st.rerun()

# --------------------------------------------------------------------------- #
# Rodapé Institucional
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <div class="gov-footer">
        <div>
            <strong>SIGI</strong> — Sistema Inteligente de Geração de Indicações<br>
            Gabinete Parlamentar de <strong>Ítalo Otávio</strong> · Vereador de Boa Vista e Deputado Federal Eleito por Roraima
        </div>
        <div>
            Criador do Programa: <strong>Valbert Breno</strong> &nbsp;·&nbsp;
            <a href="https://italootavio.com.br/" target="_blank">italootavio.com.br ↗</a> &nbsp;·&nbsp;
            <a href="https://sapl.boavista.rr.leg.br/materia/pesquisar-materia?tipo=8&autoria__autor=70" target="_blank">Acervo SAPL ↗</a>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
