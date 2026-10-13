# SIGI — Sistema Inteligente de Geração de Indicações
Câmara Municipal de Boa Vista – RR

Gera em lote as indicações diárias de infraestrutura (meta: 20/dia) a partir de um modelo `.docx`,
buscando as ruas de cada bairro no OpenStreetMap (Overpass API) e controlando o histórico em SQLite.

## Como executar
```bash
pip install -r requirements.txt
streamlit run app.py
```
Na primeira execução o app cria `data/sigi.db` e, se não existir, o modelo
`templates/modelo_indicacao.docx` (baseado na indicação publicada no SAPL).

## Fluxo de uso
1. **Configuração** → (opcional) envie o `.docx` oficial. O app confere as variáveis `{{RUA}}`, `{{BAIRRO}}`,
   `{{TIPO_SERVICO}}`, `{{JUSTIFICATIVA}}`, `{{DATA}}` (opcionais: `{{PREPOSICAO}}`, `{{RUA_NOME}}`).
2. **Gerar indicações** → bairro → serviço → ruas (até 20) → *Gerar*. Baixe o ZIP.
   - `🎯 Sugerir ruas` escolhe ruas sem indicação do mesmo serviço nos últimos 6 meses.
   - `⚠️` marca ruas já atendidas; `🟤` marca vias sem pavimento no OSM; ruas faltantes podem ser digitadas.
3. **Dashboard / Histórico** → produção diária, sequência de meta, filtros, exportação CSV.

## Estrutura
| Arquivo | Função |
|---|---|
| `app.py` | Interface Streamlit |
| `database.py` | SQLite: histórico, meta diária, duplicidade (6 meses), estatísticas |
| `doc_generator.py` | Substituição robusta de variáveis (runs quebrados, tabelas, cabeçalho/rodapé), lote e ZIP |
| `geo_service.py` | Overpass API: bairros (admin_level=10) e ruas (`way` + `highway`) com espelhos, retry e cache |
| `utils.py` | Datas, textos e justificativas por serviço, normalização de nomes |
| `tests_offline.py` | Testes sem rede: `python tests_offline.py` |

## Observações
- A Overpass pública oscila (504/timeout). O app tenta vários espelhos e guarda cache de 7 dias em `data/cache_geo.json`.
- Os dados do OSM podem estar incompletos; use a adição manual de ruas quando necessário.
- Boa Vista/RR é a relação OSM `326286` (a `301450` é Boa Vista/PB).
