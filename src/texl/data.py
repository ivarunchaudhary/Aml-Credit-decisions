"""German Credit (Statlog) data: download, load, and leakage-free stratified splits.

Source : UCI Machine Learning Repository, "Statlog (German Credit Data)", H. Hofmann, 1994.
DOI    : 10.24432/C5NC77      Licence: CC BY 4.0
Size   : 1,000 applicants, 20 attributes (7 numeric, 13 categorical), binary target.
Target : original coding 1 = good, 2 = bad.  We use y = 1 for "bad" (credit risk / default).
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

UCI_URL = "https://archive.ics.uci.edu/static/public/144/statlog+german+credit+data.zip"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RAW_FILE = DATA_DIR / "german.data"

COLUMNS = [
    "checking_status", "duration", "credit_history", "purpose", "credit_amount",
    "savings_status", "employment", "installment_commitment", "personal_status",
    "other_parties", "residence_since", "property_magnitude", "age",
    "other_payment_plans", "housing", "existing_credits", "job", "num_dependents",
    "own_telephone", "foreign_worker", "target",
]
NUMERIC = ["duration", "credit_amount", "installment_commitment", "residence_since",
           "age", "existing_credits", "num_dependents"]
CATEGORICAL = [c for c in COLUMNS[:-1] if c not in NUMERIC]
FEATURES = COLUMNS[:-1]
# Attributes that are protected or proxy-protected in most lending regulations.
PROTECTED = ["personal_status", "age", "foreign_worker"]


def download(force: bool = False) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_FILE.exists() and not force:
        return RAW_FILE
    for attempt in range(5):  # the UCI server can be slow; retry before giving up
        try:
            with urllib.request.urlopen(UCI_URL, timeout=120) as resp:
                blob = resp.read()
            break
        except OSError:
            if attempt == 4:
                raise
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        RAW_FILE.write_bytes(zf.read("german.data"))
    return RAW_FILE


def load() -> tuple[pd.DataFrame, np.ndarray]:
    path = download()
    df = pd.read_csv(path, sep=r"\s+", header=None, names=COLUMNS)
    y = (df.pop("target") == 2).astype(int).to_numpy()
    for c in CATEGORICAL:
        df[c] = df[c].astype(str)
    for c in NUMERIC:
        df[c] = df[c].astype(float)
    return df[FEATURES], y


def split(X: pd.DataFrame, y: np.ndarray, seed: int = 42):
    """70 / 15 / 15 stratified split. All statistics are later fitted on train only."""
    X_tr, X_tmp, y_tr, y_tmp = train_test_split(X, y, test_size=0.30, stratify=y, random_state=seed)
    X_va, X_te, y_va, y_te = train_test_split(X_tmp, y_tmp, test_size=0.50, stratify=y_tmp,
                                              random_state=seed)
    return (X_tr.reset_index(drop=True), y_tr, X_va.reset_index(drop=True), y_va,
            X_te.reset_index(drop=True), y_te)


class RawCodec:
    """Bijective encoding of raw applicant rows <-> numeric vectors.

    The explainer perturbs *raw* attributes (so explanations are stated in the applicant's
    own terms, e.g. "checking_status", not one-hot columns). Categorical attributes are
    encoded as an integer index into the category list learned on the training split.
    """

    def __init__(self, X_train: pd.DataFrame):
        self.categories = {c: sorted(X_train[c].unique().tolist()) for c in CATEGORICAL}

    def encode(self, X: pd.DataFrame) -> np.ndarray:
        out = np.empty((len(X), len(FEATURES)), dtype=float)
        for j, c in enumerate(FEATURES):
            if c in CATEGORICAL:
                lut = {v: i for i, v in enumerate(self.categories[c])}
                # unseen categories map to -1 and are decoded to a sentinel the model ignores
                out[:, j] = [lut.get(v, -1) for v in X[c]]
            else:
                out[:, j] = X[c].to_numpy(dtype=float)
        return out

    def decode(self, Z: np.ndarray) -> pd.DataFrame:
        cols = {}
        for j, c in enumerate(FEATURES):
            if c in CATEGORICAL:
                cats = np.asarray(self.categories[c] + ["__unseen__"], dtype=object)
                idx = Z[:, j].astype(int)
                idx = np.where(idx < 0, len(cats) - 1, idx)
                cols[c] = cats[idx]
            else:
                cols[c] = Z[:, j]
        return pd.DataFrame(cols, columns=FEATURES)
