#!/usr/bin/env bash
# Run the tests in the root project's environment: scripts/tests.sh <category> [pytest args]; without a category, or
# with `help`, print the categories. Every run stops at the first failure (`addopts = "-x"` in pyproject.toml).
cd "$(dirname "$0")/.." || exit 1
case "${1:-help}" in
  help|-h|--help)
    cat <<'EOF'
usage: scripts/tests.sh <category> [pytest args]

  unit         tests/unit: no model, GPU, Ollama or network
  integration  tests/integration: real tools and tiny models (Ollama with the models of tests/config.yaml)
  all          unit and integration: what runs on any machine
  cuda         tests/cuda: needs an NVIDIA GPU (Fish, GPU memory checks)
  server       tests/server: a deployed model server; needs --server-url <url of its /v1>
  models       tests/models: full-size models and remote providers; slow
EOF
    exit 0 ;;
  all) k="unit integration" ;;
  unit|integration|cuda|server|models) k=$1 ;;
  *) echo "unknown category: $1 (scripts/tests.sh help)" >&2; exit 2 ;;
esac
shift
uv run --group dev pytest $(printf 'tests/%s ' $k) "$@"
