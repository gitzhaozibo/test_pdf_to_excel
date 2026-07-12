from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from typing import Dict, List, Optional

import psycopg
from psycopg import OperationalError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import TABLE_COLUMNS


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS contracts (
    id SERIAL PRIMARY KEY,
    filename TEXT,
    pdf_hash TEXT UNIQUE,
    pdf_data BYTEA,
    extracted_at TIMESTAMPTZ DEFAULT now(),
    contract_no TEXT,
    contract_name TEXT,
    party_a TEXT,
    party_b TEXT,
    contract_date TEXT,
    amount TEXT,
    period TEXT,
    payment_terms TEXT,
    raw_json JSONB
);
"""

# 既存テーブルへPDF保存とハッシュ判定用のカラムを追加するためのマイグレーション
MIGRATE_TABLE_SQL = """
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS pdf_hash TEXT;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS pdf_data BYTEA;
CREATE UNIQUE INDEX IF NOT EXISTS contracts_pdf_hash_key ON contracts (pdf_hash);
"""


def compute_pdf_hash(pdf_bytes: bytes) -> str:
    """PDFの内容からSHA-256ハッシュ値を計算する（ファイル名ではなく内容で同一判定するため）。"""
    return hashlib.sha256(pdf_bytes).hexdigest()


def _is_retryable_db_error(exc: Exception) -> bool:
    if isinstance(exc, OperationalError):
        sqlstate = getattr(exc, "sqlstate", None)
        if sqlstate in ("28P01", "28000"):
            return False
        return True
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_retryable_db_error),
    reraise=True,
)
def get_connection() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])


def init_db() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute(MIGRATE_TABLE_SQL)
        conn.commit()


def find_contract_by_hash(pdf_hash: str) -> Optional[Dict]:
    """同一内容のPDFが既にDBに存在すれば、その抽出結果を返す。存在しなければNone。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, filename, extracted_at, raw_json
                FROM contracts
                WHERE pdf_hash = %s
                ORDER BY extracted_at DESC
                LIMIT 1
                """,
                [pdf_hash],
            )
            row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "filename": row[1],
        "extracted_at": row[2],
        "extracted": row[3],
    }


def save_contract(filename: str, extracted: Dict, pdf_bytes: bytes) -> None:
    values = [
        (extracted.get(column) or {}).get("value")
        for column in TABLE_COLUMNS
    ]
    pdf_hash = compute_pdf_hash(pdf_bytes)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO contracts (
                    filename, pdf_hash, pdf_data, contract_no, contract_name,
                    party_a, party_b, contract_date, amount, period,
                    payment_terms, raw_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (pdf_hash) DO UPDATE SET
                    filename = EXCLUDED.filename,
                    pdf_data = EXCLUDED.pdf_data,
                    extracted_at = now(),
                    contract_no = EXCLUDED.contract_no,
                    contract_name = EXCLUDED.contract_name,
                    party_a = EXCLUDED.party_a,
                    party_b = EXCLUDED.party_b,
                    contract_date = EXCLUDED.contract_date,
                    amount = EXCLUDED.amount,
                    period = EXCLUDED.period,
                    payment_terms = EXCLUDED.payment_terms,
                    raw_json = EXCLUDED.raw_json
                """,
                [
                    filename,
                    pdf_hash,
                    pdf_bytes,
                    *values,
                    json.dumps(extracted, ensure_ascii=False),
                ],
            )
        conn.commit()


def fetch_contracts(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> List[Dict]:
    sql = """
    SELECT id, filename, extracted_at, contract_no, contract_name, party_a, party_b,
           contract_date, amount, period, payment_terms
    FROM contracts
    """
    params = []
    conditions = []
    if from_date:
        conditions.append("extracted_at::date >= %s")
        params.append(from_date)
    if to_date:
        conditions.append("extracted_at::date <= %s")
        params.append(to_date)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY extracted_at DESC"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    result = []
    for row in rows:
        result.append(
            {
                "id": row[0],
                "filename": row[1],
                "extracted_at": row[2],
                "contract_no": row[3],
                "contract_name": row[4],
                "party_a": row[5],
                "party_b": row[6],
                "contract_date": row[7],
                "amount": row[8],
                "period": row[9],
                "payment_terms": row[10],
            }
        )
    return result
