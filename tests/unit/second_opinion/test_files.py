"""Unit tests for second_opinion_tool.files: kinds, MIME types and size limits."""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from second_opinion_tool import files


class TestClassify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, data: bytes) -> Path:
        p = self.dir / name
        p.write_bytes(data)
        return p

    def test_text_extensions_and_utf8_fallback(self):
        """files.classify returns text for a known text extension, an unknown extension and no
        extension when the content decodes as UTF-8. Guards the UTF-8 fallback for files outside
        the extension table.
        """
        self.assertEqual(files.classify(self.write("brief.md", b"# t")), ("text", "text/plain"))
        self.assertEqual(files.classify(self.write("storyboard.unknown", "tempo 120 — ok".encode())),
                         ("text", "text/plain"))
        self.assertEqual(files.classify(self.write("Makefile", b"all:\n")), ("text", "text/plain"))

    def test_unknown_extension_probes_first_block_only(self):
        """files.classify decodes only the first PROBE_BYTES of an unknown file and accepts a multi-
        byte character cut at that boundary. Guards the incremental decoder with final=False.
        """
        p = self.write("notes.unknown", b"a" * files.PROBE_BYTES + b"\xff\xfe")
        self.assertEqual(files.classify(p), ("text", "text/plain"))
        # a multi-byte character cut by the probe boundary is still UTF-8
        p = self.write("cut.unknown", b"a" * (files.PROBE_BYTES - 1) + "\u00e9".encode())
        self.assertEqual(files.classify(p), ("text", "text/plain"))

    def test_unknown_binary_refused(self):
        """files.classify refuses an unknown extension whose content is not UTF-8. Guards the
        refusal of unsupported binary files before any request.
        """
        with self.assertRaisesRegex(files.FileError, r"unsupported file type \.bin"):
            files.classify(self.write("x.bin", b"\xff\xfe\x00\x81"))

    def test_load_text_keeps_text_and_record(self):
        """files.load keeps a text file's decoded text, and ReviewFile.record gives path, kind, MIME
        type and bytes sent. Guards the file entry written to the --out JSON.
        """
        f = files.load(str(self.write("notes.txt", b"line one\nline two\n")))
        self.assertEqual((f.kind, f.text), ("text", "line one\nline two\n"))
        self.assertEqual(f.record(), {"path": str(self.dir / "notes.txt"), "kind": "text",
                                      "mime_type": "text/plain", "bytes_sent": 18})

    def test_empty_file_refused(self):
        """files.load refuses an empty file. Guards the documented empty-file refusal."""
        with self.assertRaisesRegex(files.FileError, "empty file"):
            files.load(str(self.write("empty.png", b"")))

    def test_unreadable_file_refused(self):
        """files.load turns an unreadable file into a FileError 'cannot read'. Guards the OSError
        handling of _read, so the CLI prints one error instead of a traceback.
        """
        p = self.write("locked.unknown", b"text")
        p.chmod(0)
        try:
            with self.assertRaisesRegex(files.FileError, "cannot read"):
                files.load(str(p))
        finally:
            p.chmod(0o644)

    def test_invalid_utf8_text_warns_and_replaces(self):
        """files.load sends a text file with invalid UTF-8 with U+FFFD in place of the bad bytes and
        warns with the byte offset. Guards the documented replacement instead of a refusal.
        """
        p = self.write("notes.md", b"ok \xff end")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            f = files.load(str(p))
        self.assertEqual(f.text, "ok \ufffd end")
        self.assertIn("not valid UTF-8 (byte 3)", err.getvalue())

    def test_missing_file_refused(self):
        """files.load refuses a path that is not a file. Guards the 'no such file' error."""
        with self.assertRaisesRegex(files.FileError, "no such file"):
            files.load(str(self.dir / "nope.png"))

    def test_file_over_limit_refused_with_size(self):
        """files.load refuses an image, audio, PDF or text file over the limit, naming its size and
        the limit. Guards the rule that only videos are transcoded.
        """
        for name in ("big.png", "big.wav", "big.pdf", "big.md", "big.unknown"):
            p = self.write(name, b"a" * 3 * 1024 * 1024)
            with self.assertRaisesRegex(files.FileError, r"3\.0 MiB is over the 2\.0 MiB inline limit"):
                files.load(str(p), limit=2 * 1024 * 1024)

    def test_total_over_limit_refused(self):
        """files.load_all refuses a set of files whose total exceeds the limit although each is
        under it. Guards the per-request inline limit.
        """
        a = self.write("a.png", b"a" * 600)
        b = self.write("b.png", b"b" * 600)
        self.assertEqual(len(files.load_all([str(a)], limit=1000)), 1)
        with self.assertRaisesRegex(files.FileError, "total .* review them in several runs"):
            files.load_all([str(a), str(b)], limit=1000)

    def test_large_video_without_ffmpeg_refused(self):
        """files.load and files.load_all transcode a video over the limit, and a video under it when
        the set is over it, and fail with 'ffmpeg is not on PATH' without FFmpeg. Guards both
        transcode triggers and the missing-FFmpeg error.
        """
        p = self.write("film.mp4", b"\x00" * 2000)
        small = self.write("clip.mp4", b"\x00" * 800)
        notes = self.write("notes.md", b"n" * 400)
        empty = self.dir / "bin"
        empty.mkdir()
        # a subprocess with a PATH that holds no ffmpeg; a video under the limit is transcoded when the
        # set is over it
        code = ("import sys\nfrom second_opinion_tool import files\n"
                "for paths in ([sys.argv[1]], sys.argv[2:]):\n"
                "    try:\n        files.load_all(paths, limit=1000)\n"
                "    except files.FileError as e:\n        print(e)\n")
        env = {**os.environ, "PATH": str(empty), "PYTHONPATH": os.pathsep.join(sys.path)}
        out = subprocess.run([sys.executable, "-c", code, str(p), str(small), str(notes)], env=env,
                             capture_output=True, text=True, timeout=60).stdout
        self.assertEqual(out.count("ffmpeg is not on PATH"), 2, out)

if __name__ == "__main__":
    unittest.main()
