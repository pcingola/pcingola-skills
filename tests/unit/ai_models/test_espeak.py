"""Unit tests for the espeak-ng data path decision and copy (no espeak-ng call)."""

import tempfile
import unittest
from pathlib import Path

from ai_models import espeak


class TestChooseDataDir(unittest.TestCase):
    def test_short_source_used_as_is(self):
        """espeak.choose_data_dir returns None for a source path shorter than the limit. Guards that no copy is made when espeak-ng can open the bundled path."""
        self.assertIsNone(espeak.choose_data_dir("/a" * 10, [Path("/short")], limit=150))

    def test_source_at_limit_is_copied(self):
        """espeak.choose_data_dir picks a copy directory for a source of exactly the limit length.
        Guards the boundary of the 150-character rule (espeak-ng drops paths of 160 characters or more)."""
        source = "/" + "x" * 149
        self.assertEqual(espeak.choose_data_dir(source, [Path("/short")], limit=150), Path("/short"))

    def test_first_short_candidate_wins(self):
        """espeak.choose_data_dir skips candidates at or over the limit and returns the first short one.
        Guards the candidate order: beside the weights, then the temp dir."""
        long_dir = Path("/" + "y" * 200)
        got = espeak.choose_data_dir("/" + "x" * 200, [long_dir, Path("/b"), Path("/c")], limit=150)
        self.assertEqual(got, Path("/b"))

    def test_no_short_candidate_raises(self):
        """espeak.choose_data_dir raises when the source and every candidate are too long.
        Guards against espeak-ng's silent failure on a long path."""
        with self.assertRaises(RuntimeError):
            espeak.choose_data_dir("/" + "x" * 200, [Path("/" + "y" * 200)], limit=150)

    def test_default_candidates_are_short(self):
        """espeak.candidates includes a directory shorter than PATH_LIMIT, also under a long weights directory.
        Guards the temp-dir fallback that makes the copy possible under a long weights directory."""
        self.assertTrue(any(len(str(d)) < espeak.PATH_LIMIT for d in espeak.candidates(Path("/" + "w" * 200))))


class TestEnsureCopy(unittest.TestCase):
    def test_copies_once_and_recopies_on_new_source(self):
        """espeak.ensure_copy copies the data once, keeps the copy for the same source and replaces it for another source, leaving no temporary directory.
        Guards the .source marker that makes the copy a one-time step."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "src" / "espeak-ng-data"
            src.mkdir(parents=True)
            (src / "phontab").write_text("a", encoding="utf-8")
            dest = tmp / "dest" / "espeak-ng-data"

            self.assertEqual(espeak.ensure_copy(src, dest), dest)
            self.assertEqual((dest / "phontab").read_text(encoding="utf-8"), "a")

            # same source: the existing copy is kept
            (dest / "phontab").write_text("kept", encoding="utf-8")
            espeak.ensure_copy(src, dest)
            self.assertEqual((dest / "phontab").read_text(encoding="utf-8"), "kept")

            # another source: copied again
            src2 = tmp / "src2" / "espeak-ng-data"
            src2.mkdir(parents=True)
            (src2 / "phontab").write_text("b", encoding="utf-8")
            espeak.ensure_copy(src2, dest)
            self.assertEqual((dest / "phontab").read_text(encoding="utf-8"), "b")
            self.assertEqual(sorted(p.name for p in dest.parent.iterdir()), ["espeak-ng-data"])


if __name__ == "__main__":
    unittest.main()
