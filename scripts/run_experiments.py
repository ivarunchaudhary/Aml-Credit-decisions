"""Reproduce every table, figure and number reported in the TEXL paper.

Usage:   python scripts/run_experiments.py            (about 5-10 minutes on a laptop CPU)
Outputs: results/results.json, results/tables/*.csv, results/figures/*.png,
         results/example_record.json, results/example_receipt.json
"""

from __future__ import annotations

import copy
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from texl import canonical, data, merkle, models  # noqa: E402
from texl.attacks import ATTACKS, Context, Decision, run_attack  # noqa: E402
from texl.explain import PermutationShapley  # noqa: E402
from texl.ledger import Ledger, Witness, demo_signing_key, verify_sig  # noqa: E402
from texl.verify import Replayer, verify_ledger, verify_receipt  # noqa: E402

RES = ROOT / "results"
TAB = RES / "tables"
FIG = RES / "figures"
for p in (RES, TAB, FIG):
    p.mkdir(parents=True, exist_ok=True)

SEED = 42                 # primary split / model seed
MODEL_SEEDS = [0, 1, 2, 3, 4]
PRIMARY = "gbm"
ALT_MODEL = "rf"          # undisclosed substitute model for attack A9
N_PERM = 16
BG_SIZE = 32
EPOCH = 32
TRIALS = 200
RECEIPT_FRACTION = 0.05

VERIFIER_LEVELS = [
    ("V0 Plain log", []),
    ("V1 +Record hash", ["hash"]),
    ("V2 +Hash chain", ["hash", "chain"]),
    ("V3 +Signatures", ["hash", "chain", "sig"]),
    ("V4 +Anchored checkpoints", ["hash", "chain", "sig", "anchor"]),
    ("V5 +Applicant receipts", ["hash", "chain", "sig", "anchor", "receipts"]),
    ("V6 +Additivity gate", ["hash", "chain", "sig", "anchor", "receipts", "additivity"]),
    ("V7 TEXL (+Replay)", ["hash", "chain", "sig", "anchor", "receipts", "additivity", "replay"]),
]

OUT: dict = {}


def log(*a):
    print(*a, flush=True)


def timeit(fn, repeat=5):
    ts = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return float(np.mean(ts)), float(np.std(ts))


# ============================================================================ E0 data
def _shap_version():
    try:
        return __import__("shap").__version__
    except ImportError:
        return None


def e0_data():
    X, y = data.load()
    sha = hashlib.sha256(data.RAW_FILE.read_bytes()).hexdigest()
    OUT["dataset"] = {
        "n": int(len(X)), "n_features": len(data.FEATURES), "n_numeric": len(data.NUMERIC),
        "n_categorical": len(data.CATEGORICAL), "bad_rate": float(y.mean()), "sha256": sha,
    }
    OUT["environment"] = {
        "python": platform.python_version(), "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "numpy": np.__version__, "pandas": pd.__version__,
        "sklearn": __import__("sklearn").__version__, "shap": _shap_version(),
        "cryptography": __import__("cryptography").__version__,
    }
    log("E0", OUT["dataset"])
    return X, y


# ============================================================================ E1 models
def e1_models(X, y):
    rows = []
    for kind in models.MODEL_NAMES:
        for s in MODEL_SEEDS:
            X_tr, y_tr, X_va, y_va, X_te, y_te = data.split(X, y, seed=s)
            m = models.make_pipeline(kind, s).fit(X_tr, y_tr)
            thr = models.choose_threshold(y_va, m.predict_proba(X_va)[:, 1])
            r = models.evaluate(y_te, m.predict_proba(X_te)[:, 1], thr)
            r.update(model=kind, seed=s, threshold=thr)
            rows.append(r)
        # trivial baseline: approve everybody (cost = 5 * bad rate)
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "model_performance_per_seed.csv", index=False)
    agg = df.groupby("model").agg(["mean", "std"])
    summary = {}
    for kind in models.MODEL_NAMES:
        summary[kind] = {k: [float(agg.loc[kind, (k, "mean")]), float(agg.loc[kind, (k, "std")])]
                         for k in ["roc_auc", "pr_auc", "brier", "accuracy", "cost", "reject_rate", "threshold"]}
    # Reference policies on the same five test splits
    approve_all, reject_all = [], []
    for s in MODEL_SEEDS:
        *_, y_te = data.split(X, y, seed=s)
        approve_all.append(models.COST_FN * y_te.mean())
        reject_all.append(models.COST_FP * (1 - y_te.mean()))
    summary["approve_all_cost"] = [float(np.mean(approve_all)), float(np.std(approve_all))]
    summary["reject_all_cost"] = [float(np.mean(reject_all)), float(np.std(reject_all))]
    OUT["models"] = summary
    log("E1", json.dumps(summary, indent=1)[:600])


