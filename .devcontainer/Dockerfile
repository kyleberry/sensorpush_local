# One image for the devcontainer and CI (SENS-10). The devcontainer builds it
# locally; .forgejo/workflows/ci-image.yml builds the same file, runs
# smoke-test.sh and the test suite in it, and publishes it to
# registry.berry.house/sensorpush-local/ci, which every CI job runs in. Keep
# this the only place the Python version and system packages are set.
#
# Every version below is pinned where Renovate can see it, so updates arrive
# as PRs that change this file. ci-image.yml rebuilds only when the file's
# hash changes, so a version that floated at build time (a bare tag, an
# installer script) would stay frozen in the published image.
#   - Base: Python minor+patch and digest. The digest moves when Debian
#     security updates land, and a rebuild also pulls the apt packages below
#     fresh. Python version bumps ride the "home assistant ecosystem" group;
#     digest bumps the "ci image" group (renovate.json).
#   - Node.js and uv: copied from their official images, like homelab's
#     act-runner image, so Renovate's dockerfile manager tracks them.
FROM python:3.14.10-bookworm@sha256:3fe825da0a80fa8e2cd79baadeb76b03c0ddf3d6cdbc8346778a0208b9d6038c

# Build tools and system dependencies for the integration's test suite, plus
# what CI jobs need: gnupg to sign release commits and tags. libatomic1: the
# official Node.js binaries link against it from Node 25, and the node binary
# copied in below doesn't bring its shared libraries along.
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    bluez \
    libudev-dev \
    libavahi-compat-libdnssd-dev \
    git \
    jq \
    curl \
    ca-certificates \
    gnupg \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# Node.js, because the runner executes JavaScript actions (actions/checkout,
# actions/cache, 1password/load-secrets-action) with the job container's
# `node`. npm/npx are symlinks into node_modules/npm/bin in the source image;
# COPY would dereference them and break their relative requires, so they're
# recreated here, as in homelab's act-runner Dockerfile.
COPY --from=node:24.22.2-bookworm-slim /usr/local/include/node /usr/local/include/node
COPY --from=node:24.22.2-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=node:24.22.2-bookworm-slim /usr/local/bin/node /usr/local/bin/node
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# uv, from its distroless image as astral-sh/uv's docs recommend.
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /usr/local/bin/
