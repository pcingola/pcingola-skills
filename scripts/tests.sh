#!/usr/bin/env bash
# Run the tests in the root project's environment: scripts/tests.sh unit|integration|all [pytest args]
cd "$(dirname "$0")/.." && k=${1:-unit} && shift; [ "$k" = all ] && k="unit integration"
uv run --group dev pytest $(printf 'tests/%s ' $k) "$@"
