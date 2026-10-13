"""
database.py — Camada de persistência do SIGI (SQLite nativo).

Armazena tanto as indicações geradas localmente quanto o acervo oficial
sincronizado com o SAPL da Câmara Municipal de Boa Vista.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Iterator

from utils import DATA_DIR, MESES_ALERTA, normalizar, subtrair_meses

DB_PATH = DATA_DIR / "sigi.db"

_SCHEMA = """
-- Indicações geradas pelo SIGI
CREATE TABLE IF NOT EXISTS indicacoes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    rua           TEXT    NOT NULL,
    rua_norm      TEXT    NOT NULL,
    bairro        TEXT    NOT NULL,
    bairro_norm   TEXT    NOT NULL,
    tipo_servico  TEXT    NOT NULL,
    data          TEXT    NOT NULL,           -- ISO (YYYY-MM-DD)
    arquivo       TEXT,
    origem        TEXT    DEFAULT 'SIGI',
    criado_em     TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_ind_data  ON indicacoes (data);
CREATE INDEX IF NOT EXISTS idx_ind_busca ON indicacoes (rua_norm, tipo_servico, data);

-- Acervo Oficial sincronizado com a API do SAPL da Câmara
CREATE TABLE IF NOT EXISTS sapl_materias (
    sapl_id          INTEGER PRIMARY KEY,
    numero           INTEGER,
    ano              INTEGER,
    numero_protocolo INTEGER,
    data             TEXT    NOT NULL,
    ementa           TEXT    NOT NULL,
    texto_original   TEXT,
    link_sapl        TEXT,
    rua              TEXT,
    rua_norm         TEXT,
    bairro           TEXT,
    bairro_norm      TEXT,
    tipo_servico     TEXT,
    sincronizado_em  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_sapl_data  ON sapl_materias (data);
CREATE INDEX IF NOT EXISTS idx_sapl_busca ON sapl_materias (rua_norm, tipo_servico, data);
"""


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.executescript(_SCHEMA)
        # Se a tabela sapl_materias estiver vazia (ex.: deploy novo na nuvem),
        # restaura o acervo histórico consolidado em milissegundos via seed compactado
        total = con.execute("SELECT count(*) FROM sapl_materias").fetchone()[0]
        if total == 0:
            seed_path = DATA_DIR / "sapl_seed.json.gz"
            if seed_path.exists():
                try:
                    import gzip
                    import json
                    with gzip.open(seed_path, "rt", encoding="utf-8") as f:
                        dados = json.load(f)
                    if dados:
                        colunas = list(dados[0].keys())
                        q = ",".join(["?"] * len(colunas))
                        sql = f"INSERT OR IGNORE INTO sapl_materias ({','.join(colunas)}) VALUES ({q})"
                        valores = [[d.get(c) for c in colunas] for d in dados]
                        con.executemany(sql, valores)
                except Exception:
                    pass


# --------------------------------------------------------------------------- #
# Escrita Local (SIGI)
# --------------------------------------------------------------------------- #
def inserir_indicacao(rua: str, bairro: str, tipo_servico: str,
                      data: date | None = None, arquivo: str | None = None) -> int:
    data = data or date.today()
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO indicacoes (rua, rua_norm, bairro, bairro_norm, tipo_servico, data, arquivo) "
            "VALUES (?,?,?,?,?,?,?)",
            (rua, normalizar(rua), bairro, normalizar(bairro), tipo_servico, data.isoformat(), arquivo),
        )
        return int(cur.lastrowid)


def inserir_lote(itens: Iterable[dict]) -> list[int]:
    """Insere várias indicações numa única transação."""
    ids: list[int] = []
    with _conn() as con:
        for it in itens:
            d = it.get("data") or date.today()
            if isinstance(d, datetime):
                d = d.date()
            cur = con.execute(
                "INSERT INTO indicacoes (rua, rua_norm, bairro, bairro_norm, tipo_servico, data, arquivo) "
                "VALUES (?,?,?,?,?,?,?)",
                (it["rua"], normalizar(it["rua"]), it["bairro"], normalizar(it["bairro"]),
                 it["tipo_servico"], d.isoformat() if hasattr(d, "isoformat") else str(d), it.get("arquivo")),
            )
            ids.append(int(cur.lastrowid))
    return ids


def excluir_indicacao(id_: int) -> None:
    with _conn() as con:
        con.execute("DELETE FROM indicacoes WHERE id = ?", (id_,))


# --------------------------------------------------------------------------- #
# Sincronização SAPL Oficial
# --------------------------------------------------------------------------- #
def salvar_lote_sapl(itens: Iterable[dict]) -> int:
    """Insere ou atualiza matérias vindas do SAPL da Câmara Municipal."""
    total_inseridos = 0
    with _conn() as con:
        for it in itens:
            rua = (it.get("rua") or "").strip()
            bairro = (it.get("bairro") or "").strip()
            cur = con.execute(
                """
                INSERT INTO sapl_materias (
                    sapl_id, numero, ano, numero_protocolo, data, ementa,
                    texto_original, link_sapl, rua, rua_norm, bairro, bairro_norm, tipo_servico
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(sapl_id) DO UPDATE SET
                    numero=excluded.numero,
                    ano=excluded.ano,
                    data=excluded.data,
                    ementa=excluded.ementa,
                    texto_original=excluded.texto_original,
                    rua=excluded.rua,
                    rua_norm=excluded.rua_norm,
                    bairro=excluded.bairro,
                    bairro_norm=excluded.bairro_norm,
                    tipo_servico=excluded.tipo_servico
                """,
                (
                    it["sapl_id"], it.get("numero"), it.get("ano"), it.get("numero_protocolo"),
                    it.get("data"), it.get("ementa", ""), it.get("texto_original", ""),
                    it.get("link_sapl", ""), rua, normalizar(rua), bairro, normalizar(bairro),
                    it.get("tipo_servico", "Indicação Geral")
                ),
            )
            total_inseridos += 1
    return total_inseridos


def total_sapl() -> int:
    with _conn() as con:
        return con.execute("SELECT COUNT(*) FROM sapl_materias").fetchone()[0]


def contagem_sapl_por_ano() -> dict[int, int]:
    with _conn() as con:
        rows = con.execute("SELECT ano, COUNT(*) FROM sapl_materias GROUP BY ano ORDER BY ano DESC").fetchall()
        return {r[0]: r[1] for r in rows if r[0]}


def listar_sapl(limite: int = 500, ano: int | None = None, anos: list[int] | None = None, busca: str | None = None) -> list[dict]:
    sql = "SELECT * FROM sapl_materias WHERE 1=1"
    p: list = []
    if anos:
        valid_anos = [int(a) for a in anos if str(a).isdigit()]
        if valid_anos:
            placeholders = ",".join("?" for _ in valid_anos)
            sql += f" AND ano IN ({placeholders})"
            p.extend(valid_anos)
    elif ano:
        sql += " AND ano = ?"
        p.append(int(ano))
    if busca:
        termo = f"%{normalizar(busca)}%"
        sql += " AND (ementa LIKE ? OR rua_norm LIKE ? OR bairro_norm LIKE ?)"
        p.extend([f"%{busca}%", termo, termo])
    sql += " ORDER BY data DESC, numero DESC LIMIT ?"
    p.append(limite)
    with _conn() as con:
        return [dict(r) for r in con.execute(sql, p).fetchall()]



# --------------------------------------------------------------------------- #
# Consultas Unificadas & Detector de Duplicidade (SIGI + SAPL)
# --------------------------------------------------------------------------- #
def contar_por_data(d: date | None = None) -> int:
    d = d or date.today()
    with _conn() as con:
        return con.execute("SELECT COUNT(*) FROM indicacoes WHERE data = ?", (d.isoformat(),)).fetchone()[0]


def buscar_duplicidade(rua: str, tipo_servico: str, bairro: str | None = None,
                       meses: int = MESES_ALERTA) -> dict | None:
    """
    Retorna a indicação mais recente para a mesma rua nos últimos N meses,
    verificando tanto no banco local do SIGI quanto nas matérias oficiais do SAPL.
    """
    limite = subtrair_meses(date.today(), meses).isoformat()
    r_norm = normalizar(rua)
    b_norm = normalizar(bairro) if bairro else ""

    with _conn() as con:
        # 1. Checa banco local do SIGI
        sql = "SELECT id, rua, bairro, tipo_servico, data, 'SIGI' as fonte, null as link FROM indicacoes WHERE rua_norm = ? AND tipo_servico = ? AND data >= ?"
        params: list = [r_norm, tipo_servico, limite]
        if b_norm:
            sql += " AND bairro_norm = ?"
            params.append(b_norm)
        sql += " ORDER BY data DESC LIMIT 1"
        row = con.execute(sql, params).fetchone()
        if row:
            return dict(row)

        # 2. Checa matérias do SAPL
        sql_sapl = "SELECT sapl_id as id, rua, bairro, tipo_servico, data, ('SAPL nº ' || numero || '/' || ano) as fonte, link_sapl as link, texto_original as pdf FROM sapl_materias WHERE rua_norm = ? AND (tipo_servico = ? OR tipo_servico = 'Indicação Geral') AND data >= ?"
        p_sapl: list = [r_norm, tipo_servico, limite]
        if b_norm:
            sql_sapl += " AND bairro_norm = ?"
            p_sapl.append(b_norm)
        sql_sapl += " ORDER BY data DESC LIMIT 1"
        row_sapl = con.execute(sql_sapl, p_sapl).fetchone()
        if row_sapl:
            return dict(row_sapl)

    return None


def mapa_recentes(tipo_servico: str, meses: int = MESES_ALERTA) -> dict[tuple[str, str], dict]:
    """
    {(rua_norm, bairro_norm): {'data': 'AAAA-MM-DD', 'total': n, 'fonte': str}}
    Combina registros locais do SIGI e matérias oficiais do SAPL.
    """
    limite = subtrair_meses(date.today(), meses).isoformat()
    mapa = {}

    with _conn() as con:
        # Locais
        rows = con.execute(
            "SELECT rua_norm, bairro_norm, MAX(data) AS data, COUNT(*) AS total FROM indicacoes "
            "WHERE tipo_servico = ? AND data >= ? GROUP BY rua_norm, bairro_norm",
            (tipo_servico, limite),
        ).fetchall()
        for r in rows:
            if r["rua_norm"]:
                mapa[(r["rua_norm"], r["bairro_norm"])] = {"data": r["data"], "total": r["total"], "fonte": "SIGI"}

        # SAPL Oficial
        rows_sapl = con.execute(
            "SELECT rua_norm, bairro_norm, MAX(data) AS data, COUNT(*) AS total, MAX(numero) AS num, MAX(ano) AS ano "
            "FROM sapl_materias WHERE (tipo_servico = ? OR tipo_servico = 'Indicação Geral') AND data >= ? AND rua_norm != '' "
            "GROUP BY rua_norm, bairro_norm",
            (tipo_servico, limite),
        ).fetchall()
        for r in rows_sapl:
            k = (r["rua_norm"], r["bairro_norm"])
            if k not in mapa or r["data"] > mapa[k]["data"]:
                mapa[k] = {"data": r["data"], "total": r["total"], "fonte": f"SAPL nº {r['num']}/{r['ano']}"}

    return mapa


def listar_indicacoes(limite: int = 500, bairro: str | None = None, tipo: str | None = None,
                      busca: str | None = None, de: date | None = None, ate: date | None = None) -> list[dict]:
    sql = "SELECT * FROM indicacoes WHERE 1=1"
    p: list = []
    if bairro:
        sql += " AND bairro_norm = ?"; p.append(normalizar(bairro))
    if tipo:
        sql += " AND tipo_servico = ?"; p.append(tipo)
    if busca:
        sql += " AND rua_norm LIKE ?"; p.append(f"%{normalizar(busca)}%")
    if de:
        sql += " AND data >= ?"; p.append(de.isoformat() if hasattr(de, "isoformat") else str(de))
    if ate:
        sql += " AND data <= ?"; p.append(ate.isoformat() if hasattr(ate, "isoformat") else str(ate))
    sql += " ORDER BY data DESC, id DESC LIMIT ?"
    p.append(limite)
    with _conn() as con:
        return [dict(r) for r in con.execute(sql, p).fetchall()]


def total_geral() -> int:
    with _conn() as con:
        return con.execute("SELECT COUNT(*) FROM indicacoes").fetchone()[0]


def serie_diaria(dias: int = 14) -> list[dict]:
    from utils import ultimos_dias
    dias_lista = ultimos_dias(dias)
    with _conn() as con:
        rows = con.execute(
            "SELECT data, COUNT(*) AS total FROM indicacoes WHERE data >= ? GROUP BY data",
            (dias_lista[0].isoformat(),),
        ).fetchall()
    mapa = {r["data"]: r["total"] for r in rows}
    return [{"data": d, "total": mapa.get(d.isoformat(), 0)} for d in dias_lista]


def contagem_por(campo: str, limite: int = 10) -> list[dict]:
    if campo not in {"bairro", "tipo_servico", "rua"}:
        raise ValueError("campo inválido")
    with _conn() as con:
        rows = con.execute(
            f"SELECT {campo} AS nome, COUNT(*) AS total FROM indicacoes "
            f"GROUP BY {campo} ORDER BY total DESC LIMIT ?", (limite,)
        ).fetchall()
    return [dict(r) for r in rows]


def sequencia_dias_meta(meta: int) -> int:
    from datetime import timedelta
    with _conn() as con:
        rows = con.execute(
            "SELECT data, COUNT(*) AS total FROM indicacoes GROUP BY data HAVING total >= ?", (meta,)
        ).fetchall()
    ok = {r["data"] for r in rows}
    d = date.today()
    if d.isoformat() not in ok:
        d -= timedelta(days=1)
    streak = 0
    while d.isoformat() in ok:
        streak += 1
        d -= timedelta(days=1)
    return streak
