#!/usr/bin/env bash
# One-command reproduction of every result in the report.
#   ./run_all.sh            -> data, tests, experiments, executed notebook, report + disclosure
set -euo pipefail
if [[ $# -gt 1 || (${1:-} != "" && ${1:-} != "--no-pdf") ]]; then
  echo "Usage: $0 [--no-pdf]" >&2
  exit 2
fi
cd "$(dirname "$0")"
PY=${PY:-.venv/bin/python}

if [ ! -x "$PY" ]; then
  echo "Creating virtual environment (.venv, Python 3.11)"
  python3.11 -m venv .venv
  .venv/bin/python -m pip install -r requirements-lock.txt
  PY=.venv/bin/python
fi

"$PY" scripts/download_data.py
"$PY" -m pytest -q tests
"$PY" scripts/run_experiments.py
"$PY" notebooks/make_notebook.py
"$PY" -m nbconvert --to notebook --execute --inplace notebooks/TEXL_PoC.ipynb \
    --ExecutePreprocessor.timeout=1200
"$PY" report/build_report.py "$@"
"$PY" disclosure/build_disclosure.py "$@"
echo "Results, executed notebook, and DOCX files regenerated."
