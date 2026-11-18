"""Shared content for the IEEE report and the invention disclosure (single source of truth).

Every patent below was checked on Google Patents (title, number, assignee, dates) and every
paper against the publisher / proceedings page on 15 Nov 2026.
"""

TITLE = "TEXL: A Tamper-Evident, Replay-Verifiable Explanation Ledger for Machine-Learning Credit Decisions"
SHORT = "TEXL"
REPOSITORY_URL = "https://github.com/ivarunchaudhary/Aml-Credit-decisions"

TEAM = "Smooth operators"
TRACK = "1 – Patent Design"
SECTION = "B.Tech CSE (AI/ML)"
COORD = "anshita.shukla@iilm.edu"
AUTHORS = [("Varun Chaudhary", "2481032"), ("Om Rohilla", "2481022"), ("Nisha", "2481159"), ("Punit", "2481019")]
ACCESSED = "15 Nov. 2026"

# ----------------------------------------------------------------------------- claims
CLAIMS = [
    # 1 - independent
    "A computer-implemented method for recording automated credit decisions together with "
    "tamper-evident and independently verifiable explanations, the method comprising: "
    "(a) receiving an input record *x* comprising a plurality of attributes of a credit applicant; "
    "(b) computing, with a credit-scoring model *f*, a risk score *s* = *f*(*x*) and a decision obtained by "
    "comparing *s* with a decision threshold; "
    "(c) computing a model-agnostic feature-attribution vector φ for *x* by querying *f* under an "
    "explanation configuration *c* that fixes at least a pseudo-random seed and a background reference set, "
    "and computing a configuration digest of *c* that includes a cryptographic digest of the background reference set; "
    "(d) forming a decision record *r*_{i} comprising a model fingerprint computed as a cryptographic digest of a "
    "serialised representation of *f*, the configuration digest, a salted cryptographic commitment to *x* in place of "
    "*x* itself, the risk score, the decision, the attribution vector φ, and the record digest *h*_{i−1} of the "
    "immediately preceding decision record; "
    "(e) serialising *r*_{i} into a canonical byte string and computing a record digest *h*_{i} with a cryptographic "
    "hash function; "
    "(f) digitally signing *h*_{i} with a private key of the decision operator and appending *r*_{i}, *h*_{i} and the "
    "signature to an append-only decision ledger; and "
    "(g) issuing to the applicant a receipt comprising the signed decision record and the salt that opens the commitment; "
    "whereby a later alteration, deletion, insertion or reordering of a logged decision or explanation is detectable "
    "by recomputing digests and signatures, or, when made by the holder of the private key, by comparison with "
    "receipts already issued, and the logged explanation can be regenerated from the model fingerprint, the "
    "configuration *c* and the committed input.",
    # 2
    "The method of claim 1, further comprising, before the appending step, an additivity gate that computes the "
    "residual |*b* + Σ_{j} φ_{j} − *s*|, where *b* is the mean model output over the background "
    "reference set, and refuses to append the decision record when the residual exceeds a tolerance determined by "
    "the quantisation step of the canonical serialisation.",
    # 3
    "The method of claim 1, further comprising partitioning the ledger into epochs; computing, for each epoch, a "
    "Merkle tree root over the record digests of that epoch using domain-separated leaf and interior-node hashing; "
    "signing a checkpoint that contains the root and the digest of the previous checkpoint; publishing the checkpoint "
    "to an external witness outside the control of the decision operator; and adding to each applicant's receipt an "
    "inclusion proof of that applicant's record digest against the published root; wherein the number of records per "
    "epoch is configurable down to a single record, so as to bound the window in which unsealed records can be "
    "rewritten by the holder of the private key.",
    # 4
    "The method of claim 1, further comprising a verification step in which a verifier (i) recomputes the model "
    "fingerprint of an audited model artefact, (ii) opens the input commitment with the applicant's input and salt, "
    "(iii) regenerates the risk score and the attribution vector by re-executing the explainer under configuration *c*, "
    "and (iv) flags the decision record when a regenerated value differs from the logged value by more than one "
    "quantisation unit, thereby detecting explanations or decisions that were falsified when the record was created.",
    # 5
    "The method of claim 1, wherein the canonical serialisation encodes every real-valued quantity as a signed integer "
    "number of fixed-point units obtained by round-half-to-even quantisation at a predetermined scale and orders all "
    "keys lexicographically, so that benign floating-point differences caused by recomputation on different hardware "
    "or software do not change the record digest.",
    # 6
    "The method of claim 1, wherein the decision record and the receipt further comprise a ranked list of "
    "adverse-action reasons derived deterministically from the attribution vector as the attributes with the largest "
    "positive contribution to the risk score, so that the reasons communicated to the applicant are cryptographically "
    "bound to the logged explanation.",
]

