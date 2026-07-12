from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass
class MatchResult:
    page: int
    word_start: int
    word_end: int
    score: float


def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(normalized.split()).lower()


def build_page_char_index(words: Sequence[Dict]) -> Tuple[str, List[int]]:
    normalized_parts: List[str] = []
    char_to_word_index: List[int] = []
    for idx, word in enumerate(words):
        part = normalize_text(word.get("text", ""))
        if not part:
            continue
        normalized_parts.append(part)
        char_to_word_index.extend([idx] * len(part))
    return "".join(normalized_parts), char_to_word_index


def _word_span_from_char_span(
    char_to_word_index: Sequence[int], start: int, end: int
) -> Optional[Tuple[int, int]]:
    if start < 0 or end <= start or end > len(char_to_word_index):
        return None
    return char_to_word_index[start], char_to_word_index[end - 1]


def find_source_match_in_page(
    page_words: Sequence[Dict], source_text: str, fuzzy_threshold: float = 0.8
) -> Optional[MatchResult]:
    target = normalize_text(source_text)
    if not target:
        return None

    page_text, char_to_word_index = build_page_char_index(page_words)
    if not page_text:
        return None

    exact_pos = page_text.find(target)
    if exact_pos >= 0:
        span = _word_span_from_char_span(char_to_word_index, exact_pos, exact_pos + len(target))
        if not span:
            return None
        return MatchResult(page=page_words[0]["page"], word_start=span[0], word_end=span[1], score=1.0)

    target_len = len(target)
    if target_len == 0 or target_len > len(page_text):
        return None

    best_score = 0.0
    best_span = None
    min_len = max(1, int(target_len * 0.85))
    max_len = min(len(page_text), int(target_len * 1.15) + 1)

    for start in range(len(page_text)):
        if page_text[start] != target[0] and target_len > 3:
            continue
        for window_len in range(min_len, max_len + 1):
            end = start + window_len
            if end > len(page_text):
                break
            candidate = page_text[start:end]
            score = difflib.SequenceMatcher(None, target, candidate).ratio()
            if score > best_score:
                best_score = score
                best_span = (start, end)

    if best_score < fuzzy_threshold or not best_span:
        return None

    span = _word_span_from_char_span(char_to_word_index, best_span[0], best_span[1])
    if not span:
        return None
    return MatchResult(page=page_words[0]["page"], word_start=span[0], word_end=span[1], score=best_score)


def locate_source_text(words: Sequence[Dict], source_text: str) -> Optional[MatchResult]:
    by_page: Dict[int, List[Dict]] = {}
    for word in words:
        by_page.setdefault(word["page"], []).append(word)

    best: Optional[MatchResult] = None
    for page_no in sorted(by_page.keys()):
        result = find_source_match_in_page(by_page[page_no], source_text)
        if result and (best is None or result.score > best.score):
            best = result
            if result.score == 1.0:
                break
    return best


def _polygon_to_rect(word: Dict):
    import fitz

    polygon = word.get("polygon") or []
    xs = polygon[0::2]
    ys = polygon[1::2]
    if not xs or not ys:
        return None

    return fitz.Rect(min(xs), min(ys), max(xs), max(ys))


def render_highlighted_pages(pdf_bytes: bytes, words: Sequence[Dict], extracted: Dict[str, Dict]):
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    match_status: Dict[str, bool] = {}

    try:
        for key, item in extracted.items():
            source_text = (item or {}).get("source_text")
            if not source_text:
                match_status[key] = False
                continue

            match = locate_source_text(words, source_text)
            if not match:
                match_status[key] = False
                continue

            page = doc[match.page - 1]
            page_words = [w for w in words if w["page"] == match.page]
            selected_words = page_words[match.word_start : match.word_end + 1]
            matched_any = False

            for word in selected_words:
                rect_inch = _polygon_to_rect(word)
                if rect_inch is None:
                    continue

                page_width_in = word.get("page_width")
                page_height_in = word.get("page_height")
                if not page_width_in or not page_height_in:
                    continue

                sx = page.rect.width / page_width_in
                sy = page.rect.height / page_height_in

                rect_pt = fitz.Rect(
                    rect_inch.x0 * sx,
                    rect_inch.y0 * sy,
                    rect_inch.x1 * sx,
                    rect_inch.y1 * sy,
                )
                page.draw_rect(
                    rect_pt,
                    color=(1, 0.4, 0),
                    fill=(1, 0.9, 0.2),
                    fill_opacity=0.35,
                    width=1,
                )
                matched_any = True
            match_status[key] = matched_any

        images = [p.get_pixmap(dpi=120).tobytes("png") for p in doc]
        return images, match_status
    finally:
        doc.close()
