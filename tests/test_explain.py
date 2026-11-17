"""Unit tests for ``texl.explain.evaluate_seed_stability``.  Run:  python -m pytest -q"""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from texl.explain import evaluate_seed_stability  # noqa: E402

D = 5
SEEDS = [0, 1, 2, 3, 4]
W_LIN = np.array([0.5, -0.4, 0.3, -0.2, 0.1])  # distinct magnitudes -> no rank ties


def linear(Z):
    """Linear black box: permutation Shapley is exact, phi_j = w_j (x_j - mean_b b_j)."""
    return 0.5 + Z @ W_LIN


def nonlinear(Z):
    """Logistic model with an interaction term, so attributions depend on the permutations."""
    z = Z @ W_LIN + 0.8 * Z[:, 0] * Z[:, 2] - 0.6 * Z[:, 1] * Z[:, 3]
    return 1 / (1 + np.exp(-z))


@pytest.fixture(scope="module")
def data():
    rng = np.random.default_rng(42)
    B = rng.normal(size=(12, D))
    # Offsets bounded away from zero so no attribution sits near the sign boundary.
    offsets = rng.uniform(0.5, 1.5, size=(8, D)) * rng.choice([-1.0, 1.0], size=(8, D))
    X = B.mean(axis=0) + offsets
    return X, B


# ---------------------------------------------------------------- (1) stability / determinism
def test_summary_keys_and_metadata(data):
    X, B = data
    out = evaluate_seed_stability(linear, X, B, SEEDS, P=8)
    assert set(out) == {"mean_spearman", "mean_top3_overlap", "seeds", "n_permutations",
                        "n_instances", "n_pairs", "k"}
    assert out["seeds"] == SEEDS
    assert out["n_permutations"] == 8
    assert out["n_instances"] == X.shape[0]
    assert out["n_pairs"] == len(SEEDS) * (len(SEEDS) - 1) // 2
    assert out["k"] == 3


def test_linear_model_is_perfectly_seed_stable(data):
    X, B = data
    out = evaluate_seed_stability(linear, X, B, SEEDS, P=8)
    assert out["mean_spearman"] == pytest.approx(1.0)
    assert out["mean_top3_overlap"] == pytest.approx(1.0)


@pytest.mark.parametrize("model", [linear, nonlinear], ids=["linear", "nonlinear"])
def test_repeated_calls_are_bit_for_bit_identical(data, model):
    X, B = data
    a = evaluate_seed_stability(model, X, B, SEEDS, P=4)
    b = evaluate_seed_stability(model, X, B, SEEDS, P=4)
    assert a == b


def test_nonlinear_metrics_in_valid_range(data):
    X, B = data
    out = evaluate_seed_stability(nonlinear, X, B, SEEDS, P=4)
    assert -1.0 <= out["mean_spearman"] <= 1.0
    assert 0.0 <= out["mean_top3_overlap"] <= 1.0


def test_seed_order_does_not_change_summary(data):
    X, B = data
    a = evaluate_seed_stability(nonlinear, X, B, [0, 1, 2], P=4)
    b = evaluate_seed_stability(nonlinear, X, B, [2, 0, 1], P=4)
    assert a["mean_spearman"] == pytest.approx(b["mean_spearman"])
    assert a["mean_top3_overlap"] == pytest.approx(b["mean_top3_overlap"])


def test_predict_proba_estimator_matches_callable(data):
    X, B = data

    class Estimator:
        def predict_proba(self, Z):
            p = nonlinear(Z)
            return np.column_stack([1 - p, p])

    assert (evaluate_seed_stability(Estimator(), X, B, SEEDS, P=4)
            == evaluate_seed_stability(nonlinear, X, B, SEEDS, P=4))


def test_single_1d_instance_is_accepted(data):
    X, B = data
    out = evaluate_seed_stability(linear, X[0], B, [0, 1], P=4)
    assert out["n_instances"] == 1
    assert out["n_pairs"] == 1
    assert out["mean_spearman"] == pytest.approx(1.0)


def test_custom_k_is_reported(data):
    X, B = data
    out = evaluate_seed_stability(linear, X, B, SEEDS, P=4, k=2)
    assert out["k"] == 2
    assert out["mean_top3_overlap"] == pytest.approx(1.0)


