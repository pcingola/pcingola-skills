"""Command-line options for every suite."""

from tests import options


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--keep-tmp", action="store_true", default=False,
        help="Keep the output files of tests that write under tests/data/tmp_* (pptx: also add summary slides).",
    )
    parser.addoption(
        "--server-url", default=None,
        help="The /v1 base URL of the deployed model server that tests/server/ tests (scripts/tests.sh server).",
    )


def pytest_configure(config) -> None:
    options.record(config)
