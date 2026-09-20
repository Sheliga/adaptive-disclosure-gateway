"""Optional T12 integration pins for the real Docling adapter.

The baseline dev/test environment must not require Docling, because the
project keeps it under the optional ``documents`` extra. These tests run
only when that extra is installed, while the fake-parser tests in
``test_application_ingestion.py`` pin the core contract for every run.
"""

from __future__ import annotations

import os
from io import BytesIO

import pytest

from adaptive_disclosure_gateway.application.ingestion import normalize_text_file
from tests.document_fixtures import minimal_docx_bytes, minimal_pdf_bytes

pytest.importorskip("docling")
pytestmark = pytest.mark.skipif(
    os.environ.get("ADG_RUN_DOCLING_INTEGRATION") != "1",
    reason=(
        "real Docling conversion can require external model artifacts; set "
        "ADG_RUN_DOCLING_INTEGRATION=1 in an environment with those artifacts available"
    ),
)


def _minimal_xlsx_bytes() -> bytes:
    xlsxwriter = pytest.importorskip("xlsxwriter")
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    worksheet = workbook.add_worksheet("terms")
    worksheet.write(0, 0, "Party")
    worksheet.write(0, 1, "Role")
    worksheet.write(1, 0, "ACME")
    worksheet.write(1, 1, "vendor")
    workbook.close()
    return output.getvalue()


def test_real_docling_adapter_extracts_pdf_text():
    result = normalize_text_file("agreement.pdf", minimal_pdf_bytes())

    assert result.source_kind == "document_file"
    assert result.media_type == "application/pdf"
    assert result.parser_name == "docling"
    assert result.ingestion_version == "docling-structured-markdown-v1"
    assert "ACME Services Agreement" in result.text
    assert all(block.text in result.text for block in result.blocks)


def test_real_docling_adapter_extracts_docx_text():
    result = normalize_text_file("agreement.docx", minimal_docx_bytes())

    assert result.source_kind == "document_file"
    assert result.media_type.endswith("wordprocessingml.document")
    assert result.parser_name == "docling"
    assert "ACME Master Services Agreement" in result.text
    assert "Renewal term" in result.text
    assert any("ACME Master Services Agreement" in block.text for block in result.blocks)


def test_real_docling_adapter_extracts_xlsx_table_text():
    result = normalize_text_file("agreement.xlsx", _minimal_xlsx_bytes())

    assert result.source_kind == "document_file"
    assert result.media_type.endswith("spreadsheetml.sheet")
    assert result.parser_name == "docling"
    assert "Party" in result.text
    assert "ACME" in result.text
    assert any(block.kind == "table" and "Party" in block.text for block in result.blocks)
