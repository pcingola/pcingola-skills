"""short_video_tool.versions: numbers are never reused, order is numeric."""
import tempfile
import unittest
from pathlib import Path

from short_video_tool import versions


class TestVersions(unittest.TestCase):

    def test_numbering(self) -> None:
        """versions.next_version never reuses a number after versions are removed, versions.latest_version
        orders v10 after v2 numerically and `require` skips versions without the file. Guards the never-reused
        version numbers."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "scenes" / "intro"
            self.assertIsNone(versions.latest_version(root))
            for _ in range(10):
                versions.next_version(root)
            self.assertEqual(versions.latest_version(root).name, "v10")
            (root / "v10").rmdir()
            (root / "v5").rmdir()
            self.assertEqual(versions.next_version(root).name, "v11")
            (root / "v2" / "meta.json").write_text("{}")
            self.assertEqual(versions.latest_version(root, require="meta.json").name, "v2")


if __name__ == "__main__":
    unittest.main()
