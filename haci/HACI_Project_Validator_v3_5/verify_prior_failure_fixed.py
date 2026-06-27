#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v3_5 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "10_memory/m/parser/last.haci", "! last prior >")
    write(root, "20_runtime/runtime.haci", "? memory.m.parser.last previous result >")
    r = validate_project(root, strict=True)
    assert not r.ok, r.errors
    assert any("MISSING_PARENT_SCOPE" in e for e in r.errors), r.errors
    assert not any(e["to"].endswith("memory.m.parser.last") for e in r.edges), r.edges
    assert any("BLOCKED_SYMBOL_EDGE_PURGED" in w for w in r.warnings), r.warnings

print("PASS: prior v3.4 blocked-symbol graph-edge failure now purges the edge")
