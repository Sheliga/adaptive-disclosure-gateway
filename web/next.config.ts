import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits `.next/standalone` (a self-contained server bundle with only the
  // traced runtime files/dependencies) so the production Docker image
  // (web/Dockerfile, T25 / issue #42) copies a minimal runtime instead of
  // the full `node_modules`/build output. Has no effect on `next dev` or on
  // the existing CI `npm run build` gate beyond this extra output folder.
  output: "standalone",
};

export default nextConfig;
