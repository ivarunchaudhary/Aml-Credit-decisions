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
