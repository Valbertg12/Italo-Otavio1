"""
utils.py — Funções auxiliares do SIGI.

Datas por extenso em pt-BR, normalização de nomes de logradouros e geração
de textos padronizados (solicitação e justificativa) para cada tipo de serviço.
"""
from __future__ import annotations

import calendar
import hashlib
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

# --------------------------------------------------------------------------- #
# Caminhos e constantes
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
TEMPLATE_PATH = TEMPLATES_DIR / "modelo_indicacao.docx"

META_DIARIA = 20
MESES_ALERTA = 6

# Variáveis obrigatórias (pedidas no escopo) e opcionais (extras do SIGI)
VARIAVEIS_OBRIGATORIAS = ["{{RUA}}", "{{BAIRRO}}", "{{TIPO_SERVICO}}", "{{JUSTIFICATIVA}}", "{{DATA}}"]
VARIAVEIS_OPCIONAIS = ["{{PREPOSICAO}}", "{{RUA_NOME}}", "{{NUMERO}}"]

TIPOS_SERVICO = [
    "Tapa-Buraco",
    "Recapeamento Asfáltico",
    "Construção de Calçada",
    "Limpeza de Terreno",
    "Sinalização",
]

MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos, sem pontuação e sem espaços duplicados."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-zA-Z0-9\s]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


# Lista de apoio de bairros de Boa Vista/RR, usada se o OSM/Overpass estiver
# indisponível ou não trouxer a lista. A busca por bairro é tolerante a acentos
# e caixa. Se algum bairro estiver faltando, o app permite digitar um nome livre.
BAIRROS_BOA_VISTA = sorted({
    "13 de Setembro", "31 de Março", "Aeroporto", "Alvorada", "Aparecida",
    "Asa Branca", "Bairro dos Estados", "Bela Vista", "Buritis", "Calungá",
    "Cambará", "Caimbé", "Caranã", "Cauamé", "Centenário", "Centro",
    "Cidade Satélite", "Cinturão Verde", "Distrito Industrial",
    "Dr. Silvio Botelho", "Dr. Silvio Leite", "Jardim Floresta", "Jardim Tropical",
    "Jóquei Clube", "Liberdade", "Mecejana", "Nova Canaã", "Nova Cidade",
    "Operário", "Pedra Pintada", "Paraviana", "Pintolândia", "Piscicultura",
    "Pricumã", "Prof. Araceli Souto Maior", "Raiar do Sol", "Santa Luzia",
    "Santa Tereza", "São Francisco", "São Pedro", "São Vicente",
    "Senador Hélio Campos", "Tancredo Neves", "União",
}, key=normalizar)


# --------------------------------------------------------------------------- #
# Datas
# --------------------------------------------------------------------------- #
def data_por_extenso(d: date | datetime | None = None) -> str:
    """02 de junho de 2026."""
    d = d or date.today()
    return f"{d.day:02d} de {MESES_PT[d.month - 1]} de {d.year}"


