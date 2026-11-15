"""Download the Statlog (German Credit Data) file from the UCI repository and print its SHA-256.

Dataset : H. Hofmann, "Statlog (German Credit Data)", UCI Machine Learning Repository, 1994.
DOI     : https://doi.org/10.24432/C5NC77         Licence: CC BY 4.0
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from texl import data  # noqa: E402

if __name__ == "__main__":
    path = data.download(force="--force" in sys.argv)
    print(path, hashlib.sha256(path.read_bytes()).hexdigest())
