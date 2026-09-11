"""Optional T12 integration pins for the real Docling adapter.

The baseline dev/test environment must not require Docling, because the
project keeps it under the optional ``documents`` extra. These tests run
only when that extra is installed, while the fake-parser tests in
``test_application_ingestion.py`` pin the core contract for every run.
"""

from __future__ import annotations

import os
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from adaptive_disclosure_gateway.application.ingestion import normalize_text_file

pytest.importorskip("docling")
pytestmark = pytest.mark.skipif(
    os.environ.get("ADG_RUN_DOCLING_INTEGRATION") != "1",
    reason=(
        "real Docling conversion can require external model artifacts; set "
        "ADG_RUN_DOCLING_INTEGRATION=1 in an environment with those artifacts available"
    ),
)


def _minimal_pdf_bytes() -> bytes:
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        (
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
        ),
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    stream = b"BT /F1 18 Tf 72 720 Td (ACME Services Agreement) Tj ET\n"
    objects.append(
        b"5 0 obj << /Length "
        + str(len(stream)).encode("ascii")
        + b" >> stream\n"
        + stream
        + b"endstream endobj\n"
    )

    output = BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(output.tell())
        output.write(obj)
    xref_at = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
        ).encode("ascii")
    )
    return output.getvalue()


def _minimal_docx_bytes() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as docx:
        docx.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        docx.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        docx.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>ACME Master Services Agreement</w:t></w:r></w:p>
    <w:p><w:r><w:t>Renewal term: twelve months</w:t></w:r></w:p>
  </w:body>
</w:document>""",
        )
    return output.getvalue()


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
    result = normalize_text_file("agreement.pdf", _minimal_pdf_bytes())

    assert result.source_kind == "document_file"
    assert result.media_type == "application/pdf"
    assert result.parser_name == "docling"
    assert result.ingestion_version == "docling-markdown-v1"
    assert "ACME Services Agreement" in result.text


def test_real_docling_adapter_extracts_docx_text():
    result = normalize_text_file("agreement.docx", _minimal_docx_bytes())

    assert result.source_kind == "document_file"
    assert result.media_type.endswith("wordprocessingml.document")
    assert result.parser_name == "docling"
    assert "ACME Master Services Agreement" in result.text
    assert "Renewal term" in result.text


def test_real_docling_adapter_extracts_xlsx_table_text():
    result = normalize_text_file("agreement.xlsx", _minimal_xlsx_bytes())

    assert result.source_kind == "document_file"
    assert result.media_type.endswith("spreadsheetml.sheet")
    assert result.parser_name == "docling"
    assert "Party" in result.text
    assert "ACME" in result.text
