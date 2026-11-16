"""Command-line options for every suite."""

from tests import options


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--keep-tmp", action="store_true", default=False,
        help="Keep the output files of tests that write under tests/data/tmp_* (pptx: also add summary slides).",
    )


def pytest_configure(config) -> None:
    options.record(config)
