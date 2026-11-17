#!/usr/bin/env bash
# Run the tests in the root project's environment: scripts/tests.sh unit|integration|models|all [pytest args]
# all is unit and integration; models (tests/models/, full-size models) runs only when named.
cd "$(dirname "$0")/.." && k=${1:-unit} && shift; [ "$k" = all ] && k="unit integration"
uv run --group dev pytest $(printf 'tests/%s ' $k) "$@"
