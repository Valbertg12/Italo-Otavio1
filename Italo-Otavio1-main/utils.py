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

# Centroides geográficos consolidados de todos os bairros de Boa Vista / RR
CENTROIDES_BAIRROS_BOA_VISTA: dict[str, tuple[float, float]] = {
    "13 de setembro": (2.7985268, -60.6859828),
    "31 de marco": (2.8382857, -60.6707996),
    "5 de outubro": (2.8563096, -60.6330428),
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
    "colina park": (2.9053466, -60.9384909),
    "distrito industrial": (2.7635135, -60.7144414),
    "distrito industrial governador aquilino mota duarte": (2.7687546, -60.7118988),
    "doutor airton rocha": (2.7674016, -60.7572412),
    "doutor silvio leite": (2.8215119, -60.7416242),
    "dr airton rocha": (2.7674016, -60.7572412),
    "dr silvio botelho": (2.8013255, -60.7424217),
    "dr silvio leite": (2.8215119, -60.7416242),
    "equatorial": (2.8184254, -60.7664732),
    "estados": (2.8456052, -60.669641),
    "jardim carana": (2.8522929, -60.7233396),
    "jardim das copaibas": (2.761869, -60.7064021),
    "jardim floresta": (2.8301981, -60.7100944),
    "jardim primavera": (2.8245869, -60.7344581),
    "jardim tropical": (2.7946992, -60.7334586),
    "joao de barro": (2.8629396, -60.7801888),
    "joquei clube": (2.8046491, -60.7264193),
    "laura moreira": (2.8005162, -60.7872681),
    "liberdade": (2.8192364, -60.7005652),
    "marechal rondon": (2.7919986, -60.6938459),
    "mecejana": (2.8243788, -60.6876267),
    "monte cristo": (2.8756224, -60.7111729),
    "murilo teixeira cidade": (2.8305423, -60.7661792),
    "nossa senhora aparecida": (2.8379029, -60.6655207),
    "nova canaa": (2.8150202, -60.7407219),
    "nova cidade": (2.7650202, -60.730845),
    "olimpico": (2.8022024, -60.7347069),
    "operario": (2.7786593, -60.7455088),
    "paraviana": (2.856586, -60.6591133),
    "pedra pintada": (2.8822767, -60.6866022),
    "pintolandia": (2.8067035, -60.7485165),
    "piscicultura": (2.8351304, -60.735663),
    "pricuma": (2.8102035, -60.6976568),
    "prof araceli souto maior": (2.7875362, -60.7242869),
    "professora araceli souto maior": (2.7875362, -60.7242869),
    "raiar do sol": (2.7741627, -60.7193381),
    "residencial flores": (2.7508363, -60.7343683),
    "residencial primavera": (2.7496524, -60.7371585),
    "said salomao": (2.8875383, -60.6904574),
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
    """Retorna o centroide (lat, lon) consolidado de qualquer bairro de Boa Vista/RR."""
    alvo = normalizar(nome)
    if alvo in CENTROIDES_BAIRROS_BOA_VISTA:
        return CENTROIDES_BAIRROS_BOA_VISTA[alvo]
    for k, v in CENTROIDES_BAIRROS_BOA_VISTA.items():
        if alvo.endswith(k) or k.endswith(alvo) or (len(k) > 4 and k in alvo):
            return v
    # Centro geográfico oficial de Boa Vista (Centro Cívico)
    return (2.819611, -60.6711632)



# --------------------------------------------------------------------------- #
# Datas
# --------------------------------------------------------------------------- #
def data_por_extenso(d: date | datetime | str | None = None) -> str:
    """02 de junho de 2026."""
    if isinstance(d, str):
        return d
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
# Sazonalidade Climática Oficial de Boa Vista / Roraima (Hemisfério Norte)
# --------------------------------------------------------------------------- #
def obter_estacao(data_ref: date | datetime | None = None) -> tuple[str, str, str]:
    """
    Determina a estação climática oficial em Boa Vista - Roraima (latitude ~2.8° N).
    - Outubro a Março: Verão / Estiagem (clima seco, sol intenso, calor e poeira).
    - Abril a Setembro: Inverno / Período Chuvoso (chuvas torrenciais, alagamentos e poças).
    Retorna: (codigo, rotulo_formatado, descricao_contexto)
    """
    d = data_ref or date.today()
    if isinstance(d, datetime):
        d = d.date()
    # Outubro a Março: Verão / Estiagem
    if d.month in (10, 11, 12, 1, 2, 3):
        return (
            "verao",
            "☀️ Verão / Estiagem (Clima Seco)",
            "Período de sol forte e estiagem em Boa Vista/RR. As justificativas enfatizam poeira intensa, desagregação do asfalto ressecado, pedras soltas e risco severo de queimadas (sem citar chuvas).",
        )
    return (
        "inverno",
        "🌧️ Inverno / Período Chuvoso",
        "Período de chuvas intensas na Amazônia Setentrional. As justificativas enfatizam poças, infiltrações pluviais, lamaçais, enxurradas e crateras ocultadas pela água.",
    )


# --------------------------------------------------------------------------- #
# Textos padronizados — Calibrados por Estação Climática (Verão vs Inverno)
# --------------------------------------------------------------------------- #
_ABERTURAS_VERAO = {
    "Tapa-Buraco": [
        "A presente indicação visa atender à necessidade imediata de reparo e conservação do pavimento {na_via} no bairro {bairro}. A via apresenta diversos pontos com buracos e fendas na pista de rolamento, cujo asfalto ressecado pela intensa insolação e pelo tráfego contínuo vem se deteriorando e prejudicando a trafegabilidade local.",
        "A presente indicação faz-se necessária devido ao desgaste acentuado da via, que apresenta buracos e panelas ao longo da pista de rolamento {na_via}, no bairro {bairro}, com esfarelamento da camada asfáltica sob o forte calor, comprometendo a segurança dos condutores.",
        "A presente indicação justifica-se pelo estado de degradação do pavimento {na_via}, no bairro {bairro}, onde o surgimento de buracos e trincas na pista seca expõe motoristas, motociclistas e pedestres a riscos constantes de acidentes.",
    ],
    "Recapeamento Asfáltico": [
        "A presente indicação faz-se necessária devido ao desgaste generalizado da camada asfáltica {na_via}, no bairro {bairro}, que já perdeu o ligante em razão do tempo e das altas temperaturas, apresentando ondulações severas, desagregação do piso e fendas ao longo de todo o trecho.",
        "A presente indicação visa atender à necessidade de renovação do pavimento {na_via}, no bairro {bairro}, cuja camada asfáltica encontra-se envelhecida, ressecada e esfarelada pelo intenso fluxo de veículos, demandando intervenção definitiva de recapeamento.",
        "A presente indicação justifica-se pela situação precária do pavimento {na_via}, no bairro {bairro}, com asfalto ressecado pelo sol forte, trincado e com perda de aderência, exigindo nova capa asfáltica para restaurar a segurança viária.",
    ],
    "Construção de Calçada": [
        "A presente indicação faz-se necessária devido à ausência de calçadas pavimentadas {na_via}, no bairro {bairro}, obrigando os pedestres a disputarem o leito carroçável com veículos em alta velocidade em meio a solo irregular.",
        "A presente indicação visa atender à necessidade de construção de passeios públicos acessíveis com meio-fio {na_via}, no bairro {bairro}, onde a inexistência de calçamento e a irregularidade do terreno dificultam o deslocamento seguro dos moradores.",
        "A presente indicação justifica-se pela falta de calçadas {na_via}, no bairro {bairro}, situação que impede a livre circulação de moradores, crianças, idosos e pessoas com deficiência, forçando-os a caminhar pela pista de rolamento sob forte calor.",
    ],
    "Limpeza de Terreno": [
        "A presente indicação visa atender à necessidade urgente de limpeza e roçagem de terrenos baldios {na_via}, no bairro {bairro}, onde a vegetação ressecada pela estiagem e o descarte irregular de entulhos geram grave risco à vizinhança.",
        "A presente indicação faz-se necessária devido ao acúmulo de mato seco, lixo e detritos em terrenos abandonados {na_via}, no bairro {bairro}, comprometendo a salubridade pública e a segurança dos moradores da região.",
        "A presente indicação justifica-se pela situação de abandono de terrenos {na_via}, no bairro {bairro}, tomados por matagal desidratado e resíduos combustíveis, o que prejudica a qualidade de vida e a segurança dos moradores.",
    ],
    "Sinalização": [
        "A presente indicação faz-se necessária devido à ausência ou ao desgaste da sinalização viária {na_via}, no bairro {bairro}, deixando motoristas, motociclistas e pedestres sem a devida orientação no tráfego diário.",
        "A presente indicação visa atender à necessidade de implantação e revitalização da sinalização horizontal reflexiva e placas verticais {na_via}, no bairro {bairro}, onde faixas e marcos encontram-se apagados ou danificados pela forte incidência solar.",
        "A presente indicação justifica-se pela deficiência de sinalização de trânsito {na_via}, no bairro {bairro}, via de circulação contínua onde a falta de marcações adequadas amplia significativamente o perigo de colisões e atropelamentos.",
    ],
}

_CONSEQUENCIAS_VERAO = {
    "Tapa-Buraco": [
        "A permanência dessas irregularidades no pavimento, somada ao clima seco e ao fluxo ininterrupto de veículos, levanta densas nuvens de poeira que invadem as residências e prejudicam as vias respiratórias de crianças e idosos da comunidade, além de danificar a suspensão dos veículos e provocar manobras bruscas com risco de colisões.",
        "A manutenção desse cenário danifica pneus e suspensões, arremessa cascalho e pedras soltas contra pedestres e veículos, e eleva expressivamente o perigo de quedas de motociclistas e ciclistas, violando o direito constitucional à livre e segura locomoção dos moradores.",
    ],
    "Recapeamento Asfáltico": [
        "A degradação da camada asfáltica expõe a base arenosa da pista, provocando grande dispersão de poeira no ar, danos materiais aos veículos e riscos contínuos de colisões em decorrência da perda de aderência e das manobras arriscadas para evitar os desníveis do asfalto ressecado.",
        "O desgaste acentuado da via encarece as manutenções pontuais futuras, causa prejuízos aos condutores e gera transtornos permanentes ao comércio e às famílias locais, que necessitam de uma via estruturada para suas atividades cotidianas.",
    ],
    "Construção de Calçada": [
        "Sem calçadas apropriadas, a população é forçada a caminhar pela pista de rolamento sob sol intenso, inalando poeira levantada pelos veículos e sujeita a riscos iminentes de atropelamento, além de sofrer com desníveis e pedras soltas que provocam quedas e entorses em pedestres e idosos.",
        "A carência de passeios públicos acessíveis segrega pessoas com deficiência, cadeirantes e famílias com carrinhos de bebê, ferindo os princípios regimentais de acessibilidade urbana e dignidade no deslocamento comunitário.",
    ],
    "Limpeza de Terreno": [
        "O mato seco sob forte calor solar eleva exponencialmente a probabilidade de queimadas urbanas e incêndios que propagam fumaça sufocante pelas residências vizinhas, além de favorecer o refúgio de animais peçonhentos — como escorpiões e serpentes que fogem do solo quente para as casas — e ampliar a sensação de insegurança.",
        "A concentração de vegetação seca e entulhos cria foco para proliferação de pragas, eleva a ameaça de incêndios nas cercanias das casas e compromete diretamente a saúde respiratória, a tranquilidade e o bem-estar das famílias do entorno.",
    ],
    "Sinalização": [
        "A falta de pintura reflexiva e sinalização legível, sob a forte claridade e reflexo solar no asfalto, confunde os condutores e estimula excessos de velocidade na pista seca, colocando em perigo constante a integridade física de pedestres, ciclistas e motoristas.",
        "A deficiência de placas de advertência e faixas de pedestres eleva os índices de colisões em cruzamentos e contraria o dever da administração pública de resguardar a ordem do trânsito e a vida da população.",
    ],
}

_ABERTURAS_INVERNO = {
    "Tapa-Buraco": [
        "A presente indicação visa atender à necessidade imediata de reparo e conservação do pavimento {na_via} no bairro {bairro}. A via apresenta diversos pontos com buracos e fendas na pista de rolamento que se agravam com as fortes chuvas do período, acumulando água pluvial e prejudicando severamente a trafegabilidade local.",
        "A presente indicação faz-se necessária devido ao desgaste da via, que apresenta buracos e panelas ao longo da pista de rolamento {na_via}, no bairro {bairro}, os quais ficam encobertos pelas águas da chuva, transformando-se em armadilhas invisíveis para motoristas e motociclistas.",
        "A presente indicação justifica-se pelo estado de degradação do asfalto {na_via}, no bairro {bairro}, onde a infiltração constante das enxurradas acelera a desagregação do pavimento e amplia a abertura de crateras na pista.",
    ],
    "Recapeamento Asfáltico": [
        "A presente indicação faz-se necessária devido ao desgaste generalizado da camada asfáltica {na_via}, no bairro {bairro}, cuja base saturada pelas chuvas constantes já não oferece sustentação ao tráfego, apresentando desagregação do revestimento e refluxo de águas pluviais.",
        "A presente indicação visa atender à necessidade de renovação do pavimento {na_via}, no bairro {bairro}, onde a combinação de fluxo de veículos e enxurradas destruiu a camada de rolamento, exigindo intervenção completa de recapeamento asfáltico.",
        "A presente indicação justifica-se pela situação precária do pavimento {na_via}, no bairro {bairro}, tomado por trincas e infiltrações que comprometem a drenagem e a segurança viária dos moradores.",
    ],
    "Construção de Calçada": [
        "A presente indicação faz-se necessária devido à ausência de calçadas {na_via}, no bairro {bairro}, onde as margens da via são tomadas por lama e poças d'água durante as chuvas, obrigando os pedestres a disputarem o leito carroçável com os veículos.",
        "A presente indicação visa atender à necessidade de construção de passeios públicos elevados com meio-fio {na_via}, no bairro {bairro}, impedindo o avanço de enxurradas sobre as passagens e garantindo deslocamento seguro à comunidade.",
        "A presente indicação justifica-se pela inexistência de calçadas acessíveis {na_via}, no bairro {bairro}, forçando idosos, crianças e trabalhadores a caminharem em trechos escorregadios e alagados para alcançar suas residências.",
    ],
    "Limpeza de Terreno": [
        "A presente indicação faz-se necessária devido ao crescimento descontrolado do mato alto impulsionado pelo período chuvoso e ao acúmulo de lixo em terrenos baldios {na_via}, no bairro {bairro}, comprometendo a salubridade da região.",
        "A presente indicação visa atender à necessidade urgente de roçagem e limpeza de terrenos abandonados {na_via}, no bairro {bairro}, onde o acúmulo de recipientes com água das chuvas forma focos favoráveis à multiplicação de vetores de doenças.",
        "A presente indicação justifica-se pela situação de abandono de terrenos {na_via}, no bairro {bairro}, tomados por matagal denso e poças de água parada, exigindo ação imediata do poder público para resguardar a vizinhança.",
    ],
    "Sinalização": [
        "A presente indicação faz-se necessária devido à ausência ou ao desgaste da sinalização viária {na_via}, no bairro {bairro}, agravada pela baixa visibilidade nos períodos de chuva intensa em Boa Vista.",
        "A presente indicação visa atender à necessidade de implantação e revitalização da sinalização horizontal e vertical {na_via}, no bairro {bairro}, com faixas refletivas que permitam orientação segura sob pista molhada e temporal.",
        "A presente indicação justifica-se pela deficiência de sinalização viária {na_via}, no bairro {bairro}, onde a falta de marcações nítidas eleva expressivamente o risco de colisões e derrapagens nos dias chuvosos.",
    ],
}

_CONSEQUENCIAS_INVERNO = {
    "Tapa-Buraco": [
        "A retenção de água da chuva nos buracos camufla as imperfeições da pista, danificando os veículos dos moradores, provocando quedas graves de motociclistas e ciclistas e aumentando o risco de acidentes automobilísticos com danos à integridade física da população.",
        "O acúmulo de lama e água pluvial nas crateras gera atoleiros, prejudica o direito de ir e vir dos moradores e compromete a segurança viária, expondo condutores e pedestres a perigos contínuos durante o inverno roraimense.",
    ],
    "Recapeamento Asfáltico": [
        "A saturação do pavimento pelas enxurradas acelera a desintegração da pista, prejudica o escoamento das águas pluviais, eleva os custos públicos de manutenção e coloca em perigo diário motoristas, transporte coletivo e serviços essenciais de emergência.",
        "O asfalto danificado sob chuva contínua perde totalmente o coeficiente de atrito, propiciando derrapagens, colisões e graves transtornos diários a toda a comunidade do bairro.",
    ],
    "Construção de Calçada": [
        "O acúmulo de lamaçal e poças nas laterais da via obriga pedestres, idosos e pessoas com deficiência a caminharem pela pista molhada e escorregadia junto ao tráfego de carros, ampliando sobremaneira o risco de atropelamentos fatais sob chuva.",
        "A ausência de passeio público digno impede o trânsito seguro em dias de chuva, molhando moradores e expondo a comunidade a respingos e acidentes, ferindo o direito fundamental à mobilidade urbana e segurança.",
    ],
    "Limpeza de Terreno": [
        "A conjunção de vegetação densa e água da chuva retida em entulhos cria o ambiente propício para a proliferação acelerada do mosquito Aedes aegypti (transmissor da dengue, zika e chikungunya), além de atrair caramujos, roedores e animais peçonhentos para dentro das casas vizinhas.",
        "O estado de abandono do terreno sob chuvas constantes gera mau cheiro, proliferação de vetores epidemiológicos e acúmulo de águas estagnadas, ameaçando de forma direta a saúde pública e a tranquilidade dos moradores.",
    ],
    "Sinalização": [
        "A falta de pintura termoplástica reflexiva e de placas bem posicionadas reduz drasticamente a visibilidade dos condutores sob tempestades e pista molhada, resultando em freadas bruscas, abalroamentos e atropelamentos.",
        "A precariedade de sinalização de trânsito em período de pistas escorregadias favorece infrações involuntárias e acidentes severos, descumprindo a obrigação do poder público em zelar pela proteção da vida no trânsito.",
    ],
}


def _escolha(lista: list[str], chave: str, deslocamento: int = 0) -> str:
    h = int(hashlib.sha256(chave.encode("utf-8")).hexdigest(), 16)
    return lista[(h + deslocamento) % len(lista)]


def gerar_justificativa(tipo_servico: str, rua: str, bairro: str,
                        estacao: str = "auto", data_ref: date | datetime | None = None) -> str:
    """
    Gera a justificativa parlamentar (2 parágrafos, separados por linha em branco),
    estritamente alinhada à estação climática real de Boa Vista/RR (Verão/Estiagem vs Inverno/Chuvoso).
    No Verão, NUNCA cita chuvas, poças ou alagamentos.
    """
    if estacao == "auto":
        estacao_cod = obter_estacao(data_ref)[0]
    else:
        estacao_cod = "verao" if any(k in estacao.lower() for k in ("verao", "seco", "estiagem")) else "inverno"

    aberturas_dict = _ABERTURAS_VERAO if estacao_cod == "verao" else _ABERTURAS_INVERNO
    consequencias_dict = _CONSEQUENCIAS_VERAO if estacao_cod == "verao" else _CONSEQUENCIAS_INVERNO

    if tipo_servico not in aberturas_dict:
        tipo_servico = TIPOS_SERVICO[0]

    prep = preposicao_logradouro(rua)
    na_via = f"{'no' if prep == 'NO' else 'na'} {rua}"
    chave = f"{normalizar(rua)}|{normalizar(bairro)}|{tipo_servico}|{estacao_cod}"

    abertura = _escolha(aberturas_dict[tipo_servico], chave).format(na_via=na_via, bairro=bairro)
    consequencia = _escolha(consequencias_dict[tipo_servico], chave, 1)
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
