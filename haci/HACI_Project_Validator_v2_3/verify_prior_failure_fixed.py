#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v2_3 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha green >
m alpha yellow >
""")
    r = validate_project(root, strict=True)
    assert not r.ok, r.errors
    assert any("OPEN_CONVERSATION" in e for e in r.errors)
    assert any("RETURN_WITHOUT_OPEN_REQUEST" in e for e in r.errors)
print("PASS: prior torture-to-failure case now fails closed")
