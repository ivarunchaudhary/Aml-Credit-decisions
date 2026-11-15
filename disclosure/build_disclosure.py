"""Build the Invention Disclosure Form (Track 1 core deliverable) as DOCX + PDF.

Usage: python disclosure/build_disclosure.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from docx import Document

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "report"))

import content as C  # noqa: E402
from docx_style import (bullet, caption, heading, page_number_footer, para, picture, set_core,  # noqa: E402
                        style_document, table)

R = json.loads((ROOT / "results" / "results.json").read_text())
OUT = HERE / "Smooth_operators_TEXL_Invention_Disclosure.docx"
OV, TP = R["overhead"], R["tamper"]
full = list(TP["false_alarm_pct"])[-1]
DET = TP["detection_pct"]
W1 = R["window"]["1"]
V7 = "V7 TEXL (+Replay)"
TAIL = ["A3", "A4", "A5", "A6"]
perfect = [a for a in DET if DET[a][full] == 100.0]
imperfect = [a for a in DET if DET[a][full] < 100.0]

doc = Document()
style_document(doc)
page_number_footer(doc)
set_core(doc, "Invention Disclosure - " + C.TITLE, ", ".join(a for a, _ in C.AUTHORS),
         "AML Lab CSE2512P - Track 1 Patent Design", "invention disclosure, claims")

para(doc, "INVENTION DISCLOSURE FORM", size=14, align="center", bold=True, space_after=2)
para(doc, "Applied Machine Learning Lab (CSE2512P) – Track 1: Patent Design", size=10, align="center", space_after=1)
para(doc, f"IILM University, Gurugram  |  Team: {C.TEAM}  |  Course Coordinator: {C.COORD}", size=10, align="center",
     space_after=8)
para(doc, "CONFIDENTIAL – prepared for academic assessment. Public disclosure before a patent filing can destroy "
          "novelty; consult the university IPR cell before publishing or presenting outside the course.", size=9,
     align="center", italic=True, space_after=8)

heading(doc, "1. Title of the Invention")
para(doc, C.TITLE + " (“TEXL”).")

heading(doc, "2. Inventors")
table(doc, ["Name", "URN", "Programme", "Affiliation"],
      [[n, u, C.SECTION, "IILM University, Gurugram"] for n, u in C.AUTHORS], [2.0, 1.0, 1.6, 2.4], size=10,
      align_cols=["left", "center", "left", "left"], inner_h=True)

heading(doc, "3. Field of the Invention")
para(doc, "The invention relates to machine-learning-based credit decisioning and, more specifically, to methods for "
          "recording automated decisions together with feature-attribution explanations in a form that is tamper-evident, "
          "privacy-preserving and independently verifiable by regulators and by the affected applicant.")

heading(doc, "4. Background and Problem Solved")
para(doc, "Regulations require lenders to log the operation of high-risk AI systems and to give applicants the specific "
          "reasons for an adverse credit decision. Lenders therefore attach post-hoc explanations (e.g. Shapley-value "
          "attributions) to decisions. Two problems remain unsolved: (1) an ordinary log can be silently edited after a "
          "dispute, and (2) even an immutable log cannot show that the logged explanation was really produced by the "
          "declared model and explainer, so an operator can log a convenient (“fairwashed”) explanation from the "
          "outset. Existing ledger-based approaches additionally store raw personal data on the ledger.")

heading(doc, "5. Closest Prior Art and Differences")
rows = [[lab, typ, str(yr), idea, *f] for key, lab, typ, yr, idea, *f in C.PRIOR_ART]
table(doc, ["Document", "Type", "Year", "Key idea", "F1", "F2", "F3", "F4", "F5"], rows,
      [1.95, 0.45, 0.4, 2.85, 0.27, 0.27, 0.27, 0.27, 0.27], size=8,
      align_cols=["left", "center", "center", "left"] + ["center"] * 5)
para(doc, "F1 per-decision explanation; F2 tamper evidence; F3 no raw personal data in the log; F4 subject-verifiable "
          "receipt/proof; F5 explanation consistency or replay check (Y yes, P partial, N no).", size=9, align="center",
     space_before=2)
para(doc, "**Closest document: US 12,579,454 B2 (IBM, granted 17 Mar. 2026).** Its claim 1 adds a block containing the raw "
          "input data, the result, an XAI explanation, the model version and model data structure to a distributed ledger, "
          "and re-validates a result by re-processing the stored input with the stored model. TEXL differs in that it "
          "(i) never stores the input, only a salted commitment opened by the applicant’s receipt; (ii) binds the "
          "explainer’s seed and background set by digest so that the *explanation itself* is bit-exactly replayable; "
          "(iii) gates every record on the additivity (local-accuracy) identity; (iv) uses a lightweight single-writer "
          "signed hash chain with externally witnessed Merkle checkpoints and offline inclusion proofs instead of a "
          "consensus ledger; and (v) uses fixed-point canonical encoding for cross-platform hash stability.")

heading(doc, "6. Summary of the Invention")
para(doc, "For every credit decision, TEXL (a) explains the score with a seeded, model-agnostic permutation-Shapley "
          "explainer whose configuration, including a digest of its background data, is hashed; (b) checks that base value "
          "plus attributions reproduce the score; (c) builds a canonical, fixed-point record containing the model "
          "fingerprint, configuration digest, salted input commitment, score, decision, attributions, adverse-action "
          "reasons and the previous record’s digest; (d) hashes, signs and appends it; (e) periodically seals Merkle "
          "checkpoints to an external witness; and (f) issues the applicant a receipt with the salt and an inclusion proof. "
          "Regulators verify the ledger and deterministically replay decisions; applicants verify their own receipt offline.")

heading(doc, "7. Brief Description of the Drawing")
picture(doc, ROOT / "results" / "figures" / "fig1_architecture.png", 6.9)
caption(doc, "Fig. 1.  System overview with components (101)–(110).")

heading(doc, "8. Detailed Description")
for t in [
    "**(101) Input.** The applicant’s raw attributes *x* (20 attributes in the embodiment: 7 numeric, 13 categorical). "
    "Categorical values are integer-coded with a codebook learned on training data only.",
    "**(102) Model and fingerprint.** Any scoring model *f* returning P(bad | *x*). The fingerprint *F*(*f*) is SHA-256 over "
    "a domain tag, the library versions and the serialised fitted pipeline.",
    "**(103) Seeded explainer.** Antithetic permutation sampling: *P*/2 permutations drawn from a seeded generator plus their "
    "reverses; *m* background rows. For each (permutation, background row) the explainer walks from the background row to *x* "
    "one attribute at a time and credits each attribute with the change in *f*. Configuration *c* = (method, *P*, seed, |*B*|, "
    "digest of fixed-point *B*, feature list, scale) and its digest are recorded.",
    "**(104) Additivity gate.** Rejects the record if |*b* + Σφ − *s*| exceeds floor(*d*/2) + 2 fixed-point "
    "units (a bound on the accumulated rounding error of the quantised terms), so arithmetically inconsistent explanations can never be written.",
    "**(105) Canonical record.** JSON with lexicographically sorted keys, no whitespace, ASCII only and no floating-point "
    "literals; reals become integers of 10^{−6} units (round half to even). Digest *h*_{i} = SHA-256(tag || bytes); "
    "Ed25519 signature over *h*_{i}.",
    "**(106) Ledger.** Append-only sequence; each record contains *h*_{i−1}. Every *E* records (E = 32 in the embodiment) "
    "an epoch is sealed with the RFC 6962 Merkle tree hash (leaf prefix 0x00, node prefix 0x01).",
    "**(107) External witness.** Receives signed checkpoints (epoch, first sequence, size, root, previous checkpoint digest); "
    "may be a regulator inbox, a public transparency log or a third-party time-stamping service.",
    "**(108) Receipt.** Signed record, salt, the applicant’s own encoded input, and the inclusion proof and checkpoint once "
    "sealed. It doubles as a cryptographically bound adverse-action notice.",
    "**(109) Applicant verifier.** Re-hashes the record, checks the signature, the additivity identity, the commitment opening and "
    "the inclusion proof against the published checkpoint – no access to other applicants’ data is needed.",
    "**(110) Regulator verifier.** Checks hashes, links, signatures, anchored roots and presented receipts, then replays each "
    "decision from the audited artefact, the configuration and the opened commitment.",
    "**Alternative embodiments.** Other model-agnostic explainers (e.g. KernelSHAP, integrated gradients for differentiable models) "
    "with their randomness bound in *c*; HMAC or post-quantum signatures; time-based instead of count-based epochs; anchoring "
    "checkpoint roots on a public blockchain; applying the method to insurance, hiring or medical triage decisions.",
]:
    para(doc, t, space_after=3)

heading(doc, "9. Advantages")
for t in [
    "Detects post-hoc tampering by outsiders and, once records are sealed or receipted, by insiders; detects "
    "at-birth falsification of explanations via the additivity gate and replay.",
    "No personal data in the ledger; applicants can verify their own decision offline.",
    "Model-agnostic, with no blockchain consensus required; about "
    f"{OV['gbm']['ledger_append_ms'][0]:.1f} ms ledger overhead per decision in the PoC.",
    "Cross-platform reproducible digests through fixed-point canonicalisation.",
]:
    bullet(doc, t)

heading(doc, "10. Claims")
for i, cl in enumerate(C.CLAIMS, 1):
    para(doc, f"**{i}.** {cl}", space_after=4)

heading(doc, "11. Experimental Support (Proof of Concept)")
para(doc, f"Public UCI Statlog German Credit data (CC BY 4.0). Over {TP['trials']} randomised trials for each of nine attack "
          f"classes and {TP['false_alarm_pct'][full]:.0f}% false alarms, the full verifier with 32-record epochs detected "
          f"{['zero','one','two','three','four','five','six','seven','eight','nine'][len(perfect)]} attack classes in every trial (all outsider attacks, decision flips and all at-birth "
          f"falsifications); insider deletion, reordering and truncation inside the unsealed tail were detected in "
          f"{min(DET[a][full] for a in imperfect):.1f}–{max(DET[a][full] for a in imperfect):.1f}% of trials. With one-record "
          f"epochs (embodiment of claim 3) these rose to {min(W1[a][V7] for a in TAIL):.0f}% with "
          f"{W1['false_alarm_V7']:.0f}% false alarms. Explanation {OV['gbm']['explain_ms'][0]:.0f} ms and ledger append "
          f"{OV['gbm']['ledger_append_ms'][0]:.2f} ms per decision (gradient boosting). The code, notebook and full results "
          "are in the accompanying repository (notebooks/TEXL_PoC.ipynb, results/results.json).")

heading(doc, "12. Abstract of the Disclosure")
para(doc, "A method records each automated credit decision with a seeded, model-agnostic feature-attribution explanation, "
          "a model fingerprint and a salted commitment to the applicant’s input in a canonical fixed-point record that "
          "is gated on the additivity identity, hash-chained, digitally signed, sealed into externally witnessed Merkle "
          "checkpoints and returned to the applicant as a verifiable receipt, enabling detection of post-hoc tampering and "
          "deterministic replay that detects explanations falsified at logging time.", italic=True)

heading(doc, "13. Status and Declaration")
para(doc, "Not filed with any patent office. Developed with AI assistance as declared in Section 7.3 of the accompanying "
          "report. The inventors declare that, to the best of their knowledge, the above description is accurate.")
table(doc, ["Inventor", "URN", "Signature", "Date"], [[n, u, "", ""] for n, u in C.AUTHORS], [2.2, 1.0, 2.4, 1.4],
      size=10, align_cols=["left", "center", "left", "left"], inner_h=True)

doc.save(OUT)
print("wrote", OUT)
if "--no-pdf" not in sys.argv:
    try:
        from docx2pdf import convert
        convert(str(OUT), str(OUT.with_suffix(".pdf")))
        print("wrote", OUT.with_suffix(".pdf"))
    except Exception as e:
        print("PDF conversion skipped:", e)
