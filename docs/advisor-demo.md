# Advisor-facing demo application

## Status and purpose

This document defines a **parallel demonstration/application track** for the Adaptive Disclosure Gateway.

It does **not** change the scientific Milestone 3 ordering, gates or closure criteria.

The current Python implementation is not only experimental machinery: it is the **reference application/core that will demonstrate the research concept**. The advisor-facing demo must expose this implementation directly rather than recreate simplified B0–B4 logic in a separate web application.

The intended audience is prospective PPGCA advisors and other technical reviewers who should be able to receive a URL, open the application and understand/test the core disclosure-governance concept without cloning the repository.

Tracking:

- Demo Track: Issue #41
- T20 application/CLI/HTTP/MCP: Issue #28
- T21 Next.js UI: Issue #29
- T25 container/deploy infrastructure: Issue #42
- T22 real provider: Issue #30

## Architectural boundary

The target application path is:

```text
browser
  ↓
Next.js demo
  ↓
HTTP API
  ↓
shared Python application boundary
  ↓
B0 / B1 / B2 / B3 / B4
  ↓
provider boundary
  ↓
local authorized reconstruction
  ↓
safe result / metrics
```

The web layer must not independently implement:

- sensitive-data detection;
- B3 task analysis;
- B4 policy resolution;
- pseudonymization/generalization/removal;
- reconstruction;
- scientific scoring semantics.

Those remain owned by the Python core.

## No agents in the first demo

The first advisor-facing application uses the deterministic/frozen mechanisms already implemented by the research prototype.

No agentic anonymization or autonomous policy-planning layer is required.

The first demo therefore exercises:

- the deterministic detector;
- the frozen B3 task analyzer/action spaces;
- the B4 contextual policy mechanism;
- explicit disclosure actions;
- local vault/reconstruction;
- the existing provider boundary.

Agentic variants may be studied later as separately versioned extensions. They are not part of the first demonstration path and must not silently change the B0–B4 experimental treatments.

## Minimum advisor-facing experience

A reviewer should be able to:

1. open a hosted URL;
2. choose a prepared synthetic HR case or provide explicitly controlled demo text;
3. enter/select a task;
4. select B0–B4 or request a comparison;
5. execute the actual Python gateway;
6. inspect what stays local and what crosses the local-cloud boundary;
7. inspect transformation/policy decisions;
8. inspect the provider response;
9. inspect the authorized locally reconstructed response;
10. inspect selected safe metrics and provenance.

The UI should make the trust-boundary effect visually obvious.

A minimal result view should expose, when safe/applicable:

- treatment and version;
- policy version/contextual cell for B4;
- original/control representation for synthetic demo cases;
- provider-bound representation;
- per-category/span action;
- policy/task reason;
- provider mode/model metadata;
- reconstruction outcome;
- conformance/exposure/utility/timing summary.

## Provider modes

Two provider modes are useful:

### FakeProvider

The deterministic provider remains valuable for:

- reproducible demonstration;
- offline/local development;
- showing B0–B4 transformation/reconstruction behavior without external dependencies.

### Real provider

T22 adds the mode that is most useful for an interactive advisor demo:

- a reviewer asks a real task;
- the gateway controls what leaves the local boundary;
- an external LLM produces a real response;
- reconstruction happens locally.

T22 is not required to build the demo shell, but a real-provider mode is the preferred state before broadly sharing the URL with prospective advisors.

## Demo work sequence

The demo has its own parallel sequence:

1. **T20 / Issue #28 — application boundary + HTTP API.**
   - HTTP is the first demo-facing adapter.
   - CLI and MCP share the same application boundary but do not have to block the first hosted URL.
2. **T21 / Issue #29 — Next.js interactive UI.**
   - Start from the safe T10 read model/artifacts.
   - Integrate the real HTTP API without redefining scientific semantics in the frontend.
3. **T25 / Issue #42 — containerized demo/deploy infrastructure.**
   - Package API and web application into reproducible images and a simple hosted topology.
4. **T22 / Issue #30 — real-provider mode.**
   - Can proceed independently under M3 and is consumed by the demo when available.

This sequence is parallel to M3. It does not become a prerequisite for T23/T12/T24 or confirmatory-readiness.

## Container/deployment objective

The application is not intended for mass distribution or desktop installation. The deployment objective is a small, reproducible research-demo stack that can be hosted and shared by URL.

Target topology:

```text
browser -> web container -> API container -> external provider
                           -> optional OTEL/Jaeger
```

The current root `compose.yaml` is a development/test harness, not the final demo topology. It mounts the repository and runs the test suite. T25 therefore owns a distinct demo/deploy configuration.

T25 must provide at least:

- Python API image on the supported Python 3.13 runtime;
- Next.js image;
- explicit internal networking;
- health/readiness checks;
- deployment-safe API origin/CORS configuration;
- server-side-only provider secrets;
- one-command local startup;
- a documented hosted deployment path suitable for sharing a URL;
- core/application version provenance.

Observability services such as Jaeger may remain optional for the lightweight hosted demo.

## Security stance

The demo remains subject to the same trust-boundary guarantees as the research core.

- provider credentials never reach the browser;
- vault mappings remain local to the Python trust boundary;
- logs/audit remain metadata-only by default;
- raw/synthetic views are explicit;
- prepared examples use synthetic data;
- free-form input, if enabled, must not weaken logging/error/no-leak guarantees;
- frontend-visible configuration contains no secrets/private policy state.

## Explicit non-goals

The first advisor demo does not require:

- agentic anonymization;
- multi-user SaaS accounts;
- policy editing in the browser;
- billing;
- desktop installer/executable;
- persistent shared vault;
- arbitrary document upload before T12;
- multi-turn experiments;
- production-scale orchestration;
- a polished general-purpose audit platform.

## Relationship to the scientific project

The demo exists to make the research implementation inspectable and testable by humans.

It must therefore **consume scientific capabilities without driving them**.

A UI/deployment concern must never be used as a reason to alter frozen corpus cases, treatments, policies or metrics to make the demonstration look better.

As M3 capabilities arrive, the application can expose them:

- T22 adds real LLM inference;
- T12 adds structured document ingestion;
- T24/Contracts adds a second demonstrable domain;
- later scientific versions can add new explicitly versioned treatments.

The first completion criterion remains deliberately narrower: a prospective advisor can open a URL and execute the controlled HR B0–B4 concept through the actual Python core without local setup.