"""Verification by a regulator / auditor (whole ledger) and by an applicant (own receipt).

``verify_ledger`` runs a configurable subset of checks so that the evaluation can ablate
each TEXL component:

    hash       recompute every record hash from its body
    chain      body.seq == position and body.prev_hash == previous hash
    sig        Ed25519 signature of every record hash under the lender's public key
    anchor     recompute each epoch's Merkle root and compare with the witness checkpoint
    receipts   compare receipts presented by applicants with the ledger content
    additivity base + sum(phi) == score within rounding tolerance
    replay     deterministically recompute score and attributions from model + input
"""

from __future__ import annotations

from typing import Callable, Iterable

from . import canonical, merkle
from .ledger import (
    GENESIS,
    additivity_residual,
    additivity_tolerance,
    checkpoint_hash,
    input_commitment,
    record_hash,
    verify_sig,
)

ALL_CHECKS = ("hash", "chain", "sig", "anchor", "receipts", "additivity", "replay")


def verify_ledger(records: list[dict], public_key, *, checks: Iterable[str] = ALL_CHECKS,
                  witness_checkpoints: list[dict] | None = None,
                  receipts: list[dict] | None = None,
                  replayer: Callable[[dict], dict | None] | None = None,
                  n_features: int = 20, replay_tol_units: int = 1) -> list[dict]:
    checks = set(checks)
    findings: list[dict] = []
    tol = additivity_tolerance(n_features)

    def flag(kind, seq, detail=""):
        findings.append({"check": kind, "seq": seq, "detail": detail})

    prev = GENESIS
    for i, rec in enumerate(records):
        body = rec["body"]
        if "hash" in checks and record_hash(body) != rec["hash"]:
            flag("hash", i, "stored hash does not match body")
        if "chain" in checks:
            if body.get("seq") != i:
                flag("chain", i, f"sequence number {body.get('seq')} at position {i}")
            if body.get("prev_hash") != prev:
                flag("chain", i, "prev_hash does not link to previous record")
        if "sig" in checks and not verify_sig(public_key, rec["hash"], rec["sig"]):
            flag("sig", i, "invalid signature")
        if "additivity" in checks and additivity_residual(body) > tol:
            flag("additivity", i, f"residual {additivity_residual(body)} units > {tol}")
        if "replay" in checks and replayer is not None:
            expected = replayer(body)
            if expected is None:
                flag("replay", i, "input cannot be opened / model artefact missing")
            else:
                if expected["model_fp"] != body["model_fp"]:
                    flag("replay", i, "model fingerprint differs from audited artefact")
                if expected["cfg_digest"] != body["explainer_cfg_digest"]:
                    flag("replay", i, "explainer configuration differs")
                if abs(expected["score"] - body["score"]) > replay_tol_units:
                    flag("replay", i, "replayed score differs")
                diff = max(abs(expected["attributions"][k] - body["attributions"].get(k, 10**12))
                           for k in expected["attributions"])
                if diff > replay_tol_units:
                    flag("replay", i, f"replayed attribution differs by {diff} units")
                if expected["decision"] != body["decision"]:
                    flag("replay", i, "replayed decision differs")
        prev = rec["hash"]

    if "anchor" in checks and witness_checkpoints:
        prev_cp = GENESIS
        for cp in witness_checkpoints:
            b = cp["body"]
            if checkpoint_hash(b) != cp["hash"] or not verify_sig(public_key, cp["hash"], cp["sig"]):
                flag("anchor", b["first_seq"], "checkpoint signature/hash invalid")
            if b["prev_checkpoint"] != prev_cp:
                flag("anchor", b["first_seq"], "checkpoint chain broken")
            prev_cp = cp["hash"]
            seg = records[b["first_seq"]: b["first_seq"] + b["tree_size"]]
            if len(seg) != b["tree_size"]:
                flag("anchor", b["first_seq"], "records covered by checkpoint are missing")
                continue
            root = merkle.mth([bytes.fromhex(r["hash"]) for r in seg]).hex()
            if root != b["root"]:
                flag("anchor", b["first_seq"], "Merkle root differs from published checkpoint")

    if "receipts" in checks and receipts:
        for rc in receipts:
            seq = rc["record"]["body"]["seq"]
            # A receipt is evidence only if it carries the lender's valid signature.
            if not verify_sig(public_key, rc["record"]["hash"], rc["record"]["sig"]):
                continue
            if seq >= len(records) or records[seq]["hash"] != rc["record"]["hash"]:
                flag("receipts", seq, "ledger disagrees with signed applicant receipt")
    return findings


def verify_receipt(receipt: dict, public_key, witness_checkpoints: list[dict],
                   x_fixed: list[int] | None = None) -> dict:
    """Applicant-side verification of a single receipt; needs no access to other records."""
    rec = receipt["record"]
    body = rec["body"]
    out = {
        "record_hash_ok": record_hash(body) == rec["hash"],
        "signature_ok": verify_sig(public_key, rec["hash"], rec["sig"]),
        "additivity_ok": additivity_residual(body) <= additivity_tolerance(len(body["attributions"])),
        "commitment_ok": None,
        "inclusion_ok": None,
        "checkpoint_published": None,
    }
    xf = x_fixed if x_fixed is not None else receipt["x_fixed"]
    out["commitment_ok"] = input_commitment(bytes.fromhex(receipt["salt"]), xf) == body["input_commitment"]
    if receipt.get("checkpoint"):
        cp = receipt["checkpoint"]
        b = cp["body"]
        idx = body["seq"] - b["first_seq"]
        out["inclusion_ok"] = merkle.verify_inclusion(
            bytes.fromhex(rec["hash"]), idx, b["tree_size"],
            [bytes.fromhex(p) for p in receipt["proof"]], bytes.fromhex(b["root"]))
        out["checkpoint_published"] = any(w["hash"] == cp["hash"] for w in witness_checkpoints)
    out["valid"] = all(v for v in out.values() if v is not None)
    return out


class Replayer:
    """Regulator-side deterministic replay.

    The regulator holds the audited model artefact (whose fingerprint it recomputes) and
    obtains (x, salt) for an input commitment from the lender's input store, checks that the
    commitment opens, then recomputes score and attributions with the configured explainer.
    """

    def __init__(self, model_fp: str, explainer, input_store: dict, threshold: float,
                 cache: dict | None = None):
        self.model_fp = model_fp
        self.explainer = explainer
        self.input_store = input_store  # commitment -> (salt bytes, encoded x)
        self.threshold = threshold
        self.cache = cache if cache is not None else {}

    def __call__(self, body: dict) -> dict | None:
        c = body["input_commitment"]
        if c in self.cache:
            return self.cache[c]
        if c not in self.input_store:
            return None
        salt, x_enc = self.input_store[c]
        x_fixed = canonical.fixed_vector(x_enc)
        if input_commitment(salt, x_fixed) != c:
            return None
        score, phi = self.explainer.explain(x_enc)
        res = {
            "model_fp": self.model_fp,
            "cfg_digest": self.explainer.config_digest,
            "score": canonical.to_fixed(score),
            "attributions": {n: canonical.to_fixed(v) for n, v in zip(self.explainer.names, phi)},
            "decision": "REJECT" if score >= self.threshold else "APPROVE",
        }
        self.cache[c] = res
        return res
