"""Normalization boundary from raw caller input to ``NormalizedContent`` --
the one shape every future adapter (HTTP/CLI/MCP) and the application
service beneath it agree on (T20 / issue #28, slice 1).

This boundary supports direct pasted/typed text (``normalize_text``), plain
UTF-8 ``.txt``/``.md`` files and, as of T12 / issue #9, structured document
formats parsed through Docling. Docling is deliberately only an ingestion
adapter here: the rest of the application sees project-owned
``NormalizedContent`` with canonical text, never a Docling object or a
format-specific representation. That keeps the parser path constant across
B0-B4: parse/normalize once before the disclosure treatments run, then hand
the same normalized text to every strategy.

No-leak invariant (CLAUDE.md): every ``IngestionError`` message names the
extension, source kind, byte count or character count involved -- never the
file's content or any decoded text. In particular, a stdlib
``UnicodeDecodeError`` embeds a slice of the offending bytes and their
position in its own message; the chain is broken with ``raise ... from
None`` at the raise site rather than trusting that this module's own message
is clean (an unbroken chain would still let the raw bytes resurface through
a full traceback dump -- see ``tests/test_application_ingestion.py``'s
dedicated regression pin for this).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib import metadata
from io import BytesIO
from pathlib import PurePosixPath
from typing import Literal, Protocol, runtime_checkable

_TEXT_FILE_MEDIA_TYPES: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
}

_DOCUMENT_FILE_MEDIA_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
}

_DOCLING_INPUT_FORMAT_BY_EXTENSION: Mapping[str, str] = {
    ".pdf": "PDF",
    ".docx": "DOCX",
    ".xlsx": "XLSX",
    ".png": "IMAGE",
    ".jpg": "IMAGE",
    ".jpeg": "IMAGE",
    ".tif": "IMAGE",
    ".tiff": "IMAGE",
    ".bmp": "IMAGE",
}

_DIRECT_TEXT_INGESTION_VERSION = "direct-text-v1"
_UTF8_TEXT_FILE_INGESTION_VERSION = "utf8-text-file-v1"
_DOCLING_MARKDOWN_INGESTION_VERSION = "docling-markdown-v1"


class IngestionError(Exception):
    """Raised when caller input cannot be normalized into ``NormalizedContent``.

    Messages name the extension/kind/size/count involved -- never file
    content or decoded text. See the module docstring's no-leak contract.
    """


@dataclass(frozen=True)
class NormalizedContent:
    """The one shape every source of input -- pasted text today, a
    UTF-8 file or a Docling-parsed document -- normalizes into before
    reaching the application service. ``source_name`` is caller-facing
    metadata only; parser adapters receive generated safe names instead.
    """

    text: str
    source_kind: Literal["direct_text", "text_file", "document_file"]
    source_name: str | None
    media_type: str
    character_count: int
    byte_count: int
    parser_name: str = "builtin"
    parser_version: str = "builtin"
    ingestion_version: str = "unknown"


@runtime_checkable
class DocumentParser(Protocol):
    """Project-owned parser adapter protocol.

    Implementations can use Docling, a test double, or another parser behind
    this boundary, but must return Markdown text only -- never parser-native
    objects.
    """

    parser_name: str
    parser_version: str

    def parse_to_markdown(self, *, safe_name: str, data: bytes) -> str: ...


class DoclingDocumentParser:
    """Docling-backed ``DocumentParser`` loaded only when a document needs it."""

    parser_name = "docling"

    def __init__(self) -> None:
        try:
            from docling.datamodel.base_models import DocumentStream, InputFormat
            from docling.document_converter import DocumentConverter, NativePdfFormatOption
        except Exception:  # noqa: BLE001 - dependency loaders can surface dynamic internals.
            raise IngestionError(
                "docling is required to ingest document files; install the documents extra"
            ) from None

        self.parser_version = _package_version("docling")
        allowed_formats = [
            getattr(InputFormat, format_name)
            for format_name in sorted(set(_DOCLING_INPUT_FORMAT_BY_EXTENSION.values()))
        ]
        self._document_stream_type = DocumentStream
        self._converter = DocumentConverter(
            allowed_formats=allowed_formats,
            format_options={InputFormat.PDF: NativePdfFormatOption()},
        )

    def parse_to_markdown(self, *, safe_name: str, data: bytes) -> str:
        stream = self._document_stream_type(name=safe_name, stream=BytesIO(data))
        result = self._converter.convert(stream, raises_on_error=True)
        return result.document.export_to_markdown()


def _extension(filename: str) -> str:
    # PurePosixPath's .suffix is used purely for its extension-splitting
    # rule (not for any filesystem path semantics) so a filename containing
    # backslashes on the caller's OS is not misparsed as a directory
    # separator here.
    return PurePosixPath(filename).suffix.lower()


def _package_version(package_name: str) -> str:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return "unknown"


def _safe_parser_name(extension: str) -> str:
    return f"uploaded{extension}"


def _default_document_parser() -> DocumentParser:
    return DoclingDocumentParser()


def normalize_text(text: str) -> NormalizedContent:
    """Normalize direct pasted/typed text. Rejects empty or whitespace-only
    input with ``IngestionError`` -- there is nothing for the pipeline to
    run detection over otherwise.
    """
    if not text.strip():
        raise IngestionError("direct text input is empty or whitespace-only")

    encoded = text.encode("utf-8")
    return NormalizedContent(
        text=text,
        source_kind="direct_text",
        source_name=None,
        media_type="text/plain",
        character_count=len(text),
        byte_count=len(encoded),
        parser_name="direct_text",
        parser_version="builtin",
        ingestion_version=_DIRECT_TEXT_INGESTION_VERSION,
    )


def normalize_text_file(
    filename: str, data: bytes, *, document_parser: DocumentParser | None = None
) -> NormalizedContent:
    """Normalize an uploaded file into canonical project-owned text.

    ``.txt`` and ``.md`` are decoded directly as UTF-8. PDF/DOCX/XLSX/image
    formats are parsed through the supplied ``document_parser`` or Docling's
    optional adapter. Parser failures are wrapped with chain suppression so
    parser-native messages, filenames and payload excerpts cannot leak.
    """
    extension = _extension(filename)
    media_type = _TEXT_FILE_MEDIA_TYPES.get(extension)
    if media_type is None:
        return _normalize_document_file(filename, data, extension, document_parser)

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        # `from None`: UnicodeDecodeError's own message embeds a slice of
        # the offending bytes and their position -- see the module
        # docstring's no-leak contract.
        raise IngestionError(
            f"file with extension {extension!r} ({len(data)} bytes) is not valid UTF-8 text"
        ) from None

    if not text.strip():
        raise IngestionError(
            f"text file with extension {extension!r} ({len(data)} bytes) is empty or "
            "whitespace-only"
        )

    return NormalizedContent(
        text=text,
        source_kind="text_file",
        source_name=filename,
        media_type=media_type,
        character_count=len(text),
        byte_count=len(data),
        parser_name="utf8_text",
        parser_version="builtin",
        ingestion_version=_UTF8_TEXT_FILE_INGESTION_VERSION,
    )


def _normalize_document_file(
    filename: str, data: bytes, extension: str, document_parser: DocumentParser | None
) -> NormalizedContent:
    media_type = _DOCUMENT_FILE_MEDIA_TYPES.get(extension)
    if media_type is None:
        supported = tuple(sorted((*_TEXT_FILE_MEDIA_TYPES, *_DOCUMENT_FILE_MEDIA_TYPES)))
        raise IngestionError(
            f"unsupported file extension {extension!r} ({len(data)} bytes); supported "
            f"extensions: {supported}"
        )

    try:
        parser = document_parser if document_parser is not None else _default_document_parser()
    except IngestionError:
        raise IngestionError(
            f"document file with extension {extension!r} ({len(data)} bytes) requires docling; "
            "install the documents extra"
        ) from None

    safe_name = _safe_parser_name(extension)

    try:
        text = parser.parse_to_markdown(safe_name=safe_name, data=data)
    except IngestionError:
        raise
    except Exception:  # noqa: BLE001 - parser messages may contain file content.
        raise IngestionError(
            f"document file with extension {extension!r} ({len(data)} bytes) could not be parsed"
        ) from None

    if not text.strip():
        raise IngestionError(
            f"document file with extension {extension!r} ({len(data)} bytes) produced no text"
        )

    return NormalizedContent(
        text=text,
        source_kind="document_file",
        source_name=filename,
        media_type=media_type,
        character_count=len(text),
        byte_count=len(data),
        parser_name=parser.parser_name,
        parser_version=parser.parser_version,
        ingestion_version=_DOCLING_MARKDOWN_INGESTION_VERSION,
    )
