import hashlib

from services.db import compute_pdf_hash


def test_compute_pdf_hash_matches_sha256():
    data = b"%PDF-1.4 sample bytes"
    assert compute_pdf_hash(data) == hashlib.sha256(data).hexdigest()


def test_compute_pdf_hash_is_content_based_not_filename():
    same_content_a = b"identical pdf content"
    same_content_b = b"identical pdf content"
    different_content = b"other pdf content"

    assert compute_pdf_hash(same_content_a) == compute_pdf_hash(same_content_b)
    assert compute_pdf_hash(same_content_a) != compute_pdf_hash(different_content)
