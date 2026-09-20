"""T20 / issue #28, slice 1: the ingestion normalization boundary
(``application/ingestion.py``). This is the seam T12/Docling (issue #9)
will later plug PDF/DOCX/XLSX/image support into behind the same
``NormalizedContent`` contract -- these tests pin the plain-text/`.txt`/`.md`
behavior this slice actually implements, plus the no-leak contract every
``IngestionError`` must honor.
"""

from __future__ import annotations

import ast
import traceback
from dataclasses import dataclass
from pathlib import Path

import pytest

from adaptive_disclosure_gateway.application.ingestion import (
    DoclingDocumentParser,
    DocumentParser,
    IngestionError,
    NormalizedBlock,
    NormalizedContent,
    ParsedDocument,
    normalize_text,
    normalize_text_file,
)


def test_normalize_text_produces_direct_text_metadata():
    result = normalize_text("Employee: Ana Souza\nCPF: 123.456.789-09\n")

    assert isinstance(result, NormalizedContent)
    assert result.source_kind == "direct_text"
    assert result.source_name is None
    assert result.media_type == "text/plain"
    assert result.text == "Employee: Ana Souza\nCPF: 123.456.789-09\n"
    assert result.character_count == len(result.text)
    assert result.byte_count == len(result.text.encode("utf-8"))
    assert result.parser_name == "direct_text"
    assert result.parser_version == "builtin"
    assert result.ingestion_version == "direct-text-v1"


def test_normalize_text_rejects_empty_input():
    with pytest.raises(IngestionError):
        normalize_text("")


def test_normalize_text_rejects_whitespace_only_input():
    with pytest.raises(IngestionError):
        normalize_text("   \n\t  ")


def test_normalize_text_file_supports_txt():
    data = b"Department: Engineering\n"
    result = normalize_text_file("record.txt", data)

    assert result.source_kind == "text_file"
    assert result.source_name == "record.txt"
    assert result.media_type == "text/plain"
    assert result.text == "Department: Engineering\n"
    assert result.byte_count == len(data)
    assert result.parser_name == "utf8_text"
    assert result.parser_version == "builtin"
    assert result.ingestion_version == "utf8-text-file-v1"


def test_normalize_text_file_supports_md():
    data = b"# Notes\nDepartment: Engineering\n"
    result = normalize_text_file("record.md", data)

    assert result.source_kind == "text_file"
    assert result.media_type == "text/markdown"


@dataclass
class RecordingParser:
    calls: list[tuple[str, bytes]]
    markdown: str = "# Services\n\n| Party | Role |\n| --- | --- |\n| ACME | vendor |\n"
    blocks: tuple[NormalizedBlock, ...] = ()
    parser_name: str = "fake-docling"
    parser_version: str = "0.0-test"

    def parse(self, *, safe_name: str, data: bytes) -> ParsedDocument:
        self.calls.append((safe_name, data))
        return ParsedDocument(text=self.markdown, blocks=self.blocks)


