"""Canonical serialization + hashing — one byte-representation, shared by every
layer so substrate equality is exact and result hashes are reproducible."""
import json, hashlib

def canon(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            ).encode("utf-8") + b"\n"

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
