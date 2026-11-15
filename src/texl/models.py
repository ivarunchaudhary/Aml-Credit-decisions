"""Leakage-free preprocessing, model zoo, cost-optimal threshold and model fingerprint."""

from __future__ import annotations

import hashlib
import pickle

import numpy as np
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import canonical
from .data import CATEGORICAL, NUMERIC

# Statlog cost matrix: approving a bad applicant (false negative for class "bad") costs 5,
# rejecting a good applicant (false positive) costs 1.
COST_FN = 5.0
COST_FP = 1.0


def make_pipeline(kind: str, seed: int) -> Pipeline:
    # Preprocessing lives *inside* the pipeline, so scaler means / one-hot vocabularies are
    # learned from the training split only (no validation/test leakage).
    pre = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
    ])
    if kind == "logreg":
        clf = LogisticRegression(C=1.0, max_iter=2000, random_state=seed)
    elif kind == "rf":
        clf = RandomForestClassifier(n_estimators=300, min_samples_leaf=3, n_jobs=1, random_state=seed)
    elif kind == "gbm":
        clf = GradientBoostingClassifier(n_estimators=150, learning_rate=0.05, max_depth=3,
                                         subsample=0.8, random_state=seed)
    else:
        raise ValueError(kind)
    return Pipeline([("pre", pre), ("clf", clf)])


MODEL_NAMES = {"logreg": "Logistic Regression", "rf": "Random Forest", "gbm": "Gradient Boosting"}


def expected_cost(y_true, p_bad, threshold) -> float:
    """Average misclassification cost per applicant; REJECT when P(bad) >= threshold."""
    reject = p_bad >= threshold
    fn = np.sum((~reject) & (y_true == 1))
    fp = np.sum(reject & (y_true == 0))
    return float((COST_FN * fn + COST_FP * fp) / len(y_true))


def choose_threshold(y_val, p_val) -> float:
    """Pick the threshold that minimises expected cost on the *validation* split."""
    grid = np.round(np.arange(0.05, 0.951, 0.01), 2)
    costs = [expected_cost(y_val, p_val, t) for t in grid]
    return float(grid[int(np.argmin(costs))])


def evaluate(y, p, threshold) -> dict:
    reject = p >= threshold
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "accuracy": float(np.mean(reject.astype(int) == y)),
        "cost": expected_cost(y, p, threshold),
        "reject_rate": float(np.mean(reject)),
    }


def model_fingerprint(model) -> str:
    """SHA-256 over the serialised fitted pipeline plus library versions.

    Binds every logged decision to the exact model artefact that produced it.  A verifier
    holding the artefact recomputes the fingerprint before replaying (Claim 5).
    """
    meta = {"sklearn": sklearn.__version__, "numpy": np.__version__}
    blob = pickle.dumps(model, protocol=4)
    return hashlib.sha256(canonical.TAG_MODEL + canonical.canonical_bytes(meta) + blob).hexdigest()
