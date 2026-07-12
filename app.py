from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from azure.core.exceptions import HttpResponseError, ServiceRequestError
from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, APIStatusError
from psycopg import OperationalError

from config import EXTRACT_FIELDS
from services.db import fetch_contracts, init_db, save_contract
from services.di_client import analyze_pdf
from services.excel_writer import contracts_to_excel
from services.gpt_extractor import extract_fields_from_text
from services.pdf_marker import render_highlighted_pages

load_dotenv()

st.set_page_config(page_title="契約書抽出アプリ", layout="wide")
st.title("契約書スキャンPDF 抽出アプリ")


def _show_error(prefix: str, exc: Exception) -> None:
    if isinstance(exc, (HttpResponseError, APIStatusError)):
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            st.error(f"{prefix}: 認証エラーです。設定を確認してください。")
            return
    st.error(f"{prefix}: 一時的エラーが発生しました。時間をおいて再試行してください。\n{exc}")


def extract_tab() -> None:
    st.subheader("抽出・確認")

    uploaded_file = st.file_uploader("契約書PDFをアップロード", type=["pdf"])

    if "preview_images" not in st.session_state:
        st.session_state.preview_images = None
    if "editable_extracted" not in st.session_state:
        st.session_state.editable_extracted = None
    if "match_status" not in st.session_state:
        st.session_state.match_status = {}
    if "current_filename" not in st.session_state:
        st.session_state.current_filename = None

    if uploaded_file and st.button("データ抽出", type="primary"):
        pdf_bytes = uploaded_file.getvalue()

        try:
            with st.status("処理中", expanded=True) as status:
                st.write("OCR中 (Azure Document Intelligence)")
                full_text, words = analyze_pdf(pdf_bytes)

                st.write("AI抽出中 (Azure OpenAI)")
                extracted = extract_fields_from_text(full_text)

                st.write("マーキング中")
                images, match_status = render_highlighted_pages(pdf_bytes, words, extracted)

                st.session_state.preview_images = images
                st.session_state.editable_extracted = extracted
                st.session_state.match_status = match_status
                st.session_state.current_filename = uploaded_file.name
                status.update(label="完了", state="complete")
        except (HttpResponseError, ServiceRequestError) as exc:
            _show_error("OCR処理エラー", exc)
        except (APIConnectionError, APITimeoutError, APIStatusError) as exc:
            _show_error("AI抽出エラー", exc)
        except Exception as exc:
            st.error(f"予期しないエラーが発生しました: {exc}")

    if st.session_state.preview_images and st.session_state.editable_extracted:
        left, right = st.columns([2, 1])

        with left:
            st.markdown("#### ハイライト付きPDFページ")
            page_no = st.number_input(
                "ページ",
                min_value=1,
                max_value=len(st.session_state.preview_images),
                value=1,
                step=1,
            )
            st.image(st.session_state.preview_images[page_no - 1], use_container_width=True)

        with right:
            st.markdown("#### 項目確認")
            for field in EXTRACT_FIELDS:
                key = field["key"]
                current = st.session_state.editable_extracted.get(key) or {}
                source_text = current.get("source_text")
                if source_text and not st.session_state.match_status.get(key, False):
                    st.warning(f"{field['label']}: 位置特定不可")

                current_value = current.get("value")
                value = st.text_input(
                    field["label"],
                    value="" if current_value is None else str(current_value),
                    key=f"edit_{key}",
                    help=f"原文: {source_text if source_text else 'なし'}",
                )
                st.session_state.editable_extracted[key] = {
                    "value": value if value != "" else None,
                    "source_text": source_text,
                }

            if st.button("OK（DBに保存）", type="primary"):
                try:
                    save_contract(
                        st.session_state.current_filename or "unknown.pdf",
                        st.session_state.editable_extracted,
                    )
                    st.success("DBに保存しました。")
                except OperationalError as exc:
                    _show_error("DB保存エラー", exc)
                except Exception as exc:
                    st.error(f"保存中にエラーが発生しました: {exc}")


def excel_tab() -> None:
    st.subheader("Excel出力")
    use_filter = st.checkbox("期間フィルタを使用する", value=False)
    from_date = None
    to_date = None
    if use_filter:
        c1, c2 = st.columns(2)
        today = date.today()
        from_date = c1.date_input("開始日", value=today)
        to_date = c2.date_input("終了日", value=today)

    try:
        records = fetch_contracts(
            from_date=from_date,
            to_date=to_date,
        )
    except OperationalError as exc:
        _show_error("DB取得エラー", exc)
        return
    except Exception as exc:
        st.error(f"一覧取得中にエラーが発生しました: {exc}")
        return

    if not records:
        st.info("保存済みデータはありません。")
        return

    st.dataframe(pd.DataFrame(records), use_container_width=True)
    st.download_button(
        label="Excelダウンロード",
        data=contracts_to_excel(records),
        file_name="contracts.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


try:
    init_db()
except OperationalError as exc:
    _show_error("DB初期化エラー", exc)
    st.stop()
except Exception as exc:
    st.error(f"起動時エラー: {exc}")
    st.stop()

extract, excel = st.tabs(["データ抽出", "Excel出力"])
with extract:
    extract_tab()
with excel:
    excel_tab()
