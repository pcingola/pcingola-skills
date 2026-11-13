"""Eval metrics on hand-computed examples."""
import pytest

from classify_tool.metrics import THRESHOLDS, Prediction, evaluate

P = [
    Prediction("a", "a", 0.9, {"a": 0.9, "b": 0.1}),
    Prediction("b", "a", 0.6, {"a": 0.6, "b": 0.4}),
    Prediction("b", "b", 0.7, {"a": 0.3, "b": 0.7}),
    Prediction("a", "a", 0.95, {"a": 0.95, "b": 0.05}),
]


def test_accuracy_brier_ece():
    """metrics.evaluate computes accuracy, the multi-class Brier score and ECE over 10 bins on a
    hand-computed example. Guards the formulas documented in metrics.py and docs/classify.md.
    """
    m = evaluate(P, ["a", "b"])
    assert m["accuracy"] == 0.75
    # (0.02 + 0.72 + 0.18 + 0.005) / 4
    assert m["brier"] == pytest.approx(0.23125)
    # bin 0.9-1.0: 2/4 * |1 - 0.925|; bin 0.6-0.7: 1/4 * 0.6; bin 0.7-0.8: 1/4 * 0.3
    assert m["ece"] == pytest.approx(0.0375 + 0.15 + 0.075)


def test_reliability_bins():
    """metrics.reliability puts each prediction in its p_top bin with count, mean p_top and
    accuracy. Guards bin_index and the per-bin values.
    """
    rows = {r["bin"]: r for r in evaluate(P, ["a", "b"])["reliability"] if r["n"]}
    assert set(rows) == {"0.6-0.7", "0.7-0.8", "0.9-1.0"}
    assert rows["0.9-1.0"]["n"] == 2
    assert rows["0.9-1.0"]["mean_p_top"] == pytest.approx(0.925)
    assert rows["0.6-0.7"]["accuracy"] == 0.0


def test_thresholds():
    """metrics.thresholds gives coverage, count and accuracy at each threshold 0.5 to 0.95, keeping
    p_top equal to the threshold. Guards the >= comparison and the threshold list.
    """
    rows = {r["threshold"]: r for r in evaluate(P, ["a", "b"])["thresholds"]}
    assert list(rows) == THRESHOLDS == [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
    assert (rows[0.5]["coverage"], rows[0.5]["accuracy"]) == (1.0, 0.75)
    assert (rows[0.6]["n"], rows[0.65]["n"]) == (4, 3)
    assert (rows[0.7]["n"], rows[0.7]["accuracy"]) == (3, 1.0)  # p_top 0.7 is kept at 0.7
    assert (rows[0.9]["coverage"], rows[0.95]["coverage"]) == (0.5, 0.25)


def test_confusion():
    """metrics.confusion counts label against predicted class. Guards the orientation of the
    confusion matrix (rows labels, columns predictions).
    """
    assert evaluate(P, ["a", "b"])["confusion"] == {"a": {"a": 2, "b": 0}, "b": {"a": 1, "b": 1}}


def test_binary_brier_on_p_yes():
    """metrics.evaluate with binary=True computes Brier as (p_yes - y)^2, half the two-class sum.
    Guards the yes/no Brier definition.
    """
    preds = [Prediction("true", "true", 0.8, {"true": 0.8, "false": 0.2}),
             Prediction("false", "false", 0.7, {"true": 0.3, "false": 0.7})]
    assert evaluate(preds, ["true", "false"], binary=True)["brier"] == pytest.approx((0.04 + 0.09) / 2)
    assert evaluate(preds, ["true", "false"])["brier"] == pytest.approx(0.13)


def test_failed_items_left_out():
    """metrics.evaluate leaves failed items out of the metrics and counts them in errors. Guards the
    documented handling of failed requests in eval.
    """
    m = evaluate([*P, Prediction("a", None)], ["a", "b"])
    assert (m["n"], m["errors"], m["accuracy"]) == (5, 1, 0.75)


def test_labels_only_chat_backend():
    """metrics.evaluate on predictions without probabilities gives accuracy and None for Brier, ECE
    and thresholds. Guards the chat backend's label-only eval.
    """
    m = evaluate([Prediction("a", "a"), Prediction("b", "a")], ["a", "b"])
    assert m["accuracy"] == 0.5
    assert m["brier"] is m["ece"] is m["thresholds"] is None
