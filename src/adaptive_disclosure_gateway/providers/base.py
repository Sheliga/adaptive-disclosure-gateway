from __future__ import annotations

import concurrent.futures
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

# Every treatment that talks to an external provider must go through exactly
# this module -- see docs/experimental-design.md's "Provider model, snapshot
# and decoding configuration" held-constant requirement and issue #12. This
# is deliberately the *only* place a provider can be reached from: it is the
# isolation boundary of the whole architecture. A provider never sees the
# raw document, the detected spans, the policy set, the vault or a
# GovernanceContext -- only a ``ProviderRequest``, whose two fields are the
# entire contract.

DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class ProviderRequest:
    """The only object a ``Provider`` implementation is ever handed.

    ``payload`` must be exactly the payload a treatment already decided to
    disclose -- typically ``DisclosureResult.external_payload`` -- never the
    raw document, a detected span's original value, or anything from the
    policy set or vault. ``task`` is the non-sensitive task/prompt
    instruction (docs/experimental-design.md's "prompt scaffolding", held
    identical across treatments being compared), not free-form context.

    There is no third field, and none should be added lightly: widening
    what a provider can see must mean deliberately adding a field here
    (a reviewable, test-visible change --
    tests/test_provider_isolation.py pins the exact field set), never
    passing a whole ``GovernanceContext`` or ``DisclosureRequest`` through
    because stripping fields individually was forgotten.
    """

    payload: str
    task: str


@dataclass(frozen=True)
class ProviderResponse:
    """Everything a provider call yields, including the reproducibility and
    metrics metadata issue #12 requires.

    ``model_id`` and ``model_snapshot`` identify exactly which model
    answered (for FakeProvider, synthetic but stable identifiers -- the
    point is that the shape exists so a real provider can populate it
    meaningfully). ``decoding_config`` records the decoding parameters used
    for this call (temperature, sampling strategy, max tokens, ...) so that
    an experiment run can confirm they were held identical across
    treatments, per docs/experimental-design.md. ``transmitted_bytes`` is
    the transmitted-volume metric for issue #8 -- see
    ``count_transmitted_bytes`` for the exact, documented counting rule.
    """

    text: str
    model_id: str
    model_snapshot: str
    decoding_config: Mapping[str, Any]
    transmitted_bytes: int


class ProviderError(Exception):
    """Raised whenever a provider call cannot be completed for any reason
    (a network/transport error, a malformed response, a timeout, ...).

    Fail-closed contract (issue #12): a caller must treat this as the whole
    disclosure request failing -- blocked -- never as a signal to fall back
    to B0 -- Direct disclosure of the original document, and never as a
    reason to retry (with the same payload or a different one). This is the
    base class specifically so that a caller handling providers generically
    can write one ``except ProviderError`` and fail closed uniformly,
    without special-casing timeouts.

    ``provider_invoked`` records the one fact only ``invoke_provider``
    itself knows for certain: whether ``provider.generate`` was actually
    submitted before this failure happened. It defaults to ``True`` because
    every failure site in ``invoke_provider`` *except* the provider_class
    pre-flight check happens after ``executor.submit(provider.generate,
    request)`` has already run. A caller (``pipeline.run_disclosure_case``)
    must read this attribute to decide what an audit record's
    ``ProviderStage.called`` should say -- never infer it by checking
    ``isinstance(exc, ProviderClassMismatchError)``, which would silently
    stop being correct the moment a future pre-flight check is added to
    ``invoke_provider`` before the ``generate`` call without also being
    special-cased at every call site.
    """

    def __init__(self, *args: object, provider_invoked: bool = True) -> None:
        super().__init__(*args)
        self.provider_invoked = provider_invoked


class ProviderTimeoutError(ProviderError):
    """Raised when a provider call does not complete within its timeout.

    Subclasses ``ProviderError`` -- see its docstring for the fail-closed
    contract, which applies identically here: never retried, never
    degraded to direct disclosure. A timeout can only happen after
    ``provider.generate`` was actually submitted (the deadline is enforced
    while awaiting its result), so ``provider_invoked`` is ``True`` here,
    exactly like the base class default.
    """


