"""
doc_generator.py — Preenchimento do template .docx com python-docx.

Substituição robusta: o Word costuma "quebrar" um texto como {{RUA}} em vários
*runs* (por causa de correção ortográfica, formatação parcial, etc.). Por isso
a troca é feita no texto concatenado do parágrafo e depois redistribuída sobre
os runs originais, preservando fonte, negrito, tamanho, alinhamento e recuos.

Cobre: corpo do documento, tabelas (inclusive aninhadas), cabeçalhos e rodapés.
"""
from __future__ import annotations

import copy
import io
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Iterator

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docx.text.paragraph import Paragraph

from utils import (
    OUTPUT_DIR,
    VARIAVEIS_OBRIGATORIAS,
    VARIAVEIS_OPCIONAIS,
    data_por_extenso,
    nome_arquivo_seguro,
    nome_sem_tipo,
    preposicao_logradouro,
)
import geo_service as geo
import signature_service as sig_serv

# {{ NOME }} — tolera espaços internos
_PADRAO = re.compile(r"\{\{\s*([A-Za-zÀ-ÿ_]+)\s*\}\}")
_PADRAO_CHAVE = re.compile(r"\{\{\s*([A-Za-zÀ-ÿ_]+)\s*\}\}")


# --------------------------------------------------------------------------- #
# Varredura de parágrafos
# --------------------------------------------------------------------------- #
def _paragrafos_em(container) -> Iterator[Paragraph]:
    """Todos os parágrafos de um container (Document, célula, header, footer), incl. tabelas aninhadas."""
    for p in container.paragraphs:
        yield p
    for tabela in getattr(container, "tables", []):
        for linha in tabela.rows:
            vistos = set()
            for celula in linha.cells:
                if id(celula._tc) in vistos:  # células mescladas aparecem repetidas
                    continue
                vistos.add(id(celula._tc))
                yield from _paragrafos_em(celula)


def _todos_paragrafos(doc: Document) -> Iterator[Paragraph]:
    yield from _paragrafos_em(doc)
    for secao in doc.sections:
        for parte in (secao.header, secao.footer, secao.first_page_header,
                      secao.first_page_footer, secao.even_page_header, secao.even_page_footer):
            try:
                if parte is not None:
                    yield from _paragrafos_em(parte)
            except Exception:  # cabeçalhos "vinculados" podem não existir
                continue


def _texto_paragrafo(p: Paragraph) -> str:
    return "".join(r.text for r in p.runs)


# --------------------------------------------------------------------------- #
# Validação do template
# --------------------------------------------------------------------------- #
def _detectar_secoes_texto(doc: Document) -> tuple[int, int, int]:
    """Identifica os índices de (solicitação, justificativa, data) em um documento oficial sem tags."""
    idx_solic = -1
    idx_just = -1
    idx_data = -1

    for i, p in enumerate(doc.paragraphs):
        t = p.text.strip().upper()
        if not t:
            continue

        # 1. Justificativa
        if idx_just == -1 and (t.startswith("JUSTIFICATIVA") or "JUSTIFICATIVA:" in t):
            idx_just = i
            continue

        # 2. Solicitação
        if idx_solic == -1 and any(w in t for w in ("SOLICITO", "SOLICITA", "INDICA", "INDICO", "REQUER", "REQUEIRO", "SERVIÇO DE")):
            if any(k in t for k in ("RUA", "AVENIDA", "TRAVESSA", "BAIRRO", "SERVIÇO", "TAPA", "BURACO", "ASFALT", "CALÇADA", "LIMPEZA", "SINALIZAÇÃO", "ILUMINAÇÃO", "DRENAGEM")):
                idx_solic = i
                continue

        # 3. Data / Plenário
        if idx_data == -1 and ("BOA VISTA" in t or "PLENÁRIO" in t) and re.search(r"\d{4}", t):
            idx_data = i

    return idx_solic, idx_just, idx_data


