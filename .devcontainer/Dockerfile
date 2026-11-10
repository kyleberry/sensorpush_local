# One image for the devcontainer and CI (SENS-10). The devcontainer builds it
# locally; .forgejo/workflows/ci-image.yml builds the same file, runs
# smoke-test.sh and the test suite in it, and publishes it to
# registry.berry.house/sensorpush-local/ci, which every CI job runs in. Keep
# this the only place the Python version and system packages are set.
FROM python:3.14-bookworm

# Build tools and system dependencies for the integration's test suite, plus
# what CI jobs need: gnupg to sign release commits and tags, and Node.js because
# the runner executes JavaScript actions (actions/checkout, actions/cache,
# 1password/load-secrets-action) with the job container's `node`.
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
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools wheel uv
