#!/usr/bin/env bash
# Run the tests in the root project's environment: scripts/tests.sh unit|integration|models|server|all [pytest args]
# all is unit and integration; models (tests/models/, full-size models) and server (tests/server/, a deployed model
# server: scripts/tests.sh server --server-url <url of its /v1>) run only when named. Every run stops at the first
# failure (`addopts = "-x"` in pyproject.toml).
cd "$(dirname "$0")/.." && k=${1:-unit} && shift; [ "$k" = all ] && k="unit integration"
uv run --group dev pytest $(printf 'tests/%s ' $k) "$@"
