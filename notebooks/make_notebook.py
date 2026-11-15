"""Generate notebooks/TEXL_PoC.ipynb (executed afterwards by run_all.sh via nbconvert)."""

from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()
C = []


def md(s):
    C.append(nbf.v4.new_markdown_cell(s.strip()))


def code(s):
    C.append(nbf.v4.new_code_cell(s.strip()))


md("""
# TEXL - Tamper-Evident eXplanation Ledger: Proof-of-Concept Notebook

**AML Lab (CSE2512P) - Track 1: Patent Design - Team: Smooth operators - IILM University, Gurugram**

This notebook is the proof of concept (PoC) for the invention disclosed in the report. It shows, step by step,
how every claim of the claims set is realised in working code:

| Claim | What it covers | Section below |
|---|---|---|
| 1 (independent) | seeded model-agnostic explanation, committed input, canonical record, hash chain, signature, receipt | 3-5 |
| 2 | additivity (local-accuracy) gate before a record is written | 6 |
| 3 | Merkle-sealed epochs, external witness, inclusion proof in the receipt | 5 |
| 4 | deterministic replay verification of score and explanation | 8 |
| 5 | fixed-point canonical serialisation | 9 |
| 6 | adverse-action reasons cryptographically bound to the logged explanation | 4 |

Data: UCI Statlog (German Credit Data), CC BY 4.0, DOI 10.24432/C5NC77. All random seeds are fixed.
""")

code("""
import sys, json, copy, hashlib
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "src"))
import numpy as np, pandas as pd
from texl import canonical, data, models
from texl.explain import PermutationShapley
from texl.ledger import Ledger, demo_signing_key, ConsistencyError, additivity_residual
from texl.verify import verify_ledger, verify_receipt, Replayer
from texl.attacks import resign_from
pd.set_option("display.width", 140)
SEED = 42
""")

md("## 1. Data and leakage-free split (70 / 15 / 15, stratified, seed 42)")
code("""
X, y = data.load()
print("rows:", len(X), " features:", X.shape[1], " bad-credit rate:", round(y.mean(), 3))
print("SHA-256 of german.data:", hashlib.sha256(data.RAW_FILE.read_bytes()).hexdigest())
X_tr, y_tr, X_va, y_va, X_te, y_te = data.split(X, y, seed=SEED)
print("train/val/test:", len(X_tr), len(X_va), len(X_te))
X.head()
""")

md("""
## 2. Credit model (any black box works - here Gradient Boosting)
Pre-processing (scaling, one-hot) is fitted **inside** the pipeline on the training split only. The decision threshold
minimises the Statlog cost matrix (approving a bad applicant costs 5, rejecting a good one costs 1) on the validation split.
""")
code("""
model = models.make_pipeline("gbm", SEED).fit(X_tr, y_tr)
thr = models.choose_threshold(y_va, model.predict_proba(X_va)[:, 1])
print("cost-optimal threshold on validation:", thr)
print("test metrics:", {k: round(v, 3) for k, v in models.evaluate(y_te, model.predict_proba(X_te)[:, 1], thr).items()})
model_fp = models.model_fingerprint(model)
print("model fingerprint F(f):", model_fp)
""")

md("""
## 3. Seeded, model-agnostic permutation-Shapley explainer (Claim 1c)
The explainer only calls `f(x) = P(bad | x)`. Its configuration (seed, permutations, background set) is hashed into a
**configuration digest**; the background set is bound by its own digest, so it cannot be swapped silently.
""")
code("""
codec = data.RawCodec(X_tr)
rng = np.random.default_rng(SEED)
background = codec.encode(X_tr.iloc[rng.choice(len(X_tr), 32, replace=False)])
f = lambda Z: model.predict_proba(codec.decode(Z))[:, 1]
explainer = PermutationShapley(f, background, data.FEATURES, n_permutations=16, seed=2026)
print(json.dumps({k: v for k, v in explainer.config.items() if k != "features"}, indent=1))
print("configuration digest:", explainer.config_digest)
""")

md("## 4. One explained, logged decision (Claims 1 and 6)")
code("""
sk = demo_signing_key()           # deterministic demo key - a real lender would use an HSM
ledger = Ledger(sk, model_fp, explainer.config_digest, data.FEATURES, thr, epoch_size=32)
Xenc = codec.encode(X_te)
salts = [np.random.default_rng(1000 + i).bytes(16) for i in range(len(Xenc))]  # demo salts (use os.urandom in production)
input_store = {}
rec0 = ledger.decide(Xenc[0], explainer, salt=salts[0])
input_store[rec0["body"]["input_commitment"]] = (salts[0], Xenc[0])
b = rec0["body"]
print("decision:", b["decision"], "  P(bad) =", b["score"] / 1e6, "  reasons:", b["reasons"])
print("additivity residual (units of 1e-6):", additivity_residual(b))
print(json.dumps(rec0, indent=1)[:1500], "...")
""")

