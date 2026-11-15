#!/usr/bin/env bash
# One-command reproduction of every result in the report.
#   ./run_all.sh            -> data, tests, experiments, executed notebook, report + disclosure
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-.venv/bin/python}

if [ ! -x "$PY" ]; then
  echo "Creating virtual environment (.venv, Python 3.11)"
  python3.11 -m venv .venv
  .venv/bin/pip install -r requirements-lock.txt
fi

$PY scripts/download_data.py
$PY -m pytest -q tests
$PY scripts/run_experiments.py
$PY notebooks/make_notebook.py
$PY -m jupyter nbconvert --to notebook --execute --inplace notebooks/TEXL_PoC.ipynb \
    --ExecutePreprocessor.timeout=1200
$PY report/build_report.py
$PY disclosure/build_disclosure.py
echo "All artefacts regenerated (results/, notebooks/, report/, disclosure/)."
