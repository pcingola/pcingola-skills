"""short_video_tool.cli.play_commands: on macOS images open in `play.image_app`, other files in `play.app`;
elsewhere each file opens with `xdg-open`."""
import unittest
from pathlib import Path

from short_video_tool import cli


class TestPlay(unittest.TestCase):

    def test_images_and_media_split_by_application(self) -> None:
        """cli.play_commands opens images, suffix case-insensitive, in play.image_app and other files in
        play.app, keeping order. Guards `play` opening images in an image viewer."""
        paths = [Path("a.png"), Path("film.mp4"), Path("b.JPG"), Path("music.mp3")]
        self.assertEqual(cli.play_commands(paths, "Darwin"), [
            ["open", "-a", "Preview", "a.png", "b.JPG"],
            ["open", "-a", "VLC", "film.mp4", "music.mp3"],
        ])

    def test_one_command_per_application_used(self) -> None:
        """cli.play_commands gives no command for an application with no files. Guards `open -a` being run
        without files."""
        self.assertEqual(cli.play_commands([Path("film.mp4")], "Darwin"), [["open", "-a", "VLC", "film.mp4"]])
        self.assertEqual(cli.play_commands([Path("a.png")], "Darwin"), [["open", "-a", "Preview", "a.png"]])

    def test_xdg_open_outside_macos(self) -> None:
        """cli.play_commands gives one xdg-open command per file on Linux, in order. Guards `play` on a
        machine without `open -a`."""
        self.assertEqual(cli.play_commands([Path("a.png"), Path("film.mp4")], "Linux"),
                         [["xdg-open", "a.png"], ["xdg-open", "film.mp4"]])


if __name__ == "__main__":
    unittest.main()
