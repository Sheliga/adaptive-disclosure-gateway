"""T20 / issue #28, slice 1: the ingestion normalization boundary
(``application/ingestion.py``). This is the seam T12/Docling (issue #9)
will later plug PDF/DOCX/XLSX/image support into behind the same
``NormalizedContent`` contract -- these tests pin the plain-text/`.txt`/`.md`
behavior this slice actually implements, plus the no-leak contract every
``IngestionError`` must honor.
"""

from __future__ import annotations

import pytest

from adaptive_disclosure_gateway.application.ingestion import (
    IngestionError,
    NormalizedContent,
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


def test_normalize_text_file_supports_md():
    data = b"# Notes\nDepartment: Engineering\n"
    result = normalize_text_file("record.md", data)

    assert result.source_kind == "text_file"
    assert result.media_type == "text/markdown"


def test_normalize_text_file_rejects_unsupported_extension():
    with pytest.raises(IngestionError) as excinfo:
        normalize_text_file("record.pdf", b"%PDF-1.4 fake bytes")

    # The error must name the extension, never echo the file's own bytes.
    assert ".pdf" in str(excinfo.value)
    assert "%PDF" not in str(excinfo.value)


def test_normalize_text_file_rejects_empty_file():
    with pytest.raises(IngestionError):
        normalize_text_file("record.txt", b"")


def test_normalize_text_file_rejects_whitespace_only_file():
    with pytest.raises(IngestionError):
        normalize_text_file("record.txt", b"   \n\t ")


# --- No-leak invariant: an undecodable file must never let the raw bytes,
# or the stdlib UnicodeDecodeError's own message (which can echo the
# offending bytes/context), reach the caller. -------------------------------

SENSITIVE_LOOKING_LATIN1_BYTES = "Empregado: Jos\xe9 da Concei\xe7\xe3o".encode("latin-1")


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
    import traceback

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
        normalize_text_file("payroll.xlsx", b"binary spreadsheet content here")

    message = str(excinfo.value)
    assert "binary spreadsheet content" not in message
    assert ".xlsx" in message
