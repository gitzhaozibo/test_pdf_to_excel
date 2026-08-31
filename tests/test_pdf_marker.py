import fitz
import pytest

from services.pdf_marker import (
    _polygon_to_page_rect,
    build_page_char_index,
    find_source_match_in_page,
    locate_source_text,
    normalize_text,
)


def test_normalize_text_nfkc_and_space():
    assert normalize_text("  ＡＢＣ １２３\n") == "abc123"


def test_normalize_text_handles_empty_and_none():
    assert normalize_text("") == ""
    assert normalize_text("   \n\t") == ""
    assert normalize_text(None) == ""


def test_build_page_char_index_maps_char_to_word():
    words = [
        {"page": 1, "text": "契約", "polygon": [], "page_width": 8.27, "page_height": 11.69},
        {"page": 1, "text": "番号", "polygon": [], "page_width": 8.27, "page_height": 11.69},
    ]
    text, mapping = build_page_char_index(words)
    assert text == "契約番号"
    assert mapping == [0, 0, 1, 1]


def test_find_source_match_in_page_exact_across_words():
    words = [
        {"page": 1, "text": "契約", "polygon": [], "page_width": 8.27, "page_height": 11.69},
        {"page": 1, "text": "書", "polygon": [], "page_width": 8.27, "page_height": 11.69},
        {"page": 1, "text": "番号", "polygon": [], "page_width": 8.27, "page_height": 11.69},
    ]
    result = find_source_match_in_page(words, "契約書番号")
    assert result is not None
    assert result.word_start == 0
    assert result.word_end == 2
    assert result.score == 1.0


def test_find_source_match_in_page_fuzzy_when_not_exact():
    words = [
        {"page": 1, "text": "契約金額", "polygon": [], "page_width": 8.27, "page_height": 11.69},
        {"page": 1, "text": "100,000円", "polygon": [], "page_width": 8.27, "page_height": 11.69},
    ]
    result = find_source_match_in_page(words, "契約金額100000円")
    assert result is not None
    assert result.score >= 0.8


def test_locate_source_text_searches_per_page_only():
    words = [
        {"page": 1, "text": "契約", "polygon": [], "page_width": 8.27, "page_height": 11.69},
        {"page": 1, "text": "番号", "polygon": [], "page_width": 8.27, "page_height": 11.69},
        {"page": 2, "text": "契約", "polygon": [], "page_width": 8.27, "page_height": 11.69},
        {"page": 2, "text": "日", "polygon": [], "page_width": 8.27, "page_height": 11.69},
    ]
    assert locate_source_text(words, "契約番号").page == 1
    assert locate_source_text(words, "契約日").page == 2


def test_locate_source_text_returns_none_when_not_found():
    words = [
        {"page": 1, "text": "契約", "polygon": [], "page_width": 8.27, "page_height": 11.69},
        {"page": 1, "text": "番号", "polygon": [], "page_width": 8.27, "page_height": 11.69},
    ]
    assert locate_source_text(words, "支払条件") is None


@pytest.mark.parametrize(
    ("rotation", "page_width", "page_height", "expected"),
    [
        (0, 200, 100, fitz.Rect(10, 20, 30, 40)),
        (90, 100, 200, fitz.Rect(20, 70, 40, 90)),
        (180, 200, 100, fitz.Rect(170, 60, 190, 80)),
        (270, 100, 200, fitz.Rect(160, 10, 180, 30)),
    ],
)
def test_polygon_to_page_rect_accounts_for_pdf_rotation(
    rotation, page_width, page_height, expected
):
    doc = fitz.open()
    page = doc.new_page(width=200, height=100)
    page.set_rotation(rotation)
    word = {
        "polygon": [10, 20, 30, 20, 30, 40, 10, 40],
        "page_width": page_width,
        "page_height": page_height,
    }

    try:
        assert _polygon_to_page_rect(word, page) == expected
    finally:
        doc.close()


def test_polygon_to_page_rect_rejects_incomplete_coordinates():
    doc = fitz.open()
    page = doc.new_page()

    try:
        assert (
            _polygon_to_page_rect(
                {"polygon": [10, 20, 30], "page_width": 100, "page_height": 100},
                page,
            )
            is None
        )
    finally:
        doc.close()
