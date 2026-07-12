EXTRACT_FIELDS = [
    {"key": "contract_no", "label": "契約書番号"},
    {"key": "contract_name", "label": "契約名"},
    {"key": "party_a", "label": "甲"},
    {"key": "party_b", "label": "乙"},
    {"key": "contract_date", "label": "契約日"},
    {"key": "period", "label": "契約期間"},
    {"key": "amount", "label": "契約金額"},
    {"key": "payment_terms", "label": "支払条件"},
]

TABLE_COLUMNS = [field["key"] for field in EXTRACT_FIELDS]

RETRYABLE_HTTP_STATUS_CODES = (408, 429, 500, 502, 503, 504)
OCR_FUZZY_LENGTH_TOLERANCE = 0.15
