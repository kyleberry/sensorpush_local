FROM python:3.14-bookworm

# Install build tools and system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    bluez \
    libudev-dev \
    libavahi-compat-libdnssd-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools wheel uv