md("## 5. Ledger for the whole test set, epoch sealing and applicant receipts (Claims 1g and 3)")
code("""
for i in range(1, len(Xenc)):
    r = ledger.decide(Xenc[i], explainer, salt=salts[i])
    input_store[r["body"]["input_commitment"]] = (salts[i], Xenc[i])
ledger.seal_epoch()
cps = ledger.witness.checkpoints
print(len(ledger.records), "records,", len(cps), "checkpoints published to the external witness")
print("first checkpoint:", json.dumps(cps[0]["body"], indent=1))
rc = ledger.receipts[5]
print("receipt for seq 5 -> inclusion proof length:", len(rc["proof"]))
print("applicant-side verification:", verify_receipt(rc, ledger.public_key, cps, canonical.fixed_vector(Xenc[5])))
""")

md("## 6. Additivity gate rejects an inconsistent explanation (Claim 2)")
code("""
demo = Ledger(sk, model_fp, explainer.config_digest, data.FEATURES, thr)
score, phi = explainer.explain(Xenc[1])
xf = canonical.fixed_vector(Xenc[1])
body = demo.build_body(xf, salts[1], score, phi, explainer.base_value)
body["attributions"]["personal_status"] = 0       # try to hide a protected attribute
try:
    demo.append(body, salts[1], xf)
except ConsistencyError as e:
    print("BLOCKED by gate:", e)
""")

md("## 7. Regulator verification of the honest ledger - no false alarms")
code("""
replayer = Replayer(model_fp, explainer, input_store, thr)
findings = verify_ledger(ledger.records, ledger.public_key, witness_checkpoints=cps,
                         receipts=list(ledger.receipts.values())[:8], replayer=replayer)
print("findings on honest ledger:", findings)
""")

md("""
## 8. Tampering demonstrations (Claims 3 and 4)
(a) An **insider** flips a decision and re-signs the whole tail: the hash chain and signatures look valid, but the
anchored Merkle checkpoint exposes the rewrite.  (b) An insider **fairwashes** an explanation *at logging time*,
moving the protected-attribute contribution to another feature so that additivity still holds: only deterministic
replay detects it.
""")
code("""
recs = copy.deepcopy(ledger.records)
recs[10]["body"]["decision"] = "APPROVE" if recs[10]["body"]["decision"] == "REJECT" else "REJECT"
resign_from(recs, 10, sk)
print("chain+signature checks:", verify_ledger(recs, ledger.public_key, checks=["hash", "chain", "sig"]))
print("anchor check:", verify_ledger(recs, ledger.public_key, checks=["anchor"], witness_checkpoints=cps)[:2])
""")
code("""
t = int(np.argmax([abs(sum(r["body"]["attributions"][p] for p in data.PROTECTED)) for r in ledger.records]))
recs = copy.deepcopy(ledger.records)
att = recs[t]["body"]["attributions"]
moved = sum(att[p] for p in data.PROTECTED)
for p in data.PROTECTED: att[p] = 0
att["checking_status"] += moved                     # sum preserved -> additivity gate passes
resign_from(recs, t, sk)                            # done at birth: receipts/checkpoints would agree
no_replay = ["hash", "chain", "sig", "additivity"]
print("without replay:", verify_ledger(recs, ledger.public_key, checks=no_replay))
print("with replay   :", [f for f in verify_ledger(recs, ledger.public_key, checks=["replay"], replayer=replayer)])
""")

md("## 9. Why fixed-point canonicalisation is needed (Claim 5)")
code("""
s1, p1 = explainer.explain(Xenc[3])
s2, p2 = explainer.explain(Xenc[3], reverse_accumulation=True)   # same maths, different float summation order
print("max |difference| between float runs:", np.max(np.abs(p1 - p2)))
print("raw float64 JSON hashes equal? ", hashlib.sha256(canonical.naive_float_bytes(p1.tolist())).hexdigest()
      == hashlib.sha256(canonical.naive_float_bytes(p2.tolist())).hexdigest())
print("fixed-point vectors equal?     ", canonical.fixed_vector(p1) == canonical.fixed_vector(p2))
""")

md("## 10. Full evaluation results (produced by `scripts/run_experiments.py`)")
code("""
res = json.loads((ROOT / "results" / "results.json").read_text())
det = pd.DataFrame(res["tamper"]["detection_pct"]).T
det.insert(0, "attack", [res["tamper"]["attacks"][a] for a in det.index])
det
""")
md("""
Insider deletion, reordering and truncation can only succeed in the **unsealed tail** (records not yet covered by a
published checkpoint). The sealing-window experiment re-runs attacks A3–A6 with smaller epochs:
""")
code("""
pd.read_csv(ROOT / "results" / "tables" / "sealing_window.csv")
""")
code("""
pd.DataFrame({k: {m: round(v[0], 3) for m, v in res["models"][k].items()} for k in ["logreg", "rf", "gbm"]})
""")
code("""
pd.DataFrame(res["overhead"]).T[["predict_ms", "explain_ms", "ledger_append_ms", "verify_per_record_ms",
                                 "receipt_verify_ms", "record_bytes", "honest_findings"]]
""")

nb["cells"] = C
nb["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
out = Path(__file__).with_name("TEXL_PoC.ipynb")
nbf.write(nb, out)
print("wrote", out)
