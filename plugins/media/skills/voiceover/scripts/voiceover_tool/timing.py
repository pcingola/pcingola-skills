"""Build and write `timing.json`.

All times are seconds from the start of the audio file, rounded to ms.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SentenceTiming:
    index: int  # 1-based
    text: str
    start: float
    end: float
    aligned: bool
    words: list[tuple[str, float, float]] = field(default_factory=list)
    style: str | None = None  # the sentence's own style (a `[style]` line)


def _ms(t: float) -> float:
    return round(float(t), 3)


def build_timing(
    *,
    audio: str,
    sample_rate: int,
    duration: float,
    model: str,
    voice: str,
    speed: float,
    sentences: list[SentenceTiming],
    style: str | None = None,
) -> dict:
    """`model` is the speech model id; `style` is written only when given."""
    return {
        "audio": audio,
        "sample_rate": sample_rate,
        "duration": _ms(duration),
        "model": model,
        **({"style": style} if style else {}),
        "voice": voice,
        "speed": speed,
        "sentences": [
            {
                "index": s.index,
                "text": s.text,
                "start": _ms(s.start),
                "end": _ms(s.end),
                **({"style": s.style} if s.style else {}),
                "aligned": s.aligned,
                "words": [{"text": w, "start": _ms(ws), "end": _ms(we)} for w, ws, we in s.words],
            }
            for s in sentences
        ],
    }


def write_timing(path: str | Path, timing: dict) -> Path:
    path = Path(path)
    path.write_text(json.dumps(timing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
