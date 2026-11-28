"""`ai_models.cancel`: the cancel signal of an in-process call (docs/ai_models.md, Cancellation)."""

import threading

import pytest
import torch

from ai_models import Cancelled, cancel


def test_check_raises_only_when_the_signal_is_set():
    """Without a signal `check` does nothing; with one it raises `Cancelled` once the signal is set."""
    cancel.check()
    event = threading.Event()
    with cancel.signal(event):
        cancel.check()
        event.set()
        with pytest.raises(Cancelled):
            cancel.check()
    assert not cancel.active()
    cancel.check()


def test_hooked_module_stops_at_its_next_forward():
    """A torch module under `hooked` runs while the signal is clear and raises `Cancelled` at its next forward once
    the signal is set; the hook is removed after the block, and without a signal no hook is added."""
    layer = torch.nn.Linear(2, 2)
    x = torch.zeros(1, 2)
    event = threading.Event()
    with cancel.signal(event), cancel.hooked(layer):
        layer(x)
        event.set()
        with pytest.raises(Cancelled):
            layer(x)
    layer(x)
    with cancel.hooked(layer):
        assert not layer._forward_pre_hooks