def analisar_template(origem: str | Path | bytes | io.BytesIO) -> dict:
    """
    Analisa o template .docx oficial.
    Detecta tanto modelos com tags ({{RUA}}, etc.) quanto modelos oficiais reais
    sem tags (com auto-detecção de solicitação, justificativa, cabeçalho e rodapé com imagens).
    NUNCA bloqueia a geração: aceita ambos os formatos com 100% de compatibilidade!
    """
    if isinstance(origem, (bytes, bytearray)):
        origem = io.BytesIO(origem)
    doc = Document(origem)
    achadas: set[str] = set()
    for p in _todos_paragrafos(doc):
        for m in _PADRAO.finditer(_texto_paragrafo(p)):
            achadas.add("{{" + m.group(1).upper() + "}}")
    obrig = set(VARIAVEIS_OBRIGATORIAS)
    opc = set(VARIAVEIS_OPCIONAIS)

    # Contagem de imagens em cabeçalho, rodapé e corpo
    img_cabecalho = 0
    img_rodape = 0
    for sec in doc.sections:
        for parte in (sec.header, sec.first_page_header, sec.even_page_header):
            if parte is not None:
                try:
                    img_cabecalho += sum(1 for r in parte.part.rels.values() if "image" in r.reltype.lower())
                except Exception:
                    pass
        for parte in (sec.footer, sec.first_page_footer, sec.even_page_footer):
            if parte is not None:
                try:
                    img_rodape += sum(1 for r in parte.part.rels.values() if "image" in r.reltype.lower())
                except Exception:
                    pass

    img_corpo = 0
    try:
        img_corpo = sum(1 for r in doc.part.rels.values() if "image" in r.reltype.lower())
    except Exception:
        pass

    idx_solic, idx_just, idx_data = _detectar_secoes_texto(doc)
    tem_tags = bool(achadas & obrig)
    modo = "tags" if tem_tags else "auto"

    txt_solic = doc.paragraphs[idx_solic].text.strip() if idx_solic != -1 else ""
    txt_just = doc.paragraphs[idx_just].text.strip() if idx_just != -1 else ""
    txt_data = doc.paragraphs[idx_data].text.strip() if idx_data != -1 else ""

    return {
        "valido": True,
        "modo": modo,
        "encontradas": sorted(achadas & obrig),
        # Se for modo auto ou tiver tags, 'faltando' é vazio para NÃO travar a geração
        "faltando": [] if (modo == "auto" or not (obrig - achadas)) else [v for v in VARIAVEIS_OBRIGATORIAS if v not in achadas],
        "tags_faltando": [v for v in VARIAVEIS_OBRIGATORIAS if v not in achadas],
        "opcionais": sorted(achadas & opc),
        "desconhecidas": sorted(achadas - obrig - opc),
        "tem_cabecalho_img": img_cabecalho > 0,
        "tem_rodape_img": img_rodape > 0,
        "imagens_cabecalho": img_cabecalho,
        "imagens_rodape": img_rodape,
        "imagens_corpo": img_corpo,
        "total_paragrafos": len(doc.paragraphs),
        "detectados": {
            "idx_solic": idx_solic,
            "idx_just": idx_just,
            "idx_data": idx_data,
            "solic": txt_solic[:90] if txt_solic else "",
            "just": txt_just[:90] if txt_just else "",
            "data": txt_data[:90] if txt_data else "",
        },
    }


# --------------------------------------------------------------------------- #
# Substituição robusta
# --------------------------------------------------------------------------- #
def _sanitizar(valor: str) -> str:
    # impede que o valor reintroduza um marcador e gere laço infinito
    return str(valor).replace("{{", "{ {").replace("}}", "} }")


