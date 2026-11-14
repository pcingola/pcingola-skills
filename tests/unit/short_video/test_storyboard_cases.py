"""short_video_tool: the storyboard structure check on the storyboards shared with the Studio server's tests, which
mirror this check."""
import json
import unittest
from pathlib import Path

from short_video_tool import settings, storyboard

CASES = json.loads((Path(__file__).parent / "storyboard_cases.json").read_text())["cases"]


class TestSharedCases(unittest.TestCase):

    def setUp(self) -> None:
        settings.use_project(None)

    def test_cases(self) -> None:
        """storyboard.check, on the structure as parse_json normalizes it, gives each shared case its verdict.
        Guards the Studio server's copy of the rules: a rule changed here fails this test until the shared cases,
        and with them the server's test, are changed."""
        for case in CASES:
            with self.subTest(case["case"]):
                problems = storyboard.check(storyboard.normalize(case["storyboard"]))
                self.assertEqual(problems == [], case["valid"], problems)


if __name__ == "__main__":
    unittest.main()