# ============================================================================ setup
def build_system(X, y, kind, seed=SEED):
    X_tr, y_tr, X_va, y_va, X_te, y_te = data.split(X, y, seed=seed)
    model = models.make_pipeline(kind, seed).fit(X_tr, y_tr)
    thr = models.choose_threshold(y_va, model.predict_proba(X_va)[:, 1])
    codec = data.RawCodec(X_tr)
    rng = np.random.default_rng(seed)
    bg = codec.encode(X_tr.iloc[rng.choice(len(X_tr), BG_SIZE, replace=False)])

    def f(Z):
        return model.predict_proba(codec.decode(Z))[:, 1]

    expl = PermutationShapley(f, bg, data.FEATURES, n_permutations=N_PERM, seed=2026)
    return dict(model=model, thr=thr, codec=codec, bg=bg, f=f, expl=expl, fp=models.model_fingerprint(model),
                X_te=X_te, y_te=y_te, X_tr=X_tr)


def salts(n, seed=7):
    rng = np.random.default_rng(seed)
    return [rng.bytes(16) for _ in range(n)]


# ============================================================================ E2 ledger + overhead
def e2_ledger_overhead(X, y):
    sk = demo_signing_key()
    per_model = {}
    systems = {}
    for kind in models.MODEL_NAMES:
        S = build_system(X, y, kind)
        systems[kind] = S
        Xenc = S["codec"].encode(S["X_te"])
        led = Ledger(sk, S["fp"], S["expl"].config_digest, data.FEATURES, S["thr"], epoch_size=EPOCH)
        st = salts(len(Xenc))
        t_pred, t_expl, t_app = [], [], []
        for i, xe in enumerate(Xenc):
            t0 = time.perf_counter(); S["f"](xe[None, :]); t1 = time.perf_counter()
            score, phi = S["expl"].explain(xe); t2 = time.perf_counter()
            xf = canonical.fixed_vector(xe)
            body = led.build_body(xf, st[i], score, phi, S["expl"].base_value)
            led.append(body, st[i], xf); t3 = time.perf_counter()
            t_pred.append(t1 - t0); t_expl.append(t2 - t1); t_app.append(t3 - t2)
        led.seal_epoch()
        wit = led.witness.checkpoints
        t0 = time.perf_counter()
        f_all = verify_ledger(led.records, led.public_key, checks=["hash", "chain", "sig", "anchor"],
                              witness_checkpoints=wit)
        t_ver = (time.perf_counter() - t0) / len(led.records)
        t0 = time.perf_counter()
        rc_ok = [verify_receipt(r, led.public_key, wit)["valid"] for r in led.receipts.values()]
        t_rc = (time.perf_counter() - t0) / len(rc_ok)
        per_model[kind] = {
            "predict_ms": [1e3 * np.mean(t_pred), 1e3 * np.std(t_pred)],
            "explain_ms": [1e3 * np.mean(t_expl), 1e3 * np.std(t_expl)],
            "ledger_append_ms": [1e3 * np.mean(t_app), 1e3 * np.std(t_app)],
            "verify_per_record_ms": 1e3 * t_ver,
            "receipt_verify_ms": 1e3 * t_rc,
            "record_bytes": led.storage_bytes_per_record(),
            "receipt_bytes": float(np.mean([len(json.dumps(r)) for r in led.receipts.values()])),
            "honest_findings": len(f_all),
            "receipts_valid": int(sum(rc_ok)), "receipts_total": len(rc_ok),
            "threshold": S["thr"],
            "reject_rate": float(np.mean([r["body"]["decision"] == "REJECT" for r in led.records])),
        }
        if kind == PRIMARY:
            # running example: the highest-risk REJECTED test applicant
            j = max((i for i, r in enumerate(led.records) if r["body"]["decision"] == "REJECT"),
                    key=lambda i: led.records[i]["body"]["score"])
            (RES / "example_record.json").write_text(json.dumps(led.records[j], indent=2))
            (RES / "example_receipt.json").write_text(json.dumps(led.receipts[j], indent=2))
            OUT["example"] = {"seq": j, "record": led.records[j],
                              "proof_len": len(led.receipts[j]["proof"])}
        log("E2", kind, {k: v for k, v in per_model[kind].items()})
    OUT["overhead"] = per_model
    return systems


