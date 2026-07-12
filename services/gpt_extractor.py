from __future__ import annotations

import json
import os
from typing import Dict

from openai import APIConnectionError, APITimeoutError, APIStatusError, AzureOpenAI
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import EXTRACT_FIELDS, RETRYABLE_HTTP_STATUS_CODES


SYSTEM_PROMPT = """あなたは契約書抽出アシスタントです。
OCRテキストから指定項目をJSONで抽出してください。
- 各項目は {"value": 正規化値, "source_text": OCR原文}。
- OCR原文に実在しない値は出力しない。
- 存在しない項目は {"value": null, "source_text": null}。
- 推測は禁止。
- 日付はYYYY/MM/DDに正規化（和暦は西暦へ変換）。
"""


def _is_retryable_openai_error(exc: Exception) -> bool:
    if isinstance(exc, APIStatusError):
        if exc.status_code in (401, 403):
            return False
        return exc.status_code in RETRYABLE_HTTP_STATUS_CODES
    return isinstance(exc, (APIConnectionError, APITimeoutError))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_retryable_openai_error),
    reraise=True,
)
def extract_fields_from_text(full_text: str) -> Dict:
    client = AzureOpenAI(
        azure_endpoint=os.environ["AOAI_ENDPOINT"],
        api_key=os.environ["AOAI_KEY"],
        api_version=os.environ.get("AOAI_API_VERSION", "2024-10-21"),
    )

    item_lines = "\n".join([f"- {f['key']}: {f['label']}" for f in EXTRACT_FIELDS])
    response = client.chat.completions.create(
        model=os.environ["AOAI_DEPLOYMENT"],
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"抽出項目:\n{item_lines}\n\nOCR全文:\n{full_text}",
            },
        ],
    )

    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)

    result: Dict = {}
    for field in EXTRACT_FIELDS:
        key = field["key"]
        item = parsed.get(key)
        if not isinstance(item, dict):
            result[key] = {"value": None, "source_text": None}
            continue
        result[key] = {
            "value": item.get("value"),
            "source_text": item.get("source_text"),
        }
    return result
