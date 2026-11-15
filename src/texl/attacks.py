"""Tamper-attack simulator used in the evaluation (Section 5 of the report).

Threat model
------------
* Outsider: can read/write the ledger store but does NOT hold the lender's signing key.
* Insider : the lender (or a rogue employee) - holds the signing key and controls the
  decision software, but cannot rewrite checkpoints already published to the external
  witness, nor the signed receipts already handed to applicants.

Post-hoc attacks modify a ledger after it was written.  At-birth attacks falsify a record at
decision time (before any receipt or checkpoint exists), which no hash chain can detect.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from . import canonical
from .ledger import Ledger, record_hash, sign
from .explain import top_reasons


# ---------------------------------------------------------------------------- re-linking
def rehash_from(records: list[dict], start: int) -> None:
    """Outsider: recompute links + hashes from ``start``; old signatures stay (now invalid)."""
    prev = records[start - 1]["hash"] if start > 0 else "00" * 32
    for i in range(start, len(records)):
        records[i]["body"]["seq"] = i
        records[i]["body"]["prev_hash"] = prev
        records[i]["hash"] = record_hash(records[i]["body"])
        prev = records[i]["hash"]


def resign_from(records: list[dict], start: int, sk) -> None:
    """Insider: recompute links + hashes AND re-sign from ``start``."""
    rehash_from(records, start)
    for i in range(start, len(records)):
        records[i]["sig"] = sign(sk, records[i]["hash"])


# ---------------------------------------------------------------------------- context
@dataclass
class Decision:
    x_enc: np.ndarray
    x_fixed: list[int]
    salt: bytes
    score: float
    phi: np.ndarray
    alt_score: float      # score of an undisclosed substitute model (attack A9)
    alt_phi: np.ndarray


@dataclass
class Context:
    decisions: list[Decision]
    make_ledger: Callable[[bool], Ledger]   # gate flag -> fresh empty ledger
    base_value: float
    alt_base_value: float
    feature_names: list[str]
    protected: list[str]
    sk: object
    honest: Ledger = field(init=False)

    def __post_init__(self):
        self.honest = self.build()

    def build(self, hook: Callable[[dict, int], None] | None = None, gate: bool = True) -> Ledger:
        led = self.make_ledger(gate)
        for i, d in enumerate(self.decisions):
            body = led.build_body(d.x_fixed, d.salt, d.score, d.phi, self.base_value)
            if hook is not None:
                hook(body, i)
            led.append(body, d.salt, d.x_fixed)
        # The last, partially filled epoch is deliberately left unsealed: this is the
        # realistic window in which an insider rewrite is not yet covered by a checkpoint.
        return led

    # protected attribution mass of decision i (fixed-point units)
    def protected_mass(self, i: int) -> int:
        b = self.honest.records[i]["body"]["attributions"]
        return sum(b[p] for p in self.protected)


ATTACKS = {
    "A1": "Edit one attribution, no re-hash (outsider)",
    "A2": "Flip decision, re-hash tail, no key (outsider)",
    "A3": "Flip decision, re-hash + re-sign tail (insider)",
    "A4": "Delete a record, re-link + re-sign (insider)",
    "A5": "Swap two adjacent records, re-sign (insider)",
    "A6": "Truncate the last 5 records (insider)",
    "A7": "Fairwash at birth: zero protected attributions (insider)",
    "A8": "Fairwash at birth: move protected mass, sum kept (insider)",
    "A9": "Undisclosed model substitution at birth (insider)",
}


def run_attack(name: str, ctx: Context, rng: np.random.Generator):
    """Return (records, witness_checkpoints, receipts_dict, target) after the attack."""
    honest = ctx.honest
    n = len(honest.records)
    recs = copy.deepcopy(honest.records)
    wit = honest.witness.checkpoints
    rcpts = copy.deepcopy(honest.receipts)

    if name == "A1":
        t = int(rng.integers(n))
        f = ctx.feature_names[int(rng.integers(len(ctx.feature_names)))]
        recs[t]["body"]["attributions"][f] += int(rng.choice([-1, 1])) * int(rng.integers(5_000, 50_000))
        return recs, wit, rcpts, t

    if name in ("A2", "A3"):
        t = int(rng.integers(n))
        b = recs[t]["body"]
        b["decision"] = "APPROVE" if b["decision"] == "REJECT" else "REJECT"
        (rehash_from(recs, t) if name == "A2" else resign_from(recs, t, ctx.sk))
        return recs, wit, rcpts, t

    if name == "A4":
        t = int(rng.integers(n))
        del recs[t]
        if t < len(recs):
            resign_from(recs, t, ctx.sk)
        return recs, wit, rcpts, t

    if name == "A5":
        t = int(rng.integers(n - 1))
        recs[t], recs[t + 1] = recs[t + 1], recs[t]
        resign_from(recs, t, ctx.sk)
        return recs, wit, rcpts, t

    if name == "A6":
        t = n - 5
        del recs[t:]
        return recs, wit, rcpts, t

    # ------------------------------------------------------------ at-birth attacks
    if name in ("A7", "A8"):
        tol = 50  # only fairwash records where the protected attributes really matter
        cands = [i for i in range(n) if abs(ctx.protected_mass(i)) > tol]
        t = int(rng.choice(cands))

        def hook(body, i):
            if i != t:
                return
            att = body["attributions"]
            moved = sum(att[p] for p in ctx.protected)
            for p in ctx.protected:
                att[p] = 0
            if name == "A8":
                others = [k for k in ctx.feature_names if k not in ctx.protected]
                k_star = max(others, key=lambda k: abs(att[k]))
                att[k_star] += moved  # efficiency preserved, protected reliance hidden
            phi = np.array([att[k] for k in ctx.feature_names], dtype=float)
            body["reasons"] = top_reasons(phi, ctx.feature_names, k=3)

        led = ctx.build(hook=hook, gate=False)  # insider bypasses the gate
        return led.records, led.witness.checkpoints, led.receipts, t

    if name == "A9":
        t = int(rng.integers(n))
        d = ctx.decisions[t]

        def hook(body, i):
            if i != t:
                return
            body["score"] = canonical.to_fixed(d.alt_score)
            body["base_value"] = canonical.to_fixed(ctx.alt_base_value)
            body["attributions"] = {k: canonical.to_fixed(v) for k, v in zip(ctx.feature_names, d.alt_phi)}
            thr = canonical.from_fixed(body["threshold"])
            body["decision"] = "REJECT" if d.alt_score >= thr else "APPROVE"
            body["reasons"] = top_reasons(d.alt_phi, ctx.feature_names, k=3)

        led = ctx.build(hook=hook, gate=True)  # substitute explanation is self-consistent
        return led.records, led.witness.checkpoints, led.receipts, t

    raise KeyError(name)