def _substituir_uma_ocorrencia(par: Paragraph, valores: dict[str, str]) -> bool:
    """Substitui a primeira variável conhecida do parágrafo. Retorna False se não houver nenhuma."""
    runs = par.runs
    textos = [r.text for r in runs]
    cheio = "".join(textos)

    m = None
    for cand in _PADRAO.finditer(cheio):
        if cand.group(1).upper() in valores:
            m = cand
            break
    if m is None:
        return False

    ini, fim = m.span()
    valor = _sanitizar(valores[m.group(1).upper()])

    # Descobre os runs inicial/final que cobrem [ini, fim)
    pos = 0
    primeiro = ultimo = None
    ini_primeiro = ini_ultimo = 0
    for i, t in enumerate(textos):
        s, e = pos, pos + len(t)
        if primeiro is None and s <= ini < e:
            primeiro, ini_primeiro = i, s
        if primeiro is not None and s < fim <= e:
            ultimo, ini_ultimo = i, s
            break
        pos = e
    if primeiro is None or ultimo is None:  # defensivo
        return False

    resto_apos = cheio[fim:]
    prefixo = textos[primeiro][: ini - ini_primeiro]
    sufixo = textos[ultimo][fim - ini_ultimo:]

    # Valor com parágrafos (linha em branco) e nada depois da variável -> vira parágrafos reais
    partes = [x.strip() for x in re.split(r"\n\s*\n", valor)] if "\n\n" in valor or "\n \n" in valor else [valor]
    multiparagrafo = len(partes) > 1 and resto_apos.strip() == ""

    texto_primeiro = partes[0] if multiparagrafo else valor
    if primeiro == ultimo:
        runs[primeiro].text = prefixo + texto_primeiro + sufixo
    else:
        runs[primeiro].text = prefixo + texto_primeiro
        for k in range(primeiro + 1, ultimo):
            runs[k].text = ""
        runs[ultimo].text = sufixo

    if multiparagrafo:
        ancora = par._p
        for parte in partes[1:]:
            clone = copy.deepcopy(par._p)
            ancora.addnext(clone)
            novo = Paragraph(clone, par._parent)
            runs_clone = novo.runs
            for k, r in enumerate(runs_clone):
                r.text = parte if k == primeiro else ""
            ancora = clone
    return True


def substituir_variaveis(doc: Document, valores: dict[str, str]) -> int:
    """Substitui todas as variáveis conhecidas no documento. Retorna o número de substituições."""
    valores = {k.strip("{} ").upper(): v for k, v in valores.items()}
    total = 0
    # list(): parágrafos clonados durante a iteração não precisam ser reprocessados
    for par in list(_todos_paragrafos(doc)):
        guarda = 0
        while _substituir_uma_ocorrencia(par, valores) and guarda < 50:
            total += 1
            guarda += 1
    return total


# --------------------------------------------------------------------------- #
# Montagem dos valores
# --------------------------------------------------------------------------- #
def montar_valores(rua: str, bairro: str, tipo_servico: str, justificativa: str,
                   data: date | None = None, caixa_alta: bool = True, numero: str = "") -> dict[str, str]:
    fmt = (lambda s: s.upper()) if caixa_alta else (lambda s: s)
    return {
        "RUA": fmt(rua),
        "RUA_NOME": fmt(nome_sem_tipo(rua)),
        "BAIRRO": fmt(bairro),
        "TIPO_SERVICO": fmt(tipo_servico),
        "JUSTIFICATIVA": justificativa,
        "DATA": data_por_extenso(data),
        "PREPOSICAO": preposicao_logradouro(rua) if caixa_alta else preposicao_logradouro(rua).lower(),
        "NUMERO": numero,
    }


# --------------------------------------------------------------------------- #
# Geração
# --------------------------------------------------------------------------- #
# Inserção de Mapa & Croqui no Documento
# --------------------------------------------------------------------------- #
def _inserir_imagem_mapa(doc: Document, imagem_bytes: bytes, rua: str, bairro: str,
                         ancora_p: Paragraph | None = None) -> None:
    """Insere o print do mapa com moldura, legenda e alinhamento oficial no documento."""
    try:
        p_map = doc.add_paragraph()
        p_map.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_map.paragraph_format.space_before = Pt(8)
        p_map.paragraph_format.space_after = Pt(2)
        r = p_map.add_run()
        r.add_picture(io.BytesIO(imagem_bytes), width=Cm(13.5))

        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_before = Pt(2)
        p_cap.paragraph_format.space_after = Pt(12)
        r_cap = p_cap.add_run(f"Figura 1 — Croqui de Localização: {rua}, Bairro {bairro} — Boa Vista/RR (Integrado ao Google Maps & Waze)")
        r_cap.font.size = Pt(9)
        r_cap.font.italic = True

        if ancora_p is not None:
            ancora_p._p.addnext(p_cap._p)
            ancora_p._p.addnext(p_map._p)
    except Exception:
        pass


