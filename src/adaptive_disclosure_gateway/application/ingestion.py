"""Normalization boundary from raw caller input to ``NormalizedContent`` --
the one shape every future adapter (HTTP/CLI/MCP) and the application
service beneath it agree on (T20 / issue #28, slice 1).

This slice supports exactly two input shapes: direct pasted/typed text
(``normalize_text``) and a plain ``.txt``/``.md`` file
(``normalize_text_file``). Structured formats -- PDF, DOCX, XLSX, images --
are deliberately OUT OF SCOPE here: T12/Docling (issue #9) will add a
producer of ``NormalizedContent`` for those formats behind this exact same
contract, so ``DisclosureApplicationService`` never has to change when they
arrive -- it already only ever consumes ``NormalizedContent``, never a
specific source format. This module is deliberately small and is not a
plugin framework: adding a format means adding one more function that
returns ``NormalizedContent``, not registering into an extensibility layer
that does not exist yet.

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

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

# Extension -> media type for the text-file formats this slice supports.
# Adding a format here later (as part of T12/#9, for binary formats that
# need a real parser) would be the wrong place -- those need their own
# normalize_* function, not a new entry mapping straight to text/plain-style
# handling, since they are not decodable as UTF-8 text at all.
_TEXT_FILE_MEDIA_TYPES: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
}


class IngestionError(Exception):
    """Raised when caller input cannot be normalized into ``NormalizedContent``.

    Messages name the extension/kind/size/count involved -- never file
    content or decoded text. See the module docstring's no-leak contract.
    """


@dataclass(frozen=True)
class NormalizedContent:
    """The one shape every source of input -- pasted text today, a
    Docling-parsed document later (T12/#9) -- normalizes into before
    reaching the application service. ``source_name`` is the filename when
    ``source_kind`` is ``"text_file"``, else ``None``.
    """

    text: str
    source_kind: Literal["direct_text", "text_file"]
    source_name: str | None
    media_type: str
    character_count: int
    byte_count: int


def _extension(filename: str) -> str:
    # PurePosixPath's .suffix is used purely for its extension-splitting
    # rule (not for any filesystem path semantics) so a filename containing
    # backslashes on the caller's OS is not misparsed as a directory
    # separator here.
    return PurePosixPath(filename).suffix.lower()


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
    )


def normalize_text_file(filename: str, data: bytes) -> NormalizedContent:
    """Normalize an uploaded ``.txt`` or ``.md`` file. Any other extension,
    undecodable UTF-8 content, or empty/whitespace-only decoded text raises
    ``IngestionError``.
    """
    extension = _extension(filename)
    media_type = _TEXT_FILE_MEDIA_TYPES.get(extension)
    if media_type is None:
        raise IngestionError(
            f"unsupported file extension {extension!r} ({len(data)} bytes); only "
            "'.txt' and '.md' text files are supported in this slice"
        )

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
    )