# ============================================================================ E3 determinism / canonicalisation
def e3_determinism(S):
    Xenc = S["codec"].encode(S["X_te"])
    same, fixed_mismatch, naive_mismatch, max_resid = 0, 0, 0, 0.0
    for xe in Xenc:
        s1, p1 = S["expl"].explain(xe)
        s2, p2 = S["expl"].explain(xe)                              # replay, same config
        s3, p3 = S["expl"].explain(xe, reverse_accumulation=True)   # benign recomputation
        same += int(np.array_equal(p1, p2) and s1 == s2)
        fixed_mismatch += int(canonical.fixed_vector(p1) != canonical.fixed_vector(p3))
        naive_mismatch += int(hashlib.sha256(canonical.naive_float_bytes(p1.tolist())).digest()
                              != hashlib.sha256(canonical.naive_float_bytes(p3.tolist())).digest())
        max_resid = max(max_resid, abs(S["expl"].base_value + p1.sum() - s1))
    n = len(Xenc)
    OUT["determinism"] = {
        "n": n, "replay_identical_pct": 100 * same / n,
        "benign_recompute_hash_mismatch_naive_pct": 100 * naive_mismatch / n,
        "benign_recompute_hash_mismatch_fixed_pct": 100 * fixed_mismatch / n,
        "max_additivity_residual_float": max_resid,
    }
    log("E3", OUT["determinism"])


