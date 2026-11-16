"""`providers.<p>.models.<m>` of a google provider; any model id is served, an entry only gives attributes."""

from __future__ import annotations

from .voices import Voices


class GoogleModel(Voices):
    """`predict`: a music model served by the Vertex predict endpoint (Lyria 2), else streamed; `voice`, `voices`:
    those of a speech model."""

    predict: bool = False
