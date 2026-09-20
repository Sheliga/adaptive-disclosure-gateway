import type { NextConfig } from "next";

import { BASE_PATH_ENV_VAR, normalizeBasePath } from "./lib/basePath";

// Subpath deployment (e.g. behind nginx at
// `https://host/disclosure-gateway`, not the domain root): Next.js requires
// `basePath` to be known at BUILD time -- it is inlined into the client
// bundle and the server's own route matching, and "cannot be changed
// without re-building" (Next.js docs). `ADG_WEB_BASE_PATH` is therefore read
// here, once, at config-load time -- never at request time -- from a real
// process env var the build process must set (see `web/Dockerfile`'s
// `ADG_WEB_BASE_PATH` build ARG). Empty/unset normalizes to `""`, which is
// Next.js's own documented default and preserves today's root-path behavior
// exactly, in dev and in every existing test.
const basePath = normalizeBasePath(process.env[BASE_PATH_ENV_VAR]);

const nextConfig: NextConfig = {
  // Emits `.next/standalone` (a self-contained server bundle with only the
  // traced runtime files/dependencies) so the production Docker image
  // (web/Dockerfile, T25 / issue #42) copies a minimal runtime instead of
  // the full `node_modules`/build output. Has no effect on `next dev` or on
  // the existing CI `npm run build` gate beyond this extra output folder.
  output: "standalone",

  basePath,

  // Re-exposes the SAME resolved value to application code (both server and
  // client bundles) as `process.env.ADG_WEB_BASE_PATH` -- see
  // `web/lib/basePath.ts`'s module docstring for why this is not a
  // `NEXT_PUBLIC_*` variable: Next.js's `env` config inlines whatever it
  // lists into the client bundle regardless of naming convention, unlike a
  // plain `.env`/system env var, where only the `NEXT_PUBLIC_*` prefix does
  // that. `lib/basePath.ts`'s `BASE_PATH` constant reads exactly this at
  // application build time, so the two can never disagree.
  env: {
    [BASE_PATH_ENV_VAR]: basePath,
  },
};

export default nextConfig;
