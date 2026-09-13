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

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# No secret and no API URL is available (or needed) at build time -- see the
# module docstring above. `next build` only needs the source tree.
RUN npm run build

# ---------------------------------------------------------------------------
FROM base AS runtime

# No fixed UID/GID: node:24-slim already reserves 1000 for its own "node"
# user, so a hardcoded 1000 here would collide on that base image.
RUN groupadd --system adg \
    && useradd --system --gid adg --home-dir /app --shell /usr/sbin/nologin adg

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

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
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD node -e "fetch('http://127.0.0.1:3000/api/ready').then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", "server.js"]
