"""torch's CPU threads for models that run on the CPU (`chatterbox`).

On a CPU with cores of two speeds (Arm big.LITTLE, Intel performance and efficiency cores) torch starts one thread
per core, and each parallel step waits for the slow cores. `performance_threads` runs a block on one thread per fast
core: on a 10 + 10 core Arm CPU (Cortex-X925 and A725) Chatterbox Turbo speaks a sentence in 3.8 s instead of 9.5 s.
The fast cores are those with the highest `cpuinfo_max_freq` in Linux's sysfs; elsewhere, or when every core has the
same speed, torch keeps its default.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache
from pathlib import Path

SYSFS_CPU = Path("/sys/devices/system/cpu")


@cache
def performance_cores() -> int | None:
    """The number of usable cores whose maximum frequency is the highest; None when sysfs gives no frequencies or
    all cores have the same."""
    freqs = []
    for cpu in sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []:
        try:
            freqs.append(int((SYSFS_CPU / f"cpu{cpu}" / "cpufreq" / "cpuinfo_max_freq").read_text()))
        except (OSError, ValueError):
            return None
    if not freqs or min(freqs) == max(freqs):
        return None
    return freqs.count(max(freqs))


@contextmanager
def performance_threads() -> Iterator[None]:
    """Run the block with torch's intra-op threads set to `performance_cores` (when not None) in the calling thread;
    the earlier count is restored after it."""
    import torch

    n = performance_cores()
    before = torch.get_num_threads()
    if n is not None:
        torch.set_num_threads(n)
    try:
        yield
    finally:
        torch.set_num_threads(before)