def _inserir_assinatura(doc: Document, imagem_assinatura: bytes) -> bool:
    """
    Insere a rubrica/assinatura visual do vereador centralizada e remove
    automaticamente o bloco manual (linha e textos), garantindo que fique
    APENAS a imagem anexada, sem solicitar assinatura manual repetida.
    """
    if not imagem_assinatura:
        return False
    try:
        alvo = None
        for p in doc.paragraphs:
            t = p.text.strip().upper()
            if "____" in t or "TALO OT" in t or "ITALO OTAVIO" in t or "{{ASSINATURA}}" in t:
                alvo = p
                break

        if alvo is not None:
            p_sig = doc.add_paragraph()
            p_sig.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_sig.paragraph_format.space_before = Pt(12)
            p_sig.paragraph_format.space_after = Pt(2)
            r = p_sig.add_run()
            r.add_picture(io.BytesIO(imagem_assinatura), width=Cm(4.8))
            alvo._p.addprevious(p_sig._p)

            # Remove os parágrafos do bloco manual de assinatura
            for p in list(doc.paragraphs):
                if p == p_sig:
                    continue
                t = p.text.strip().upper()
                if "____" in t or "TALO OT" in t or "ITALO OTAVIO" in t or "VEREADOR DE BOA VISTA" in t or "{{ASSINATURA}}" in t:
                    try:
                        p._p.getparent().remove(p._p)
                    except Exception:
                        pass
            return True
    except Exception:
        pass
    return False

def _inserir_carimbo_digital(doc: Document, texto_carimbo: str) -> None:
    """Insere a certificação digital ICP-Brasil com hash e carimbo legal no rodapé."""
    if not texto_carimbo:
        return
    try:
        p_sep = doc.add_paragraph()
        p_sep.paragraph_format.space_before = Pt(18)
        p_sep.paragraph_format.space_after = Pt(4)
        r_sep = p_sep.add_run("─" * 68)
        r_sep.font.size = Pt(8)

        p_stamp = doc.add_paragraph()
        p_stamp.paragraph_format.space_before = Pt(2)
        p_stamp.paragraph_format.space_after = Pt(6)
        p_stamp.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r_stamp = p_stamp.add_run("🔒 " + texto_carimbo)
        r_stamp.font.size = Pt(7.5)
        r_stamp.font.italic = True
    except Exception:
        pass


def _aplicar_modo_auto(doc: Document, valores: dict[str, str],
                       imagem_mapa: bytes | None = None, incluir_mapa: bool = True) -> None:
    """Preenche um documento oficial sem tags substituindo objeto, justificativa e data."""
    idx_solic, idx_just, idx_data = _detectar_secoes_texto(doc)

    # 1. Substitui parágrafo de solicitação
    if idx_solic != -1 and idx_solic < len(doc.paragraphs):
        p_solic = doc.paragraphs[idx_solic]
        for r in p_solic.runs:
            r.text = ""
        texto_solic = (
            f"SOLICITO A EXECUÇÃO DO SERVIÇO DE {valores['TIPO_SERVICO']} "
            f"{valores['PREPOSICAO']} {valores['RUA']}, NO BAIRRO {valores['BAIRRO']}."
        )
        r_novo = p_solic.add_run(texto_solic)
        r_novo.bold = True
        p_solic.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # 2. Substitui parágrafo de justificativa
    ancora_mapa = None
    if idx_just != -1 and idx_just < len(doc.paragraphs):
        p_just = doc.paragraphs[idx_just]
        for r in p_just.runs:
            r.text = ""
        r_rot = p_just.add_run("Justificativa: ")
        r_rot.bold = True
        p_just.add_run(valores["JUSTIFICATIVA"])
        p_just.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        ancora_mapa = p_just
    elif idx_solic != -1 and idx_solic < len(doc.paragraphs):
        ancora_mapa = doc.paragraphs[idx_solic]

    # 3. Substitui data/plenário
    if idx_data != -1 and idx_data < len(doc.paragraphs):
        p_data = doc.paragraphs[idx_data]
        for r in p_data.runs:
            r.text = ""
        p_data.add_run(f"Plenário “Estácio Pereira de Melo”, Boa Vista – RR, {valores['DATA']}.")

    # 4. Inserção do croqui do mapa
    if incluir_mapa and imagem_mapa:
        _inserir_imagem_mapa(doc, imagem_mapa, valores["RUA"], valores["BAIRRO"], ancora_p=ancora_mapa)