# ----------------------------------------------------------------------------- prior art
# F1 per-decision explanation | F2 tamper evidence | F3 no raw personal data in the log |
# F4 subject-verifiable receipt/proof | F5 explanation consistency or replay check
PRIOR_ART = [
    # key, label, type, year, idea, F1..F5
    ("merkle_pat", "US 4,309,569 A (Stanford)", "Patent", 1982, "Hash-tree (Merkle) authentication of many messages", "N", "Y", "–", "P", "N"),
    ("haber_pat", "US 5,136,646 A (Bellcore)", "Patent", 1992, "Linked time-stamp chain; receipt returned to author", "N", "Y", "Y", "Y", "N"),
    ("schneier_pat", "US 5,978,475 A (Counterpane)", "Patent", 1999, "Forward-secure audit log on an untrusted machine", "N", "Y", "P", "N", "N"),
    ("fico_pat", "US 7,280,980 B1 (Fair Isaac)", "Patent", 2007, "Score explanation from bureau reason codes", "Y", "N", "N", "N", "N"),
    ("equifax_pat", "WO 2016/160539 A1 (Equifax)", "Patent", 2016, "Monotonic neural network emitting adverse-action codes", "Y", "N", "N", "N", "N"),
    ("pointr_pat", "US 2019/0012595 A1 (Pointr)", "Patent", 2019, "Blockchain consensus over neural-network model updates", "N", "Y", "N", "N", "N"),
    ("zest_fair_pat", "US 10,977,729 B2 (ZestFinance)", "Patent", 2021, "Fairness-aware model selection with reason-code reports", "Y", "N", "N", "N", "N"),
    ("zest_decomp_pat", "US 11,960,981 B2 (ZestFinance)", "Patent", 2024, "Model evaluation by output decomposition vs. baseline", "Y", "N", "N", "N", "N"),
    ("ibm_pat", "US 12,579,454 B2 (IBM)", "Patent", 2026, "XAI explanation, raw input and model stored on a distributed ledger; result re-validation", "Y", "Y", "N", "P", "P"),
    ("schneier_paper", "Schneier & Kelsey, ACM TISSEC", "Paper", 1999, "Secure audit logs for forensics (hash chain + MAC keys)", "N", "Y", "P", "N", "N"),
    ("crosby", "Crosby & Wallach, USENIX Sec.", "Paper", 2009, "History tree with logarithmic membership proofs", "N", "Y", "–", "P", "N"),
    ("rfc6962", "RFC 6962 Cert. Transparency", "Std.", 2013, "Public Merkle log, signed tree heads, inclusion proofs", "N", "Y", "–", "Y", "N"),
    ("kroll", "Kroll et al., U. Pa. L. Rev.", "Paper", 2017, "Commitments and zero-knowledge proofs for accountable algorithms", "N", "Y", "Y", "P", "P"),
    ("nassar", "Nassar et al., WIREs DMKD", "Paper", 2020, "Blockchain framework for explainable, trustworthy AI", "P", "Y", "N", "N", "N"),
    ("texl", "TEXL (this work)", "–", 2026, "Seeded explanation + committed input + signed hash chain + anchored receipts + replay", "Y", "Y", "Y", "Y", "Y"),
]

