"""Unit tests for the TEXL proof of concept.  Run:  python -m pytest -q"""

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from texl import canonical, merkle  # noqa: E402
from texl.attacks import resign_from  # noqa: E402
from texl.explain import PermutationShapley  # noqa: E402
from texl.ledger import ConsistencyError, Ledger, demo_signing_key  # noqa: E402
from texl.verify import verify_ledger, verify_receipt  # noqa: E402

FEATS = [f"x{j}" for j in range(5)]
W = np.array([0.3, -0.2, 0.5, 0.0, 0.1])


def f(Z):  # small non-linear black box with an interaction term
    z = Z @ W + 0.2 * Z[:, 0] * Z[:, 2]
    return 1 / (1 + np.exp(-z))


@pytest.fixture(scope="module")
def setup():
    rng = np.random.default_rng(0)
    bg = rng.normal(size=(8, 5))
    ex = PermutationShapley(f, bg, FEATS, n_permutations=8, seed=1)
    sk = demo_signing_key()
    led = Ledger(sk, "fp", ex.config_digest, FEATS, threshold=0.5, epoch_size=4)
    X = rng.normal(size=(10, 5))
    inputs = {}
    for i, x in enumerate(X):
        salt = bytes([i]) * 16
        rec = led.decide(x, ex, salt=salt)
        inputs[rec["body"]["input_commitment"]] = (salt, x)
    led.seal_epoch()
    return ex, sk, led, X, inputs


# ---------------------------------------------------------------------------- canonical
def test_canonical_rejects_floats():
    with pytest.raises(TypeError):
        canonical.canonical_bytes({"a": 0.1})


def test_canonical_key_order_independent():
    assert canonical.canonical_bytes({"b": 1, "a": 2}) == canonical.canonical_bytes({"a": 2, "b": 1})


def test_fixed_point_absorbs_last_bit_noise():
    v = 0.123456789
    assert canonical.to_fixed(v) == canonical.to_fixed(v + 1e-15)


# ---------------------------------------------------------------------------- merkle
@pytest.mark.parametrize("n", [1, 2, 3, 5, 7, 8, 13, 32, 33])
def test_merkle_inclusion_all_leaves(n):
    leaves = [bytes([i]) * 32 for i in range(n)]
    root = merkle.mth(leaves)
    for m in range(n):
        p = merkle.inclusion_proof(m, leaves)
        assert merkle.verify_inclusion(leaves[m], m, n, p, root)
        assert not merkle.verify_inclusion(b"\xff" * 32, m, n, p, root)


# ---------------------------------------------------------------------------- explainer
def test_efficiency_exact(setup):
    ex, *_ , X, _ = setup
    for x in X:
        s, phi = ex.explain(x)
        assert abs(ex.base_value + phi.sum() - s) < 1e-12


def test_replay_is_deterministic(setup):
    ex, *_ , X, _ = setup
    s1, p1 = ex.explain(X[0])
    ex2 = PermutationShapley(f, ex.B, FEATS, n_permutations=8, seed=1)
    s2, p2 = ex2.explain(X[0])
    assert s1 == s2 and np.array_equal(p1, p2)
    assert ex.config_digest == ex2.config_digest


def test_background_bound_in_config(setup):
    ex = setup[0]
    other = PermutationShapley(f, ex.B + 1.0, FEATS, n_permutations=8, seed=1)
    assert other.config_digest != ex.config_digest


# ---------------------------------------------------------------------------- ledger
def test_honest_ledger_verifies(setup):
    ex, sk, led, X, _ = setup
    assert verify_ledger(led.records, led.public_key, checks=["hash", "chain", "sig", "anchor", "additivity"],
                         witness_checkpoints=led.witness.checkpoints, n_features=5) == []


def test_receipts_verify(setup):
    ex, sk, led, X, _ = setup
    for seq, rc in led.receipts.items():
        r = verify_receipt(rc, led.public_key, led.witness.checkpoints, canonical.fixed_vector(X[seq]))
        assert r["valid"], r


def test_wrong_input_does_not_open_commitment(setup):
    ex, sk, led, X, _ = setup
    r = verify_receipt(led.receipts[0], led.public_key, led.witness.checkpoints, canonical.fixed_vector(X[1]))
    assert r["commitment_ok"] is False


def test_gate_blocks_inconsistent_explanation(setup):
    ex, sk, led, X, _ = setup
    l2 = Ledger(sk, "fp", ex.config_digest, FEATS, threshold=0.5)
    s, phi = ex.explain(X[0])
    xf = canonical.fixed_vector(X[0])
    body = l2.build_body(xf, b"s" * 16, s, phi, ex.base_value)
    body["attributions"]["x0"] += 10_000
    with pytest.raises(ConsistencyError):
        l2.append(body, b"s" * 16, xf)


def test_insider_rewrite_caught_by_anchor_not_by_chain(setup):
    ex, sk, led, X, _ = setup
    recs = copy.deepcopy(led.records)
    recs[1]["body"]["decision"] = "APPROVE" if recs[1]["body"]["decision"] == "REJECT" else "REJECT"
    resign_from(recs, 1, sk)
    assert verify_ledger(recs, led.public_key, checks=["hash", "chain", "sig"], n_features=5) == []
    found = verify_ledger(recs, led.public_key, checks=["anchor"], witness_checkpoints=led.witness.checkpoints,
                          n_features=5)
    assert any(f["check"] == "anchor" for f in found)
