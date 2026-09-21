/**
 * Subpath-deployment support (this app served behind a reverse proxy under
 * e.g. `https://host/disclosure-gateway`, not the domain root).
 *
 * Next.js's `basePath` config (`web/next.config.ts`) automatically rewrites
 * `next/link`, the router and asset URLs, but it does NOT rewrite a literal
 * string passed to `fetch()` -- so every client-side call to this app's own
 * `/api/**` proxy routes (`web/lib/api.ts`) must be prefixed explicitly
 * through `apiPath(...)` below. `tests/test_demo_deployment_config.py`'s
 * `TestWebApiCallsGoThroughBasePathHelper` statically pins that every
 * `/api/...` literal under `web/lib`, `web/app` and `web/components` is
 * either this module or an `apiPath(...)` call -- never a bare literal.
 *
 * `ADG_WEB_BASE_PATH` (empty/unset means "no prefix", i.e. today's
 * root-path behavior, in dev and in every existing test) is read here AND
 * in `next.config.ts`, which is the only reason this module can be imported
 * from `next.config.ts` without pulling in anything Next-specific: it must
 * stay a plain function of its input, no Next/React imports.
 *
 * Getting the resolved value to the BROWSER without `NEXT_PUBLIC_*` (this
 * repository forbids that prefix outright -- see
 * `tests/test_demo_deployment_config.py::test_web_service_has_no_next_public_variable`
 * and `web/Dockerfile`'s module docstring): `next.config.ts` sets its own
 * `env` block to `{ ADG_WEB_BASE_PATH: <normalized value> }`. Next.js's `env`
 * config -- unlike a plain `.env` file entry -- is inlined into BOTH the
 * server and the client bundle regardless of naming convention; the
 * `NEXT_PUBLIC_*` convention only governs variables sourced from the system
 * environment/`.env` files directly, not ones explicitly listed in `env`
 * (see the Next.js docs for `next.config.js`'s `env` option). So
 * `process.env.ADG_WEB_BASE_PATH` below resolves to a literal string inlined
 * at build time in application code, exactly like a `NEXT_PUBLIC_*` variable
 * would -- without ever being one.
 *
 * That inlining is done by webpack's DefinePlugin, which only recognizes the
 * exact literal AST shape `process.env.ADG_WEB_BASE_PATH` -- a plain member
 * expression on the literal identifiers `process`, `env`, and the variable
 * name written out by hand. It does NOT evaluate the program: `env[SOME_VAR]`
 * (a computed/bracket member expression), `process.env` captured in a
 * variable or passed as a function's default parameter and indexed later,
 * or any other indirection all compile without error but are never
 * substituted. In that case the expression survives into the shipped bundle
 * unchanged and reads the BROWSER's `process.env` at runtime -- which does
 * not exist there, so it silently resolves to `undefined`/`{}` and
 * `BASE_PATH` collapses to `""`. This shipped to production exactly once
 * (every client-side `/api/**` call went out with no `/disclosure-gateway`
 * prefix and 404'd at the domain root) precisely because `BASE_PATH` used to
 * be computed via `resolveBasePath()`, which reads `env[BASE_PATH_ENV_VAR]`
 * -- a computed access DefinePlugin cannot see. Every Vitest unit test below
 * still passed, because Node's `process.env` is real; only the compiled
 * browser artifact was wrong. `web/scripts/check-basepath-inlined.mjs`
 * (`npm run check:basepath`) guards against a regression by inspecting the
 * actual built `.next/static` chunks, not source or Node-side behavior.
 *
 * Consequently `BASE_PATH` below must be computed from the literal
 * expression `process.env.ADG_WEB_BASE_PATH` directly -- never through
 * `resolveBasePath`, a destructured/aliased `process.env`, or any other
 * indirection, no matter how equivalent it looks in Node.
 */

export const BASE_PATH_ENV_VAR = "ADG_WEB_BASE_PATH";

/**
 * Normalizes a raw `ADG_WEB_BASE_PATH` value to Next.js's own `basePath`
 * shape: `""` (no prefix) or a leading-slash, no-trailing-slash path.
 * `next.config.ts` calls this directly (to compute the `basePath` Next.js
 * config value itself) and this module's own `resolveBasePath` calls it too,
 * so the two can never disagree about what "no prefix" or a sloppily-typed
 * value normalizes to.
 */
export function normalizeBasePath(raw: string | undefined): string {
  const trimmed = (raw ?? "").trim();
  if (trimmed === "" || trimmed === "/") {
    return "";
  }
  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  return withLeadingSlash.replace(/\/+$/, "");
}

/**
 * `env` is an explicit, required parameter (mirroring
 * `lib/demoVaultExplorer.ts`'s `isDemoVaultExplorerEnabled`) so tests can
 * exercise every input without mutating the real process environment.
 *
 * This function reads `env[BASE_PATH_ENV_VAR]` -- a computed/bracket
 * property access. That is exactly the indirection the module docstring
 * above warns is invisible to webpack's DefinePlugin, so this helper must
 * NEVER be used to compute `BASE_PATH` (the value application code actually
 * calls in the browser). It exists only for tests, which run in Node and
 * can supply an arbitrary `env` map directly; `next.config.ts` also uses the
 * same computed-lookup shape, but only at Node build-config-eval time,
 * never in bundled application code.
 */
export function resolveBasePath(env: Record<string, string | undefined>): string {
  return normalizeBasePath(env[BASE_PATH_ENV_VAR]);
}

/**
 * Resolved once at module load, from the literal expression
 * `process.env.ADG_WEB_BASE_PATH` -- see the module docstring above for why
 * it must be written out literally, and must not be routed through
 * `resolveBasePath` or any other indirection. In application code this
 * reads the value `next.config.ts`'s `env` block inlined at build time.
 */
export const BASE_PATH = normalizeBasePath(process.env.ADG_WEB_BASE_PATH);

/**
 * Joins an absolute `path` (e.g. `"/api/health"`) onto `basePath` without
 * introducing a double slash, and without re-prefixing a path that is
 * already prefixed (idempotent).
 */
export function prefixWithBasePath(path: string, basePath: string): string {
  if (!path.startsWith("/")) {
    throw new Error("prefixWithBasePath expects a path starting with '/'");
  }
  if (basePath === "" || path === basePath || path.startsWith(`${basePath}/`)) {
    return path;
  }
  return `${basePath}${path}`;
}

/**
 * The helper every call in `lib/api.ts` must use instead of a bare `"/api/..."`
 * literal -- see the module docstring above for why.
 */
export function apiPath(path: string): string {
  return prefixWithBasePath(path, BASE_PATH);
}
