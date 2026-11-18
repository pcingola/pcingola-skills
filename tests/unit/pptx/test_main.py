"""Unit tests for pptx_tool.pptx.main: exit codes of argument parsing, in process."""
import contextlib
import io
import unittest

from pptx_tool.pptx import main


def _run(argv: list[str]) -> tuple[int, str, str]:
    """Call main(argv) with stdout and stderr captured; return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class TestMainArgparse(unittest.TestCase):

    def test_help_returns_zero(self) -> None:
        """main(["--help"]) returns 0 and prints the usage to stdout. Guards that main turns the
        SystemExit argparse raises for --help into a return value, so a caller in process
        is not terminated."""
        code, out, err = _run(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("usage: pptx", out)
        self.assertEqual(err, "")

    def test_unknown_option_returns_two(self) -> None:
        """main with an unknown option after a complete `get` command returns 2 and prints the
        argparse error to stderr, without running the command. Guards that an argument error
        keeps argparse's exit code 2 when main returns it instead of exiting."""
        code, out, err = _run(["get", "deck.pptx", "slide-0/shape-0", "--no-such-option"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("unrecognized arguments: --no-such-option", err)


if __name__ == "__main__":
    unittest.main()