# ============================================================================ E4 tamper detection
def e4_tamper(X, y, systems):
    S, A = systems[PRIMARY], systems[ALT_MODEL]
    sk = demo_signing_key()
    Xenc = S["codec"].encode(S["X_te"])
    st = salts(len(Xenc))
    # Substitute model explained with the SAME background and configuration
    alt_expl = PermutationShapley(lambda Z: A["model"].predict_proba(S["codec"].decode(Z))[:, 1],
                                  S["bg"], data.FEATURES, n_permutations=N_PERM, seed=2026)
    decisions = []
    for i, xe in enumerate(Xenc):
        s, p = S["expl"].explain(xe)
        sa, pa = alt_expl.explain(xe)
        decisions.append(Decision(xe, canonical.fixed_vector(xe), st[i], s, p, sa, pa))

    def make_ledger(gate):
        return Ledger(sk, S["fp"], S["expl"].config_digest, data.FEATURES, S["thr"],
                      epoch_size=EPOCH, gate=gate)

    ctx = Context(decisions, make_ledger, S["expl"].base_value, alt_expl.base_value,
                  data.FEATURES, data.PROTECTED, sk)
    input_store = {r["body"]["input_commitment"]: (d.salt, d.x_enc)
                   for r, d in zip(ctx.honest.records, decisions)}
    replayer = Replayer(S["fp"], S["expl"], input_store, S["thr"])
    for r in ctx.honest.records:      # warm the deterministic replay cache once
        replayer(r["body"])
    pk = sk.public_key()
    n = len(decisions)
    k_rc = max(1, round(RECEIPT_FRACTION * n))

    def detect(recs, wit, rcpts, checks, rng):
        presented = [rcpts[i] for i in rng.choice(sorted(rcpts), size=min(k_rc, len(rcpts)), replace=False)]
        return len(verify_ledger(recs, pk, checks=checks, witness_checkpoints=wit, receipts=presented,
                                 replayer=replayer, n_features=len(data.FEATURES))) > 0

    table, false_alarms = {}, {}
    rng_fa = np.random.default_rng(99)
    for lvl, checks in VERIFIER_LEVELS:   # honest ledger: false-alarm rate
        fa = [detect(ctx.honest.records, ctx.honest.witness.checkpoints, ctx.honest.receipts, checks, rng_fa)
              for _ in range(TRIALS)]
        false_alarms[lvl] = 100 * float(np.mean(fa))
    for a in ATTACKS:
        rng = np.random.default_rng(1000 + int(a[1:]))
        hits = {lvl: 0 for lvl, _ in VERIFIER_LEVELS}
        for _ in range(TRIALS):
            recs, wit, rcpts, t = run_attack(a, ctx, rng)
            sub = np.random.default_rng(int(rng.integers(2**31)))
            for lvl, checks in VERIFIER_LEVELS:
                hits[lvl] += detect(recs, wit, rcpts, checks, copy.deepcopy(sub))
        table[a] = {lvl: 100 * h / TRIALS for lvl, h in hits.items()}
        log("E4", a, table[a])
    OUT["tamper"] = {"trials": TRIALS, "ledger_size": n, "epoch_size": EPOCH,
                     "sealed": len(ctx.honest.witness.checkpoints) * EPOCH,
                     "receipts_presented": k_rc, "detection_pct": table, "false_alarm_pct": false_alarms,
                     "attacks": ATTACKS}
    rows = [{"attack": a, "description": ATTACKS[a], **table[a]} for a in ATTACKS]
    rows.append({"attack": "Honest", "description": "No tampering (false-alarm rate)", **false_alarms})
    pd.DataFrame(rows).to_csv(TAB / "tamper_detection.csv", index=False)
    ctx.replayer = replayer
    return ctx


# ============================================================================ E4b sealing-window sensitivity
WINDOW_EPOCHS = [32, 8, 1]
WINDOW_ATTACKS = ["A3", "A4", "A5", "A6"]
WINDOW_LEVELS = ["V4 +Anchored checkpoints", "V5 +Applicant receipts", "V7 TEXL (+Replay)"]


def e4b_window(ctx):
    """Insider rewrites succeed only inside the not-yet-sealed tail; measure how the epoch size closes it."""
    sk, pk = ctx.sk, ctx.sk.public_key()
    S0 = ctx.honest
    levels = dict(VERIFIER_LEVELS)
    n = len(ctx.decisions)
    k_rc = max(1, round(RECEIPT_FRACTION * n))
    res = {}
    for E in WINDOW_EPOCHS:
        def make_ledger(gate, E=E):
            return Ledger(sk, S0.model_fp, S0.explainer_cfg_digest, data.FEATURES, S0.threshold,
                          epoch_size=E, gate=gate)
        t0 = time.perf_counter()
        c = Context(ctx.decisions, make_ledger, ctx.base_value, ctx.alt_base_value, data.FEATURES,
                    data.PROTECTED, sk)
        build_ms = 1e3 * (time.perf_counter() - t0) / n
        sealed = len(c.honest.witness.checkpoints) * E
        row = {"epoch_size": E, "sealed": sealed, "unsealed_tail": n - sealed,
               "checkpoints": len(c.honest.witness.checkpoints), "build_ms_per_record": build_ms}

        def detect(recs, wit, rcpts, checks, rng):
            presented = [rcpts[i] for i in rng.choice(sorted(rcpts), size=min(k_rc, len(rcpts)), replace=False)]
            return len(verify_ledger(recs, pk, checks=checks, witness_checkpoints=wit, receipts=presented,
                                     replayer=ctx.replayer, n_features=len(data.FEATURES))) > 0

        rng_fa = np.random.default_rng(99)
        row["false_alarm_V7"] = 100 * float(np.mean(
            [detect(c.honest.records, c.honest.witness.checkpoints, c.honest.receipts,
                    levels["V7 TEXL (+Replay)"], rng_fa) for _ in range(TRIALS)]))
        for a in WINDOW_ATTACKS:
            rng = np.random.default_rng(1000 + int(a[1:]))
            hits = {lv: 0 for lv in WINDOW_LEVELS}
            for _ in range(TRIALS):
                recs, wit, rcpts, _t = run_attack(a, c, rng)
                sub = np.random.default_rng(int(rng.integers(2**31)))
                for lv in WINDOW_LEVELS:
                    hits[lv] += detect(recs, wit, rcpts, levels[lv], copy.deepcopy(sub))
            row[a] = {lv: 100 * h / TRIALS for lv, h in hits.items()}
        res[E] = row
        log("E4b", E, row)
    OUT["window"] = res
    pd.DataFrame([{"epoch_size": E, "unsealed_tail": r["unsealed_tail"], "checkpoints": r["checkpoints"],
                   **{f"{a} {lv.split()[0]}": r[a][lv] for a in WINDOW_ATTACKS for lv in WINDOW_LEVELS},
                   "false_alarm_V7": r["false_alarm_V7"]} for E, r in res.items()]
                 ).to_csv(TAB / "sealing_window.csv", index=False)


