from __future__ import annotations

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


def _is_retryable_db_error(exc: Exception) -> bool:
    if isinstance(exc, OperationalError):
        text = str(exc).lower()
        if "password authentication failed" in text or "invalid authorization" in text:
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
        conn.commit()


def save_contract(filename: str, extracted: Dict) -> None:
    values = [
        (extracted.get(column) or {}).get("value")
        for column in TABLE_COLUMNS
    ]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO contracts (
                    filename, contract_no, contract_name, party_a, party_b,
                    contract_date, amount, period, payment_terms, raw_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                [filename, *values, json.dumps(extracted, ensure_ascii=False)],
            )
        conn.commit()


def fetch_contracts(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> List[Dict]:
    # conditions は固定SQL断片のみを連結し、値は必ずパラメータバインドで渡す
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
