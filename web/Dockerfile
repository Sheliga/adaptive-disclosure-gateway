# syntax=docker/dockerfile:1
#
# Demo/production image for the Next.js advisor UI (T25 / issue #42). Build
# context is `web/` itself:
#
#   docker build -t adg-demo-web web
#
# or, normally, through ../compose.demo.yaml.
#
# `ADG_API_BASE_URL` is deliberately NOT set here (no ENV/ARG for it): it is
# read at request time by `lib/proxy.ts` (`process.env.ADG_API_BASE_URL`),
# so compose supplies it as a plain runtime environment variable pointed at
# the `api` service (e.g. `http://api:8000`). Baking it in at build time
# would freeze one deployment's network address into the image and make it
# non-portable across environments -- and there is deliberately no
# `NEXT_PUBLIC_*` variable anywhere in this stack: the browser never talks
# to the Python API directly (see `lib/proxy.ts`'s module docstring), so
# nothing about that address belongs in the client bundle.
#
# `ADG_WEB_BASE_PATH` is the opposite case, deliberately: it IS a build ARG.
# It is not a secret -- it is visible in every URL the browser sends -- and
# Next.js requires `basePath` to be known at BUILD time (see
# `web/next.config.ts`/`web/lib/basePath.ts`): it gets inlined into the
# client bundle and into the server's own route matching, so it cannot be
# supplied as a plain runtime environment variable the way
# `ADG_API_BASE_URL` is. Defaults to "" (root path, today's behavior)
# whenever a deployment does not pass `--build-arg ADG_WEB_BASE_PATH=...`.

# Pinned by exact version and digest, not a floating "24-slim" tag -- see
# docker/api.Dockerfile's base-image comment for why, and
# docs/advisor-demo.md's "Reproducible dependencies" section for the refresh
# procedure. Digest captured by pulling node:24.21.0-slim and reading
# `docker inspect --format='{{index .RepoDigests 0}}'`.
FROM node:24.21.0-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS base

# ---------------------------------------------------------------------------
FROM base AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---------------------------------------------------------------------------
FROM base AS builder

# See the ADG_WEB_BASE_PATH comment at the top of this file: this is the
# one build-time value this stage legitimately needs, and it is not a
# secret.
ARG ADG_WEB_BASE_PATH=""

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# No secret and no API URL is available (or needed) at build time -- see the
# module docstring above. `next build` only needs the source tree (plus
# ADG_WEB_BASE_PATH, which next.config.ts reads via process.env).
RUN ADG_WEB_BASE_PATH="$ADG_WEB_BASE_PATH" npm run build

# ---------------------------------------------------------------------------
FROM base AS runtime

# Re-declared (build ARGs do not cross FROM boundaries): needed here only to
# feed ADG_WEB_BASE_PATH into ENV below, which is what the plain `node -e`
# HEALTHCHECK script reads at container runtime -- it runs outside the
# Next.js bundle, so it cannot see the value next.config.ts inlined into the
# app itself.
ARG ADG_WEB_BASE_PATH=""

# No fixed UID/GID: node:24-slim already reserves 1000 for its own "node"
# user, so a hardcoded 1000 here would collide on that base image.
RUN groupadd --system adg \
    && useradd --system --gid adg --home-dir /app --shell /usr/sbin/nologin adg

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    ADG_WEB_BASE_PATH=$ADG_WEB_BASE_PATH

WORKDIR /app

# `output: "standalone"` (next.config.ts) traces only the files the server
# actually needs -- this is deliberately not `COPY . .` plus `npm ci`.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

RUN chown -R adg:adg /app
USER adg

EXPOSE 3000

# node, not curl: the slim base has no curl, and this avoids adding a
# package purely for the healthcheck. Hits the app's OWN readiness proxy
# (`/api/ready` -> `lib/proxy.ts` -> the api service's /ready), not
# `/api/health` (T25 review finding 2): /health always reports 200 once the
# api process is up, even mid-startup-refusal, while /ready reports 503
# until the api is actually ready -- so a healthy status here also proves
# the web container can reach a genuinely ready api container, not merely a
# live one.
#
# This hits the container's OWN loopback directly, bypassing whatever
# reverse proxy/basePath sits in front of it in production -- but Next.js's
# own server-side routing still requires the request path to carry the
# configured basePath once ADG_WEB_BASE_PATH is set (basePath is not just a
# client-bundle rewrite), so the healthcheck path is built from the SAME
# ADG_WEB_BASE_PATH runtime env var `ENV` set above, not a bare "/api/ready"
# literal.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD node -e "fetch('http://127.0.0.1:3000' + (process.env.ADG_WEB_BASE_PATH || '') + '/api/ready').then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", "server.js"]
