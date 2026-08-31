"""テスト用契約書PDFを生成するスクリプト。

生成物 (tests/data/):
- test_contract.pdf          : 通常のスキャン風契約書PDF
- test_contract_rotated.pdf  : ページ内容が90度回転したスキャン風契約書PDF

実行方法:
    python scripts/generate_test_pdfs.py
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

OUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "data"

LINES = [
    ("業務委託契約書", 18, True),
    ("", 12, False),
    ("契約書番号: KE-2026-00123", 12, False),
    ("", 12, False),
    ("株式会社サンプル商事（以下「甲」という。）と、テスト情報システム株式会社", 11, False),
    ("（以下「乙」という。）とは、以下のとおり業務委託契約（以下「本契約」という。）", 11, False),
    ("を締結する。", 11, False),
    ("", 12, False),
    ("第1条（契約名）", 12, True),
    ("本契約の名称は「基幹システム保守運用業務委託契約」とする。", 11, False),
    ("", 12, False),
    ("第2条（契約期間）", 12, True),
    ("本契約の契約期間は、2026年4月1日から2027年3月31日までとする。", 11, False),
    ("", 12, False),
    ("第3条（契約金額）", 12, True),
    ("本業務の契約金額は、金12,100,000円（消費税込み）とする。", 11, False),
    ("", 12, False),
    ("第4条（支払条件）", 12, True),
    ("甲は、乙に対し、毎月末日締め翌月末日までに乙の指定する銀行口座に振り込み", 11, False),
    ("支払うものとする。振込手数料は甲の負担とする。", 11, False),
    ("", 12, False),
    ("第5条（秘密保持）", 12, True),
    ("甲および乙は、本契約に関して知り得た相手方の秘密情報を第三者に開示または", 11, False),
    ("漏洩してはならない。", 11, False),
    ("", 12, False),
    ("本契約の成立を証するため、本書2通を作成し、甲乙記名押印のうえ、", 11, False),
    ("各1通を保有する。", 11, False),
    ("", 12, False),
    ("契約日: 2026年3月15日", 12, False),
    ("", 12, False),
    ("甲: 東京都千代田区丸の内一丁目1番1号", 11, False),
    ("   株式会社サンプル商事", 11, False),
    ("   代表取締役 山田 太郎", 11, False),
    ("", 12, False),
    ("乙: 大阪府大阪市北区梅田二丁目2番2号", 11, False),
    ("   テスト情報システム株式会社", 11, False),
    ("   代表取締役 佐藤 花子", 11, False),
]


def build_text_page(doc: fitz.Document) -> None:
    page = doc.new_page(width=595, height=842)  # A4
    y = 60.0
    for text, size, bold in LINES:
        if text:
            x = 200 if "業務委託契約書" == text else 60
            page.insert_text(
                (x, y),
                text,
                fontsize=size,
                fontname="japan" if not bold else "japan",
                fill=(0, 0, 0),
            )
        y += size + 8


def rasterize(doc: fitz.Document, rotate: int = 0) -> fitz.Document:
    """テキストPDFを画像化してスキャン風PDFに変換する。rotate で内容自体を回転。"""
    scan_doc = fitz.open()
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        if rotate == 0:
            new_page = scan_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, pixmap=pix)
        else:
            # 内容自体を回転させた横向きページを作成（回転スキャンの再現）
            new_page = scan_doc.new_page(width=page.rect.height, height=page.rect.width)
            new_page.insert_image(new_page.rect, pixmap=pix, rotate=rotate)
    return scan_doc


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    text_doc = fitz.open()
    build_text_page(text_doc)

    normal = rasterize(text_doc, rotate=0)
    normal.save(OUT_DIR / "test_contract.pdf")
    normal.close()

    rotated = rasterize(text_doc, rotate=90)
    rotated.save(OUT_DIR / "test_contract_rotated.pdf")
    rotated.close()

    text_doc.close()
    print(f"generated: {OUT_DIR / 'test_contract.pdf'}")
    print(f"generated: {OUT_DIR / 'test_contract_rotated.pdf'}")


if __name__ == "__main__":
    main()
