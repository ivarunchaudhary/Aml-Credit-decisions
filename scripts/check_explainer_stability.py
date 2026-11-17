"""Check how stable permutation-Shapley explanations are across seeds, per permutation budget.

Builds the same system as ``scripts/run_experiments.py`` (split, model, codec and background set
with seed 42), then runs ``evaluate_seed_stability`` on a sample of test applicants for each
permutation budget P and prints a summary table.  Writes nothing to disk.

Usage:   python scripts/check_explainer_stability.py [--model gbm] [--n-inst 40]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from texl import data, models  # noqa: E402
from texl.explain import evaluate_seed_stability  # noqa: E402

SEED = 42                       # split / model / background seed (matches run_experiments.py)
BG_SIZE = 32                    # background set size (matches run_experiments.py)
BUDGETS = [4, 8, 16, 32, 64]
STABILITY_SEEDS = [0, 1, 2, 3, 4]


def build(kind: str, seed: int = SEED):
    """Train ``kind`` on the standard split; return (f, background, encoded test applicants)."""
    X, y = data.load()
    X_tr, y_tr, _, _, X_te, _ = data.split(X, y, seed=seed)
    model = models.make_pipeline(kind, seed).fit(X_tr, y_tr)
    codec = data.RawCodec(X_tr)
    rng = np.random.default_rng(seed)
    bg = codec.encode(X_tr.iloc[rng.choice(len(X_tr), BG_SIZE, replace=False)])

    def f(Z):
        return model.predict_proba(codec.decode(Z))[:, 1]

    return f, bg, codec.encode(X_te)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="gbm", choices=models.MODEL_NAMES)
    ap.add_argument("--n-inst", type=int, default=40, help="number of test applicants to explain")
    args = ap.parse_args()

    f, bg, X_te = build(args.model)
    X = X_te[: args.n_inst]
    print(f"model={args.model}  applicants={len(X)}  background={len(bg)}  "
          f"features={X.shape[1]}  seeds={STABILITY_SEEDS}\n")

    header = f"{'P':>4}  {'Spearman':>9}  {'Top-3 overlap':>13}  {'Time (s)':>9}  {'ms/expl':>8}"
    print(header)
    print("-" * len(header))
    n_expl = len(X) * len(STABILITY_SEEDS)
    for P in BUDGETS:
        t0 = time.perf_counter()
        r = evaluate_seed_stability(f, X, bg, STABILITY_SEEDS, P=P)
        dt = time.perf_counter() - t0
        print(f"{P:>4}  {r['mean_spearman']:>9.4f}  {r['mean_top3_overlap']:>13.4f}  "
              f"{dt:>9.2f}  {1e3 * dt / n_expl:>8.1f}")


if __name__ == "__main__":
    main()