# ============================================================================ E5 fidelity / stability
def e5_stability(S, n_inst=40):
    Xenc = S["codec"].encode(S["X_te"])[:n_inst]
    ref = PermutationShapley(S["f"], S["bg"], data.FEATURES, n_permutations=256, seed=99)
    R = np.array([ref.explain(x)[1] for x in Xenc])
    ref_top = [set(np.argsort(-r)[:3]) for r in R]
    rows = []
    for P in [4, 8, 16, 32, 64]:
        for s in range(5):
            ex = PermutationShapley(S["f"], S["bg"], data.FEATURES, n_permutations=P, seed=s)
            t0 = time.perf_counter()
            E = np.array([ex.explain(x)[1] for x in Xenc])
            dt = (time.perf_counter() - t0) / n_inst
            mae = float(np.mean(np.abs(E - R)))
            top = float(np.mean([len(set(np.argsort(-e)[:3]) & rt) / 3 for e, rt in zip(E, ref_top)]))
            rho = float(np.mean([spearmanr(e, r).statistic for e, r in zip(E, R)]))
            rows.append({"P": P, "seed": s, "mae": mae, "top3_overlap": top, "spearman": rho, "ms": 1e3 * dt})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "explainer_stability.csv", index=False)
    g = df.groupby("P").agg(["mean", "std"])
    OUT["stability"] = {int(P): {k: [float(g.loc[P, (k, "mean")]), float(g.loc[P, (k, "std")])]
                                 for k in ["mae", "top3_overlap", "spearman", "ms"]} for P in g.index}
    log("E5", OUT["stability"])
    e5_shap(S, Xenc)


def e5_shap(S, Xenc=None):
    """Agreement with the SHAP library's KernelExplainer on the same background."""
    try:
        import shap
    except ImportError:
        OUT["shap_agreement"] = None
        log("E5", "shap not installed - KernelExplainer comparison skipped")
        return
    if Xenc is None:
        Xenc = S["codec"].encode(S["X_te"])
    E16 = np.array([S["expl"].explain(x)[1] for x in Xenc[:30]])
    np.random.seed(0)                      # KernelExplainer samples coalitions with NumPy's global RNG
    kern = shap.KernelExplainer(S["f"], S["bg"])
    K = np.array(kern.shap_values(Xenc[:30], nsamples=2048, silent=True))
    OUT["shap_agreement"] = {
        "n": 30,
        "spearman_mean": float(np.mean([spearmanr(a, b).statistic for a, b in zip(E16, K)])),
        "top3_overlap": float(np.mean([len(set(np.argsort(-a)[:3]) & set(np.argsort(-b)[:3])) / 3
                                       for a, b in zip(E16, K)])),
        "mae": float(np.mean(np.abs(E16 - K))),
    }
    log("E5", OUT["shap_agreement"])


