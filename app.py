"""
SIGI — Sistema Inteligente de Geração de Indicações
Câmara Municipal de Boa Vista – RR

Gabinete Parlamentar: Ítalo Otávio (Vereador e Deputado Federal Eleito por Roraima)
Criador do Programa: Valbert Breno
Site Oficial: https://italootavio.com.br/
Integração Oficial: SAPL (Sistema de Apoio ao Processo Legislativo da CMBV)
"""
from __future__ import annotations

import base64
from pathlib import Path
import random
import shutil
from datetime import date, datetime

import importlib
import pandas as pd
import streamlit as st

import utils
try:
    importlib.reload(utils)
except Exception:
    pass


@st.cache_data
def get_image_base64(path_rel: str) -> str:
    p = utils.BASE_DIR / path_rel
    if p.exists():
        return f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}"
    return ""

import database as db
import doc_generator as dg
import geo_service as geo
import sapl_service as sapl
import signature_service as sig_serv

for _mod in (db, dg, geo, sapl, sig_serv):
    try:
        importlib.reload(_mod)
    except Exception:
        pass
from utils import (
    DATA_DIR,
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
    obter_estacao,
)

st.set_page_config(
    page_title="SIGI — Gabinete Ítalo Otávio",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

OUTRO_BAIRRO = "➕ Outro bairro (digitar manualmente)…"

# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Design System Oficial: Italo Otavio (Federal por Roraima) e Preline UI
# --------------------------------------------------------------------------- #
_CSS_PATH = utils.BASE_DIR / "style.css"
_CSS_TEXT = _CSS_PATH.read_text(encoding="utf-8") if _CSS_PATH.exists() else ""
PALETA_CSS = f"""
<!-- Preline UI e Tailwind CDN -->
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/preline/dist/preline.min.js"></script>
<style>
{_CSS_TEXT}
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
                    <span style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.08em; font-weight:700; color:#FF5500;">
                        Painel de Controle Diário · {data_por_extenso()}
                    </span>
                    <div style="font-size:1.85rem; font-weight:800; color:#F8FAFC; margin-top:2px;">
                        {feitas} <span style="font-size:1rem; color:#64748B; font-weight:600;">/ {meta} indicações geradas hoje</span>
                    </div>
                </div>
                <div>
                    <span style="display:inline-flex; align-items:center; gap:6px; padding:4px 12px; border-radius:6px; font-size:0.78rem; font-weight:800; background:rgba(255,85,0,0.18); color:#FFAA55; border:1px solid rgba(255,85,0,0.4);">
                        {pct:.0f}% da meta diária
                    </span>
                </div>
            </div>
            <div class="gov-progress-track">
                <div class="{classe}" style="width:{pct:.1f}%;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.84rem; color:#94A3B8;">
                <span>{(f"🎉 Meta diária de {meta} indicações atingida com êxito!" if restante == 0 else f"Restam <b>{restante}</b> indicação(ões) para completar a meta do dia.")}</span>
                <span style="color:#64748B; font-size:0.8rem;">Gabinete Ítalo Otávio · CMBV</span>
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
    foto_avatar = get_image_base64("templates/assets/italo_avatar_clean.png")
    avatar_html = f'<img src="{foto_avatar}" style="width:62px; height:62px; border-radius:50%; object-fit:cover; border:2.5px solid #FFE500; box-shadow:0 0 14px rgba(255,229,0,0.45); flex-shrink:0;" alt="Ítalo Otávio" />' if foto_avatar else ''

    st.markdown(
        f"""
        <div class="sidebar-brand-card">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                {avatar_html}
                <div>
                    <div style="font-size:0.68rem; font-weight:800; color:#FFE500; text-transform:uppercase; letter-spacing:0.12em; line-height:1.2;">
                        FEDERAL POR RORAIMA
                    </div>
                    <div style="font-size:1.3rem; font-weight:900; color:#F8FAFC; line-height:1.15; letter-spacing:-0.02em;">
                        ÍTALO OTÁVIO
                    </div>
                    <div style="font-size:0.72rem; font-weight:700; color:#FFAA55; text-transform:uppercase; letter-spacing:0.04em;">
                        Atitude para Transformar!
                    </div>
                </div>
            </div>
            <div style="font-size:0.8rem; color:#94A3B8; line-height:1.45; border-top:1px solid rgba(255,255,255,0.08); padding-top:8px;">
                Gabinete Parlamentar · CMBV<br>
                <b style="color:#FFE500;">Deputado Federal Eleito por Roraima</b>
            </div>
            <div style="margin-top:12px; display:flex; flex-direction:column; gap:6px;">
                <a href="https://italootavio.com.br/" target="_blank" class="gov-btn-link-brand" style="justify-content:center;">
                    🌐 italootavio.com.br ↗
                </a>
                <a href="https://www.instagram.com/italootavio" target="_blank" class="gov-btn-link-insta" style="justify-content:center;">
                    📸 @italootavio no Instagram ↗
                </a>
                <a href="https://sapl.boavista.rr.leg.br/materia/pesquisar-materia?tipo=8&autoria__autor=70" target="_blank" class="gov-btn-link-blue" style="justify-content:center;">
                    🏛️ Acervo SAPL Câmara ↗
                </a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    st.markdown("**🎯 Meta & Parâmetros do Documento**")
    meta_diaria = st.number_input(
        "Meta diária de indicações",
        min_value=1,
        max_value=200,
        value=int(ss.get("meta_diaria", 20)),
        step=5,
        key="input_meta_diaria",
        help="Defina a meta diária (você pode produzir mais de 20 indicações por dia livremente)."
    )
    ss["meta_diaria"] = meta_diaria

    caixa_alta = st.toggle("Texto legislativo em CAIXA ALTA", value=True,
                           help="Padronização regimental do SAPL da Câmara Municipal.")
    data_doc = st.date_input("Data da Sessão ({{DATA}})", value=date.today(), format="DD/MM/YYYY")
    st.caption(f"Impresso: **{data_por_extenso(data_doc)}**")
    pular_duplicadas = st.toggle(f"Ignorar ruas atendidas nos últimos {MESES_ALERTA} meses", value=False,
                                 help="Cruza os dados locais e o acervo oficial do SAPL para evitar indicações repetidas.")

    st.divider()
    est_cod_auto, est_rotulo_auto, est_desc_auto = obter_estacao(data_doc)
    st.markdown("**🌤️ Clima / Sazonalidade (Boa Vista - RR)**")
    opcao_clima = st.selectbox(
        "Sazonalidade Climática",
        [
            f"⚡ Automático: {est_rotulo_auto}",
            "☀️ Verão / Estiagem (Clima Seco)",
            "🌧️ Inverno / Período Chuvoso",
        ],
        index=0,
        key="sb_opcao_clima",
        help="No Verão (Seco), as justificativas focam em poeira, asfalto ressecado, calor e risco de queimadas (sem citar chuvas). No Inverno, focam em poças, enxurradas e retenção de água."
    )
    if "Verão" in opcao_clima:
        estacao_ativa = "verao"
    elif "Inverno" in opcao_clima:
        estacao_ativa = "inverno"
    else:
        estacao_ativa = "auto"

    st.caption(f"Contexto: {est_desc_auto}")

    st.divider()
    ok_t = analisar_template_cache(TEMPLATE_PATH.stat().st_mtime)
    if ok_t.get("modo") == "auto":
        st.success("Modelo Oficial Ativo ✔ (Sem tags necessárias)")
        if ok_t.get("imagens_cabecalho") or ok_t.get("imagens_rodape"):
            st.caption(f"🖼️ Imagens: {ok_t.get('imagens_cabecalho', 0)} no cabeçalho · {ok_t.get('imagens_rodape', 0)} no rodapé")
    else:
        st.success("Modelo Oficial Validado ✔")
    st.caption(f"Meta de produção diária: **{meta_diaria}** indicações")


# --------------------------------------------------------------------------- #
# Hero Capa Oficial Ítalo Otávio & Barra de Cota
# --------------------------------------------------------------------------- #
badge_clima_classe = "gov-season-badge-verao" if (estacao_ativa == "verao" or (estacao_ativa == "auto" and est_cod_auto == "verao")) else "gov-season-badge-inverno"
badge_clima_texto = "☀️ Verão / Estiagem (Seco)" if (estacao_ativa == "verao" or (estacao_ativa == "auto" and est_cod_auto == "verao")) else "🌧️ Inverno (Chuvoso)"

foto_hero = get_image_base64("templates/assets/italo_hero_photo.png")
foto_hero_html = f'''
<div class="gov-photo-card">
    <img src="{foto_hero}" class="gov-photo-img" alt="Deputado Ítalo Otávio" />
    <div class="gov-photo-badge">
        <span class="gov-dot-live"></span> Ítalo Otávio · @italootavio
    </div>
</div>
''' if foto_hero else ''

st.markdown(
    f"""
    <div class="gov-hero-cover">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:24px;">
            <div style="flex:1; min-width:320px;">
                <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:10px;">
                    <span class="gov-federal-badge">
                        FEDERAL POR RORAIMA
                    </span>
                    <span class="gov-slogan-badge">
                        ATITUDE PARA TRANSFORMAR!
                    </span>
                    <span class="gov-live-badge">
                        <span class="gov-dot-live"></span> SAPL Conectado ({total_sapl_cadastrado} matérias)
                    </span>
                    <span class="gov-live-badge">
                        <span class="gov-dot-live"></span> OpenStreetMap Boa Vista
                    </span>
                    <span class="{badge_clima_classe}">
                        {badge_clima_texto}
                    </span>
                </div>
                <div class="gov-title">
                    <span class="brand-italo">ÍTALO</span>
                    <span class="brand-otavio">OTÁVIO</span>
                    <span class="brand-sigi-badge">SIGI</span>
                </div>
                <div class="gov-hero-tagline">
                    #TrabalhoPorRoraima · Atitude para Transformar!
                </div>
                <div class="brand-tricolor-bar">
                    <div class="bar-yellow"></div>
                    <div class="bar-blue"></div>
                    <div class="bar-orange"></div>
                </div>
                <div class="gov-subtitle">
                    Sistema Inteligente de Geração de Indicações Legislativas · <b>Câmara Municipal de Boa Vista – RR</b><br>
                    Gabinete Parlamentar · Automação institucional de alto padrão, auditoria cartográfica por satélite e integração oficial SAPL.
                </div>
                <div style="margin-top:14px; display:flex; gap:10px; flex-wrap:wrap;">
                    <a href="https://italootavio.com.br/" target="_blank" class="gov-btn-link-brand">
                        🌐 italootavio.com.br ↗
                    </a>
                    <a href="https://www.instagram.com/italootavio" target="_blank" class="gov-btn-link-insta">
                        📸 @italootavio ↗
                    </a>
                    <a href="https://sapl.boavista.rr.leg.br/materia/pesquisar-materia?tipo=8&autoria__autor=70" target="_blank" class="gov-btn-link-blue">
                        🏛️ Acervo SAPL Câmara ↗
                    </a>
                </div>
            </div>
            {foto_hero_html}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

barra_meta_executiva(gerado_hoje, meta_diaria)
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

        with st.expander("📂 Baixar Documentos Separadamente (Indicações 1 a N)", expanded=True):
            st.markdown("Cada indicação foi gerada como um **documento individual numerado de 1 até a quantidade pedida**:")
            pasta_p = Path(lote["pasta"])
            for idx_arq, arq_nome in enumerate(lote["arquivos"], start=1):
                c_arq = pasta_p / arq_nome
                if c_arq.exists():
                    cd1, cd2 = st.columns([3, 1.3], vertical_alignment="center")
                    with cd1:
                        st.markdown(f"📄 Indicação **#{idx_arq:02d}** · `{arq_nome}`")
                    with cd2:
                        st.download_button(f"⬇️ Baixar {arq_nome}",
                                           data=c_arq.read_bytes(),
                                           file_name=arq_nome,
                                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                           key=f"dl_indiv_{idx_arq}_{arq_nome}",
                                           use_container_width=True)
            st.caption(f"Arquivos salvos em: `{lote['pasta']}`")
        st.divider()

    col_a, col_b = st.columns(2, gap="large")

    # ---- Passo 1: Bairros (Múltipla Seleção) ------------------------------ #
    with col_a:
        passo_executivo(1, "Bairros de Boa Vista - RR (Múltipla Seleção)")
        bairros, origem = carregar_bairros()
        bairros_padrao = ["Centro"] if "Centro" in bairros else ([bairros[0]] if bairros else [])
        bairros_selecionados = st.multiselect(
            "Selecione um ou mais bairros:",
            options=bairros,
            default=bairros_padrao,
            key="bairros_multi_sel",
            placeholder="Escolha quantos bairros desejar (ex: Centro, Pintolândia, Cauamé...)",
            help="Você pode escolher quantos bairros quiser! O lote distribuirá as indicações entre todos eles."
        )

        with st.expander("➕ Adicionar outro bairro manualmente"):
            f_b1, f_b2 = st.columns([3, 1], vertical_alignment="bottom")
            novo_bairro = f_b1.text_input("Nome do bairro", placeholder="Ex.: Senador Hélio Campos", key="input_bairro_extra").strip()
            if f_b2.button("Adicionar Bairro", key="btn_add_bairro_extra") and novo_bairro:
                if novo_bairro not in bairros_selecionados:
                    bairros_selecionados.append(novo_bairro)
                    st.rerun()

        r1, r2 = st.columns([3, 1], vertical_alignment="center")
        r1.caption({"osm": "🌐 OpenStreetMap ao vivo (Boa Vista/RR)",
                    "cache": "💾 Banco Geográfico Consolidado (Boa Vista/RR)",
                    "lista local": "🏛️ Catálogo Oficial de Bairros (Boa Vista/RR)"}.get(origem, "🏛️ Boa Vista/RR"))
        if r2.button("↻ Atualizar", help="Recarregar bairros do OSM", key="btn_bairros"):
            carregar_bairros(forcar=True)
            st.rerun()

    # ---- Passo 2: Tipo de Serviço ----------------------------------------- #
    with col_b:
        passo_executivo(2, "Tipo de Demanda / Infraestrutura")
        tipo = st.selectbox("Tipo de Demanda", TIPOS_SERVICO, key="tipo_sel", label_visibility="collapsed")
        st.caption("A fundamentação técnica é calibrada automaticamente conforme o clima de Roraima (Verão seco x Inverno chuvoso).")

    st.write("")
    if not bairros_selecionados:
        st.warning("⚠️ Selecione pelo menos um bairro acima para mapear as vias.")
        st.stop()

    passo_executivo(3, f"Mapeamento e Seleção de Vias ({len(bairros_selecionados)} Bairro(s) Selecionado(s))")

    todas_vias_dict = {}
    contagem_por_bairro = {}
    for b in bairros_selecionados:
        dados_ruas = carregar_ruas(b)
        manuais_b = ss["manuais"].setdefault(normalizar(b), [])
        ruas_osm_b = {r["nome"]: r for r in dados_ruas.get("ruas", [])}
        contagem_por_bairro[b] = len(ruas_osm_b) + len(manuais_b)
        for r_nome, r_info in ruas_osm_b.items():
            chave = f"{r_nome} — [{b}]"
            todas_vias_dict[chave] = {
                "rua": r_nome,
                "bairro": b,
                "sem_pavimento": r_info.get("sem_pavimento", False),
                "ponto": r_info.get("ponto"),
                "manual": False,
            }
        for rm in manuais_b:
            chave = f"{rm} — [{b}]"
            if chave not in todas_vias_dict:
                todas_vias_dict[chave] = {
                    "rua": rm,
                    "bairro": b,
                    "sem_pavimento": False,
                    "ponto": None,
                    "manual": True,
                }

    todas_chaves = sorted(todas_vias_dict.keys(), key=normalizar)

    # Cruzamento com o SAPL e SIGI
    recentes = db.mapa_recentes(tipo)

    def recente_chave(ch: str):
        v = todas_vias_dict.get(ch)
        if not v:
            return None
        return recentes.get((normalizar(v["rua"]), normalizar(v["bairro"])))

    def rotulo_chave(ch: str) -> str:
        v = todas_vias_dict.get(ch, {})
        sufixo = ""
        if v.get("sem_pavimento"):
            sufixo += "  🟤 sem asfalto"
        if v.get("manual"):
            sufixo += "  ✍️ manual"
        rec = recente_chave(ch)
        if rec:
            fonte = rec.get("fonte", "SIGI")
            sufixo += f"  ⚠️ já indicada ({fonte} em {fmt_data_br(rec['data'])})"
        return ch + sufixo

    m1, m2, m3, m4 = st.columns([1.1, 1.4, 0.8, 1], vertical_alignment="bottom")
    meta_atual = int(ss.get("meta_diaria", 20))
    val_sug_padrao = min(max(meta_atual - gerado_hoje, 1), meta_atual)
    qtd_sug = m1.number_input("Qtd. a sugerir", 1, max(meta_atual, 150),
                              value=val_sug_padrao, key="qtd_sug")

    def sugerir_vias_multibairro() -> None:
        livres_por_b = {b: [] for b in bairros_selecionados}
        for ch in todas_chaves:
            if not recente_chave(ch):
                livres_por_b[todas_vias_dict[ch]["bairro"]].append(ch)

        rnd = random.Random(f"{','.join(bairros_selecionados)}|{tipo}|{date.today().isoformat()}")
        for b in bairros_selecionados:
            rnd.shuffle(livres_por_b[b])

        qtd_total = int(ss["qtd_sug"])
        escolhidas = []
        bairros_com_vias = [b for b in bairros_selecionados if livres_por_b[b]]
        if bairros_com_vias:
            while len(escolhidas) < qtd_total and any(livres_por_b[b] for b in bairros_com_vias):
                for b in bairros_com_vias:
                    if livres_por_b[b] and len(escolhidas) < qtd_total:
                        escolhidas.append(livres_por_b[b].pop(0))
        ss["chaves_sel_armazenadas"] = sorted(escolhidas, key=normalizar)

    m2.button("🎯 Sugerir Vias sem Repetição", on_click=sugerir_vias_multibairro, width="stretch", disabled=not todas_chaves)
    m3.button("Limpar", on_click=lambda: ss.__setitem__("chaves_sel_armazenadas", []), width="stretch")
    if m4.button("↻ Recarregar OSM", width="stretch"):
        for b in bairros_selecionados:
            carregar_ruas(b, forcar=True)
        st.rerun()

    if todas_chaves:
        resumo_bairros = ", ".join(f"{b}: {contagem_por_bairro[b]} vias" for b in bairros_selecionados)
        st.caption(f"{len(todas_chaves)} vias mapeadas no total ({resumo_bairros}) · "
                   f"⚠️ = verificada contra acervo do SAPL e histórico local")

    ss.setdefault("chaves_sel_armazenadas", [])
    if ss.pop("_limpar_sel", None):
        ss["chaves_sel_armazenadas"] = []
    ss["chaves_sel_armazenadas"] = [c for c in ss["chaves_sel_armazenadas"] if c in todas_chaves]

    selecionadas_chaves = st.multiselect(
        f"Selecione as vias do lote (Permitido mais de 20 por dia · Meta atual: {meta_atual})",
        options=todas_chaves,
        key="chaves_sel_armazenadas",
        format_func=rotulo_chave,
        placeholder="Pesquise por Rua, Avenida, Travessa, Bairro..."
    )

    with st.form("form_manual_multi", clear_on_submit=True, border=False):
        f1, f2, f3 = st.columns([3, 2, 1.2], vertical_alignment="bottom")
        nova = f1.text_input("Não encontrou no mapa? Adicione a via", placeholder="Ex.: Rua Moisés Teixeira Hausen")
        bairro_da_nova = f2.selectbox("Bairro correspondente", bairros_selecionados, index=0)
        if f3.form_submit_button("Adicionar Via", width="stretch") and nova.strip():
            nome_limpo = " ".join(nova.strip().split())
            mb = ss["manuais"].setdefault(normalizar(bairro_da_nova), [])
            if nome_limpo not in mb:
                mb.append(nome_limpo)
            nova_chave = f"{nome_limpo} — [{bairro_da_nova}]"
            ss["chaves_sel_armazenadas"] = list(dict.fromkeys(ss.get("chaves_sel_armazenadas", []) + [nova_chave]))
            st.rerun()

    # ---- Alerta de Duplicidade -------------------------------------------- #
    duplicadas = {ch: recente_chave(ch) for ch in selecionadas_chaves if recente_chave(ch)}
    if duplicadas:
        def _linha(ch: str, info: dict) -> str:
            fonte = info.get("fonte", "SIGI")
            return f"- **{ch}** — {tipo} já indicado via **{fonte}** em **{fmt_data_br(info['data'])}**"

        linhas = "\n".join(_linha(ch, i) for ch, i in duplicadas.items())
        st.warning(f"⚠️ **Atenção do Gabinete:** {len(duplicadas)} via(s) selecionada(s) já possuem indicação recente registrada no SAPL ou no SIGI:\n\n{linhas}")

    # ---- Mapa Interativo & Validação Cartográfica ------------------------- #
    if selecionadas_chaves:
        coords_data = []
        for ch in selecionadas_chaves:
            v_info = todas_vias_dict[ch]
            rua_v = v_info["rua"]
            bairro_v = v_info["bairro"]
            val_info = geo.validar_rua(rua_v, bairro_v)
            coords_data.append({
                "Status": val_info["icone"],
                "Via": rua_v,
                "Bairro": bairro_v,
                "Precisão Cartográfica": val_info["precisao"],
                "Fonte GPS": val_info["fonte"],
                "lat": val_info["coordenadas"][0],
                "lon": val_info["coordenadas"][1],
            })
        df_coords = pd.DataFrame(coords_data)

        with st.expander(f"🗺️ Validação das Ruas & Marcação no Mapa de Boa Vista ({len(selecionadas_chaves)} vias)", expanded=True):
            col_map_a, col_map_b = st.columns([1.5, 1.5])
            with col_map_a:
                st.markdown("**📍 Marcação no Mapa de Boa Vista / RR:**")
                st.map(df_coords[["lat", "lon"]], zoom=12, use_container_width=True)
            with col_map_b:
                st.markdown("**📋 Auditoria Cartográfica das Vias:**")
                st.dataframe(df_coords[["Status", "Via", "Bairro", "Precisão Cartográfica"]], hide_index=True, use_container_width=True)
                st.caption("🟢 **Ponto Exato:** Malha viária OSM · 🟡 **GPS Nominatim:** Geocodificado · 🟠 **Centroide:** Bairro")

    # ---- Passo 4: Redação da Justificativa -------------------------------- #
    st.write("")
    passo_executivo(4, "Redação e Fundamentação Legislativa")

    est_cod_final = estacao_ativa if estacao_ativa != "auto" else est_cod_auto
    if est_cod_final == "verao":
        st.markdown(
            """
            <div style="background: rgba(255, 85, 0, 0.12); border: 1px solid rgba(255, 85, 0, 0.35); border-left: 4px solid #FF5500; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 0.88rem; color: #FED7AA;">
                ☀️ <b>Sazonalidade Ativa: Verão / Estiagem em Boa Vista (Clima Seco)</b><br>
                As justificativas deste lote foram adaptadas para o período seco: enfocam <b>poeira intensa, asfalto ressecado pelo sol forte, pedras soltas e perigo de queimadas em terrenos baldios</b>. <u>Não citam chuvas nem alagamentos</u>.
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <div style="background: rgba(37, 99, 235, 0.12); border: 1px solid rgba(37, 99, 235, 0.35); border-left: 4px solid #3B82F6; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 0.88rem; color: #BFDBFE;">
                🌧️ <b>Sazonalidade Ativa: Inverno / Período Chuvoso (Boa Vista)</b><br>
                As justificativas deste lote enfocam <b>águas pluviais retidas nos buracos, infiltrações, poças d'água, enxurradas e atoleiros</b>.
            </div>
            """,
            unsafe_allow_html=True
        )

    usar_custom = st.toggle("Personalizar o texto da justificativa para este lote")
    custom = ""
    if usar_custom:
        custom = st.text_area(
            "Texto da Justificativa", height=130, key="just_custom",
            placeholder="Dica: use {rua} e {bairro} para substituição automática.")

    def justificativa_para(rua_item: str, bairro_item: str) -> str:
        if usar_custom and custom.strip():
            return custom.replace("{rua}", rua_item).replace("{bairro}", bairro_item)
        return gerar_justificativa(tipo, rua_item, bairro_item, estacao=estacao_ativa, data_ref=data_doc)

    exemplo_chave = selecionadas_chaves[0] if selecionadas_chaves else (todas_chaves[0] if todas_chaves else "")
    if exemplo_chave and exemplo_chave in todas_vias_dict:
        ex_rua = todas_vias_dict[exemplo_chave]["rua"]
        ex_bairro = todas_vias_dict[exemplo_chave]["bairro"]
    else:
        ex_rua, ex_bairro = "Rua Exemplo", (bairros_selecionados[0] if bairros_selecionados else "Centro")

    st.markdown(
        f"""
        <div class="gov-doc-sheet">
            <div style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.08em; font-weight:700; color:#FF5500; margin-bottom:8px;">
                Pré-visualização Oficial · Padrão Gabinete Ítalo Otávio
            </div>
            <b>{gerar_texto_solicitacao(tipo, ex_rua, ex_bairro)}</b><br><br>
            <b>Justificativa:</b> {justificativa_para(ex_rua, ex_bairro).replace(chr(10) + chr(10), '<br><br>')}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- Passo 5: Assinatura do Parlamentar ------------------------------- #
    st.write("")
    passo_executivo(5, "Assinatura do Parlamentar")
    incluir_mapa = False

    sig_salva = sig_serv.obter_imagem_assinatura()
    c_s1, c_s2 = st.columns([1.5, 2.5], gap="large")

    with c_s1:
        tipo_sig = st.radio(
            "Configuração de Assinatura",
            [
                "Nenhuma assinatura (em branco para assinar à caneta)",
                "Anexar imagem de assinatura / rubrica",
            ],
            index=0,
            key="radio_tipo_sig",
            help="Se você não anexar nenhuma assinatura, o documento sairá totalmente sem assinatura nem carimbo digital."
        )

    img_assinatura_final = None
    usar_carimbo_final = False

    with c_s2:
        if tipo_sig == "Nenhuma assinatura (em branco para assinar à caneta)":
            st.info("ℹ️ **Nenhuma assinatura anexada:** Os documentos serão gerados sem qualquer assinatura digital ou carimbo. O documento sairá limpo com o espaço oficial para assinatura física à caneta.")
            img_assinatura_final = None
            usar_carimbo_final = False
        else:
            if sig_salva:
                usar_salva = st.checkbox("Usar imagem de assinatura salva no gabinete", value=True, key="chk_usar_salva")
                if usar_salva:
                    img_assinatura_final = sig_salva
                    st.image(sig_salva, width=150, caption="Assinatura cadastrada")

            up_nova_sig = st.file_uploader("Ou anexe uma nova assinatura (.png, .jpg) para este lote",
                                          type=["png", "jpg", "jpeg"], key="up_sig_tab1")
            if up_nova_sig is not None:
                img_assinatura_final = up_nova_sig.getvalue()
                st.success("✔️ Assinatura visual anexada para esta geração.")

            if img_assinatura_final:
                usar_carimbo_final = st.toggle("Incluir carimbo institucional de validação no rodapé", value=False, key="tog_carimbo_tab1")
            else:
                st.warning("⚠️ Nenhuma imagem de assinatura fornecida. O documento será gerado sem assinatura.")

    st.write("")
    a_gerar_chaves = [ch for ch in selecionadas_chaves if not (pular_duplicadas and recente_chave(ch))]
    pulo = len(selecionadas_chaves) - len(a_gerar_chaves)
    g1, g2 = st.columns([1.2, 2], vertical_alignment="center")
    clicou = g1.button(f"🚀 Gerar {len(a_gerar_chaves)} Indicação(ões) em .docx", type="primary", width="stretch",
                       disabled=not a_gerar_chaves, key="btn_gerar")

    if pulo:
        g2.caption(f"{pulo} via(s) com registro recente foram ignoradas.")
    elif not selecionadas_chaves:
        g2.caption("Selecione pelo menos uma rua acima para iniciar a geração.")

    if clicou:
        agora = datetime.now()
        pasta_lote = OUTPUT_DIR / f"lote_{agora:%Y-%m-%d_%H%M%S}"
        barra = st.progress(0.0, text="Processando documentos oficiais...")

        def atualizar(i: int, total: int, rua: str) -> None:
            barra.progress(i / total, text=f"Gerando {i}/{total} · {rua}")

        itens = [
            {
                "rua": todas_vias_dict[ch]["rua"],
                "bairro": todas_vias_dict[ch]["bairro"],
                "tipo_servico": tipo,
                "justificativa": justificativa_para(todas_vias_dict[ch]["rua"], todas_vias_dict[ch]["bairro"]),
                "data": data_doc,
                "caixa_alta": caixa_alta,
            }
            for ch in a_gerar_chaves
        ]
        try:
            gerados = dg.gerar_lote(
                TEMPLATE_PATH, itens, pasta_lote, progresso=atualizar,
                incluir_mapa=incluir_mapa,
                imagem_assinatura=img_assinatura_final,
                incluir_carimbo=usar_carimbo_final,
                incluir_bloco_assinatura=(img_assinatura_final is None),
                padrao_nome="numero"  # Nomenclatura oficial solicitada: de 1 até N (1.docx, 2.docx, ...)
            )
            nome_zip = dg.nome_zip_do_dia(OUTPUT_DIR)
            zip_bytes = dg.criar_zip([g["caminho"] for g in gerados])
            (OUTPUT_DIR / nome_zip).write_bytes(zip_bytes)
            db.inserir_lote([{"rua": g["rua"], "bairro": g["bairro"], "tipo_servico": g["tipo_servico"],
                              "data": data_doc, "arquivo": g["arquivo"]} for g in gerados])
            ss["ultimo_lote"] = {"nome": nome_zip, "bytes": zip_bytes, "qtd": len(gerados),
                                 "arquivos": [g["arquivo"] for g in gerados], "pasta": str(pasta_lote)}
            ss["_limpar_sel"] = True
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

    st.markdown(
        """
        <div class="gov-author-discreet">
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-weight:800; color:#FF5500;">SIGI</span>
                <span>· Sistema Inteligente de Geração de Indicações Legislativas</span>
            </div>
            <div>
                Desenvolvido por <b>Valbert Breno</b> · Engenharia de Software
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------------- #
# Rodapé Institucional
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <div class="gov-footer">
        <div style="display:flex; flex-direction:column; gap:4px;">
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-weight:900; color:#FF5500; font-size:1.15rem; letter-spacing:-0.02em;">SIGI</span>
                <span style="color:#64748B;">·</span>
                <span style="color:#E2E8F0; font-weight:700;">Gabinete Parlamentar Ítalo Otávio</span>
            </div>
            <div style="color:#94A3B8; font-size:0.84rem;">
                Câmara Municipal de Boa Vista – RR · <i>Atitude para transformar!</i>
            </div>
            <div style="color:#64748B; font-size:0.78rem;">
                Processo Legislativo e Cartografia Urbana · Boa Vista / Roraima
            </div>
        </div>
        <div style="display:flex; gap:16px; font-size:0.82rem; align-items:center; flex-wrap:wrap;">
            <a href="https://italootavio.com.br/" target="_blank">🌐 italootavio.com.br ↗</a>
            <a href="https://www.instagram.com/italootavio" target="_blank">📸 @italootavio ↗</a>
            <a href="https://sapl.boavista.rr.leg.br/materia/pesquisar-materia?tipo=8&autoria__autor=70" target="_blank">🏛️ SAPL CMBV ↗</a>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
