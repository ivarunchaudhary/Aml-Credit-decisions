"""Logic behind the live demo (demo/app.py), kept free of Streamlit so it can be unit-tested.

The demo rebuilds exactly the system used for the paper - same split, models, threshold,
explainer configuration, salts and verifier levels - by importing them from
``scripts/run_experiments.py``, so every number on screen matches the report.  The ledger is
preloaded with the first ``n_ledger`` test applicants (the last, partly filled epoch is left
unsealed, as in the tamper experiment); attacks always run against a copy of it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_experiments as rx  # noqa: E402
from texl import canonical, data  # noqa: E402
from texl.attacks import ATTACKS, Context, Decision, run_attack  # noqa: E402
from texl.explain import PermutationShapley, top_reasons  # noqa: E402
from texl.ledger import Ledger, demo_signing_key  # noqa: E402
from texl.verify import Replayer, verify_ledger, verify_receipt  # noqa: E402


@dataclass
class Demo:
    S: dict                     # primary system from run_experiments.build_system
    ctx: Context                # honest preloaded ledger + attack context
    replayer: Replayer
    pk: object                  # lender's Ed25519 public key
    X_te: pd.DataFrame          # raw test applicants
    categories: dict[str, list[str]]


def build_demo(n_ledger: int = 72) -> Demo:
    """Mirror of ``e4_tamper`` restricted to the first ``n_ledger`` test applicants."""
    X, y = data.load()
    S = rx.build_system(X, y, rx.PRIMARY)
    A = rx.build_system(X, y, rx.ALT_MODEL)
    sk = demo_signing_key()
    X_te = S["X_te"].iloc[:n_ledger]
    Xenc = S["codec"].encode(X_te)
    st = rx.salts(len(Xenc))
    alt_expl = PermutationShapley(lambda Z: A["model"].predict_proba(S["codec"].decode(Z))[:, 1],
                                  S["bg"], data.FEATURES, n_permutations=rx.N_PERM, seed=2026)
    decisions = []
    for i, xe in enumerate(Xenc):
        s, p = S["expl"].explain(xe)
        sa, pa = alt_expl.explain(xe)
        decisions.append(Decision(xe, canonical.fixed_vector(xe), st[i], s, p, sa, pa))

    def make_ledger(gate=True):
        return Ledger(sk, S["fp"], S["expl"].config_digest, data.FEATURES, S["thr"],
                      epoch_size=rx.EPOCH, gate=gate)

    ctx = Context(decisions, make_ledger, S["expl"].base_value, alt_expl.base_value,
                  data.FEATURES, data.PROTECTED, sk)
    input_store = {r["body"]["input_commitment"]: (d.salt, d.x_enc)
                   for r, d in zip(ctx.honest.records, decisions)}
    replayer = Replayer(S["fp"], S["expl"], input_store, S["thr"])
    for r in ctx.honest.records:  # warm the replay cache so verification is instant on stage
        replayer(r["body"])
    return Demo(S, ctx, replayer, sk.public_key(), S["X_te"], S["codec"].categories)


def new_session_ledger(demo: Demo) -> Ledger:
    """A fresh copy of the honest preloaded ledger (re-hashed, not re-explained)."""
    return demo.ctx.build()


def decide(demo: Demo, ledger: Ledger, row: pd.DataFrame) -> dict:
    """Explain, gate, record, sign and receipt one raw applicant row."""
    x = demo.S["codec"].encode(row)[0]
    score, phi = demo.S["expl"].explain(x)
    x_fixed = canonical.fixed_vector(x)
    salt = np.random.default_rng().bytes(16)
    rec = ledger.append(ledger.build_body(x_fixed, salt, score, phi, demo.S["expl"].base_value),
                        salt, x_fixed)
    return {
        "score": score,
        "threshold": demo.S["thr"],
        "decision": rec["body"]["decision"],
        "base_value": demo.S["expl"].base_value,
        "phi": dict(zip(data.FEATURES, map(float, phi))),
        "reasons": top_reasons(phi, data.FEATURES, k=3),
        "record": rec,
        "receipt": ledger.receipts[rec["body"]["seq"]],  # live: gains a proof when sealed
    }


def check_receipt(demo: Demo, ledger: Ledger, receipt: dict) -> dict:
    return verify_receipt(receipt, demo.pk, ledger.witness.checkpoints)


def attack_report(demo: Demo, attack: str, seed: int = 0) -> dict:
    """Run one attack on a copy of the honest ledger and verify it at every level V0-V7."""
    recs, wit, rcpts, target = run_attack(attack, demo.ctx, np.random.default_rng(seed))
    k = max(1, round(rx.RECEIPT_FRACTION * len(demo.ctx.decisions)))
    pick = np.random.default_rng(seed).choice(sorted(rcpts), size=min(k, len(rcpts)), replace=False)
    presented = [rcpts[i] for i in pick]  # the same applicants come forward at every level
    levels = []
    for name, checks in rx.VERIFIER_LEVELS:
        found = verify_ledger(recs, demo.pk, checks=checks, witness_checkpoints=wit,
                              receipts=presented, replayer=demo.replayer,
                              n_features=len(data.FEATURES))
        levels.append({"level": name, "caught": bool(found), "findings": found})
    return {"attack": attack, "description": ATTACKS[attack], "target": int(target), "levels": levels}


def load_results(root: Path) -> pd.DataFrame | None:
    path = Path(root) / "results" / "tables" / "tamper_detection.csv"
    return pd.read_csv(path) if path.exists() else None
