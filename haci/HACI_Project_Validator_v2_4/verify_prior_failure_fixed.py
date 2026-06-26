#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v2_4 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "10_memory/m.haci", "? m clarify this ?")
    r = validate_project(root, strict=True)
    assert not r.ok
    assert any("INBOUND_QUESTION_UNRESOLVED" in e for e in r.errors)
    assert any("ASK_WITHOUT_RETURN" in e for e in r.errors)
print("PASS: prior v2.3 inbound-question failure now fails closed")
