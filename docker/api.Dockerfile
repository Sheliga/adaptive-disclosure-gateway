# syntax=docker/dockerfile:1
#
# Demo/production image for the Python API (T25 / issue #42). Build context
# is the repository root:
#
#   docker build -f docker/api.Dockerfile -t adg-demo-api .
#
# or, normally, through compose.demo.yaml.
#
# Two stages:
#   builder  -- installs dependencies into a venv and prewarms Docling's
#               model cache with one real PDF+DOCX conversion.
#   runtime  -- copies only the venv, the prewarmed model cache and the
#               source tree actually needed to serve the app; runs as a
#               non-root user.
#
# Path trap (see application/settings.py's `_REPO_ROOT`): that module
# computes the repository root as `Path(__file__).resolve().parents[3]`,
# i.e. three directories above `application/settings.py`. A non-editable
# `pip install` into site-packages would break that computation, so this
# image keeps the source layout on disk at `/app/src/...` (matching the
# repository's own `src/...` layout) and points `PYTHONPATH` at it instead
# of relying on whatever `pip install .` placed in site-packages. With
# `/app` as the repository-root stand-in, `/app/configs/policies` and
# `/app/corpus/hr/v1/cases` resolve as the default policy/examples
# directories with no extra environment configuration.

# Pinned by digest, not tag alone: a tag can be republished to point at a
# different image; the digest is the only immutable part of this reference.
# Digest captured by pulling python:3.13.13-slim and reading
# `docker inspect --format='{{index .RepoDigests 0}}'`; see
# docs/advisor-demo.md's "Reproducible dependencies" section for the exact
# refresh procedure (re-pull the tag, re-capture the digest, re-verify the
# constraints file still resolves cleanly).
FROM python:3.13.13-slim@sha256:aa938a849bcb82dce8f49480f056ab82bf5c1c3ebc294f0430f37b6820e7f286 AS base

# ---------------------------------------------------------------------------
FROM base AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# build-essential: a small number of transitive dependencies (via the
# `documents`/`anthropic` extras) do not ship a manylinux wheel for every
# platform; keeping this in the builder stage only means it never reaches
# the runtime image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
# Only the two files scripts/prewarm_docling.py needs for synthetic
# PDF/DOCX fixtures -- never the rest of the test suite.
COPY tests/__init__.py tests/document_fixtures.py ./tests/
# T25 review finding 4: the full resolved runtime dependency closure, pinned
# to exact versions -- see that file's own header for what it covers and how
# to regenerate it. Copied in before the installs below so both `pip
# install` steps can constrain against it.
COPY docker/api-constraints.txt ./docker/api-constraints.txt

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# CPU-only torch wheels, installed BEFORE the extras that pull torch in
# transitively (via `docling`). Plain PyPI `torch` bundles CUDA runtime
# libraries and is multiple gigabytes; installing the CPU build first means
# pip's resolver finds it already satisfied when `docling` asks for `torch`
# and never replaces it with the CUDA build. This demo has no GPU and no use
# for one.
#
# `-c docker/api-constraints.txt` on both steps: a constraint never adds a
# package pip was not already going to install (unlike a requirements file),
# it only pins the version once pip decides to install it -- so this cannot
# accidentally pull in something extra, only make the resolved closure
# reproducible. Adding a runtime dependency to pyproject.toml without
# refreshing this file makes the *build* keep working (pip still resolves
# it, just unpinned) while `tests/test_docker_reproducibility.py` fails the
# local test suite -- refresh the lock before that PR merges.
RUN pip install -c docker/api-constraints.txt \
        --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install -c docker/api-constraints.txt \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        ".[api,documents,anthropic]"

# Prewarm Docling's model cache: one real PDF + DOCX conversion of synthetic,
# disposable content through the exact parser the app uses
# (scripts/prewarm_docling.py -> application/ingestion.DoclingDocumentParser).
# HF_HOME is fixed so the populated cache can be copied verbatim into the
# runtime stage -- a fresh container then never pays a first-request model
# download.
ENV HF_HOME=/opt/docling-cache
RUN mkdir -p "${HF_HOME}" && python scripts/prewarm_docling.py

# ---------------------------------------------------------------------------
FROM base AS runtime

RUN groupadd --system adg \
    && useradd --system --gid adg --home-dir /app --shell /usr/sbin/nologin adg

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app/src \
    HF_HOME=/opt/docling-cache \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/docling-cache /opt/docling-cache
COPY src ./src
COPY configs/policies ./configs/policies
COPY corpus/hr/v1/cases ./corpus/hr/v1/cases
COPY README.md pyproject.toml ./

RUN chown -R adg:adg /app
USER adg

EXPOSE 8000

# python, not curl: python:3.13-slim has no curl installed, and adding one
# just for the healthcheck would be a needless extra package/layer.
#
# Targets /ready, not /health (T25 review finding 2): /health is
# liveness/introspection and always reports 200 once the process is up, even
# mid-startup-refusal; /ready is the purely local readiness check that
# reports 503 while, e.g., a real-provider deployment has no credential yet.
# urlopen() itself raises urllib.error.HTTPError on a non-2xx response, which
# already makes this CMD exit non-zero on a 503 with no extra handling.
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)" || exit 1

# `api/app.py` exposes `create_app()`, a factory, not a module-level `app` --
# `--factory` tells uvicorn to call it. Single worker: Docling's model
# memory footprint makes multiple workers expensive for a small demo, and
# this deployment does not need the concurrency multiple workers would buy.
CMD ["uvicorn", "adaptive_disclosure_gateway.api.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