def test_rounding_makes_tied_features_exactly_rank_stable(data):
    _, B = data
    # phi_j = -|w_j| * offset_j = [-0.25, -0.30, -0.30, -0.25, -0.15]: two exact ties that
    # float summation noise breaks differently depending on the permutation order (seed).
    X = np.tile(B.mean(axis=0) + np.linspace(0.5, 1.5, D), (4, 1))
    model = lambda Z: 0.5 - Z @ np.abs(W_LIN)  # noqa: E731
    raw = evaluate_seed_stability(model, X, B, SEEDS, P=4, round_decimals=None)
    rounded = evaluate_seed_stability(model, X, B, SEEDS, P=4)  # default round_decimals=12
    assert raw["mean_spearman"] < 1.0          # noise flips tied ranks between seeds
    assert rounded["mean_spearman"] == 1.0     # ties restored -> identical ranks, exactly
    assert rounded["mean_top3_overlap"] == raw["mean_top3_overlap"]  # overlap is unaffected


# ---------------------------------------------------------------- (2) zero / constant attributions
def test_constant_model_gives_nan_spearman_and_full_overlap(data):
    X, B = data
    out = evaluate_seed_stability(lambda Z: np.full(len(Z), 0.3), X, B, SEEDS, P=4)
    # All attributions are exactly zero: rank correlation is undefined for every pair...
    assert math.isnan(out["mean_spearman"])
    # ...and no feature raises risk under any seed, which counts as full agreement.
    assert out["mean_top3_overlap"] == 1.0


def test_no_risk_raising_features_counts_as_agreement(data):
    _, B = data
    # Every feature lowers risk: x_j > mean(B_j) and the model decreases in every feature.
    # A uniform +1 offset makes phi_j = -|w_j|, which are distinct (no rank ties).
    X = np.tile(B.mean(axis=0) + 1.0, (4, 1))
    out = evaluate_seed_stability(lambda Z: 0.5 - Z @ np.abs(W_LIN), X, B, SEEDS, P=4)
    assert out["mean_top3_overlap"] == 1.0
    assert out["mean_spearman"] == pytest.approx(1.0)  # attributions vary, so rho is defined


def test_x_equal_to_background_gives_zero_attributions():
    B = np.tile(np.arange(D, dtype=float), (3, 1))  # identical background rows
    X = B[:2].copy()                                  # applicants identical to background
    out = evaluate_seed_stability(nonlinear, X, B, [0, 1, 2], P=4)
    assert math.isnan(out["mean_spearman"])
    assert out["mean_top3_overlap"] == 1.0


# ---------------------------------------------------------------- (3) validation errors
@pytest.mark.parametrize("seeds", [[1, 1], [0, 1, 1], [3, 3, 3]], ids=["pair", "partial", "all"])
def test_duplicate_seeds_rejected(data, seeds):
    X, B = data
    with pytest.raises(ValueError, match="distinct"):
        evaluate_seed_stability(linear, X, B, seeds, P=4)


@pytest.mark.parametrize("seeds", [[], [0]], ids=["empty", "single"])
def test_fewer_than_two_seeds_rejected(data, seeds):
    X, B = data
    with pytest.raises(ValueError, match="at least two seeds"):
        evaluate_seed_stability(linear, X, B, seeds, P=4)


@pytest.mark.parametrize("P", [1, 3, 7])
def test_odd_permutation_count_rejected(data, P):
    X, B = data
    with pytest.raises(ValueError, match="even"):
        evaluate_seed_stability(linear, X, B, SEEDS, P=P)


def test_feature_dimension_mismatch_rejected(data):
    X, B = data
    with pytest.raises(ValueError, match="features"):
        evaluate_seed_stability(linear, X[:, :-1], B, SEEDS, P=4)


@pytest.mark.parametrize("model", [object(), None, 42, "model"], ids=["object", "none", "int", "str"])
def test_invalid_model_rejected(data, model):
    X, B = data
    with pytest.raises(TypeError, match="predict_proba"):
        evaluate_seed_stability(model, X, B, SEEDS, P=4)
