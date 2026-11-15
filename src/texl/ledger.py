"""TEXL ledger: explained decision records, hash chain, signatures, epochs and receipts.

Per decision i the ledger stores

    body_i = { seq, ts, model_fp, explainer_cfg_digest, input_commitment,
               score, threshold, decision, base_value, attributions, reasons, prev_hash }
    h_i    = SHA-256( TAG_RECORD || C(body_i) ),        body_i.prev_hash = h_{i-1}
    sig_i  = Ed25519_sign( sk, h_i )

where C() is the fixed-point canonical encoding.  Every ``epoch_size`` records the ledger
seals an epoch: it computes the RFC 6962 Merkle root over (h_first .. h_last), signs a
checkpoint and publishes it to an external *witness* (regulator inbox, transparency log,
public bulletin) which the operator cannot rewrite.  Each applicant receives a *receipt*:
their signed record, the salt that opens their input commitment and - once the epoch is
sealed - a Merkle inclusion proof against the published checkpoint.
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import os
from dataclasses import dataclass, field

import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

from . import canonical, merkle
from .explain import top_reasons

GENESIS = "00" * 32


class ConsistencyError(RuntimeError):
    """Raised by the additivity gate: the explanation does not reproduce the score."""


# ---------------------------------------------------------------------------- keys
def demo_signing_key(seed: bytes = b"TEXL demo key - NOT FOR PRODUCTION") -> Ed25519PrivateKey:
    """Deterministic key so that experiments are reproducible. Real deployments use an HSM."""
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(seed).digest())


def public_key_bytes(pk: Ed25519PublicKey) -> bytes:
    return pk.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def sign(sk: Ed25519PrivateKey, hex_hash: str) -> str:
    return sk.sign(bytes.fromhex(hex_hash)).hex()


def verify_sig(pk: Ed25519PublicKey, hex_hash: str, sig_hex: str) -> bool:
    try:
        pk.verify(bytes.fromhex(sig_hex), bytes.fromhex(hex_hash))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------- helpers
def input_commitment(salt: bytes, x_fixed: list[int]) -> str:
    """Hiding + binding commitment to the applicant's raw attributes (Claim 2).

    The ledger never stores personal data, only this salted hash.  The salt is handed to
    the applicant (in the receipt) and kept in the lender's access-controlled input store,
    so only someone holding both x and the salt can open the commitment.
    """
    return hashlib.sha256(canonical.TAG_INPUT + salt + canonical.canonical_bytes(x_fixed)).hexdigest()


def record_hash(body: dict) -> str:
    return canonical.digest(canonical.TAG_RECORD, body)


def additivity_residual(body: dict) -> int:
    """|base + sum(phi) - score| in fixed-point units."""
    total = body["base_value"] + sum(body["attributions"].values())
    return abs(total - body["score"])


def additivity_tolerance(n_features: int) -> int:
    # each of (n_features + 2) quantised terms carries at most 0.5 unit of rounding error
    return n_features // 2 + 2


def checkpoint_hash(cp_body: dict) -> str:
    return canonical.digest(canonical.TAG_CHECKPOINT, cp_body)


class Witness:
    """External append-only store of signed checkpoints (outside the operator's control)."""

    def __init__(self):
        self._items: list[dict] = []

    def publish(self, checkpoint: dict) -> None:
        self._items.append(copy.deepcopy(checkpoint))

    @property
    def checkpoints(self) -> list[dict]:
        return copy.deepcopy(self._items)


@dataclass
class Ledger:
    signing_key: Ed25519PrivateKey
    model_fp: str
    explainer_cfg_digest: str
    feature_names: list[str]
    threshold: float
    epoch_size: int = 32
    witness: Witness = field(default_factory=Witness)
    start_time: _dt.datetime = field(
        default_factory=lambda: _dt.datetime(2026, 11, 1, 9, 0, 0, tzinfo=_dt.timezone.utc))
    logical_clock: bool = True  # deterministic timestamps for reproducible experiments
    gate: bool = True           # additivity gate on (Claim 3)

    def __post_init__(self):
        self.records: list[dict] = []
        self.receipts: dict[int, dict] = {}
        self._sealed_upto = 0
        self._last_cp_hash = GENESIS

    # ------------------------------------------------------------------ properties
    @property
    def public_key(self) -> Ed25519PublicKey:
        return self.signing_key.public_key()

    @property
    def head(self) -> str:
        return self.records[-1]["hash"] if self.records else GENESIS

    def _now(self) -> str:
        if self.logical_clock:
            t = self.start_time + _dt.timedelta(seconds=len(self.records))
        else:
            t = _dt.datetime.now(_dt.timezone.utc)
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ------------------------------------------------------------------ appending
    def build_body(self, x_fixed: list[int], salt: bytes, score: float, phi: np.ndarray,
                   base_value: float) -> dict:
        decision = "REJECT" if score >= self.threshold else "APPROVE"
        attributions = {n: canonical.to_fixed(v) for n, v in zip(self.feature_names, phi)}
        return {
            "v": 1,
            "seq": len(self.records),
            "ts": self._now(),
            "model_fp": self.model_fp,
            "explainer_cfg_digest": self.explainer_cfg_digest,
            "input_commitment": input_commitment(salt, x_fixed),
            "score": canonical.to_fixed(score),
            "threshold": canonical.to_fixed(self.threshold),
            "decision": decision,
            "base_value": canonical.to_fixed(base_value),
            "attributions": attributions,
            "reasons": top_reasons(np.asarray(phi), self.feature_names, k=3),
            "prev_hash": self.head,
        }

    def append(self, body: dict, salt: bytes, x_fixed: list[int]) -> dict:
        """Gate -> hash -> sign -> append -> receipt -> (maybe) seal epoch."""
        if self.gate and additivity_residual(body) > additivity_tolerance(len(self.feature_names)):
            raise ConsistencyError(f"explanation does not reproduce score for seq {body['seq']}")
        h = record_hash(body)
        rec = {"body": body, "hash": h, "sig": sign(self.signing_key, h)}
        self.records.append(rec)
        self.receipts[body["seq"]] = {
            "record": copy.deepcopy(rec),
            "salt": salt.hex(),
            "x_fixed": list(x_fixed),
            "epoch": None, "proof": None, "checkpoint": None,
        }
        if len(self.records) - self._sealed_upto >= self.epoch_size:
            self.seal_epoch()
        return rec

    def decide(self, x_encoded: np.ndarray, explainer, salt: bytes | None = None) -> dict:
        """End-to-end: explain -> build record -> append.  Returns the new record."""
        salt = salt if salt is not None else os.urandom(16)
        score, phi = explainer.explain(x_encoded)
        x_fixed = canonical.fixed_vector(x_encoded)
        body = self.build_body(x_fixed, salt, score, phi, explainer.base_value)
        return self.append(body, salt, x_fixed)

    # ------------------------------------------------------------------ epochs
    def seal_epoch(self) -> dict | None:
        first = self._sealed_upto
        last = len(self.records)
        if last == first:
            return None
        leaves = [bytes.fromhex(r["hash"]) for r in self.records[first:last]]
        memo: dict = {}
        root = merkle.mth(leaves, memo).hex()
        epoch = len(self.witness.checkpoints)
        cp_body = {
            "epoch": epoch, "first_seq": first, "tree_size": last - first, "root": root,
            "prev_checkpoint": self._last_cp_hash, "ts": self._now(),
        }
        cp_h = checkpoint_hash(cp_body)
        cp = {"body": cp_body, "hash": cp_h, "sig": sign(self.signing_key, cp_h)}
        self.witness.publish(cp)
        self._last_cp_hash = cp_h
        for idx in range(first, last):
            proof = merkle.inclusion_proof(idx - first, leaves, memo)
            rc = self.receipts[idx]
            rc["epoch"] = epoch
            rc["proof"] = [p.hex() for p in proof]
            rc["checkpoint"] = copy.deepcopy(cp)
        self._sealed_upto = last
        return cp

    # ------------------------------------------------------------------ export
    def storage_bytes_per_record(self) -> float:
        sizes = [len(canonical.canonical_bytes(r["body"])) + 64 + 64 for r in self.records]
        return float(np.mean(sizes))
