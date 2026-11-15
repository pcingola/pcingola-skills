"""The pinned library files: version, jsDelivr path, SHA-256 and the global each defines."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LibPin:
    """A pinned library file at `https://cdn.jsdelivr.net/npm/<package>@<version>/<path>`."""

    key: str
    package: str
    version: str
    path: str
    sha256: str
    glob: str

    @property
    def url(self) -> str:
        return f"https://cdn.jsdelivr.net/npm/{self.package}@{self.version}/{self.path}"

    @property
    def file(self) -> str:
        """The file name in the animation's lib/."""
        return Path(self.path).name

    @property
    def vendor_dir(self) -> str:
        """The directory under `<data dir>/vendor/`."""
        return f"{self.package}@{self.version}"


# Classic UMD scripts only: module scripts do not load from file://. The order is the script order in index.html.
PINS = {
    "gsap": LibPin("gsap", "gsap", "3.13.0", "dist/gsap.min.js",
                   "96c01b81f44a3290e2b4532f55e2c9534b2adc43273a19f3756b2cb41f0fd0b6", "gsap"),
    "anime": LibPin("anime", "animejs", "4.5.0", "dist/bundles/anime.umd.min.js",
                    "8d5b3a58a1f64023a04a4cedeef135a2263b18da04b35177ac13438a0bad033b", "anime"),
    "motion": LibPin("motion", "motion", "14.14.0", "dist/motion.js",
                     "521cfef8910fdd997463ea9881d4b790e017331e3d2f79c02adfc4d5fe1f2cae", "Motion"),
    "d3": LibPin("d3", "d3", "7.9.0", "dist/d3.min.js",
                 "f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539", "d3"),
    "three": LibPin("three", "three", "0.159.0", "build/three.min.js",
                    "7b1c5d75b28d9de15042e2b374f83566d8c7146697af8fdeb4558b0fb528a585", "THREE"),
}
