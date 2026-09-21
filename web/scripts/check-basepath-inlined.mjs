#!/usr/bin/env node
/**
 * Regression guard for the subpath-deployment basePath bug (production
 * incident: `https://host/disclosure-gateway`, every browser-side call to
 * this app's own `/api/**` proxy routes went out with no `/disclosure-gateway`
 * prefix and 404'd at the domain root -- the example list, preview and
 * execute all broke, while the server side worked fine).
 *
 * `web/lib/basePath.ts`'s `BASE_PATH` constant must resolve to a build-time
 * LITERAL string in the CLIENT bundle. Next.js's `env` config (`next.config.ts`)
 * only inlines the literal AST expression `process.env.ADG_WEB_BASE_PATH` --
 * any indirection (`env[SOME_VAR]`, `process.env` passed as a function
 * default parameter, etc.) compiles without error, every Vitest unit test in
 * `basePath.test.ts` passes (Node has a real `process.env`, unlike the
 * browser), and the bug reaches production silently. "The local tests
 * passed" is not evidence the artifact shipped to the browser is correct --
 * see CLAUDE.md's no-leak invariant on side channels for the same shape of
 * lesson applied here to a different boundary (the compiled bundle, not a
 * sensitive value).
 *
 * This script builds the app with ADG_WEB_BASE_PATH set, then inspects the
 * CLIENT static chunks Next.js emits (`.next/static/**\/*.js`, exactly what
 * ships to the browser -- never `.next/server`, which is not observable by
 * the client and where `process.env` is real):
 *
 *   1. POSITIVE: the chunk containing the literal `"/api/examples"` (the
 *      example-list request `lib/api.ts`'s `getExamples` issues) must also
 *      contain the literal basePath value (e.g. "/disclosure-gateway").
 *      That proves `BASE_PATH` resolved to a real string at build time
 *      rather than "".
 *   2. NEGATIVE: no client chunk may contain a dot-access on the property
 *      name `ADG_WEB_BASE_PATH` (e.g. minified `e.ADG_WEB_BASE_PATH`). This
 *      is the exact shape the broken bundle had in production
 *      (`(e.ADG_WEB_BASE_PATH??"").trim()`, `e` being an empty runtime
 *      object in the browser) -- a truly inlined literal leaves no trace of
 *      the property name anywhere in the output, because DefinePlugin
 *      replaces the whole `process.env.ADG_WEB_BASE_PATH` expression with
 *      the literal value textually.
 *
 * Exit code is non-zero on any failure so this can gate CI
 * (`.github/workflows/test.yml`'s `web` job) as well as run locally via
 * `npm run check:basepath`.
 */
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import process from "node:process";

const ROOT = path.resolve(import.meta.dirname, "..");
const BASE_PATH = process.env.ADG_WEB_BASE_PATH ?? "/disclosure-gateway";
const API_EXAMPLES_LITERAL = "/api/examples";
// Matches a property-access on the env var's name, e.g. `e.ADG_WEB_BASE_PATH`
// or `e .ADG_WEB_BASE_PATH` post-minification -- the exact shape a dynamic
// `env[BASE_PATH_ENV_VAR]` / `env.ADG_WEB_BASE_PATH` lookup compiles to,
// which a real literal substitution never leaves behind.
const DYNAMIC_ACCESS_PATTERN = /\.ADG_WEB_BASE_PATH(?![A-Za-z0-9_])/;

function collectJsFiles(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    const stats = statSync(full);
    if (stats.isDirectory()) {
      out.push(...collectJsFiles(full));
    } else if (entry.endsWith(".js")) {
      out.push(full);
    }
  }
  return out;
}

console.log(`[check-basepath-inlined] building with ADG_WEB_BASE_PATH=${BASE_PATH} ...`);
// Invoke the local `next` CLI's own entry script directly through the
// current Node binary, rather than `npx`/`npx.cmd` -- spawning a `.cmd`
// batch file on Windows requires `shell: true`, which node flags as a
// deprecated/unsafe pattern (args are concatenated, not escaped) even
// though these args are fixed constants, not user input.
const require = createRequire(import.meta.url);
const nextBin = require.resolve("next/dist/bin/next");
const build = spawnSync(process.execPath, [nextBin, "build"], {
  cwd: ROOT,
  stdio: "inherit",
  env: { ...process.env, ADG_WEB_BASE_PATH: BASE_PATH },
});
if (build.status !== 0) {
  console.error("[check-basepath-inlined] next build failed");
  process.exit(build.status ?? 1);
}

const staticDir = path.join(ROOT, ".next", "static");
let files;
try {
  files = collectJsFiles(staticDir);
} catch (err) {
  console.error(`[check-basepath-inlined] could not read ${staticDir}: ${err.message}`);
  process.exit(1);
}
if (files.length === 0) {
  console.error(`[check-basepath-inlined] no .js files found under ${staticDir}`);
  process.exit(1);
}

let examplesChunk = null;
const dynamicAccessChunks = [];
for (const file of files) {
  const text = readFileSync(file, "utf-8");
  if (examplesChunk === null && text.includes(API_EXAMPLES_LITERAL)) {
    examplesChunk = { file, text };
  }
  if (DYNAMIC_ACCESS_PATTERN.test(text)) {
    dynamicAccessChunks.push(file);
  }
}

const failures = [];
if (examplesChunk === null) {
  failures.push(
    `no client chunk under .next/static contains the literal "${API_EXAMPLES_LITERAL}" -- ` +
      `cannot verify its basePath prefix was inlined`,
  );
} else if (!examplesChunk.text.includes(BASE_PATH)) {
  failures.push(
    `chunk ${path.relative(ROOT, examplesChunk.file)} contains "${API_EXAMPLES_LITERAL}" but not the ` +
      `inlined basePath literal "${BASE_PATH}" -- BASE_PATH did not resolve to a build-time literal, so ` +
      `the browser will fetch "${API_EXAMPLES_LITERAL}" with no prefix and 404 at the domain root`,
  );
}
if (dynamicAccessChunks.length > 0) {
  for (const file of dynamicAccessChunks) {
    failures.push(
      `chunk ${path.relative(ROOT, file)} contains a dot-access on "ADG_WEB_BASE_PATH" -- this is the ` +
        `exact shape a dynamic env-object lookup compiles to (the confirmed production bug); the value must ` +
        `be a build-time literal via the literal expression "process.env.ADG_WEB_BASE_PATH", leaving no trace ` +
        `of the property name in the output`,
    );
  }
}

if (failures.length > 0) {
  console.error("[check-basepath-inlined] FAIL");
  for (const failure of failures) {
    console.error(`  - ${failure}`);
  }
  process.exit(1);
}

console.log(
  `[check-basepath-inlined] OK -- "${BASE_PATH}" is inlined as a build-time literal into the client bundle`,
);
