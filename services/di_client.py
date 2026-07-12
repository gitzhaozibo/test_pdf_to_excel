from __future__ import annotations

import os
from typing import Dict, List, Tuple

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError, ServiceRequestError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _is_retryable_di_error(exc: Exception) -> bool:
    if isinstance(exc, HttpResponseError):
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            return False
        return status in (408, 429, 500, 502, 503, 504)
    return isinstance(exc, ServiceRequestError)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_retryable_di_error),
    reraise=True,
)
def analyze_pdf(pdf_bytes: bytes) -> Tuple[str, List[Dict]]:
    client = DocumentIntelligenceClient(
        endpoint=os.environ["DI_ENDPOINT"],
        credential=AzureKeyCredential(os.environ["DI_KEY"]),
    )
    poller = client.begin_analyze_document(
        "prebuilt-layout",
        body=pdf_bytes,
        content_type="application/pdf",
    )
    result = poller.result()

    words: List[Dict] = []
    for page in result.pages or []:
        for word in page.words or []:
            words.append(
                {
                    "page": page.page_number,
                    "text": word.content,
                    "polygon": list(word.polygon or []),
                    "page_width": page.width,
                    "page_height": page.height,
                }
            )

    return result.content or "", words