# --------------------------------------------------------------------------- #
# Geração
# --------------------------------------------------------------------------- #
def gerar_documento(template: str | Path | bytes, valores: dict[str, str],
                    imagem_mapa: bytes | None = None, incluir_mapa: bool = False,
                    imagem_assinatura: bytes | None = None,
                    texto_carimbo: str | None = None,
                    incluir_bloco_assinatura: bool | None = None) -> bytes:
    """
    Preenche o template e devolve o .docx em bytes.
    Preserva 100% de cabeçalhos e rodapés com imagens, tabelas e formatações originais.
    Suporta tanto modelos com tags ({{RUA}}, etc.) quanto modelos oficiais sem tags.
    Remove fotos residuais estáticas do corpo do template para que nunca vazem em documentos gerados.
    Se imagem de assinatura for anexada, coloca APENAS a imagem e remove o bloco de assinatura manual.
    Se nenhuma imagem de assinatura for anexada, preserva a linha oficial para assinatura à caneta.
    """
    origem = io.BytesIO(template) if isinstance(template, (bytes, bytearray)) else template
    doc = Document(origem)

    # 1. Remove qualquer desenho estático residual do corpo do template (ex: fotos de ruas anteriores)
    for p in doc.paragraphs:
        for d in p._element.xpath('.//w:drawing'):
            try:
                d.getparent().remove(d)
            except Exception:
                pass

    # 2. Se uma imagem de assinatura foi anexada, omite o bloco manual de assinatura
    if incluir_bloco_assinatura is None:
        incluir_bloco_assinatura = (imagem_assinatura is None)

    # Verifica se existem tags {{...}} no documento
    achou_tag = False
    for p in _todos_paragrafos(doc):
        if _PADRAO.search(_texto_paragrafo(p)):
            achou_tag = True
            break

    if achou_tag:
        substituir_variaveis(doc, valores)
        # Se houver tag explícita {{MAPA}} ou {{FOTO}}, substitui diretamente
        substituiu_tag_mapa = False
        if incluir_mapa and imagem_mapa:
            for p in doc.paragraphs:
                txt = p.text.upper()
                if "{{MAPA}}" in txt or "{{FOTO}}" in txt:
                    for r in p.runs:
                        r.text = ""
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    r_img = p.add_run()
                    r_img.add_picture(io.BytesIO(imagem_mapa), width=Cm(13.5))
                    substituiu_tag_mapa = True
                    break
            if not substituiu_tag_mapa:
                ancora = None
                for p in doc.paragraphs:
                    if "JUSTIFICATIVA" in p.text.upper():
                        ancora = p
                        break
                _inserir_imagem_mapa(doc, imagem_mapa, valores["RUA"], valores["BAIRRO"], ancora_p=ancora)
    else:
        _aplicar_modo_auto(doc, valores, imagem_mapa=imagem_mapa, incluir_mapa=incluir_mapa)

    # Aplicação de Assinatura Visual (apenas se imagem anexada)
    if imagem_assinatura:
        _inserir_assinatura(doc, imagem_assinatura)
    
    # Aplicação de Carimbo de Autenticidade (apenas se texto de carimbo válido)
    if texto_carimbo:
        _inserir_carimbo_digital(doc, texto_carimbo)

    # Opção de remoção de bloco de assinatura manual (se não solicitado ou se imagem foi anexada)
    if not incluir_bloco_assinatura:
        for p in list(doc.paragraphs):
            t = p.text.strip().upper()
            if "____" in t or "TALO OT" in t or "ITALO OTAVIO" in t or "VEREADOR DE BOA VISTA" in t:
                try:
                    p._p.getparent().remove(p._p)
                except Exception:
                    pass

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()

