"""short_video_tool.settings: how the project's settings.yaml combines with the defaults."""
import unittest

from short_video_tool import settings


class TestMerge(unittest.TestCase):

    def test_mappings_merge_other_values_replace(self) -> None:
        """settings.merge merges mappings key by key, lets a project's null replace a default and replaces lists
        whole. Guards how a project's settings.yaml overrides the skill defaults."""
        self.assertEqual(settings.merge({"a": {"x": 1, "y": 2}, "b": [1]}, {"a": {"y": None}, "b": [2]}),
                         {"a": {"x": 1, "y": None}, "b": [2]})


if __name__ == "__main__":
    unittest.main()
