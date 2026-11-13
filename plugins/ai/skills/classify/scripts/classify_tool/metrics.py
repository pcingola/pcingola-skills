"""Evaluation metrics on labelled items.

    accuracy     fraction of items whose top answer equals the label
    brier        mean squared error of the probabilities against the label:
                 yes/no questions (p_yes - y)^2 with y = 1 for "true";
                 choice and score questions sum over classes of (p_k - y_k)^2
    ece          expected calibration error over 10 equal-width bins of p_top:
                 sum over bins of n_b / N * |accuracy_b - mean p_top_b|
    reliability  per bin: item count, mean p_top, accuracy
    confusion    label -> predicted -> count
    thresholds   per threshold t: coverage = fraction with p_top >= t,
                 accuracy among those items (None when none)

Items whose request failed are left out and counted in `errors`. Without
probabilities (chat backend) brier, ece, reliability and thresholds are None.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

N_BINS = 10
CORNER = "label \\ predicted"
THRESHOLDS = [round(0.5 + 0.05 * i, 2) for i in range(10)]


@dataclass(frozen=True)
class Prediction:
    label: str
    top: str | None
    p_top: float | None = None
    probabilities: dict[str, float] | None = None

    @property
    def failed(self) -> bool:
        return self.top is None

    @property
    def correct(self) -> bool:
        return self.top == self.label


def brier_one(p: Prediction, binary: bool) -> float:
    if binary:
        y = 1.0 if p.label == "true" else 0.0
        return (p.probabilities["true"] - y) ** 2
    return sum((pk - (1.0 if k == p.label else 0.0)) ** 2 for k, pk in p.probabilities.items())


def bin_index(p_top: float) -> int:
    return min(int(p_top * N_BINS), N_BINS - 1)


def reliability(preds: list[Prediction]) -> list[dict[str, Any]]:
    rows = []
    for b in range(N_BINS):
        inside = [p for p in preds if bin_index(p.p_top) == b]
        rows.append({
            "bin": f"{b / N_BINS:.1f}-{(b + 1) / N_BINS:.1f}",
            "n": len(inside),
            "mean_p_top": sum(p.p_top for p in inside) / len(inside) if inside else None,
            "accuracy": sum(p.correct for p in inside) / len(inside) if inside else None,
        })
    return rows


def ece(preds: list[Prediction]) -> float:
    n = len(preds)
    return sum(r["n"] / n * abs(r["accuracy"] - r["mean_p_top"]) for r in reliability(preds) if r["n"])


def thresholds(preds: list[Prediction]) -> list[dict[str, Any]]:
    rows = []
    for t in THRESHOLDS:
        kept = [p for p in preds if p.p_top >= t]
        rows.append({
            "threshold": t,
            "coverage": len(kept) / len(preds),
            "accuracy": sum(p.correct for p in kept) / len(kept) if kept else None,
            "n": len(kept),
        })
    return rows


def confusion(preds: list[Prediction], classes: list[str]) -> dict[str, dict[str, int]]:
    table = {label: {pred: 0 for pred in classes} for label in classes}
    for p in preds:
        table[p.label][p.top] += 1
    return table


def evaluate(preds: list[Prediction], classes: list[str], binary: bool = False) -> dict[str, Any]:
    """Metrics over `preds`; `binary` for yes/no questions (classes true, false)."""
    ok = [p for p in preds if not p.failed]
    out: dict[str, Any] = {"n": len(preds), "errors": len(preds) - len(ok), "classes": classes}
    if not ok:
        out.update(accuracy=None, brier=None, ece=None, reliability=None, confusion=None, thresholds=None)
        return out
    out["accuracy"] = sum(p.correct for p in ok) / len(ok)
    out["confusion"] = confusion(ok, classes)
    if any(p.probabilities is None or p.p_top is None for p in ok):
        out.update(brier=None, ece=None, reliability=None, thresholds=None)
        return out
    out["brier"] = sum(brier_one(p, binary) for p in ok) / len(ok)
    out["ece"] = ece(ok)
    out["reliability"] = reliability(ok)
    out["thresholds"] = thresholds(ok)
    return out


def _f(v: float | None, digits: int = 3) -> str:
    return "-" if v is None else f"{v:.{digits}f}"


def report(m: dict[str, Any]) -> str:
    """The metrics as plain text."""
    lines = [f"items: {m['n']}  errors: {m['errors']}",
             f"accuracy: {_f(m['accuracy'])}  brier: {_f(m['brier'])}  ece (10 bins): {_f(m['ece'])}"]
    if m.get("confusion"):
        classes = m["classes"]
        width = max(len(c) for c in [*classes, CORNER])
        lines += ["", "confusion (rows: label, columns: predicted)",
                  "  ".join([f"{CORNER:<{width}}", *(f"{c:>{max(len(c), 3)}}" for c in classes)])]
        for label in classes:
            row = m["confusion"][label]
            lines.append("  ".join([f"{label:<{width}}", *(f"{row[c]:>{max(len(c), 3)}}" for c in classes)]))
    if m.get("reliability"):
        lines += ["", "reliability", "bin        n  mean_p_top  accuracy"]
        for r in m["reliability"]:
            if r["n"]:
                lines.append(f"{r['bin']:<9}{r['n']:>3}  {_f(r['mean_p_top']):>10}  {_f(r['accuracy']):>8}")
    if m.get("thresholds"):
        lines += ["", "threshold  coverage  accuracy    n"]
        for r in m["thresholds"]:
            lines.append(f"{r['threshold']:>9.2f}  {r['coverage']:>8.3f}  {_f(r['accuracy']):>8}  {r['n']:>3}")
    return "\n".join(lines)