def gerar_lote(template: str | Path | bytes, itens: Iterable[dict], pasta_saida: Path | None = None,
               progresso: Callable[[int, int, str], None] | None = None,
               incluir_mapa: bool = False,
               imagem_assinatura: bytes | None = None,
               incluir_carimbo: bool = False,
               incluir_bloco_assinatura: bool | None = None,
               padrao_nome: str = "numero") -> list[dict]:
    """
    itens: dicts com rua, bairro, tipo_servico, justificativa, data (opcional), caixa_alta (opcional), imagem_mapa (opcional).
    Salva um .docx por rua em `pasta_saida` e devolve [{**item, 'arquivo': nome, 'caminho': Path}].
    Se imagem_assinatura for anexada, coloca APENAS a imagem (sem linha de assinatura manual).
    Se imagem_assinatura for None e incluir_carimbo for False, NENHUMA assinatura ou carimbo será colocado.
    """
    pasta = Path(pasta_saida or OUTPUT_DIR)
    pasta.mkdir(parents=True, exist_ok=True)
    if isinstance(template, (str, Path)):
        template = Path(template).read_bytes()  # lê uma única vez

    if incluir_bloco_assinatura is None:
        incluir_bloco_assinatura = (imagem_assinatura is None)

    itens = list(itens)
    usados: set[str] = set()
    resultado = []
    for n, it in enumerate(itens, start=1):
        valores = montar_valores(
            it["rua"], it["bairro"], it["tipo_servico"], it["justificativa"],
            it.get("data"), it.get("caixa_alta", True),
        )

        img_mapa = it.get("imagem_mapa")
        if img_mapa is None and incluir_mapa:
            try:
                img_mapa = geo.obter_mapa_rua(it["rua"], it["bairro"], it["tipo_servico"])
            except Exception:
                img_mapa = None

        carimbo_txt = None
        # Só gera carimbo se o usuário pediu E se houver assinatura anexada ou certificado ativo
        if incluir_carimbo and (imagem_assinatura or sig_serv.tem_assinatura_ativa()):
            try:
                carimbo_txt = sig_serv.gerar_carimbo_autenticidade(it["rua"], it["bairro"], it.get("data"))
            except Exception:
                carimbo_txt = None

        conteudo = gerar_documento(
            template, valores,
            imagem_mapa=img_mapa, incluir_mapa=incluir_mapa,
            imagem_assinatura=imagem_assinatura,
            texto_carimbo=carimbo_txt,
            incluir_bloco_assinatura=incluir_bloco_assinatura,
        )

        if padrao_nome == "descritivo":
            base = f"{n:02d}_indicacao_{nome_arquivo_seguro(it['rua'])}_{nome_arquivo_seguro(it['bairro'], 30)}"
            nome, k = f"{base}.docx", 2
            while nome in usados:
                nome, k = f"{base}_{k}.docx", k + 1
        else:
            # Padrão oficial solicitado: nomeados de 1 até N (1.docx, 2.docx, ...)
            nome, k = f"{n}.docx", 2
            while nome in usados:
                nome, k = f"{n}_{k}.docx", k + 1
        usados.add(nome)

        caminho = pasta / nome
        caminho.write_bytes(conteudo)
        resultado.append({**it, "arquivo": nome, "caminho": caminho})
        if progresso:
            progresso(n, len(itens), it["rua"])
    return resultado

