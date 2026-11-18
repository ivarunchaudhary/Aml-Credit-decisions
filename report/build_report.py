"""Build the IEEE-format project report (DOCX + PDF) from results/results.json.

Usage: python report/build_report.py          -> report/Smooth_operators_Track1_TEXL_Report.docx (+ .pdf)
All numbers in the text and tables are read from results/results.json, so the report can
never drift from the code that produced the results.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ROW_HEIGHT_RULE
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import content as C  # noqa: E402
from docx_style import (bullet, caption, heading, page_number_footer, para, picture,  # noqa: E402
                        pictures_row, set_core, set_run_font, style_document, table)

R = json.loads((ROOT / "results" / "results.json").read_text())
FIG = ROOT / "results" / "figures"
OUT_DOCX = HERE / "Smooth_operators_Track1_TEXL_Report.docx"

# ----------------------------------------------------------------------------- citations
_order: list[str] = []


def cite(*keys) -> str:
    nums = []
    for k in keys:
        if k not in C.REFS:
            raise KeyError(k)
        if k not in _order:
            _order.append(k)
        nums.append(_order.index(k) + 1)
    nums = sorted(set(nums))
    # compress consecutive runs: [3]-[5]
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(f"[{nums[i]}]" if j == i else (f"[{nums[i]}], [{nums[j]}]" if j == i + 1 else f"[{nums[i]}]–[{nums[j]}]"))
        i = j + 1
    return ", ".join(out)


def pm(v, d=3):
    return f"{v[0]:.{d}f} ± {v[1]:.{d}f}"


def pct(v):
    return f"{v:.1f}" if v not in (0.0, 100.0) else f"{v:.0f}"


# ----------------------------------------------------------------------------- numbers
M = R["models"]
OV = R["overhead"]
TP = R["tamper"]
DET = TP["detection_pct"]
FA = TP["false_alarm_pct"]
STB = R["stability"]
SH = R["shap_agreement"]
DT = R["determinism"]
SC = R["scale"]
ENV = R["environment"]
DS = R["dataset"]
CFG = R["config"]
P = "gbm"
LV = list(FA.keys())
full = LV[-1]
min_full = min(DET[a][full] for a in DET)
e2e_ms = OV[P]["explain_ms"][0] + OV[P]["ledger_append_ms"][0]
scale_max = max(SC, key=lambda k: int(k))
NUM_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
WN = R["window"]                       # sealing-window sensitivity (keys: epoch size as str)
W_DEF = WN[str(CFG["epoch_size"])]
W_ONE = WN["1"]
TAIL = ["A3", "A4", "A5", "A6"]
V7 = "V7 TEXL (+Replay)"
perfect = [a for a in DET if DET[a][full] == 100.0]
imperfect = [a for a in DET if DET[a][full] < 100.0]
w1_min = min(W_ONE[a][V7] for a in TAIL)
w1_fa = W_ONE["false_alarm_V7"]


def rng_pct(vals):
    lo, hi = min(vals), max(vals)
    return f"{pct(lo)}%" if lo == hi else f"{pct(lo)}–{pct(hi)}%"


def alist(xs):
    """['A1','A2','A3','A7'] -> 'A1–A3 and A7'."""
    nums = sorted(int(a[1:]) for a in xs)
    parts, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        parts.append(f"A{nums[i]}" if i == j else (f"A{nums[i]}, A{nums[j]}" if j == i + 1 else f"A{nums[i]}–A{nums[j]}"))
        i = j + 1
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]

doc = Document()
style_document(doc)
page_number_footer(doc)
set_core(doc, C.TITLE, ", ".join(a for a, _ in C.AUTHORS), "AML Lab CSE2512P - Track 1 Patent Design",
         "explainable AI, tamper-evident logging, credit scoring")

# ============================================================================ title block
para(doc, C.TITLE, size=14, align="center", bold=True, space_after=6)
para(doc, ", ".join(f"{n} ({u})" for n, u in C.AUTHORS), size=10, align="center", space_after=1)
para(doc, f"Team: {C.TEAM}  |  Track: {C.TRACK}  |  Section / Specialisation: {C.SECTION}", size=10,
     align="center", space_after=1)
para(doc, f"IILM University, Gurugram  |  Course Coordinator: {C.COORD}", size=10, align="center", space_after=8)

# ============================================================================ abstract
para(doc, "Abstract", size=10, align="left", bold=True, space_after=2)
ABSTRACT = (
    "Lenders increasingly justify automated credit decisions with post-hoc explanations, yet nothing prevents an operator "
    "from editing a logged explanation after a complaint, or from logging a convenient explanation that the model never "
    "produced. We disclose TEXL, a tamper-evident, replay-verifiable explanation ledger. For every decision TEXL computes a "
    "seeded, model-agnostic permutation-Shapley explanation, commits to the applicant’s input with a salted hash instead "
    "of storing personal data, chains a fixed-point canonical record into an Ed25519-signed hash chain, seals epochs into "
    "Merkle checkpoints held by an external witness, and gives each applicant a verifiable receipt. A verifier can "
    "deterministically replay the score and explanation from the committed input. A proof of concept on the public German "
    f"Credit dataset with three model families ran nine tamper attacks in {TP['trials']} randomised trials each. The full "
    f"verifier detected {NUM_WORDS[len(perfect)]} attack classes in every trial with {pct(FA[full])}% false alarms, including "
    "fairwashed explanations created at logging time that hash chains and signatures alone miss. Insider deletion, "
    "reordering and truncation escaped only inside the not-yet-sealed tail of the ledger "
    f"({rng_pct([DET[a][full] for a in imperfect])} detected); sealing a checkpoint after every record closed this window "
    f"({pct(w1_min)}% detected). Ledger operations add {OV[P]['ledger_append_ms'][0]:.2f} ms per decision and receipts "
    f"verify in {OV[P]['receipt_verify_ms']:.2f} ms."
)
para(doc, ABSTRACT, size=9, italic=True, space_after=3)
para(doc, "**Keywords:** explainable AI, tamper-evident logging, credit scoring, Shapley values, Merkle tree, "
          "algorithmic accountability", size=9, align="left", space_after=6)
_ABSTRACT_WORDS = len(ABSTRACT.split())

# ============================================================================ 1 Introduction
heading(doc, "1. Introduction")
para(doc, "Credit scoring is classified as a high-risk AI use case, and regulators now require automatic event logs and "
          f"specific reasons for adverse decisions {cite('euaiact', 'regb')}. Lenders therefore attach post-hoc explanations "
          f"such as SHAP {cite('lundberg')} to each decision. However, explanations are easy to manipulate: a biased model can "
          f"be scaffolded to produce innocuous explanations {cite('slack')}, and rationalisations can hide unfair reliance on "
          f"protected attributes {cite('aivodji')}. An ordinary database log offers no protection: whoever controls it can "
          "edit, delete or back-date an explanation once an applicant disputes a rejection.")
para(doc, "**Problem statement.** Design a method that, for every automated credit decision, records the score, decision and "
          "a feature-attribution explanation such that (i) any post-hoc alteration, deletion, insertion or reordering is "
          "detected by a regulator and by the affected applicant, (ii) an explanation that was *falsified at logging time* "
          "(not produced by the declared model and explainer) is also detected, (iii) the log holds no raw personal data, "
          "and (iv) the overhead is small enough for real-time lending (measured targets are fixed in Section 3).")
para(doc, "**Contributions.**", space_after=1)
bullet(doc, "An invention disclosure with one independent and five dependent claims for TEXL, which binds a seeded "
            "model-agnostic explanation, a model fingerprint and a salted input commitment into a signed, hash-chained, "
            "Merkle-anchored record with an applicant receipt (Section 4).")
bullet(doc, "Two explanation-integrity mechanisms not found in the prior art we surveyed: an additivity gate and "
            "deterministic replay of the logged explanation, which detect falsification at logging time.")
bullet(doc, f"A prior-art search of {len(C.PRIOR_ART) - 1} patents, papers and standards with a feature comparison (Table I).")
bullet(doc, "An open, seeded proof of concept with an ablation over eight verifier configurations and nine attack "
            "classes, a sealing-window study, and latency, storage and explanation-fidelity measurements (Section 5).")
para(doc, "Section 2 reviews prior art, Section 3 formalises the problem, Section 4 describes the method and claims, "
          "Sections 5–6 report and discuss results, and Sections 7–8 cover limitations, ethics and future work.")

# ============================================================================ 2 Related work
heading(doc, "2. Related Work / Prior Art")
para(doc, f"**Explaining credit decisions.** Reason codes derived from score drivers are long established "
          f"{cite('fico_pat')}; later patents constrain neural networks to be monotonic so that adverse-action codes "
          f"can be generated {cite('equifax_pat')}, decompose model outputs relative to a baseline population "
          f"{cite('zest_decomp_pat')} and report reason codes while searching for fairer models {cite('zest_fair_pat')}. "
          f"Shapley-value attributions {cite('strumbelj', 'lundberg')} are now the default model-agnostic explanation. "
          "None of these documents protects the explanation after it is issued.")
para(doc, f"**Tamper-evident records.** Merkle’s hash-tree authentication {cite('merkle_pat')}, Haber and Stornetta’s "
          f"linked time-stamping with receipts {cite('haber_pat')}, and Schneier and Kelsey’s secure audit logs "
          f"{cite('schneier_pat', 'schneier_paper')} established hash chaining for logs. Crosby and Wallach add logarithmic "
          f"membership proofs {cite('crosby')}, and Certificate Transparency operates public Merkle logs with signed tree heads "
          f"and inclusion proofs {cite('rfc6962', 'rfc9162')}. These systems protect generic events and say nothing about "
          "whether a logged explanation is faithful to a model.")
para(doc, f"**Machine learning on ledgers and accountability.** Blockchain consensus has been patented for validating "
          f"model updates {cite('pointr_pat')}, Nassar *et al.* survey blockchain-based trustworthy XAI {cite('nassar')}, and "
          f"Kroll *et al.* propose cryptographic commitments for accountable algorithms {cite('kroll')}. The closest prior art "
          f"is IBM’s US 12,579,454 B2 {cite('ibm_pat')}, whose claim 1 stores the raw input, the result, an XAI explanation "
          "and the model on a distributed ledger and re-validates a result by re-running the model. It stores personal data "
          "in the ledger, does not bind the explainer’s randomness or background data, has no consistency check on the "
          "explanation, and gives the data subject no offline inclusion proof. Table I summarises the comparison.")
caption(doc, "TABLE I.  PRIOR-ART COMPARISON. F1 per-decision explanation; F2 tamper evidence; F3 no raw personal data in the "
             "log; F4 subject-verifiable receipt/proof; F5 explanation consistency or replay check. "
             "Y = yes, P = partial, N = no, – = not applicable.", keep_next=True, space_after=2)
rows = []
for key, label, typ, yr, idea, *f in C.PRIOR_ART:
    ref = cite(key) if key in C.REFS else ""
    rows.append([f"{label} {ref}".strip(), typ, str(yr), idea, *f])
table(doc, ["Document", "Type", "Year", "Key idea", "F1", "F2", "F3", "F4", "F5"], rows,
      [1.95, 0.45, 0.4, 2.85, 0.27, 0.27, 0.27, 0.27, 0.27], size=8,
      align_cols=["left", "center", "center", "left"] + ["center"] * 5)
para(doc, "**Gap.** No surveyed document combines a per-decision explanation with tamper evidence, privacy-preserving input "
          "commitments, applicant-verifiable proofs and a check that the logged explanation was really produced by the "
          "declared model and explainer (F5). TEXL fills this gap.", space_before=4)

# ============================================================================ 3 Problem formulation
heading(doc, "3. Problem Formulation and Success Metrics")
para(doc, "**Formal statement.** A lender operates a scoring model *f*: X → [0, 1] giving *s* = P(bad | *x*) and rejects "
          "when *s* ≥ τ. For the *i*-th applicant it outputs a tuple (*s*_{i}, *d*_{i}, φ_{i}) and writes a "
          "ledger entry *L*_{i}. A verifier *V* is given the ledger, the lender’s public key, checkpoints held by an "
          "external witness, any receipts presented by applicants, and (under audit) the model artefact and the committed "
          "inputs. *V* must output “tampered” whenever the ledger differs from what was originally issued or a "
          "logged (*s*_{i}, φ_{i}) is not the output of the declared (*f*, *c*) on *x*_{i}. **Threat model:** an "
          "*outsider* can write to the store but lacks the signing key; an *insider* holds the key and controls the "
          "decision software but cannot rewrite checkpoints already published to the witness or receipts already issued.")
para(doc, f"**Dataset.** Statlog (German Credit Data) {cite('dataset')}: {DS['n']:,} applicants, {DS['n_features']} attributes "
          f"({DS['n_numeric']} numeric, {DS['n_categorical']} categorical), binary target (bad-credit rate "
          f"{100 * DS['bad_rate']:.0f}%), licence CC BY 4.0, file SHA-256 {DS['sha256'][:16]}…. We use a stratified "
          f"70/15/15 train/validation/test split (seed {CFG['seed']}); model baselines are repeated over seeds 0–4. "
          "The ledger logs the 150 test decisions.")
para(doc, "**Success metrics.** S1: detection rate ≥ 99% for every attack class under the full TEXL verifier. "
          "S2: 0% false alarms on honest ledgers and under benign recomputation. S3: ledger overhead (excluding the "
          "explanation) ≤ 5 ms per decision and end-to-end decision latency ≤ 500 ms on a laptop CPU. "
          "S4: explanation fidelity, Spearman ρ ≥ 0.9 against the SHAP library’s KernelExplainer. "
          "S5: ≤ 4 KB per record and ≤ 10 ms receipt verification. These metrics serve the business goal: a "
          "lender or regulator can settle a dispute about an adverse-action notice from cryptographic evidence.")
para(doc, "**Ethical constraints (stated up front).** The dataset contains protected or proxy-protected attributes "
          "(personal_status encodes sex and marital status; age; foreign_worker). We keep them deliberately so that the "
          "PoC can show an auditor detecting hidden reliance on them. No raw attribute value is written to the ledger.")

# ============================================================================ 4 Method
heading(doc, "4. Method")
heading(doc, "4.1 Pre-processing and Leakage Prevention", 2)
para(doc, f"Numeric attributes are standardised and categorical attributes one-hot encoded inside a scikit-learn "
          f"{cite('sklearn')} pipeline fitted on the training split only. The decision threshold τ minimises the "
          "Statlog cost matrix (approving a bad applicant costs 5, rejecting a good one costs 1) on the validation split. "
          "The explainer’s background set and the categorical codebook are drawn from the training split, and the test "
          "split is used only for reporting. Models: logistic regression (C = 1), random forest (300 trees, minimum leaf 3) "
          "and gradient boosting (150 trees, learning rate 0.05, depth 3, subsample 0.8), all seeded.")
heading(doc, "4.2 System Architecture", 2)
picture(doc, FIG / "fig1_architecture.png", 6.9)
caption(doc, "Fig. 1.  TEXL architecture. Numbers (101)–(110) are the components referred to by the claims.")
para(doc, "Fig. 1 shows the flow. The model (102) scores input (101), and the explainer (103) produces attributions φ "
          "under configuration *c*. The additivity gate (104) blocks inconsistent explanations. The canonical record (105) "
          "is hashed, chained and signed into the ledger (106). Epoch roots go to the external witness (107), and receipts "
          "(108) go to applicants. Applicants (109) and regulators (110) verify independently.")
heading(doc, "4.3 Seeded Model-Agnostic Explainer", 2)
para(doc, f"TEXL uses antithetic permutation sampling of Shapley values {cite('strumbelj')}. For a seed, *P* feature "
          f"permutations (half of them reversed) and a background set *B* of *m* training rows, each walk from a row *b* of *B* "
          "to *x* switches one attribute at a time and credits it with the change in *f*:")
para(doc, "φ_{j} = (1 / *Pm*) Σ_{π, b} [ *f*(*z*^{π,b}_{k(j)}) − *f*(*z*^{π,b}_{k(j)−1}) ],"
          "        *b*̄ + Σ_{j} φ_{j} = *f*(*x*),        *b*̄ = (1/*m*) Σ_{b} *f*(*b*).",
     align="center", space_after=3)
para(doc, f"Because every walk telescopes, efficiency holds exactly, and this is what the additivity gate checks. We use "
          f"*P* = {CFG['n_permutations']}, *m* = {CFG['background_size']} and seed {CFG['explainer_seed']}. The configuration "
          "(method, *P*, seed, |*B*|, feature list, scale) and a SHA-256 digest of the fixed-point background set form "
          "*c*. Attributions are stated on the 20 raw attributes, not on one-hot columns, so the reasons are "
          "meaningful to the applicant.")
heading(doc, "4.4 Canonical Record, Hash Chain and Signatures", 2)
para(doc, "Each record *r*_{i} holds the sequence number, timestamp, model fingerprint *F*(*f*) (SHA-256 of the serialised "
          "pipeline and library versions), configuration digest, input commitment *C*_{i} = SHA-256(*t*_{in} || *salt*_{i} || "
          "enc(*x*_{i})), score, threshold, decision, base value, the 20 attributions, the top-3 adverse-action reasons and "
          "*h*_{i−1}. Every real number is encoded as an integer count of 10^{−6} units (round half to even) and "
          f"keys are sorted, so the bytes are platform-independent. The record digest is *h*_{{i}} = SHA-256(*t*_{{rec}} || enc(*r*_{{i}})) "
          f"{cite('fips180')}, signed with Ed25519 {cite('ed25519', 'pyca')}. The tags *t* separate hash domains.")
heading(doc, "4.5 Epochs, External Witness and Receipts", 2)
para(doc, f"Every *E* records (default *E* = {CFG['epoch_size']}; Section 5.3 also tests *E* = 8 and 1) the ledger computes the RFC 6962 Merkle tree hash over the epoch’s digests "
          f"{cite('rfc6962')}, signs a checkpoint (root, size, previous-checkpoint digest) and publishes it to the external "
          "witness. Each applicant’s receipt contains the signed record, the salt and, once the epoch is sealed, a "
          f"{R['example']['proof_len']}-hash inclusion proof verified with the RFC 9162 algorithm {cite('rfc9162')}.")
heading(doc, "4.6 Verification and Deterministic Replay", 2)
para(doc, "The regulator’s verifier recomputes every hash, link and signature and every anchored Merkle root, compares "
          "the ledger with any presented receipts, and checks additivity. Under audit it then *replays* each decision: it "
          "recomputes *F*(*f*) of the audited artefact, opens *C*_{i} with (*x*_{i}, *salt*_{i}), re-runs the explainer under "
          "*c*, and flags any score or attribution that differs by more than one unit (10^{−6}).")
heading(doc, "4.7 Claims Set", 2)
for i, cl in enumerate(C.CLAIMS, 1):
    para(doc, f"**Claim {i}{' (independent)' if i == 1 else ''}.** {cl}", size=10, left_indent=0.0, space_after=3)

# ============================================================================ 5 Experiments
heading(doc, "5. Experiments and Results")
heading(doc, "5.1 Setup", 2)
para(doc, f"All experiments ran on a single laptop CPU ({ENV['processor']}, {ENV['platform'].split('-')[0]}) with Python "
          f"{ENV['python']}, NumPy {ENV['numpy']} {cite('numpy')}, pandas {ENV['pandas']} {cite('pandas')}, scikit-learn "
          f"{ENV['sklearn']}, SciPy {cite('scipy')}, SHAP {ENV['shap']} {cite('shaplib')}, cryptography {ENV['cryptography']} "
          f"and Matplotlib {cite('matplotlib')}, in a Jupyter PoC notebook {cite('jupyter')}, with unit tests and report "
          f"generation via the tools in {cite('tooling')}. Each tamper attack was run in {TP['trials']} randomised trials on a "
          f"{TP['ledger_size']}-record ledger whose first {TP['sealed']} records are sealed ({TP['epoch_size']}-record epochs; "
          f"the open tail is realistic). In each trial {TP['receipts_presented']} randomly chosen applicants "
          f"({100 * CFG['receipt_fraction']:.0f}%) present their receipts. Attack A9 uses an undisclosed random forest "
          "in place of the audited gradient-boosting model. Verifier levels V0–V7 add one mechanism at a time (ablation).")
heading(doc, "5.2 Credit-Model Baselines", 2)
caption(doc, "TABLE II.  TEST PERFORMANCE OVER FIVE SEEDS (MEAN ± STD). COST = STATLOG COST PER APPLICANT AT THE "
             "VALIDATION-OPTIMAL THRESHOLD (LOWER IS BETTER).", keep_next=True, space_after=2)
rows = []
names = {"logreg": "Logistic regression", "rf": "Random forest", "gbm": "Gradient boosting"}
for k in ["logreg", "rf", "gbm"]:
    rows.append([names[k], pm(M[k]["roc_auc"]), pm(M[k]["pr_auc"]), pm(M[k]["brier"]), pm(M[k]["cost"]),
                 pm(M[k]["reject_rate"], 2)])
rows.append(["Approve everyone (reference)", "–", "–", "–", pm(M["approve_all_cost"]), "0.00"])
rows.append(["Reject everyone (reference)", "–", "–", "–", pm(M["reject_all_cost"]), "1.00"])
table(doc, ["Model", "ROC-AUC", "PR-AUC", "Brier", "Cost", "Reject rate"], rows,
      [1.9, 1.0, 1.0, 1.0, 1.0, 1.0], size=8.5, align_cols=["left"] + ["center"] * 5)
best_auc = max(["logreg", "rf", "gbm"], key=lambda k: M[k]["roc_auc"][0])
para(doc, f"All three models beat both reference policies on cost (Table II). {names[best_auc]} has the highest mean "
          f"ROC-AUC ({M[best_auc]['roc_auc'][0]:.3f}). The invention does not change the model, so these figures are "
          "context: TEXL is model-agnostic and logs gradient boosting (primary), random forest and logistic regression "
          "decisions alike.", space_before=4)

heading(doc, "5.3 Tamper Detection and Ablation", 2)
caption(doc, f"TABLE III.  DETECTION RATE (%) OVER {TP['trials']} TRIALS PER ATTACK. EACH COLUMN ADDS ONE MECHANISM; "
             "V7 IS THE FULL TEXL VERIFIER. LAST ROW: FALSE-ALARM RATE ON THE HONEST LEDGER.", keep_next=True, space_after=2)
short = ["V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7"]
rows = []
for a, desc in TP["attacks"].items():
    rows.append([f"{a}  {desc}"] + [pct(DET[a][lv]) for lv in LV])
rows.append(["Honest ledger (false alarms)"] + [pct(FA[lv]) for lv in LV])
table(doc, ["Attack (attacker)"] + short, rows, [3.25] + [0.46] * 8, size=8,
      align_cols=["left"] + ["center"] * 8)
para(doc, "V0 plain log; V1 +record hash; V2 +hash chain; V3 +Ed25519 signatures; V4 +anchored Merkle checkpoints; "
          "V5 +applicant receipts; V6 +additivity gate; V7 +deterministic replay.", size=9, align="center", space_before=2)
para(doc, f"Table III shows that every mechanism is needed. A per-record hash (V1) catches only naive edits (A1). Chaining (V2) "
          "adds nothing against an outsider who re-hashes the tail (A2); signatures (V3) stop the outsider but not the "
          f"insider, whose re-signed rewrites (A3–A6) all pass V3. Anchored checkpoints (V4) expose rewrites of sealed "
          f"records ({rng_pct([DET[a][LV[4]] for a in ['A3', 'A4', 'A5']])} for A3–A5); the misses are rewrites inside the "
          f"{TP['ledger_size'] - TP['sealed']}-record unsealed tail. Receipts (V5) catch some of these "
          f"({rng_pct([DET[a][LV[5]] for a in ['A3', 'A4', 'A5']])}), and truncation of the tail (A6) is caught only by "
          f"receipts ({pct(DET['A6'][LV[5]])}%). The at-birth attacks are invisible to every cryptographic layer (V0–V5), "
          "because checkpoints and receipts were built on the falsified record. Zeroing protected attributions (A7) is "
          "caught by the additivity gate, while additivity-preserving fairwashing (A8) and model substitution (A9) are "
          f"caught only by replay, which also exposes tail decision flips (A3, {pct(DET['A3'][full])}%) because the logged "
          f"decision no longer matches the replayed score. With {CFG['epoch_size']}-record epochs the full verifier detects "
          f"{alist(perfect)} in every trial with {pct(FA[full])}% false alarms (S2 met), but "
          f"{alist(imperfect)} in only {rng_pct([DET[a][full] for a in imperfect])} of trials, so S1 is not met at this "
          "setting.", space_before=4)
caption(doc, "TABLE IV.  SEALING-WINDOW SENSITIVITY: DETECTION (%) OF INSIDER ATTACKS BY THE FULL VERIFIER (V7) AS THE "
             f"EPOCH SIZE SHRINKS ({TP['trials']} TRIALS EACH).", keep_next=True, space_after=2, space_before=4)
rows = []
for E in sorted(WN, key=int, reverse=True):
    w = WN[E]
    rows.append([E, str(w["unsealed_tail"]), str(w["checkpoints"])] + [pct(w[a][V7]) for a in TAIL]
                + [pct(w["false_alarm_V7"]), f"{w['build_ms_per_record']:.2f}"])
table(doc, ["Epoch size", "Unsealed tail", "Checkpoints", "A3", "A4", "A5", "A6", "False alarms",
            "Log ms/record"], rows, [0.75, 0.8, 0.85, 0.55, 0.55, 0.55, 0.55, 0.85, 1.0], size=8,
      align_cols=["center"] * 9)
para(doc, f"Table IV closes this gap. Smaller epochs shrink the unsealed tail, and with one-record epochs a checkpoint "
          f"is published for every decision: all four insider attacks are then detected in {pct(w1_min)}% of trials with "
          f"{pct(w1_fa)}% false alarms, so S1 and S2 are met for all nine attacks. The cost is one witness message per "
          f"decision and {W_ONE['build_ms_per_record']:.2f} ms of logging time per record (record construction, signing, "
          "receipt and checkpoint), compared with "
          f"{W_DEF['build_ms_per_record']:.2f} ms with {CFG['epoch_size']}-record epochs.", space_before=4)

heading(doc, "5.4 Overhead, Storage and Scalability", 2)
caption(doc, "TABLE V.  PER-DECISION COST ON THE 150 TEST DECISIONS (MEAN ± STD, MILLISECONDS) AND STORAGE.",
        keep_next=True, space_after=2)
rows = []
for k in ["logreg", "rf", "gbm"]:
    o = OV[k]
    rows.append([names[k], pm(o["predict_ms"], 2), pm(o["explain_ms"], 1), pm(o["ledger_append_ms"], 3),
                 f"{o['verify_per_record_ms']:.3f}", f"{o['receipt_verify_ms']:.3f}", f"{o['record_bytes']:.0f}",
                 f"{o['receipts_valid']}/{o['receipts_total']}"])
table(doc, ["Model", "Predict", "Explain", "Ledger append", "Verify/record", "Receipt verify", "Bytes/record",
            "Receipts valid"], rows, [1.25, 0.78, 0.85, 0.92, 0.85, 0.85, 0.8, 0.7], size=8,
      align_cols=["left"] + ["center"] * 7)
s_max = SC[scale_max]
para(doc, f"Table V shows that hashing, signing and receipt creation cost about {OV[P]['ledger_append_ms'][0]:.2f} ms per "
          f"decision, which is negligible next to the explanation ({OV[P]['explain_ms'][0]:.0f} ms for gradient boosting, "
          f"{OV['rf']['explain_ms'][0]:.0f} ms for the 300-tree forest). The end-to-end latency of the primary model is "
          f"{e2e_ms:.0f} ms (S3). Records take about {OV[P]['record_bytes'] / 1024:.1f} KB and receipts verify in "
          f"{OV[P]['receipt_verify_ms']:.2f} ms (S5). For a synthetic {int(scale_max):,}-record ledger, appending ran at "
          f"{s_max['append_per_s']:,.0f} records/s and full verification (hash, chain, signatures, anchors, additivity) "
          f"took {s_max['verify_s']:.1f} s with {s_max['findings']} findings; with 1,024-record epochs a receipt carries a "
          f"{s_max['proof_len']}-hash proof that verifies in {s_max['receipt_ms']:.2f} ms.", space_before=4)

heading(doc, "5.5 Explanation Fidelity, Determinism and Canonicalisation", 2)
pictures_row(doc, [(FIG / "fig2_example_explanation.png", 3.35), (FIG / "fig3_explainer_budget.png", 3.35)])
caption(doc, "Fig. 2.  (a) Explanation logged for the highest-risk rejected test applicant (ten largest attributions; red raises, "
             "blue lowers P(bad)). (b) Explainer budget: "
             "mean absolute error against a 256-permutation reference (five seeds, 40 applicants) and latency per decision.")
if SH:
    sh_txt = (f"Against the SHAP library’s KernelExplainer (2,048 samples, same background, {SH['n']} applicants), TEXL’s "
              f"16-permutation attributions reach a mean Spearman ρ of {SH['spearman_mean']:.3f} and "
              f"{100 * SH['top3_overlap']:.0f}% top-3 overlap (S4 {'met' if SH['spearman_mean'] >= 0.9 else 'not met'}). ")
else:
    print("WARNING: shap_agreement missing - run `python scripts/run_experiments.py --shap-only`")
    sh_txt = "[[HL: SHAP KernelExplainer comparison missing - rerun with --shap-only.]] "
p16 = STB.get("16") or STB.get(16)
para(doc, sh_txt + f"Against the 256-permutation reference, *P* = 16 gives MAE {1e3 * p16['mae'][0]:.2f}×10^{{−3}} "
          f"and {100 * p16['top3_overlap'][0]:.0f}% top-3 agreement (Fig. 2b). Different seeds give different "
          "explanations, which is why the seed is bound into *c*. Replays under the same configuration were bit-identical "
          f"for {DT['replay_identical_pct']:.0f}% of decisions, and the largest additivity residual before quantisation was "
          f"{DT['max_additivity_residual_float']:.1e}. Re-computing attributions with a different floating-point summation "
          f"order changed the raw-float64 hash for {DT['benign_recompute_hash_mismatch_naive_pct']:.0f}% of decisions but "
          f"the fixed-point encoding for {DT['benign_recompute_hash_mismatch_fixed_pct']:.0f}%, which supports Claim 5.")
ex = R["example"]["record"]["body"]
para(doc, f"**Qualitative analysis.** Fig. 2a shows the logged record of the highest-risk rejected test applicant "
          f"(record {ex['seq']}, P(bad) = {ex['score'] / 1e6:.3f} against τ = {ex['threshold'] / 1e6:.2f}). Its bound "
          f"adverse-action reasons, the three largest risk-raising attributions, are {', '.join(ex['reasons'])}. Detection errors in Table III "
          "fall in two places. Insider rewrites confined to the unsealed tail evade V4, and evade V5 when no affected "
          "receipt is presented; Table IV shows that per-record sealing removes them. Additivity-preserving fairwashing "
          "and model substitution evade every check except replay, so replay is the component that makes explanations "
          "evidence rather than claims.")

# ============================================================================ 6 Discussion
heading(doc, "6. Discussion")
para(doc, "The results answer the business question: can a lender prove, and can a regulator or applicant check, that the "
          "explanation behind a credit decision is the one the model produced and has not changed since? Cryptographic "
          "layering alone (V1–V5) answers only the second half, and only for records already anchored or receipted. "
          "The two ML-specific mechanisms answer the first half. The additivity gate costs almost nothing and catches crude "
          "edits, while replay catches every falsification we simulated because the seeded explainer is a deterministic "
          "function of (*f*, *c*, *x*). What worked was combining these: no single layer detected all nine attacks, but "
          f"together, with a checkpoint after every record, they detected every simulated attack. What did not work was "
          f"leaving a {CFG['epoch_size']}-record sealing window open, which let insider deletions and truncations escape, "
          "and hashing raw floats, which breaks "
          "independent verification across machines; fixed-point canonicalisation fixed this. Limits on what the results "
          "can claim are discussed next.")

# ============================================================================ 7 Limitations / ethics / AI
heading(doc, "7. Limitations, Ethics and AI-Use Declaration")
heading(doc, "7.1 Limitations / Threats to Validity", 2)
bullet(doc, "Replay requires the regulator to hold the audited model artefact and the committed inputs; if the lender "
            "withholds the true inputs, replay reports a failure but cannot reconstruct the truth.")
bullet(doc, "The witness and the receipts are trusted not to collude with the lender. Insider rewrites inside an unsealed "
            "epoch with no later receipt remain undetected (Tables III–IV); per-record sealing removes this window but "
            "needs a witness that accepts one message per decision.")
bullet(doc, "Results come from one small public dataset (1,000 rows), one laptop and simulated attacks; latency will differ "
            "with hardware, model size and the number of attributes. Detection rates are empirical over seeded trials, not proofs.")
bullet(doc, "Permutation-Shapley attributions are sampling estimates; attribution quality, not only integrity, depends on "
            "*P* and the background set, and Shapley values can themselves be misleading for correlated attributes.")
bullet(doc, "Patentability is not established: claim 1 may be argued obvious over the IBM patent combined with hash-chained "
            "audit logs; Claims 2 and 4 carry the strongest novelty. A professional freedom-to-operate search was not performed.")
heading(doc, "7.2 Ethical Considerations and Potential Harms", 2)
para(doc, "TEXL makes explanations verifiable, not fair: a faithfully logged discriminatory decision remains discriminatory. "
          "Protected attributes were kept only to show that hidden reliance on them becomes detectable; a production system "
          "must assess legal admissibility of each attribute. Salted commitments keep personal data out of the ledger, but "
          "the salt and input store must be access-controlled and retained under data-protection law, and receipts must not "
          "be shared publicly. Dual use: an operator could cite the ledger as false reassurance, so verification must be "
          "performed by an independent party. The environmental cost is small (all experiments ran on one CPU in minutes).")
heading(doc, "7.3 AI-Use Declaration (compulsory)", 2)
para(doc, f"An AI assistant {cite('claude')} was used extensively: literature and patent search; design of the TEXL "
          "architecture and drafting of the claims; the Python implementation (package, unit tests, experiment script, "
          "notebook generator and report builder); generation of figures; and first drafts of every section of this "
          "report. OpenAI Codex assisted with the final repository review, reproduction checks and submission edits. "
          "The experiment runner supplies the quantitative results and the unit suite checks the implementation. "
          "Appendix A provides space for each author to record their manual verification and revisions.")

# ============================================================================ 8 Conclusion
heading(doc, "8. Conclusion and Future Work")
para(doc, "We disclosed and prototyped TEXL, which turns per-decision credit explanations into tamper-evident, "
          "privacy-preserving and independently replayable evidence. In the PoC, the full verifier detected every outsider "
          "attack and every at-birth falsification, including fairwashing, in all trials. With a checkpoint after every "
          "record it also detected every insider deletion, reordering and truncation, for about "
          f"{W_ONE['build_ms_per_record']:.1f} ms of logging time per decision. As a next step we will replace the shared-artefact replay with a zero-knowledge proof of correct "
          "explanation, so that regulators can verify an explanation without receiving the model.")

# ============================================================================ References
heading(doc, "References")
for i, k in enumerate(_order, 1):
    para(doc, f"[{i}]  {C.REFS[k]}", size=9, align="left", space_after=1.5, left_indent=0.3, indent_first=-0.3)
unused = set(C.REFS) - set(_order)
assert not unused, f"references never cited: {unused}"

# ============================================================================ Appendices
heading(doc, "Appendix A – Contribution Table")
para(doc, "The assignments and percentages are provisional. Each member should confirm their contributions, "
          "record the checks and revisions they performed, and sign their row before submission.", size=9, space_after=2)
contrib = [
    ("Varun Chaudhary", "2481032", "Ledger, hash chain, signatures, receipts (ledger.py, merkle.py); Sections 4.4–4.5; claims drafting", "25"),
    ("Om Rohilla", "2481022", "Data pipeline, models and thresholds (data.py, models.py); Sections 3, 5.2; submission review", "25"),
    ("Nisha", "2481159", "Seeded explainer, fidelity/stability study, figures (explain.py); Sections 4.3, 5.5; prior-art search", "25"),
    ("Punit", "2481019", "Verifier, attack simulator, tamper experiments, tests (verify.py, attacks.py); Sections 5.3–7", "25"),
]
contribution_table = table(
    doc, ["Member", "URN", "Major contributions", "Approx. %", "Manual checks and revisions", "Signature"],
    [[a, b, c, d, "", ""] for a, b, c, d in contrib], [1.03, 0.58, 2.55, 0.59, 1.43, 0.82], size=9,
    align_cols=["left", "center", "left", "center", "left", "left"], inner_h=True,
)
for row in contribution_table.rows[1:]:
    row.height, row.height_rule = Inches(0.34), WD_ROW_HEIGHT_RULE.AT_LEAST
heading(doc, "Appendix B – Reproducibility Checklist")
for item in [
    f"√  README with exact environment: Python {ENV['python']}, requirements.txt and pinned requirements-lock.txt.",
    f"√  Random seeds recorded: split/model seed {CFG['seed']} (baselines 0–4), explainer seed {CFG['explainer_seed']}, "
    "attack seeds 1001–1009, receipt-sampling seed 99, demo signing key derived from a fixed string.",
    "√  Data source and licence stated (UCI Statlog German Credit, CC BY 4.0, DOI 10.24432/C5NC77); download script "
    "scripts/download_data.py prints the file SHA-256.",
    "√  One command reproduces all tables and figures: ./run_all.sh (tests → experiments → executed notebook "
    "→ this report).",
]:
    para(doc, item, size=10, align="left", space_after=2, left_indent=0.1)

repo_line = para(doc, "√  Project repository: ", size=10, align="left", space_after=2, left_indent=0.1)
link = OxmlElement("w:hyperlink")
link.set(qn("r:id"), repo_line.part.relate_to(C.REPOSITORY_URL, RELATIONSHIP_TYPE.HYPERLINK, is_external=True))
link_run = set_run_font(repo_line.add_run(C.REPOSITORY_URL))
link_run.underline = True
link.append(link_run._element)
repo_line._p.append(link)

doc.save(OUT_DOCX)
print("abstract words:", _ABSTRACT_WORDS)
print("wrote", OUT_DOCX)

if "--no-pdf" not in sys.argv:
    try:
        from docx2pdf import convert
        convert(str(OUT_DOCX), str(OUT_DOCX.with_suffix(".pdf")))
        print("wrote", OUT_DOCX.with_suffix(".pdf"))
    except Exception as e:  # Word not available
        print("PDF conversion skipped:", e)
