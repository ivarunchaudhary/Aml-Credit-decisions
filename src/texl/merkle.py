"""Merkle Tree Hash and inclusion (audit) proofs as specified in RFC 6962 / RFC 9162.

Leaves are record hashes.  Leaf nodes are hashed as SHA-256(0x00 || leaf) and interior
nodes as SHA-256(0x01 || left || right) - the domain separation prevents second-preimage
attacks that swap leaves for interior nodes.
"""

from __future__ import annotations

import hashlib


def _h(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def leaf_hash(leaf: bytes) -> bytes:
    return _h(b"\x00" + leaf)


def node_hash(left: bytes, right: bytes) -> bytes:
    return _h(b"\x01" + left + right)


def _split(n: int) -> int:
    """Largest power of two strictly smaller than n (n >= 2)."""
    k = 1
    while k << 1 < n:
        k <<= 1
    return k


def _mth(leaves: list[bytes], lo: int, hi: int, memo: dict) -> bytes:
    key = (lo, hi)
    if key in memo:
        return memo[key]
    n = hi - lo
    if n == 0:
        out = _h(b"")
    elif n == 1:
        out = leaf_hash(leaves[lo])
    else:
        k = _split(n)
        out = node_hash(_mth(leaves, lo, lo + k, memo), _mth(leaves, lo + k, hi, memo))
    memo[key] = out
    return out


def mth(leaves: list[bytes], memo: dict | None = None) -> bytes:
    """Merkle Tree Hash MTH(D[n]) of RFC 6962 section 2.1."""
    return _mth(leaves, 0, len(leaves), {} if memo is None else memo)


def _path(m: int, leaves: list[bytes], lo: int, hi: int, memo: dict) -> list[bytes]:
    n = hi - lo
    if n == 1:
        return []
    k = _split(n)
    if m < k:
        return _path(m, leaves, lo, lo + k, memo) + [_mth(leaves, lo + k, hi, memo)]
    return _path(m - k, leaves, lo + k, hi, memo) + [_mth(leaves, lo, lo + k, memo)]


def inclusion_proof(m: int, leaves: list[bytes], memo: dict | None = None) -> list[bytes]:
    """Audit path PATH(m, D[n]) of RFC 6962 section 2.1.1.  Pass a shared ``memo`` when
    generating proofs for many leaves of the same tree (O(n log n) instead of O(n^2))."""
    if not 0 <= m < len(leaves):
        raise IndexError(m)
    return _path(m, leaves, 0, len(leaves), {} if memo is None else memo)


def verify_inclusion(leaf: bytes, index: int, tree_size: int, proof: list[bytes], root: bytes) -> bool:
    """RFC 9162, Section 2.1.3.2 verification algorithm."""
    if index >= tree_size:
        return False
    fn, sn = index, tree_size - 1
    r = leaf_hash(leaf)
    for p in proof:
        if sn == 0:
            return False
        if (fn & 1) or fn == sn:
            r = node_hash(p, r)
            if not (fn & 1):
                while not (fn & 1) and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root
