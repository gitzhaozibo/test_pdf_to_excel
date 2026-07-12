from __future__ import annotations

import hashlib
import os
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import (
    Column,
    Date,
    Integer,
    LargeBinary,
    MetaData,
    Table,
    Text,
    cast,
    create_engine,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import func
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import TABLE_COLUMNS


metadata = MetaData()

contracts = Table(
    "contracts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("filename", Text),
    Column("pdf_hash", Text, unique=True),
    Column("pdf_data", LargeBinary),
    Column("extracted_at", TIMESTAMP(timezone=True), server_default=func.now()),
    Column("contract_no", Text),
    Column("contract_name", Text),
    Column("party_a", Text),
    Column("party_b", Text),
    Column("contract_date", Text),
    Column("amount", Text),
    Column("period", Text),
    Column("payment_terms", Text),
    Column("raw_json", JSONB),
)

# 既存テーブルへPDF保存とハッシュ判定用のカラムを追加するためのマイグレーション
MIGRATE_TABLE_SQL = [
    "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS pdf_hash TEXT",
    "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS pdf_data BYTEA",
    "CREATE UNIQUE INDEX IF NOT EXISTS contracts_pdf_hash_key ON contracts (pdf_hash)",
]


def compute_pdf_hash(pdf_bytes: bytes) -> str:
    """PDFの内容からSHA-256ハッシュ値を計算する（ファイル名ではなく内容で同一判定するため）。"""
    return hashlib.sha256(pdf_bytes).hexdigest()


def _normalize_database_url(url: str) -> str:
    """psycopg(v3)ドライバを使うようSQLAlchemy用のURLへ正規化する。"""
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def _is_retryable_db_error(exc: Exception) -> bool:
    if isinstance(exc, OperationalError):
        orig = getattr(exc, "orig", None)
        sqlstate = getattr(orig, "sqlstate", None)
        if sqlstate in ("28P01", "28000"):
            return False
        return True
    return False


_engine: Optional[Engine] = None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_retryable_db_error),
    reraise=True,
)
def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            _normalize_database_url(os.environ["DATABASE_URL"]),
            pool_pre_ping=True,
        )
    # 接続可能かを確認し、一時的な障害はリトライ対象にする
    with _engine.connect():
        pass
    return _engine


def init_db() -> None:
    engine = get_engine()
    metadata.create_all(engine)
    with engine.begin() as conn:
        for statement in MIGRATE_TABLE_SQL:
            conn.execute(text(statement))


def find_contract_by_hash(pdf_hash: str) -> Optional[Dict]:
    """同一内容のPDFが既にDBに存在すれば、その抽出結果を返す。存在しなければNone。"""
    engine = get_engine()
    stmt = (
        select(
            contracts.c.id,
            contracts.c.filename,
            contracts.c.extracted_at,
            contracts.c.raw_json,
        )
        .where(contracts.c.pdf_hash == pdf_hash)
        .order_by(contracts.c.extracted_at.desc())
        .limit(1)
    )
    with engine.connect() as conn:
        row = conn.execute(stmt).first()

    if row is None:
        return None

    return {
        "id": row[0],
        "filename": row[1],
        "extracted_at": row[2],
        "extracted": row[3],
    }


def save_contract(filename: str, extracted: Dict, pdf_bytes: bytes) -> None:
    values = {
        column: (extracted.get(column) or {}).get("value")
        for column in TABLE_COLUMNS
    }
    pdf_hash = compute_pdf_hash(pdf_bytes)
    insert_values = {
        "filename": filename,
        "pdf_hash": pdf_hash,
        "pdf_data": pdf_bytes,
        "raw_json": extracted,
        **values,
    }
    stmt = insert(contracts).values(**insert_values)
    update_values = {
        "filename": stmt.excluded.filename,
        "pdf_data": stmt.excluded.pdf_data,
        "extracted_at": func.now(),
        "raw_json": stmt.excluded.raw_json,
    }
    for column in TABLE_COLUMNS:
        update_values[column] = getattr(stmt.excluded, column)
    stmt = stmt.on_conflict_do_update(
        index_elements=["pdf_hash"],
        set_=update_values,
    )

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(stmt)


def fetch_contracts(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> List[Dict]:
    stmt = select(
        contracts.c.id,
        contracts.c.filename,
        contracts.c.extracted_at,
        contracts.c.contract_no,
        contracts.c.contract_name,
        contracts.c.party_a,
        contracts.c.party_b,
        contracts.c.contract_date,
        contracts.c.amount,
        contracts.c.period,
        contracts.c.payment_terms,
    )
    if from_date:
        stmt = stmt.where(cast(contracts.c.extracted_at, Date) >= from_date)
    if to_date:
        stmt = stmt.where(cast(contracts.c.extracted_at, Date) <= to_date)
    stmt = stmt.order_by(contracts.c.extracted_at.desc())

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(stmt).all()

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
