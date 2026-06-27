#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v2_9 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "10_memory/m.haci", "! c pending ?")
    write(root, "20_code/c.haci", "! c code >")
    r = validate_project(root, strict=False)
    assert not any(e["from"].endswith("memory.m") and e["to"].endswith("code.c") for e in r.edges), r.edges

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "10_memory/m.haci", "! c pending ?")
    write(root, "20_code/c.haci", "! m pending ?")
    r = validate_project(root, strict=False)
    assert not any("DEPENDENCY_CYCLE" in e for e in r.errors), r.errors
    assert not r.edges, r.edges

print("PASS: prior v2.8 pending-declaration graph failure now fails closed")
