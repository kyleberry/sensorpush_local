#!/usr/bin/env bash
# Checks that the devcontainer/CI image has every tool the CI jobs use
# (SENS-10). ci-image.yml runs it in a freshly built image before publishing:
#   docker run --rm -i <image> bash -s < .devcontainer/smoke-test.sh
set -euo pipefail

fail=0
check() {
  local name=$1
  shift
  if out=$("$@" 2>&1 | head -n 1); then
    printf 'ok    %-8s %s\n' "$name" "$out"
  else
    printf 'FAIL  %-8s %s\n' "$name" "$out"
    fail=1
  fi
}

# Python must match the integration's requires-python (>=3.14.6,<3.15).
check python python3 -c 'import sys; assert sys.version_info[:2] == (3, 14), sys.version; print(sys.version.split()[0])'
check uv uv --version
check node node --version
check npm npm --version
check git git --version
check gpg gpg --version
check jq jq --version
check curl curl --version
check gcc gcc --version

exit "$fail"