# ----------------------------------------------------------------------------- references (IEEE)
REFS = {
    "euaiact": "European Parliament and Council of the European Union, “Regulation (EU) 2024/1689 laying down harmonised "
               "rules on artificial intelligence (Artificial Intelligence Act),” *Official Journal of the European Union*, "
               "12 Jul. 2024, Art. 12 and Annex III, point 5(b).",
    "regb": "U.S. Consumer Financial Protection Bureau, “Equal Credit Opportunity Act (Regulation B), 12 CFR §1002.9 "
            "– Notifications (statement of specific reasons for adverse action).”",
    "slack": "D. Slack, S. Hilgard, E. Jia, S. Singh, and H. Lakkaraju, “Fooling LIME and SHAP: Adversarial attacks on post "
             "hoc explanation methods,” in *Proc. AAAI/ACM Conf. AI, Ethics, and Society (AIES)*, 2020, "
             "doi: 10.1145/3375627.3375830.",
    "aivodji": "U. Aïvodji, H. Arai, O. Fortineau, S. Gambs, S. Hara, and A. Tapp, “Fairwashing: The risk of "
               "rationalization,” in *Proc. 36th Int. Conf. Machine Learning (ICML)*, PMLR vol. 97, 2019, pp. 161–170.",
    "lundberg": "S. M. Lundberg and S.-I. Lee, “A unified approach to interpreting model predictions,” in *Advances in "
                "Neural Information Processing Systems 30 (NIPS)*, 2017, pp. 4765–4774.",
    "strumbelj": "E. Štrumbelj and I. Kononenko, “Explaining prediction models and individual predictions with feature "
                 "contributions,” *Knowledge and Information Systems*, vol. 41, no. 3, pp. 647–665, 2014.",
    "merkle_pat": "R. C. Merkle, “Method of providing digital signatures,” U.S. Patent 4 309 569 A, 5 Jan. 1982 "
                  "(assignee: Leland Stanford Junior University).",
    "haber_pat": "S. A. Haber and W. S. Stornetta, Jr., “Digital document time-stamping with catenate certificate,” U.S. "
                 "Patent 5 136 646 A, 4 Aug. 1992 (assignee: Bell Communications Research Inc.).",
    "schneier_pat": "B. Schneier and J. M. Kelsey, “Event auditing system,” U.S. Patent 5 978 475 A, 2 Nov. 1999 "
                    "(assignee: Counterpane Internet Security Inc.).",
    "fico_pat": "B. Hoadley, L. E. Rosenberger, and A. Flint, “Algorithm for explaining credit scores,” U.S. Patent "
                "7 280 980 B1, 9 Oct. 2007 (assignee: Fair Isaac Corp.).",
    "equifax_pat": "M. Turner and M. McBurnett, “Optimizing neural networks for risk assessment,” Int. Patent Appl. "
                   "WO 2016/160539 A1, 6 Oct. 2016 (applicant: Equifax Inc.).",
    "pointr_pat": "N. B. Beser, S. Saund, and P. Lambert, “Neural network consensus using blockchain,” U.S. Patent Appl. "
                  "2019/0012595 A1, 10 Jan. 2019 (applicant: Pointr Data Inc.).",
    "zest_fair_pat": "S. J. Kamkar *et al.*, “Systems and methods for model fairness,” U.S. Patent 10 977 729 B2, "
                     "13 Apr. 2021 (assignee: ZestFinance Inc.).",
    "zest_decomp_pat": "D. C. Merrill *et al.*, “Systems and methods for providing machine learning model evaluation by using "
                       "decomposition,” U.S. Patent 11 960 981 B2, 16 Apr. 2024 (assignee: ZestFinance Inc.).",
    "ibm_pat": "G. P. Szczepanik, L. J. Palus, K. S. Patel, and S. S. Patel, “Providing explainable machine learning model "
               "results using distributed ledgers,” U.S. Patent 12 579 454 B2, 17 Mar. 2026 (assignee: International "
               "Business Machines Corp.).",
    "schneier_paper": "B. Schneier and J. Kelsey, “Secure audit logs to support computer forensics,” *ACM Trans. Information "
                      "and System Security*, vol. 2, no. 2, pp. 159–176, 1999.",
    "crosby": "S. A. Crosby and D. S. Wallach, “Efficient data structures for tamper-evident logging,” in *Proc. 18th "
              "USENIX Security Symposium*, 2009, pp. 317–334.",
    "rfc6962": "B. Laurie, A. Langley, and E. Kasper, “Certificate Transparency,” IETF RFC 6962, Jun. 2013.",
    "rfc9162": "B. Laurie, E. Messeri, and R. Stradling, “Certificate Transparency version 2.0,” IETF RFC 9162, Dec. 2021.",
    "kroll": "J. A. Kroll, J. Huey, S. Barocas, E. W. Felten, J. R. Reidenberg, D. G. Robinson, and H. Yu, “Accountable "
             "algorithms,” *University of Pennsylvania Law Review*, vol. 165, no. 3, pp. 633–705, 2017.",
    "nassar": "M. Nassar, K. Salah, M. H. ur Rehman, and D. Svetinovic, “Blockchain for explainable and trustworthy artificial "
              "intelligence,” *WIREs Data Mining and Knowledge Discovery*, vol. 10, no. 1, e1340, 2020, doi: 10.1002/widm.1340.",
    "dataset": "H. Hofmann, “Statlog (German Credit Data),” UCI Machine Learning Repository, 1994, "
               "doi: 10.24432/C5NC77. Licence: CC BY 4.0. Accessed: " + ACCESSED + ".",
    "ed25519": "D. J. Bernstein, N. Duif, T. Lange, P. Schwabe, and B.-Y. Yang, “High-speed high-security signatures,” "
               "*J. Cryptographic Engineering*, vol. 2, no. 2, pp. 77–89, 2012.",
    "fips180": "National Institute of Standards and Technology, “Secure Hash Standard (SHS),” FIPS PUB 180-4, Aug. 2015.",
    "sklearn": "F. Pedregosa *et al.*, “Scikit-learn: Machine learning in Python,” *J. Machine Learning Research*, vol. 12, "
               "pp. 2825–2830, 2011.",
    "numpy": "C. R. Harris *et al.*, “Array programming with NumPy,” *Nature*, vol. 585, pp. 357–362, 2020.",
    "scipy": "P. Virtanen *et al.*, “SciPy 1.0: Fundamental algorithms for scientific computing in Python,” *Nature "
             "Methods*, vol. 17, pp. 261–272, 2020.",
    "pandas": "W. McKinney, “Data structures for statistical computing in Python,” in *Proc. 9th Python in Science Conf.*, "
              "2010, pp. 56–61.",
    "matplotlib": "J. D. Hunter, “Matplotlib: A 2D graphics environment,” *Computing in Science & Engineering*, vol. 9, "
                  "no. 3, pp. 90–95, 2007.",
    "shaplib": "SHAP contributors, “SHAP: A game theoretic approach to explain the output of any machine learning model,” "
               "software, https://github.com/shap/shap. Accessed: " + ACCESSED + ".",
    "pyca": "Python Cryptographic Authority, “cryptography” (Ed25519, SHA-256), software, https://cryptography.io. "
            "Accessed: " + ACCESSED + ".",
    "jupyter": "T. Kluyver *et al.*, “Jupyter Notebooks – a publishing format for reproducible computational "
               "workflows,” in *Positioning and Power in Academic Publishing*, IOS Press, 2016, pp. 87–90.",
    "tooling": "Open-source tooling: pytest (https://pytest.org), python-docx (https://github.com/python-openxml/python-docx), "
               "docx2pdf (https://github.com/AlJohri/docx2pdf). Accessed: " + ACCESSED + ".",
    "claude": "Anthropic, “Claude Code” AI coding assistant (model: Claude Opus 5.5), 2026; used as declared in "
              "Section 7.3.",
}
