"""Canonical serialisation and domain-separated hashing.

Why this matters (Claim 6): a hash chain is only verifiable by a third party if every
party serialises a record to *exactly the same bytes*.  Real-valued model outputs and
feature attributions are the main threat to this, because benign recomputation (different
summation order, BLAS build, CPU) changes the last bits of a float64.  TEXL therefore
encodes every real number as a signed *integer* number of micro-units (scale 10**6) using
round-half-to-even, and serialises with sorted keys and no insignificant whitespace.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

SCALE = 10**6  # fixed-point scale: 1 unit = 1e-6 (probability space)

# Domain-separation tags so that a hash of one object type can never be confused with
# a hash of another type (e.g. a record hash re-used as an input commitment).
TAG_RECORD = b"TEXL/record/v1\x00"
TAG_INPUT = b"TEXL/input-commitment/v1\x00"
TAG_MODEL = b"TEXL/model-fingerprint/v1\x00"
TAG_BACKGROUND = b"TEXL/background/v1\x00"
TAG_CONFIG = b"TEXL/explainer-config/v1\x00"
TAG_CHECKPOINT = b"TEXL/checkpoint/v1\x00"


def to_fixed(value: float) -> int:
    """Quantise a real number to an integer number of micro-units (round half to even)."""
    return int(np.rint(float(value) * SCALE))


def from_fixed(units: int) -> float:
    return units / SCALE


def fixed_vector(values) -> list[int]:
    return [to_fixed(v) for v in np.asarray(values, dtype=float).ravel()]


def canonical_bytes(obj: Any) -> bytes:
    """Deterministic JSON encoding (sorted keys, compact, ASCII only).

    Floats are rejected on purpose: callers must convert reals with :func:`to_fixed` first,
    which is what guarantees cross-platform byte equality.
    """

    def _check(o: Any) -> None:
        if isinstance(o, float):
            raise TypeError("floats are not allowed in canonical records; use to_fixed()")
        if isinstance(o, dict):
            for k, v in o.items():
                if not isinstance(k, str):
                    raise TypeError("dict keys must be str")
                _check(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                _check(v)

    _check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def sha256_hex(tag: bytes, payload: bytes) -> str:
    return hashlib.sha256(tag + payload).hexdigest()


def digest(tag: bytes, obj: Any) -> str:
    return sha256_hex(tag, canonical_bytes(obj))


def naive_float_bytes(obj: Any) -> bytes:
    """Baseline serialisation that keeps raw float64 values (used only in the ablation)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
