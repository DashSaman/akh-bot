"""64-bit SimHash over word shingles — stage 4 cheap near-duplicate screen."""
from __future__ import annotations

import hashlib

from .textnorm import normalize_text_for_hash


def _shingles(text: str, size: int = 3) -> list[str]:
    words = text.split()
    if len(words) < size:
        return [" ".join(words)] if words else []
    return [" ".join(words[i : i + size]) for i in range(len(words) - size + 1)]


def simhash64(text: str) -> int:
    bits = [0] * 64
    for sh in _shingles(normalize_text_for_hash(text)):
        digest = hashlib.md5(sh.encode()).digest()
        h = int.from_bytes(digest[:8], "big")
        for i in range(64):
            bits[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(64):
        if bits[i] > 0:
            out |= 1 << i
    return out


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def likely_near_duplicate(a: int, b: int, threshold: int = 6) -> bool:
    """Threshold 6/64 balances Persian headline variants vs different stories."""
    return hamming_distance(a, b) <= threshold
