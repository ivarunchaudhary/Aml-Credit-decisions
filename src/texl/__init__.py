"""TEXL - Tamper-Evident eXplanation Ledger for machine-learning credit decisions.

Proof-of-concept package for the AML Lab (CSE2512P) Track 1 (Patent Design) project of
team "Smooth operators", IILM University, Gurugram.

Modules
-------
canonical : fixed-point canonical serialisation and domain-separated hashing
data      : German Credit (Statlog) loader and leakage-free splits
models    : preprocessing pipelines, model training, cost-optimal threshold, model fingerprint
explain   : deterministic, model-agnostic permutation-Shapley explainer
merkle    : RFC 6962 / RFC 9162 Merkle tree hash and inclusion proofs
ledger    : decision records, hash chain, Ed25519 signatures, epochs, receipts
verify    : regulator / applicant verification, including deterministic replay
attacks   : tamper-attack simulator used for the evaluation
"""

__version__ = "1.0.0"
