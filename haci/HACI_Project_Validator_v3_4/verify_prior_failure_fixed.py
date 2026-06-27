#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v3_4 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "10_memory/m/parser/last.haci", "! last prior >")
    r = validate_project(root, strict=True)
    assert not r.ok, r.errors
    assert any("MISSING_PARENT_SCOPE" in e for e in r.errors), r.errors
    child = r.symbols["memory.m.parser.last"]
    assert "meaning" not in child, child
    assert child["commit_state"] == "blocked_missing_parent", child

print("PASS: prior v3.3 missing-parent failure now fails closed")
