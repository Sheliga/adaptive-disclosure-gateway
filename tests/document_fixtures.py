"""Synthetic PDF/DOCX/XLSX byte builders for the T12 ingestion and T20
upload tests.

**Every document these functions produce is generated from invented text at
test time.** Nothing here is corpus material, nothing is committed as a
binary, and no employer, client or counterparty document contributed a
single value -- the same stance ``tests/contracts_fixture.py`` records for
the Contracts text fixtures it draws on.

Deliberately named without a ``test_`` prefix so pytest never collects it on
its own. It exists so the ingestion tests
(``tests/test_application_ingestion_docling.py``) and the HTTP upload tests
(``tests/test_api_documents_upload.py``) build their documents the same way
instead of maintaining two drifting copies of a minimal PDF writer.
"""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


def minimal_pdf_bytes(lines: Sequence[str] = ("ACME Services Agreement",)) -> bytes:
    """A single-page PDF drawing ``lines`` as separate text lines.

    Hand-assembled rather than produced by a PDF library so the tests carry
    no extra dependency and the bytes are deterministic.
    """
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        (
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
        ),
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    drawn = b"".join(b"(" + _escape_pdf_text(line) + b") Tj T*\n" for line in lines)
    stream = b"BT /F1 12 Tf 20 TL 72 720 Td\n" + drawn + b"ET\n"
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


def _escape_pdf_text(line: str) -> bytes:
    escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return escaped.encode("latin-1", errors="replace")


def minimal_docx_bytes(
    paragraphs: Sequence[str] = ("ACME Master Services Agreement", "Renewal term: twelve months"),
) -> bytes:
    """A minimal OOXML package whose body is one ``<w:p>`` per paragraph."""
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{_escape_xml(text)}</w:t></w:r></w:p>'
        for text in paragraphs
    )
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
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{body}</w:body></w:document>",
        )
    return output.getvalue()


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
