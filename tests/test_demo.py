"""Tests for the live demo (demo/core.py).  Run:  python -m pytest -q tests/test_demo.py"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from demo.core import (  # noqa: E402
    attack_report,
    build_demo,
    check_receipt,
    decide,
    load_results,
    new_session_ledger,
)
from texl.attacks import ATTACKS  # noqa: E402
from texl.verify import verify_ledger  # noqa: E402


@pytest.fixture(scope="module")
def demo():
    return build_demo(n_ledger=40)  # one sealed epoch of 32 + an unsealed tail of 8


def _clean(demo, led):
    return verify_ledger(led.records, demo.pk, witness_checkpoints=led.witness.checkpoints,
                         replayer=demo.replayer, n_features=20) == []


def test_build_demo_honest_ledger_is_clean(demo):
    led = demo.ctx.honest
    assert len(led.records) == 40 and len(led.witness.checkpoints) == 1
    assert _clean(demo, led)


def test_decide_returns_consistent_decision(demo):
    led = new_session_ledger(demo)
    row = demo.X_te.iloc[[0]]
    out = decide(demo, led, row)
    assert out["decision"] in {"APPROVE", "REJECT"}
    assert (out["decision"] == "REJECT") == (out["score"] >= out["threshold"])
    assert abs(out["base_value"] + sum(out["phi"].values()) - out["score"]) < 1e-9
    assert out["record"]["body"]["seq"] == 40
    assert out["score"] == pytest.approx(demo.S["f"](demo.S["codec"].encode(row))[0])
    assert check_receipt(demo, led, out["receipt"])["valid"]


def test_decide_handles_out_of_range_inputs(demo):
    row = demo.X_te.iloc[[0]].copy()
    row["credit_amount"], row["age"] = 1_000_000.0, 18.0
    assert decide(demo, new_session_ledger(demo), row)["decision"] in {"APPROVE", "REJECT"}


def test_session_decisions_seal_next_epoch(demo):
    led = new_session_ledger(demo)
    outs = [decide(demo, led, demo.X_te.iloc[[i]]) for i in range(24)]  # 40 + 24 = 64
    assert len(led.witness.checkpoints) == 2
    rc = led.receipts[outs[0]["record"]["body"]["seq"]]
    assert rc["proof"] is not None
    assert check_receipt(demo, led, rc)["valid"]


def test_attack_report_levels(demo):
    a1 = {lv["level"]: lv["caught"] for lv in attack_report(demo, "A1")["levels"]}
    assert not a1["V0 Plain log"] and a1["V1 +Record hash"]
    a9 = {lv["level"]: lv["caught"] for lv in attack_report(demo, "A9")["levels"]}
    assert a9["V7 TEXL (+Replay)"] and not a9["V6 +Additivity gate"]


def test_attack_does_not_touch_honest_ledger(demo):
    for a in ATTACKS:
        attack_report(demo, a)
    assert _clean(demo, demo.ctx.honest)


def test_attack_report_is_deterministic(demo):
    assert attack_report(demo, "A3", seed=5) == attack_report(demo, "A3", seed=5)


def test_load_results_missing(tmp_path):
    assert load_results(tmp_path) is None


def test_app_starts_without_error():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "demo" / "app.py"), default_timeout=300).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Decide", "Ledger", "Tamper & verify", "Results"]


def _app():
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(ROOT / "demo" / "app.py"), default_timeout=300).run()


def _click(at, label):
    next(b for b in at.button if b.label == label).click().run()


def test_shown_risk_agrees_with_decision():
    at = _app()
    next(s for s in at.selectbox if s.label == "Test applicant").set_value(71).run()  # P(bad) 0.099994
    _click(at, "Decide and record")
    m = {x.label: x.value for x in at.metric}
    rejected = "REJECT" in m["Decision"]
    assert rejected == (float(m["Risk P(bad)"]) >= float(m["Reject if risk ≥"]))


def test_result_hidden_after_switching_applicant():
    at = _app()
    _click(at, "Decide and record")
    assert any(x.label == "Decision" for x in at.metric)
    next(s for s in at.selectbox if s.label == "Test applicant").set_value(1).run()
    assert not any(x.label == "Decision" for x in at.metric)
