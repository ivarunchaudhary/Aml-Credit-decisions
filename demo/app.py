"""TEXL live demo for the presentation and viva.

Run:  .venv/bin/streamlit run demo/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from demo.core import (  # noqa: E402
    ATTACKS,
    attack_report,
    build_demo,
    check_receipt,
    decide,
    load_results,
    new_session_ledger,
)

# Human-readable labels for the two coded attributes the presenter can edit (UCI documentation).
LABELS = {
    "checking_status": {"A11": "< 0 DM", "A12": "0 – 200 DM", "A13": ">= 200 DM / salary",
                        "A14": "no checking account"},
    "savings_status": {"A61": "< 100 DM", "A62": "100 – 500 DM", "A63": "500 – 1000 DM",
                       "A64": ">= 1000 DM", "A65": "unknown / no savings"},
}

st.set_page_config(page_title="TEXL demo", page_icon="🔐", layout="wide")
st.title("TEXL – Tamper-Evident Explanation Ledger")
st.caption("Explained, signed and auditable ML credit decisions · Smooth operators · "
           "Applied ML Lab (CSE2512P), IILM University")
st.warning("Demo signing key derived from a fixed string – never use it in production.", icon="⚠️")


@st.cache_resource(show_spinner="Training the model and building the ledger (first start only)…")
def get_demo():
    return build_demo()


demo = get_demo()
if "ledger" not in st.session_state:
    st.session_state["ledger"] = new_session_ledger(demo)
ledger = st.session_state["ledger"]

decide_tab, ledger_tab, tamper_tab, results_tab = st.tabs(
    ["Decide", "Ledger", "Tamper & verify", "Results"])

# --------------------------------------------------------------------------- Decide
with decide_tab:
    left, right = st.columns([1, 2], gap="large")
    with left:
        st.subheader("Applicant")
        idx = st.selectbox("Test applicant", range(len(demo.X_te)), format_func=lambda i: f"Applicant #{i}")
        row = demo.X_te.iloc[[idx]].copy()
        row["duration"] = st.number_input("Duration (months)", 1.0, 120.0, float(row["duration"].iloc[0]),
                                          step=1.0, key=f"dur{idx}")
        row["credit_amount"] = st.number_input("Credit amount (DM)", 100.0, 1_000_000.0,
                                               float(row["credit_amount"].iloc[0]), step=500.0, key=f"amt{idx}")
        row["age"] = st.number_input("Age (years)", 18.0, 100.0, float(row["age"].iloc[0]), step=1.0,
                                     key=f"age{idx}")
        for col, title in [("checking_status", "Checking account"), ("savings_status", "Savings")]:
            opts = demo.categories[col]
            row[col] = st.selectbox(title, opts, index=opts.index(row[col].iloc[0]),
                                    format_func=lambda v, c=col: LABELS[c].get(v, v), key=f"{col}{idx}")
        if st.button("Decide and record", type="primary", width="stretch"):
            st.session_state["last"] = (row, decide(demo, ledger, row))

    with right:
        last_row, out = st.session_state.get("last", (None, None))
        if out is not None and not last_row.equals(row):  # inputs changed since the last decision
            out = None
        if out is None:
            st.info("Pick an applicant and press **Decide and record**.")
        else:
            rejected = out["decision"] == "REJECT"
            c1, c2, c3 = st.columns(3)
            c1.metric("Decision", ("❌ " if rejected else "✅ ") + out["decision"])
            c2.metric("Risk P(bad)", f"{out['score']:.6f}")
            c3.metric("Reject if risk ≥", f"{out['threshold']:.2f}")

            st.subheader("Why? Contribution of each attribute to the risk")
            phi = pd.DataFrame({"attribute": list(out["phi"]), "contribution": list(out["phi"].values())})
            phi["effect"] = phi["contribution"].map(lambda v: "raises risk" if v > 0 else "lowers risk")
            chart = alt.Chart(phi).mark_bar().encode(
                x=alt.X("contribution:Q", title="change in P(bad)"),
                y=alt.Y("attribute:N", sort="-x", title=None),
                color=alt.Color("effect:N", scale=alt.Scale(domain=["raises risk", "lowers risk"],
                                                            range=["#d9534f", "#5cb85c"])),
                tooltip=["attribute", alt.Tooltip("contribution:Q", format="+.4f")],
            ).properties(height=440)
            st.altair_chart(chart, width="stretch")
            st.caption(f"Base rate {out['base_value']:.3f} + sum of contributions = "
                       f"{out['base_value'] + sum(out['phi'].values()):.3f} = score (additivity gate).")
            if out["reasons"]:
                st.markdown("**Top reasons for risk:** " + ", ".join(f"`{r}`" for r in out["reasons"]))

            seq = out["record"]["body"]["seq"]
            st.markdown(f"Written to the ledger as record **#{seq}**, hash `{out['record']['hash'][:16]}…`, "
                        "signed with Ed25519.")
            with st.expander("Signed ledger record"):
                st.json(out["record"])
            with st.expander("Applicant receipt"):
                st.json(out["receipt"], expanded=False)
            if st.button("Verify my receipt"):
                res = check_receipt(demo, ledger, out["receipt"])
                names = {"record_hash_ok": "Record hash matches", "signature_ok": "Lender signature valid",
                         "additivity_ok": "Explanation adds up to the score",
                         "commitment_ok": "My input commitment opens",
                         "inclusion_ok": "Record is in the sealed Merkle tree",
                         "checkpoint_published": "Checkpoint is published at the witness"}
                for k, label in names.items():
                    v = res[k]
                    st.write(("✅ " if v else "❌ ") + label if v is not None
                             else f"⏳ {label} – epoch not sealed yet")
                (st.success if res["valid"] else st.error)("Receipt valid" if res["valid"] else "Receipt INVALID")

# --------------------------------------------------------------------------- Ledger
with ledger_tab:
    cps = ledger.witness.checkpoints
    sealed = {}
    for cp in cps:
        b = cp["body"]
        sealed.update({s: b["epoch"] for s in range(b["first_seq"], b["first_seq"] + b["tree_size"])})
    m1, m2, m3 = st.columns(3)
    m1.metric("Records", len(ledger.records))
    m2.metric("Sealed epochs (checkpoints)", len(cps))
    m3.metric("Unsealed tail", len(ledger.records) - len(sealed))
    st.dataframe(pd.DataFrame([{
        "seq": r["body"]["seq"],
        "decision": r["body"]["decision"],
        "risk": r["body"]["score"] / 1e6,
        "hash": r["hash"][:16] + "…",
        "prev_hash": r["body"]["prev_hash"][:16] + "…",
        "status": f"sealed in epoch {sealed[i]}" if i in sealed else "unsealed tail",
    } for i, r in enumerate(ledger.records)]).iloc[::-1], hide_index=True, width="stretch")
    st.subheader("Checkpoints published to the external witness")
    st.dataframe(pd.DataFrame([{
        "epoch": cp["body"]["epoch"], "records": f"#{cp['body']['first_seq']} – "
        f"#{cp['body']['first_seq'] + cp['body']['tree_size'] - 1}",
        "Merkle root": cp["body"]["root"][:24] + "…", "signature": cp["sig"][:24] + "…",
    } for cp in cps]), hide_index=True, width="stretch")
    if st.button("Reset ledger"):
        st.session_state["ledger"] = new_session_ledger(demo)
        st.session_state.pop("last", None)
        st.rerun()

# --------------------------------------------------------------------------- Tamper
with tamper_tab:
    st.markdown("Each attack runs on a copy of the preloaded ledger "
                f"({len(demo.ctx.honest.records)} decisions: "
                f"{len(demo.ctx.honest.witness.checkpoints)} sealed epochs + an unsealed tail). "
                "An **outsider** cannot sign; an **insider** holds the signing key but cannot rewrite "
                "published checkpoints or receipts already handed out.")
    a1, a2 = st.columns([3, 1])
    attack = a1.selectbox("Attack", list(ATTACKS), format_func=lambda a: f"{a} – {ATTACKS[a]}")
    seed = a2.number_input("Random seed", 0, 10_000, 0)
    if st.button("Attack, then verify", type="primary"):
        st.session_state["report"] = attack_report(demo, attack, int(seed))
    rep = st.session_state.get("report")
    if rep:
        st.markdown(f"**{rep['attack']} – {rep['description']}** · target record **#{rep['target']}**")
        levels = pd.DataFrame([{"verifier": lv["level"], "result": "🚨 caught" if lv["caught"] else "— missed",
                                "findings": len(lv["findings"])} for lv in rep["levels"]])
        st.dataframe(levels, hide_index=True, width="stretch")
        first = next((lv for lv in rep["levels"] if lv["caught"]), None)
        if first is None:
            st.error("No verifier level caught this run. Try another seed – see the Results tab "
                     "for detection rates over 200 runs.")
        else:
            st.success(f"First caught by **{first['level']}**.")
            st.dataframe(pd.DataFrame(first["findings"]).rename(columns={"seq": "record"}),
                         hide_index=True, width="stretch")

# --------------------------------------------------------------------------- Results
with results_tab:
    st.subheader("Detection rate over 200 runs per attack (%)")
    table = load_results(ROOT)
    if table is None:
        st.info("results/tables/tamper_detection.csv not found – run scripts/run_experiments.py.")
    else:
        st.dataframe(table, hide_index=True, width="stretch")
    figs = sorted((ROOT / "results" / "figures").glob("*.png"))
    if not figs:
        st.info("No figures in results/figures/.")
    for fig in figs:
        st.image(str(fig), caption=fig.stem.replace("_", " "), width="stretch")