# ============================================================================ E6 scalability
def e6_scale(ctx):
    sk = demo_signing_key()
    pk = sk.public_key()
    base = ctx.decisions
    res = {}
    for N in [1_000, 5_000, 20_000]:
        led = Ledger(sk, ctx.honest.model_fp, ctx.honest.explainer_cfg_digest, data.FEATURES,
                     ctx.honest.threshold, epoch_size=1024)
        t0 = time.perf_counter()
        for i in range(N):
            d = base[i % len(base)]
            body = led.build_body(d.x_fixed, d.salt, d.score, d.phi, ctx.base_value)
            led.append(body, d.salt, d.x_fixed)
        led.seal_epoch()
        t_app = time.perf_counter() - t0
        wit = led.witness.checkpoints
        t0 = time.perf_counter()
        f = verify_ledger(led.records, pk, checks=["hash", "chain", "sig", "anchor", "additivity"],
                          witness_checkpoints=wit)
        t_ver = time.perf_counter() - t0
        rc = led.receipts[N // 2]
        t_rc, _ = timeit(lambda: verify_receipt(rc, pk, wit), repeat=20)
        res[N] = {"append_s": t_app, "append_per_s": N / t_app, "verify_s": t_ver, "findings": len(f),
                  "receipt_ms": 1e3 * t_rc, "proof_len": len(rc["proof"])}
        log("E6", N, res[N])
    OUT["scale"] = res


# ============================================================================ figures
def figures(systems):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 9, "axes.titlesize": 9,
                         "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
                         "legend.fontsize": 8, "figure.dpi": 200})

    # Fig. 2 - example explanation recorded in the ledger
    rec = OUT["example"]["record"]["body"]
    att = pd.Series(rec["attributions"]).astype(float) / canonical.SCALE
    att = att.reindex(att.abs().sort_values(ascending=True).index)[-10:]
    fig, ax = plt.subplots(figsize=(3.4, 2.5))
    colors = ["#b2182b" if v > 0 else "#2166ac" for v in att.values]
    ax.barh(att.index, att.values, color=colors)
    ax.axvline(0, color="black", lw=0.6)
    ax.set_xlabel("Contribution to P(bad)")
    ax.set_title(f"Record {rec['seq']}: P(bad) = {rec['score']/1e6:.3f}, {rec['decision']}")
    fig.tight_layout()
    fig.savefig(FIG / "fig2_example_explanation.png")
    plt.close(fig)

    # Fig. 3 - explainer budget: error vs latency
    st = OUT["stability"]
    Ps = sorted(st)
    fig, ax1 = plt.subplots(figsize=(3.4, 2.3))
    ax1.errorbar(Ps, [1e3 * st[p]["mae"][0] for p in Ps], yerr=[1e3 * st[p]["mae"][1] for p in Ps],
                 marker="o", color="black", capsize=2, lw=1, ms=3, label="MAE vs reference (x1e-3)")
    ax1.set_xscale("log", base=2)
    ax1.set_xlabel("Permutations P (seeded, antithetic)")
    ax1.set_ylabel("Attribution MAE (x1e-3)")
    ax2 = ax1.twinx()
    ax2.plot(Ps, [st[p]["ms"][0] for p in Ps], marker="s", ls="--", color="grey", lw=1, ms=3,
             label="Latency (ms)")
    ax2.set_ylabel("Latency per decision (ms)")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper center", frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "fig3_explainer_budget.png")
    plt.close(fig)