def test_normalize_text_file_routes_pdf_docx_xlsx_and_images_through_document_parser():
    for filename, media_type in (
        ("contract.pdf", "application/pdf"),
        (
            "contract.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("contract.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("scan.png", "image/png"),
    ):
        parser = RecordingParser(calls=[])
        data = b"document bytes"

        result = normalize_text_file(filename, data, document_parser=parser)

        assert isinstance(parser, DocumentParser)
        assert result.source_kind == "document_file"
        assert result.source_name == filename
        assert result.media_type == media_type
        assert result.text.startswith("# Services")
        assert "| ACME | vendor |" in result.text
        assert result.character_count == len(result.text)
        assert result.byte_count == len(data)
        assert result.parser_name == "fake-docling"
        assert result.parser_version == "0.0-test"
        assert result.ingestion_version == "docling-structured-markdown-v1"


def test_normalize_text_file_sends_only_a_generated_safe_name_to_the_document_parser():
    parser = RecordingParser(calls=[])
    original_name = "../secret/Contrato de Ana Souza.pdf"

    normalize_text_file(original_name, b"%PDF pretend", document_parser=parser)

    assert parser.calls == [("uploaded.pdf", b"%PDF pretend")]


def test_normalize_text_file_preserves_parser_independent_document_blocks():
    markdown = "# Services\n\n| Party | Role |\n| --- | --- |\n| ACME | vendor |\n"
    table_start = markdown.index("| Party")
    blocks = (
        NormalizedBlock(kind="heading", text="Services", start=2, end=10, level=1),
        NormalizedBlock(
            kind="table",
            text=markdown[table_start:],
            start=table_start,
            end=len(markdown),
        ),
    )
    parser = RecordingParser(markdown=markdown, blocks=blocks, calls=[])

    result = normalize_text_file("contract.pdf", b"%PDF pretend", document_parser=parser)

    assert result.text == markdown
    assert result.blocks == blocks
    assert result.blocks[0].kind == "heading"
    assert result.blocks[1].kind == "table"


def test_normalize_text_file_rejects_document_parser_output_that_has_no_text():
    parser = RecordingParser(markdown="   \n\t", calls=[])

    with pytest.raises(IngestionError) as excinfo:
        normalize_text_file("contract.pdf", b"%PDF pretend", document_parser=parser)

    message = str(excinfo.value)
    assert ".pdf" in message
    assert "contract" not in message
    assert "pretend" not in message


def test_document_parser_failure_is_safe_and_breaks_the_exception_chain():
    class LeakyParser:
        parser_name = "fake-docling"
        parser_version = "0.0-test"

        def parse(self, *, safe_name: str, data: bytes) -> ParsedDocument:
            raise RuntimeError("Ana Souza CPF 123.456.789-09 failed")

    try:
        normalize_text_file(
            SENSITIVE_DOCUMENT_NAME, SENSITIVE_DOCUMENT_BYTES, document_parser=LeakyParser()
        )
    except IngestionError as exc:
        assert exc.__cause__ is None
        assert exc.__suppress_context__ is True
        rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        assert "Ana Souza" not in rendered
        assert "123.456.789-09" not in rendered
        assert "../leaky" not in rendered
        assert ".pdf" in str(exc)
    else:
        pytest.fail("expected IngestionError")


def test_document_parser_ingestion_error_is_sanitized_and_breaks_the_exception_chain():
    class LeakyIngestionErrorParser:
        parser_name = "fake-docling"
        parser_version = "0.0-test"

        def parse(self, *, safe_name: str, data: bytes) -> ParsedDocument:
            raise IngestionError("Ana Souza CPF 123.456.789-09")

    try:
        normalize_text_file(
            SENSITIVE_DOCUMENT_NAME,
            SENSITIVE_DOCUMENT_BYTES,
            document_parser=LeakyIngestionErrorParser(),
        )
    except IngestionError as exc:
        assert exc.__cause__ is None
        assert exc.__suppress_context__ is True
        rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        assert "Ana Souza" not in str(exc)
        assert "123.456.789-09" not in str(exc)
        assert "Ana Souza" not in rendered
        assert "123.456.789-09" not in rendered
        assert "../leaky" not in rendered
        assert ".pdf" in str(exc)
    else:
        pytest.fail("expected IngestionError")


def test_document_format_without_docling_dependency_reports_safe_actionable_error(monkeypatch):
    def unavailable_parser() -> DocumentParser:
        raise IngestionError("docling unavailable")

    monkeypatch.setattr(
        "adaptive_disclosure_gateway.application.ingestion._default_document_parser",
        unavailable_parser,
    )

    with pytest.raises(IngestionError) as excinfo:
        normalize_text_file("sensitive-name.pdf", b"%PDF secret payroll")

    message = str(excinfo.value)
    assert ".pdf" in message
    assert "docling" in message.lower()
    assert "sensitive-name" not in message
    assert "secret payroll" not in message


def test_normalize_text_file_rejects_unsupported_extension():
    with pytest.raises(IngestionError) as excinfo:
        normalize_text_file("record.zip", b"PK fake bytes")

    # The error must name the extension, never echo the file's own bytes.
    assert ".zip" in str(excinfo.value)
    assert "PK fake bytes" not in str(excinfo.value)


def test_normalize_text_file_rejects_empty_file():
    with pytest.raises(IngestionError):
        normalize_text_file("record.txt", b"")


def test_normalize_text_file_rejects_whitespace_only_file():
    with pytest.raises(IngestionError):
        normalize_text_file("record.txt", b"   \n\t ")


def test_normalize_text_rejects_input_above_byte_limit_without_leaking_content(monkeypatch):
    monkeypatch.setattr("adaptive_disclosure_gateway.application.ingestion.MAX_INPUT_BYTES", 8)

    with pytest.raises(IngestionError) as excinfo:
        normalize_text("Ana Souza")

    message = str(excinfo.value)
    assert "9 bytes" in message
    assert "8 bytes" in message
    assert "Ana Souza" not in message


def test_normalize_text_file_rejects_txt_md_above_byte_limit_without_leaking_content(monkeypatch):
    monkeypatch.setattr("adaptive_disclosure_gateway.application.ingestion.MAX_INPUT_BYTES", 4)

    with pytest.raises(IngestionError) as excinfo:
        normalize_text_file("notes.md", b"Ana Souza")

    message = str(excinfo.value)
    assert "9 bytes" in message
    assert "4 bytes" in message
    assert "Ana Souza" not in message


def test_normalize_text_file_rejects_document_above_byte_limit_before_parser(monkeypatch):
    monkeypatch.setattr("adaptive_disclosure_gateway.application.ingestion.MAX_INPUT_BYTES", 4)
    parser = RecordingParser(calls=[])

    with pytest.raises(IngestionError) as excinfo:
        normalize_text_file("contract.pdf", b"%PDF pretend", document_parser=parser)

    message = str(excinfo.value)
    assert "12 bytes" in message
    assert "4 bytes" in message
    assert "%PDF pretend" not in message
    assert parser.calls == []


def test_normalize_text_file_rejects_parser_output_above_normalized_character_limit(monkeypatch):
    monkeypatch.setattr(
        "adaptive_disclosure_gateway.application.ingestion.MAX_NORMALIZED_CHARACTERS", 5
    )
    parser = RecordingParser(markdown="abcdef", calls=[])

    with pytest.raises(IngestionError) as excinfo:
        normalize_text_file("contract.pdf", b"%PDF", document_parser=parser)

    message = str(excinfo.value)
    assert "6 characters" in message
    assert "5 characters" in message
    assert "abcdef" not in message
    assert parser.calls == [("uploaded.pdf", b"%PDF")]


# --- PR #55 review: limits must be enforced before the expensive work they
# bound, not just before the result reaches the caller. -----------------------


def test_normalize_text_rejects_oversized_input_before_strip_or_encode(monkeypatch):
    """The character ceiling must be checked before ``strip()``/``encode()``
    run on direct text, so an arbitrarily large input is rejected via a
    cheap ``len()`` check rather than being fully scanned and copied first.
    """
    monkeypatch.setattr(
        "adaptive_disclosure_gateway.application.ingestion.MAX_NORMALIZED_CHARACTERS", 10
    )

    class ExplodingStr(str):
        def strip(self, *args, **kwargs):
            raise AssertionError("strip() must not run before the character ceiling check")

        def encode(self, *args, **kwargs):
            raise AssertionError("encode() must not run before the character ceiling check")

    oversized = ExplodingStr("x" * 11)

    with pytest.raises(IngestionError) as excinfo:
        normalize_text(oversized)

    message = str(excinfo.value)
    assert "11 characters" in message
    assert "10 characters" in message
    assert "x" * 11 not in message


def _fake_docling_parser(markdown: str) -> DoclingDocumentParser:
    """Build a ``DoclingDocumentParser`` without importing/installing docling,
    by bypassing ``__init__`` and injecting fakes for the two collaborators
    ``parse()`` touches.
    """

    class FakeDocument:
        def export_to_markdown(self) -> str:
            return markdown

    class FakeConversionResult:
        document = FakeDocument()

    class FakeConverter:
        def convert(self, stream, *, raises_on_error: bool) -> FakeConversionResult:
            return FakeConversionResult()

    parser = object.__new__(DoclingDocumentParser)
    parser._document_stream_type = lambda *, name, stream: (name, stream)
    parser._converter = FakeConverter()
    return parser


def test_docling_parser_skips_block_derivation_for_oversized_export(monkeypatch):
    monkeypatch.setattr(
        "adaptive_disclosure_gateway.application.ingestion.MAX_NORMALIZED_CHARACTERS", 5
    )

    def exploding_blocks_from_markdown(text):
        raise AssertionError("_blocks_from_markdown must not run for oversized exports")

    monkeypatch.setattr(
        "adaptive_disclosure_gateway.application.ingestion._blocks_from_markdown",
        exploding_blocks_from_markdown,
    )
    oversized_markdown = "# Heading\nmore than five characters of exported text\n"
    parser = _fake_docling_parser(oversized_markdown)

    result = parser.parse(safe_name="uploaded.pdf", data=b"%PDF")

    assert result.blocks == ()
    assert result.text == oversized_markdown


def test_normalize_text_file_rejects_oversized_docling_export_without_deriving_blocks(
    monkeypatch,
):
    monkeypatch.setattr(
        "adaptive_disclosure_gateway.application.ingestion.MAX_NORMALIZED_CHARACTERS", 5
    )

    def exploding_blocks_from_markdown(text):
        raise AssertionError("_blocks_from_markdown must not run for oversized exports")

    monkeypatch.setattr(
        "adaptive_disclosure_gateway.application.ingestion._blocks_from_markdown",
        exploding_blocks_from_markdown,
    )
    oversized_markdown = "# Heading\nmore than five characters of exported text\n"
    parser = _fake_docling_parser(oversized_markdown)

    with pytest.raises(IngestionError) as excinfo:
        normalize_text_file("contract.pdf", b"%PDF", document_parser=parser)

    assert "characters" in str(excinfo.value)


def test_docling_parser_derives_blocks_for_normal_sized_export():
    markdown = "# Services\n\n| Party | Role |\n| --- | --- |\n| ACME | vendor |\n"
    parser = _fake_docling_parser(markdown)

    result = parser.parse(safe_name="uploaded.pdf", data=b"%PDF")

    assert result.text == markdown
    assert result.blocks != ()
    assert any(block.kind == "heading" for block in result.blocks)
    assert any(block.kind == "table" for block in result.blocks)


# --- No-leak invariant: an undecodable file must never let the raw bytes,
# or the stdlib UnicodeDecodeError's own message (which can echo the
# offending bytes/context), reach the caller. -------------------------------

SENSITIVE_LOOKING_LATIN1_BYTES = "Empregado: Jos\xe9 da Concei\xe7\xe3o".encode("latin-1")
SENSITIVE_DOCUMENT_NAME = "../leaky/Ana Souza.pdf"
SENSITIVE_DOCUMENT_BYTES = b"Ana Souza CPF 123.456.789-09"


def test_normalize_text_file_rejects_undecodable_bytes_without_leaking_them():
    with pytest.raises(IngestionError) as excinfo:
        normalize_text_file("record.txt", SENSITIVE_LOOKING_LATIN1_BYTES)

    message = str(excinfo.value)
    assert "Jos" not in message
    assert "Concei" not in message
    # The byte string itself must never appear in the message either.
    assert repr(SENSITIVE_LOOKING_LATIN1_BYTES) not in message


def test_normalize_text_file_breaks_the_unicode_decode_error_chain():
    """CLAUDE.md's no-leak invariant: an underlying exception whose own
    message might carry the value (a stdlib parser echoing its input) must
    have its chain broken with `raise ... from None` at the raise site --
    UnicodeDecodeError's own message includes the offending byte sequence
    and position, so it must never resurface through the raised
    IngestionError's cause, and a full traceback dump (the normal behavior
    of logging.exception / OTel exception recording) must not print it
    either -- `from None` sets `__cause__` to None and suppresses
    `__context__` from traceback formatting (Python still records
    `__context__` internally, but `__suppress_context__` stops it from ever
    being rendered).
    """
    try:
        normalize_text_file("record.txt", SENSITIVE_LOOKING_LATIN1_BYTES)
    except IngestionError as exc:
        assert exc.__cause__ is None
        assert exc.__suppress_context__ is True
        formatted = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        assert "Jos" not in formatted
        assert "Concei" not in formatted
    else:
        pytest.fail("expected IngestionError to be raised")


def test_ingestion_error_messages_never_carry_file_content_only_metadata():
    """The message must name the extension/size involved, never content."""
    with pytest.raises(IngestionError) as excinfo:
        normalize_text_file("payroll.zip", b"binary spreadsheet content here")

    message = str(excinfo.value)
    assert "binary spreadsheet content" not in message
    assert ".zip" in message


def test_docling_imports_stay_inside_the_ingestion_layer():
    source_root = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway"
    offenders: list[str] = []

    for path in source_root.rglob("*.py"):
        module_path = path.relative_to(source_root).as_posix()
        if module_path in {"application/ingestion.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            if any(module == "docling" or module.startswith("docling.") for module in modules):
                offenders.append(module_path)

    assert offenders == []
