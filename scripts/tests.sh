#!/usr/bin/env bash
# Run the tests in the root project's environment: scripts/tests.sh unit|integration|models|server|cuda|all [pytest args]
# all is unit and integration; models (tests/models/, full-size models), server (tests/server/, a deployed model
# server: scripts/tests.sh server --server-url <url of its /v1>) and cuda (tests/cuda/, an NVIDIA GPU) run only when
# named. Every run stops at the first failure (`addopts = "-x"` in pyproject.toml).
cd "$(dirname "$0")/.." && k=${1:-unit} && shift; [ "$k" = all ] && k="unit integration"
uv run --group dev pytest $(printf 'tests/%s ' $k) "$@"
