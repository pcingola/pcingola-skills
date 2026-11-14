"""Unit tests of moving a project directory to the Trash."""
from __future__ import annotations

import pytest

from studio_server.trash import move_to_trash


def test_failed_move_leaves_no_trashinfo(tmp_path):
    """A move that fails (the directory is gone) raises and leaves no `info/<name>.trashinfo` and nothing in
    `files/`, so the desktop's Trash lists no entry without files. Guards a delete that fails halfway."""
    root = tmp_path / "Trash"
    with pytest.raises(OSError):
        move_to_trash(tmp_path / "missing", "Studio images - cat", root)
    assert not [p for p in root.rglob("*") if p.is_file()]