class ProviderClassMismatchError(ProviderError):
    """Raised when the provider actually being invoked declares a
    ``provider_class`` different from the one the caller expected (normally
    ``GovernanceContext.provider_class``, the value policy already
    evaluated against).

    This is the wiring issue #12 requires between a provider's own declared
    class and what policy sees: a mismatch must be *detected*, not silently
    ignored by trusting whichever of the two labels the caller already had
    on hand, and not silently repaired by overwriting one with the other.
    ``invoke_provider`` checks this before ever calling ``provider.generate``,
    so a mismatched provider is never actually invoked -- ``provider_invoked``
    is therefore always ``False`` for this exception, unconditionally
    (there is deliberately no way to construct one with it set ``True``):
    every raise site for this specific exception is, by construction, the
    provider_class pre-flight check that runs before
    ``executor.submit(provider.generate, request)``.
    """

    def __init__(self, *args: object) -> None:
        super().__init__(*args, provider_invoked=False)


@runtime_checkable
class Provider(Protocol):
    """The single interface every treatment uses to call an external
    provider. B0 -- Direct through B4 -- Policy-governed all call providers
    the same way, through this protocol and ``invoke_provider`` below --
    never a per-treatment bespoke client.

    ``provider_class`` is a plain class attribute (matching this
    codebase's `treatment` class-attribute convention -- see
    ``StaticSanitizer.treatment``) naming which class of provider this is
    for policy purposes (for example ``"external_llm"`` or ``"fake"``).
    """

    provider_class: str

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Answer ``request``. Implementations must not perform their own
        retries -- ``invoke_provider`` is the single place retry policy
        (currently: none) is decided, and must not accept anything beyond a
        ``ProviderRequest``.
        """
        ...


def count_transmitted_bytes(payload: str) -> int:
    """The transmitted-volume counting rule for issue #12 / issue #8's
    "Transmitted tokens/data volume" metric.

    Counts the number of UTF-8 encoded bytes in ``payload`` -- and nothing
    else. In particular, it deliberately excludes ``task``/prompt
    scaffolding: docs/experimental-design.md requires prompt scaffolding to
    be held identical across every treatment in a comparison, so it must not
    contribute to a metric meant to measure what differs between
    treatments (i.e. how much of the disclosure-controlled payload each
    treatment actually transmits).

    This is a simple, deterministic, documented proxy -- not a real
    tokenizer count. A later real provider adapter should either reuse this
    exact rule for comparability with FakeProvider-based results, or, if it
    reports the provider API's own token usage instead, document precisely
    how that number relates to this one before treatments using different
    providers are compared.
    """
    return len(payload.encode("utf-8"))


def invoke_provider(
    provider: Provider,
    request: ProviderRequest,
    *,
    expected_provider_class: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ProviderResponse:
    """The single entrypoint every treatment must use to call a provider.

    provider_class wiring (issue #12): ``expected_provider_class`` is the
    class policy has already evaluated (normally
    ``GovernanceContext.provider_class``). If ``provider.provider_class``
    disagrees, this raises ``ProviderClassMismatchError`` *before* calling
    ``provider.generate`` at all -- the mismatched provider is never
    actually invoked, so a caller cannot silently answer a request with a
    provider policy never evaluated.

    Fail-closed on error/timeout: exactly one call is attempted, with a hard
    wall-clock deadline of ``timeout`` seconds enforced by this function
    itself (not merely trusted from the provider). Any exception
    ``provider.generate`` raises -- or a deadline overrun -- propagates as
    ``ProviderError`` (or ``ProviderTimeoutError``, itself a
    ``ProviderError``). There is no retry, with the same payload or a
    different one, and no fallback: a caller that catches this exception and
    proceeds to disclose the original document anyway (B0 -- Direct) is
    misusing this function, not exercising a supported code path.

    An underlying exception's own message is deliberately not chained onto
    the raised ``ProviderError`` (``from None``): a third-party provider
    client's error message could itself echo request content (e.g. an HTTP
    library quoting the request body it failed to send), and this boundary
    must not let that leak through logs or a traceback -- see CLAUDE.md's
    no-leak invariant.
    """
    if provider.provider_class != expected_provider_class:
        raise ProviderClassMismatchError(
            "provider declares a provider_class different from the one this call expected"
        )

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(provider.generate, request)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise ProviderTimeoutError("provider call exceeded its timeout") from None
        except ProviderError:
            raise
        except Exception:  # noqa: BLE001 -- a provider is arbitrary third-party
            # code; any exception it raises (network error, malformed
            # response, anything) must fail this call closed, not propagate
            # unrecognized and risk being mishandled by a caller expecting
            # only ProviderError.
            raise ProviderError("provider call failed") from None
    finally:
        # wait=False: never block the caller waiting for a hung provider
        # call to finish just to tidy up the executor -- the failed/expired
        # call's thread is abandoned, not retried or awaited.
        executor.shutdown(wait=False)
