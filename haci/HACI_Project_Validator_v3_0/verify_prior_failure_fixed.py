#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v3_0 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "10_memory/m.haci", "m alpha answer >\n? m alpha question\n")
    r = validate_project(root, strict=True)
    assert not r.ok
    assert any("SAME_FILE_RETURN_BEFORE_ASK" in e for e in r.errors), r.errors

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "00_scope/m.haci", "! m memory >")
    write(root, "10_returns/returns.haci", "m alpha answer >")
    write(root, "20_runtime/ask.haci", "? m alpha question")
    r = validate_project(root, strict=True)
    assert r.ok, r.errors

print("PASS: prior v2.9 same-file chronology failure now fails closed")
