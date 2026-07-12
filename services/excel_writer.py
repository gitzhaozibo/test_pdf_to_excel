from __future__ import annotations

import io
from typing import Dict, List

from openpyxl import Workbook

from config import EXTRACT_FIELDS


def contracts_to_excel(records: List[Dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "契約一覧"

    headers = ["ID", "ファイル名", "抽出日時"] + [f["label"] for f in EXTRACT_FIELDS]
    ws.append(headers)

    for record in records:
        row = [
            record.get("id"),
            record.get("filename"),
            str(record.get("extracted_at") or ""),
        ]
        for field in EXTRACT_FIELDS:
            row.append(record.get(field["key"]) or "")
        ws.append(row)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
