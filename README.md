# TEXL – Tamper-Evident, Replay-Verifiable Explanation Ledger for ML Credit Decisions

**Applied Machine Learning Lab (CSE2512P) · Track 1 – Patent Design · Team: Smooth operators · IILM University, Gurugram**

Members: Varun Chaudhary (2481032), Om Rohilla (2481022), Nisha (2481159), Punit (2481019)
Topic: *Group 1, Topic A – Tamper-Evident Explainable Credit Decision Log*

## Deliverables

| Deliverable (Track 1) | File |
|---|---|
| IEEE-format project report (DOCX + PDF) | `report/Smooth_operators_Track1_TEXL_Report.docx` / `.pdf` |
| Invention disclosure + claims set (1 independent + 5 dependent) | `disclosure/Smooth_operators_TEXL_Invention_Disclosure.docx` / `.pdf` |
| Proof-of-concept notebook (executed) | `notebooks/TEXL_PoC.ipynb` |
| Source package | `src/texl/` |
| All results (tables, figures, raw JSON) | `results/` |

## What TEXL does

For every credit decision TEXL
1. explains the score with a **seeded, model-agnostic permutation-Shapley** explainer (`explain.py`);
2. blocks explanations that do not add up to the score (**additivity gate**);
3. writes a **fixed-point canonical record** (model fingerprint, explainer-config digest, **salted input commitment**,
   score, decision, attributions, adverse-action reasons, previous hash), hashes it with SHA-256 and signs it with Ed25519 (`ledger.py`);
4. seals every 32 records into an **RFC 6962 Merkle checkpoint** published to an external witness (`merkle.py`);
5. hands the applicant a **receipt** (signed record + salt + inclusion proof);
6. lets a regulator **deterministically replay** score and explanation from the committed input (`verify.py`).

`attacks.py` simulates nine outsider/insider attacks; `scripts/run_experiments.py` measures detection (ablation over
verifier levels V0–V7), the effect of the epoch size on insider attacks in the unsealed tail (sealing-window study),
overhead, scalability and explanation fidelity (incl. agreement with the SHAP library's KernelExplainer).
A full run takes about 12 minutes on a laptop CPU.

### Live demo

`demo/app.py` is a Streamlit app for the presentation and viva. It rebuilds the same system as
`run_experiments.py` (seed 42, gradient boosting, P = 16) and preloads a ledger with 72 test applicants
(2 sealed epochs of 32 plus an unsealed tail of 8).

| Tab | What it shows |
|---|---|
| Decide | pick an applicant, edit duration / amount / age / checking / savings, get the decision, the per-attribute contributions, the signed record and the receipt; "Verify my receipt" runs the applicant-side checks |
| Ledger | every record with its hash, previous hash and sealed / unsealed status, plus the published checkpoints |
| Tamper & verify | run any attack A1–A9 on a copy of the ledger and see which verifier level (V0–V7) catches it and why |
| Results | the 200-run detection table and the report figures (fallback if anything fails live) |

```bash
.venv/bin/pip install streamlit
.venv/bin/streamlit run demo/app.py        # opens http://localhost:8501; first start takes about 15 s
```

Truncation (A6) is only caught when an applicant from the deleted tail shows a receipt, so most seeds
miss it (21.5 % in the report); seeds 1, 8, 9, 12 and 13 show a catch. The demo signing key is derived
from a fixed string and is **not for production**.

### Explainer seed stability

`evaluate_seed_stability(model, X, B, seeds, P)` in `src/texl/explain.py` checks how much the permutation seed moves
the explanation. It builds one permutation-Shapley explainer per seed (same background set `B`, same budget `P`),
explains every applicant in `X`, and averages over all seed pairs the **Spearman rank correlation** of the
attributions and the **top-3 adverse-action overlap** (risk-raising reasons from `top_reasons`). Attributions are
rounded to 12 decimals before ranking (`round_decimals`) so float noise on tied features does not count as instability.
`model` is either `f(Z) -> P(bad)` or an estimator with `predict_proba`.

`scripts/check_explainer_stability.py` uses the same split, model and background set as `run_experiments.py`
(seed 42) and prints P, mean Spearman, mean top-3 overlap and runtime for P = 4, 8, 16, 32, 64 with seeds 0–4.
It writes nothing to `results/` and takes a few minutes, mostly at P = 64.

```bash
.venv/bin/python scripts/check_explainer_stability.py                        # gbm, first 40 test applicants
.venv/bin/python scripts/check_explainer_stability.py --model rf --n-inst 20
.venv/bin/python -m pytest -q tests/test_explain.py                          # explainer unit tests only
```

## Environment

* Python **3.11** (results produced with 3.11.14 on macOS / Apple Silicon CPU)
* `requirements.txt` (direct dependencies) and `requirements-lock.txt` (exact versions used)

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
```

## Reproduce everything (one command)

```bash
./run_all.sh
```

This runs, in order: data download (prints SHA-256 of `german.data`) → unit tests → `scripts/run_experiments.py`
(writes `results/`) → executes the notebook → builds the report and the disclosure (DOCX; PDF via Microsoft Word if installed).
Use `./run_all.sh --no-pdf` on machines without Word to skip PDF export. Set `PY=/path/to/python`
to reuse an environment with the project dependencies already installed. The checked-in PDFs can be read
independently of the reproduction environment.
Individual steps:

```bash
.venv/bin/python scripts/download_data.py
.venv/bin/python -m pytest -q tests
.venv/bin/python scripts/run_experiments.py
.venv/bin/python scripts/run_experiments.py --shap-only   # only refresh the SHAP KernelExplainer comparison
.venv/bin/python notebooks/make_notebook.py      # regenerate the notebook source
.venv/bin/python report/build_report.py
.venv/bin/python disclosure/build_disclosure.py
```

## Data

UCI Machine Learning Repository, *Statlog (German Credit Data)*, H. Hofmann (1994), DOI 10.24432/C5NC77,
licence **CC BY 4.0**. 1,000 applicants, 20 attributes, target good/bad. The file is downloaded by
`scripts/download_data.py`; no personal or private data is used.

## Seeds

Split/model seed 42 (baselines: 0–4) · explainer seed 2026 · background-sample seed 42 · attack seeds 1001–1009 ·
receipt-sampling seed 99 · salts seed 7 · KernelExplainer NumPy seed 0 · demo Ed25519 key derived from a fixed string (**demo only, never use in production**).

## Layout

```
src/texl/        canonical.py data.py models.py explain.py merkle.py ledger.py verify.py attacks.py
scripts/         download_data.py run_experiments.py check_explainer_stability.py
demo/            core.py app.py                            -> Streamlit live demo
tests/           test_texl.py test_explain.py test_demo.py
notebooks/       make_notebook.py TEXL_PoC.ipynb
results/         results.json tables/*.csv figures/*.png example_record.json example_receipt.json
report/          content.py docx_style.py build_report.py  -> report DOCX/PDF
disclosure/      build_disclosure.py                       -> invention disclosure DOCX/PDF
```

## AI-use

Built with substantial AI assistance (Claude Code). OpenAI Codex assisted with the final repository review,
reproduction checks and submission edits. See Section 7.3 of the report.