def subtrair_meses(d: date, meses: int) -> date:
    """Subtrai meses de calendário (ex.: 31/08 - 6 meses = 28/02)."""
    total = d.year * 12 + (d.month - 1) - meses
    ano, mes = divmod(total, 12)
    mes += 1
    dia = min(d.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def data_hoje_arquivo() -> str:
    """Data para nome de arquivo: 2026-06-02."""
    return date.today().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# Logradouros
# --------------------------------------------------------------------------- #
_PREFIXOS_MASC = ("beco", "largo", "parque", "viaduto", "caminho", "conjunto", "residencial", "loteamento")
_PREFIXOS_TIPO = (
    "rua", "avenida", "travessa", "alameda", "estrada", "rodovia", "beco", "praça",
    "praca", "largo", "via", "vicinal", "ramal", "passarela", "viaduto", "parque",
)


def preposicao_logradouro(nome: str) -> str:
    """'NA' para Rua/Avenida/Travessa…; 'NO' para Beco/Largo/Parque…"""
    primeiro = normalizar(nome).split(" ")[0] if nome else ""
    return "NO" if primeiro in _PREFIXOS_MASC else "NA"


def nome_sem_tipo(nome: str) -> str:
    """'Rua Moysés Teixeira Hausen' -> 'Moysés Teixeira Hausen'."""
    partes = nome.strip().split(" ", 1)
    if len(partes) == 2 and normalizar(partes[0]) in _PREFIXOS_TIPO:
        return partes[1].strip()
    return nome.strip()


def nome_arquivo_seguro(texto: str, limite: int = 80) -> str:
    t = normalizar(texto).replace(" ", "_")
    return (t[:limite] or "sem_nome").strip("_")


# --------------------------------------------------------------------------- #
# Textos padronizados
# --------------------------------------------------------------------------- #
# Cada serviço tem vários "parágrafos de abertura" e "parágrafos de
# consequência"; a escolha é determinística por (rua, bairro, serviço) para que
# as indicações do lote não saiam todas idênticas — mas a mesma rua sempre
# gere o mesmo texto ao regerar.
_ABERTURAS = {
    "Tapa-Buraco": [
        "A presente indicação visa atender à necessidade imediata de reparo e conservação do pavimento {na_via} no bairro {bairro}. A via apresenta diversos pontos com buracos e fendas na pista de rolamento, prejudicando sensivelmente as condições de trafegabilidade locais.",
        "A presente indicação faz-se necessária devido ao desgaste da via, que apresenta buracos e panelas ao longo da pista de rolamento {na_via}, no bairro {bairro}, comprometendo a conservação do pavimento e a trafegabilidade do local.",
        "A presente indicação justifica-se pelo estado de degradação do asfalto {na_via}, no bairro {bairro}, onde há buracos, trincas e remendos deteriorados que se agravam a cada período de chuvas.",
    ],
    "Recapeamento Asfáltico": [
        "A presente indicação faz-se necessária devido ao desgaste generalizado da camada asfáltica {na_via}, no bairro {bairro}, que já não oferece condições adequadas de rolamento, apresentando ondulações, desagregação do revestimento e fendas ao longo de todo o trecho.",
        "A presente indicação visa atender à necessidade de renovação do pavimento {na_via}, no bairro {bairro}, cuja camada asfáltica encontra-se desgastada pelo tempo e pelo intenso fluxo de veículos, exigindo intervenção de recapeamento.",
        "A presente indicação justifica-se pela situação precária do pavimento {na_via}, no bairro {bairro}, com asfalto ressecado, trincado e com perda de aderência, o que reduz a segurança do tráfego local.",
    ],
    "Construção de Calçada": [
        "A presente indicação faz-se necessária devido à ausência de calçadas adequadas {na_via}, no bairro {bairro}, obrigando os pedestres a disputarem o leito carroçável com os veículos.",
        "A presente indicação visa atender à necessidade de construção de passeios públicos com meio-fio {na_via}, no bairro {bairro}, onde a inexistência de calçamento e a irregularidade do terreno dificultam o deslocamento seguro da população.",
        "A presente indicação justifica-se pela inexistência de calçadas acessíveis {na_via}, no bairro {bairro}, situação que impede a livre e segura circulação de moradores, crianças, idosos e pessoas com deficiência ou mobilidade reduzida.",
    ],
    "Limpeza de Terreno": [
        "A presente indicação faz-se necessária devido ao acúmulo de mato alto, entulhos e lixo em terrenos baldios {na_via}, no bairro {bairro}, comprometendo a salubridade e a segurança dos moradores da vizinhança.",
        "A presente indicação visa atender à necessidade de limpeza e roçagem de terrenos abandonados {na_via}, no bairro {bairro}, onde o crescimento descontrolado da vegetação e o descarte irregular de resíduos geram foco de problemas à comunidade.",
        "A presente indicação justifica-se pela situação de abandono de terrenos {na_via}, no bairro {bairro}, tomados por vegetação e detritos, o que prejudica a paisagem urbana e a qualidade de vida dos moradores.",
    ],
    "Sinalização": [
        "A presente indicação faz-se necessária devido à ausência ou ao desgaste da sinalização viária {na_via}, no bairro {bairro}, deixando motoristas, motociclistas e pedestres sem a orientação necessária para o tráfego seguro.",
        "A presente indicação visa atender à necessidade de implantação e revitalização da sinalização horizontal e vertical {na_via}, no bairro {bairro}, onde faixas, placas e demais dispositivos encontram-se apagados, danificados ou inexistentes.",
        "A presente indicação justifica-se pela deficiência de sinalização de trânsito {na_via}, no bairro {bairro}, local de circulação intensa em que a falta de identificação adequada eleva o risco de colisões e atropelamentos.",
    ],
}

_CONSEQUENCIAS = {
    "Tapa-Buraco": [
        "A permanência dessas irregularidades no asfalto danifica os veículos dos moradores, aumenta consideravelmente o risco de acidentes automobilísticos e coloca em perigo a integridade física de motociclistas, ciclistas e pedestres que transitam pelo local, comprometendo a segurança viária e o direito constitucional à livre mobilidade da comunidade.",
        "A manutenção desse cenário gera prejuízos materiais aos condutores, eleva o risco de quedas e colisões — sobretudo envolvendo motociclistas e ciclistas — e põe em risco a segurança de pedestres e motoristas que transitam pelo local.",
    ],
    "Recapeamento Asfáltico": [
        "A manutenção da via nessas condições acelera a deterioração do pavimento, eleva os custos futuros de reparo, causa danos aos veículos e compromete a segurança dos pedestres e motoristas que transitam pelo local, além de dificultar o tráfego de serviços públicos essenciais.",
        "O desgaste do revestimento aumenta o risco de acidentes, prejudica o escoamento das águas pluviais e causa transtornos diários à população, que depende da via para o acesso a residências, comércio e serviços.",
    ],
    "Construção de Calçada": [
        "A ausência de calçadas expõe os pedestres ao risco de atropelamentos, dificulta a acessibilidade e prejudica a mobilidade urbana, comprometendo o direito constitucional de ir e vir com segurança e dignidade, especialmente de idosos, crianças e pessoas com deficiência.",
        "Sem passeio adequado, a população é forçada a caminhar pela pista, em meio ao tráfego de veículos, o que aumenta de forma considerável o risco de acidentes e fere os princípios de acessibilidade e segurança no espaço urbano.",
    ],
    "Limpeza de Terreno": [
        "A situação favorece a proliferação de animais peçonhentos, insetos e vetores de doenças, como o mosquito Aedes aegypti, além de servir de abrigo para pessoas mal-intencionadas, ampliando a sensação de insegurança e os riscos à saúde pública dos moradores.",
        "O acúmulo de resíduos e de vegetação alta facilita a proliferação de pragas e doenças, aumenta o risco de incêndios e de ações criminosas, e prejudica de maneira direta a saúde, a segurança e o bem-estar da vizinhança.",
    ],
    "Sinalização": [
        "A falta de sinalização adequada aumenta o risco de acidentes de trânsito, dificulta a orientação dos condutores e coloca em perigo a vida de pedestres, ciclistas e motociclistas, comprometendo a segurança viária e a ordem do tráfego no local.",
        "A deficiência de sinalização gera insegurança no trânsito, favorece infrações involuntárias e acidentes graves, e contraria o dever do poder público de garantir condições seguras de circulação à população.",
    ],
}


def _escolha(lista: list[str], chave: str, deslocamento: int = 0) -> str:
    h = int(hashlib.sha256(chave.encode("utf-8")).hexdigest(), 16)
    return lista[(h + deslocamento) % len(lista)]


def gerar_justificativa(tipo_servico: str, rua: str, bairro: str) -> str:
    """Gera a justificativa (2 parágrafos, separados por linha em branco)."""
    if tipo_servico not in _ABERTURAS:
        tipo_servico = TIPOS_SERVICO[0]
    prep = preposicao_logradouro(rua)
    na_via = f"{'no' if prep == 'NO' else 'na'} {rua}"
    chave = f"{normalizar(rua)}|{normalizar(bairro)}|{tipo_servico}"
    abertura = _escolha(_ABERTURAS[tipo_servico], chave).format(na_via=na_via, bairro=bairro)
    consequencia = _escolha(_CONSEQUENCIAS[tipo_servico], chave, 1)
    return f"{abertura}\n\n{consequencia}"


def gerar_texto_solicitacao(tipo_servico: str, rua: str, bairro: str) -> str:
    """Pré-visualização da frase 'SOLICITO ...' usada no modelo oficial."""
    return (f"SOLICITO A EXECUÇÃO DO SERVIÇO DE {tipo_servico.upper()} "
            f"{preposicao_logradouro(rua)} {rua.upper()}, NO BAIRRO {bairro.upper()}.")


def hoje() -> date:
    return date.today()


def inicio_do_dia(d: date | None = None) -> datetime:
    d = d or date.today()
    return datetime.combine(d, datetime.min.time())


def ultimos_dias(n: int) -> list[date]:
    h = date.today()
    return [h - timedelta(days=i) for i in range(n - 1, -1, -1)]