def criar_zip(arquivos: Iterable[Path]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for a in arquivos:
            a = Path(a)
            z.write(a, arcname=a.name)
    return buf.getvalue()


def nome_zip_do_dia(pasta: Path | None = None) -> str:
    """indicacoes_AAAA-MM-DD.zip (acrescenta _2, _3… se já existir um lote no mesmo dia)."""
    pasta = Path(pasta or OUTPUT_DIR)
    base = f"indicacoes_{date.today():%Y-%m-%d}"
    nome, k = f"{base}.zip", 2
    while (pasta / nome).exists():
        nome, k = f"{base}_{k}.zip", k + 1
    return nome


# --------------------------------------------------------------------------- #
# Template padrão (baseado no modelo oficial do gabinete publicado no SAPL)
# --------------------------------------------------------------------------- #
def _par(doc, texto="", negrito=False, alinhamento=WD_ALIGN_PARAGRAPH.JUSTIFY,
         depois=6, recuo_primeira=None, tamanho=12):
    p = doc.add_paragraph()
    p.alignment = alinhamento
    p.paragraph_format.space_after = Pt(depois)
    p.paragraph_format.line_spacing = 1.15
    if recuo_primeira is not None:
        p.paragraph_format.first_line_indent = Cm(recuo_primeira)
    if texto:
        r = p.add_run(texto)
        r.bold = negrito
        r.font.size = Pt(tamanho)
    return p


def criar_template_padrao(destino: str | Path) -> Path:
    """Gera um modelo_indicacao.docx funcional, no formato do gabinete do Vereador Ítalo Otávio."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    sec.left_margin = sec.right_margin = Cm(3.0)
    sec.top_margin, sec.bottom_margin = Cm(2.5), Cm(2.5)

    estilo = doc.styles["Normal"]
    estilo.font.name = "Times New Roman"
    estilo.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    estilo.font.size = Pt(12)

    C = WD_ALIGN_PARAGRAPH.CENTER
    L = WD_ALIGN_PARAGRAPH.LEFT
    J = WD_ALIGN_PARAGRAPH.JUSTIFY

    _par(doc, "ESTADO DE RORAIMA", True, C, 0)
    _par(doc, "CÂMARA MUNICIPAL DE BOA VISTA", True, C, 0)
    _par(doc, "GABINETE DO VEREADOR ÍTALO OTÁVIO", True, C, 18)
    _par(doc, "INDICAÇÃO", True, C, 18, tamanho=14)

    _par(doc, "Excelentíssimo Senhor", False, L, 0)
    _par(doc, "GENILSON COSTA", True, L, 0)
    _par(doc, "Presidente da Câmara Municipal de Boa Vista", False, L, 14)

    _par(doc, "O Vereador que esta subscreve, com amparo no art. 110, IX do Regimento Interno, "
              "solicita que seja encaminhada ao Excelentíssimo Senhor Prefeito de Boa Vista, "
              "Marcelo Zeitoune e que seja atendida a seguinte INDICAÇÃO:", False, J, 12, 1.25)

    _par(doc, "SOLICITO A EXECUÇÃO DO SERVIÇO DE {{TIPO_SERVICO}} {{PREPOSICAO}} {{RUA}}, "
              "NO BAIRRO {{BAIRRO}}.", True, J, 12, 1.25)

    p = _par(doc, "", False, J, 12, 1.25)
    r = p.add_run("Justificativa: ")
    r.bold = True
    p.add_run("{{JUSTIFICATIVA}}")

    _par(doc, "Enquanto fiscalizador dos recursos públicos e da execução do trabalho dessa secretaria, "
              "solicita a verificação da demanda acima elencada e a devida solução.", False, J, 18, 1.25)

    _par(doc, "Plenário “Estácio Pereira de Melo”, Boa Vista – RR, {{DATA}}.", False, L, 36)

    _par(doc, "_______________________________", False, C, 0)
    _par(doc, "ÍTALO OTÁVIO", True, C, 0)
    _par(doc, "Vereador de Boa Vista/RR", False, C, 0)

    doc.save(destino)
    return destino
