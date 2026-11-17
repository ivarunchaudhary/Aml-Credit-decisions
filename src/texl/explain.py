"""Deterministic, model-agnostic permutation-Shapley explainer.

The explainer only needs black-box access to f(x) = P(bad | x), so it works for any model.
For a fixed seed it draws P feature permutations (half of them antithetic, i.e. reversed)
and a fixed background reference set B of m training rows.  For each permutation pi and
background row b it walks from b to x one feature at a time and credits each feature with
the change in f.  Because every walk telescopes, the attributions satisfy *efficiency*
(local accuracy) exactly:

        base + sum_j phi_j = f(x),   base = mean_b f(b)

which TEXL uses as a cheap consistency gate (Claim 3).  Because the permutations and B are
fixed by the configuration, anyone holding the model, x and the configuration can replay
the explanation bit-for-bit (Claim 5).  The background set is bound by digest so an
operator cannot silently swap it to steer explanations.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

import numpy as np

from . import canonical


class PermutationShapley:
    method = "perm-shapley-antithetic/v1"

    def __init__(self, predict_fn, background: np.ndarray, feature_names, n_permutations: int = 16,
                 seed: int = 2026):
        if n_permutations % 2:
            raise ValueError("n_permutations must be even (antithetic pairs)")
        self.f = predict_fn
        self.B = np.asarray(background, dtype=float)
        self.names = list(feature_names)
        self.P = int(n_permutations)
        self.seed = int(seed)
        self.d = self.B.shape[1]
        rng = np.random.default_rng(self.seed)
        half = [rng.permutation(self.d) for _ in range(self.P // 2)]
        self.perms = np.array(half + [p[::-1] for p in half])
        # The base value only depends on B, compute once.
        self._fB = np.asarray(self.f(self.B), dtype=float)
        self.base_value = float(self._fB.mean())

    # ------------------------------------------------------------------ configuration
    @property
    def background_digest(self) -> str:
        return canonical.digest(canonical.TAG_BACKGROUND,
                                [canonical.fixed_vector(r) for r in self.B])

    @property
    def config(self) -> dict:
        return {
            "method": self.method,
            "n_permutations": self.P,
            "seed": self.seed,
            "background_size": int(self.B.shape[0]),
            "background_digest": self.background_digest,
            "features": self.names,
            "output": "P(bad)",
            "scale": canonical.SCALE,
        }

    @property
    def config_digest(self) -> str:
        return canonical.digest(canonical.TAG_CONFIG, self.config)

    # ------------------------------------------------------------------ explanation
    def explain(self, x: np.ndarray, reverse_accumulation: bool = False) -> tuple[float, np.ndarray]:
        """Return (f(x), phi).  ``reverse_accumulation`` only changes float summation order
        (used to demonstrate why fixed-point canonicalisation is needed)."""
        x = np.asarray(x, dtype=float).ravel()
        m, d, P = self.B.shape[0], self.d, self.P
        # masks[p, k, j] = 1 if feature j already switched to x after k steps of permutation p
        masks = np.zeros((P, d + 1, d), dtype=bool)
        for p, perm in enumerate(self.perms):
            for k in range(1, d + 1):
                masks[p, k] = masks[p, k - 1]
                masks[p, k, perm[k - 1]] = True
        # rows[p, b, k, :] = where(mask, x, B[b])
        rows = np.where(masks[:, None, :, :], x[None, None, None, :], self.B[None, :, None, :])
        fz = np.asarray(self.f(rows.reshape(-1, d)), dtype=float).reshape(P, m, d + 1)
        deltas = np.diff(fz, axis=2)  # (P, m, d): contribution of the k-th switched feature
        contrib = np.zeros((P, m, d))
        for p, perm in enumerate(self.perms):
            contrib[p][:, perm] = deltas[p]
        flat = contrib.reshape(P * m, d)
        if reverse_accumulation:
            phi = np.zeros(d)
            for row in flat[::-1]:
                phi += row
            phi /= P * m
        else:
            phi = flat.mean(axis=0)
        fx = float(fz[0, 0, d])
        return fx, phi


def top_reasons(phi: np.ndarray, names, k: int = 3) -> list[str]:
    """Adverse-action style reasons: the k attributes that increased risk the most."""
    order = np.argsort(-np.asarray(phi), kind="stable")
    return [names[i] for i in order[:k] if phi[i] > 0]


def evaluate_seed_stability(
    model: Callable[[np.ndarray], np.ndarray] | Any,
    X: np.ndarray,
    B: np.ndarray,
    seeds: Sequence[int] = (0, 1, 2, 3, 4),
    P: int = 16,
    k: int = 3,
    round_decimals: int | None = 12,
) -> dict[str, Any]:
    """Measure how sensitive permutation-Shapley attributions are to the permutation seed.

    For every seed a :class:`PermutationShapley` explainer is built with the same background
    set ``B`` and permutation count ``P``, and every applicant in ``X`` is explained.  Then, for
    each applicant and each unordered pair of seeds, two agreement scores are computed and
    averaged over all (applicant, seed-pair) combinations:

    * **Spearman rank correlation** between the two attribution vectors.  The vectors are
      first rounded to ``round_decimals`` places so that features with tied attributions get
      tied ranks instead of an order decided by floating-point summation noise (which varies
      with the permutation order, and therefore with the seed).  Pairs where either rounded
      vector is constant (rank correlation undefined) are skipped.
    * **Top-k adverse-action overlap**: the reasons produced by :func:`top_reasons` (the ``k``
      features that *increased* risk the most, positive attributions only) are compared as
      sets, scoring ``|A & B| / max(|A|, |B|)``.  If both sets are empty (no feature raised
      risk under either seed) the pair counts as full agreement (1.0).

    Args:
        model: Either a callable ``f(Z) -> P(bad | Z)`` taking a 2-D array and returning a 1-D
            array of probabilities, or an estimator exposing ``predict_proba`` (column 1 is
            used as ``P(bad)``).
        X: Applicant instances to explain, shape ``(n, d)`` (a single 1-D row is accepted).
        B: Background reference set, shape ``(m, d)``.
        seeds: Permutation seeds to compare; at least two distinct values are required.
        P: Number of permutations per explainer; must be even (antithetic pairs).
        k: Number of adverse-action reasons to compare (default 3).
        round_decimals: Decimal places to round attributions to before the Spearman
            computation only (default 12, well above float64 noise of ~1e-16 but below any
            meaningful difference in P(bad)).  ``None`` disables rounding.  The top-``k``
            overlap always uses the unrounded attributions.

    Returns:
        A dictionary with keys:

        * ``mean_spearman`` (float): mean pairwise Spearman correlation (``nan`` if every pair
          was undefined).
        * ``mean_top3_overlap`` (float): mean pairwise top-``k`` adverse-action overlap in [0, 1].
        * ``seeds`` (list[int]), ``n_permutations`` (int), ``n_instances`` (int),
          ``n_pairs`` (int, seed pairs per instance), ``k`` (int).

    Raises:
        ValueError: if fewer than two seeds are given or any seed repeats, ``P`` is odd, or
            the feature dimensions of ``X`` and ``B`` differ.
        TypeError: if ``model`` is neither callable nor exposes ``predict_proba``.
    """
    from itertools import combinations

    from scipy.stats import spearmanr

    seeds = [int(s) for s in seeds]
    if len(seeds) < 2 or len(set(seeds)) != len(seeds):
        raise ValueError("evaluate_seed_stability needs at least two seeds, all distinct")
    X = np.atleast_2d(np.asarray(X, dtype=float))
    B = np.asarray(B, dtype=float)
    if X.shape[1] != B.shape[1]:
        raise ValueError(f"X has {X.shape[1]} features but B has {B.shape[1]}")

    if callable(model):
        predict_fn = model
    elif hasattr(model, "predict_proba"):
        predict_fn = lambda Z: model.predict_proba(Z)[:, 1]  # noqa: E731
    else:
        raise TypeError("model must be callable or expose predict_proba")

    names = [f"x{j}" for j in range(B.shape[1])]
    # phis[s, i, :] = attribution of applicant i under seed s
    phis = np.array([
        [PermutationShapley(predict_fn, B, names, n_permutations=P, seed=s).explain(x)[1] for x in X]
        for s in seeds
    ])

    rhos: list[float] = []
    overlaps: list[float] = []
    pairs = list(combinations(range(len(seeds)), 2))
    for i in range(X.shape[0]):
        reasons = [set(top_reasons(phis[s, i], names, k=k)) for s in range(len(seeds))]
        for a, b in pairs:
            pa, pb = phis[a, i], phis[b, i]
            if round_decimals is not None:
                pa, pb = np.round(pa, round_decimals), np.round(pb, round_decimals)
            if np.ptp(pa) > 0 and np.ptp(pb) > 0:
                rhos.append(float(spearmanr(pa, pb).statistic))
            ra, rb = reasons[a], reasons[b]
            denom = max(len(ra), len(rb))
            overlaps.append(1.0 if denom == 0 else len(ra & rb) / denom)

    return {
        "mean_spearman": float(np.mean(rhos)) if rhos else float("nan"),
        "mean_top3_overlap": float(np.mean(overlaps)),
        "seeds": seeds,
        "n_permutations": int(P),
        "n_instances": int(X.shape[0]),
        "n_pairs": len(pairs),
        "k": int(k),
    }
