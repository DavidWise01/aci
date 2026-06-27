#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v2_6 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "10_memory/m.haci", "? m approve deployment\nm accepted !\n")
    r = validate_project(root, strict=True)
    assert r.ok, r.errors

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "10_memory/m.haci", "? m approve deployment\n? m approve deployment\nm accepted !\n")
    r = validate_project(root, strict=True)
    assert not r.ok

print("PASS: prior v2.5 accepted-return failure now closes only when unique")
