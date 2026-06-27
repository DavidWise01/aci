#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v2_7 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "10_memory/m.haci", "! m memory ?")
    write(root, "10_memory/m/parser/last.haci", "! last prior >")
    write(root, "20_runtime/runtime.haci", "? m.parser.last previous result >")
    r = validate_project(root, strict=False)
    assert not r.ok
    assert any("PENDING_PARENT_SCOPE" in e for e in r.errors)
    child = r.symbols["memory.m.parser.last"]
    assert "meaning" not in child, child
    assert child.get("blocked_commits"), child
print("PASS: prior v2.6 pending-parent failure now fails closed")