def architecture_figure():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 8, "figure.dpi": 220})
    fig, ax = plt.subplots(figsize=(6.9, 2.55))
    ax.set_xlim(0, 100); ax.set_ylim(0, 40); ax.axis("off")

    def box(x, y, w, h, text, fc="#f2f2f2"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4", fc=fc, ec="black", lw=0.7))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=7.2, linespacing=1.15)

    def arrow(x1, y1, x2, y2, text=None, dy=1.2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", lw=0.7))
        if text:
            ax.text((x1 + x2) / 2, (y1 + y2) / 2 + dy, text, ha="center", fontsize=6.4, style="italic")

    box(0.5, 27, 12, 9, "(101) Applicant\ninput x")
    box(17, 27, 14, 9, "(102) Credit model f\n(any black box)\nfingerprint F(f)")
    box(35.5, 27, 15, 9, "(103) Seeded\npermutation-Shapley\nexplainer, config c")
    box(55, 27, 14, 9, "(104) Additivity gate\n|b + Σφ - f(x)| ≤ ε")
    box(73.5, 27, 26, 9, "(105) Canonical record r_i (fixed-point)\nprev = h_(i-1),  h_i = SHA-256(r_i)\nEd25519 signature on h_i")
    box(73.5, 13, 26, 9, "(106) Append-only ledger\n(hash chain) + epoch sealing\nMerkle root R_e (RFC 6962)", fc="#e6e6e6")
    box(44, 13, 22, 9, "(107) External witness\nsigned checkpoints\n(regulator / transparency log)")
    box(17, 13, 20, 9, "(108) Applicant receipt\nsigned r_i, salt s_i,\ninclusion proof π_i")
    box(0.5, 0.5, 30, 8.5, "(109) Applicant verifier: opens commitment,\nchecks signature, additivity, π_i against R_e")
    box(36, 0.5, 63.5, 8.5, "(110) Regulator verifier: hash, chain, signatures, anchored roots, receipts,\n"
                            "additivity, and deterministic REPLAY of f(x) and φ from F(f), c and the committed x")
    arrow(13, 31.5, 17, 31.5)
    arrow(31, 31.5, 35.5, 31.5, "f(x)")
    arrow(50.5, 31.5, 55, 31.5, "φ, b")
    arrow(69, 31.5, 73.5, 31.5, "pass")
    arrow(86.5, 27, 86.5, 22)
    arrow(73.5, 17.5, 66, 17.5, "R_e")
    arrow(44, 17.5, 37, 17.5, "π_i")
    arrow(27, 13, 20, 9)
    arrow(55, 13, 62, 9)
    arrow(86.5, 13, 86.5, 9)
    fig.tight_layout(pad=0.1)
    fig.savefig(FIG / "fig1_architecture.png")
    plt.close(fig)


def main():
    t0 = time.time()
    X, y = e0_data()
    e1_models(X, y)
    systems = e2_ledger_overhead(X, y)
    e3_determinism(systems[PRIMARY])
    ctx = e4_tamper(X, y, systems)
    e4b_window(ctx)
    e5_stability(systems[PRIMARY])
    e6_scale(ctx)
    architecture_figure()
    figures(systems)
    OUT["config"] = {"seed": SEED, "model_seeds": MODEL_SEEDS, "primary": PRIMARY, "alt_model": ALT_MODEL,
                     "n_permutations": N_PERM, "background_size": BG_SIZE, "epoch_size": EPOCH,
                     "trials": TRIALS, "receipt_fraction": RECEIPT_FRACTION, "explainer_seed": 2026,
                     "split": "70/15/15 stratified", "runtime_s": time.time() - t0}
    (RES / "results.json").write_text(json.dumps(OUT, indent=2, default=float))
    log(f"done in {time.time() - t0:.0f}s -> {RES / 'results.json'}")


def shap_only():
    """Add the KernelExplainer comparison to an existing results.json (deterministic; no other result changes)."""
    OUT.update(json.loads((RES / "results.json").read_text()))
    X, y = data.load()
    e5_shap(build_system(X, y, PRIMARY))
    OUT["environment"]["shap"] = _shap_version()
    (RES / "results.json").write_text(json.dumps(OUT, indent=2, default=float))
    log("updated", RES / "results.json")


if __name__ == "__main__":
    shap_only() if "--shap-only" in sys.argv else main()
