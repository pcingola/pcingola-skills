"""Solid-colour PNG files for brand logo tests."""
import struct
import zlib
from pathlib import Path


def solid_png(path: Path, w: int, h: int, rgb: tuple[int, int, int]) -> Path:
    """Write an opaque `w` x `h` RGBA PNG of colour `rgb` to `path`."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    row = b"\x00" + bytes((*rgb, 255)) * w
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(row * h)) + chunk(b"IEND", b""))
    return path
