import os
import platform
import shutil
from pathlib import Path

_KNOWN_PATHS = {
    "Darwin": [
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ],
    "Windows": [
        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "LibreOffice", "program", "soffice.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "LibreOffice", "program", "soffice.exe"),
    ],
}


def find_libreoffice() -> str | None:
    """Find the LibreOffice binary, checking PATH and platform-specific default locations."""
    path = shutil.which("libreoffice") or shutil.which("soffice")
    if path:
        return path
    for candidate in _KNOWN_PATHS.get(platform.system(), []):
        if Path(candidate).exists():
            return candidate
    return None
