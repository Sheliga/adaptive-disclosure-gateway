"""Build-time Docling model prewarm step for the API container image (T25 /
issue #42).

Run once, during the API image build, with ``HF_HOME`` pointed at a fixed
directory that gets copied into the runtime stage. It performs one real
conversion of each Docling-backed format the demo accepts (PDF and DOCX)
through the exact same ``DoclingDocumentParser`` the running application
uses -- not a hand-rolled substitute converter that could drift from it --
so every model that parser's ``DocumentConverter`` would otherwise fetch on
its first real request is already on disk before the container starts.

Content is synthetic and disposable, built with
``tests/document_fixtures.py``'s ``minimal_pdf_bytes``/``minimal_docx_bytes``
(the same builders the T12/T20 test suite already uses) rather than a
second, independent PDF/DOCX writer -- ``docker/api.Dockerfile`` copies only
that one file plus ``tests/__init__.py`` into the builder stage, never the
rest of the test suite. Nothing about the output of this script is
inspected beyond "did it convert without raising", because the point is the
side effect (populating the model cache), not the extracted text.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "src"))


def main() -> None:
    from adaptive_disclosure_gateway.application.ingestion import DoclingDocumentParser
    from tests.document_fixtures import minimal_docx_bytes, minimal_pdf_bytes

    lines = ["Docling model prewarm", "This content is synthetic and disposable."]
    parser = DoclingDocumentParser()

    pdf_result = parser.parse(safe_name="prewarm.pdf", data=minimal_pdf_bytes(lines))
    if not pdf_result.text.strip():
        raise RuntimeError("docling prewarm: PDF conversion produced no text")

    docx_result = parser.parse(safe_name="prewarm.docx", data=minimal_docx_bytes(lines))
    if not docx_result.text.strip():
        raise RuntimeError("docling prewarm: DOCX conversion produced no text")

    print("docling prewarm: PDF and DOCX conversion succeeded; model cache populated")


if __name__ == "__main__":
    main()
