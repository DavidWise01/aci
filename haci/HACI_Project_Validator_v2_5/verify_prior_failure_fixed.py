#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v2_5 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "10_memory/m.haci", "! m memory ?")
    r = validate_project(root, strict=True)
    assert not r.ok
    sym = r.symbols["memory.m"]
    assert "meaning" not in sym, sym
    assert "authority" not in sym, sym
    assert sym.get("pending_declarations"), sym
print("PASS: prior v2.4 commit-gating failure now fails closed")
