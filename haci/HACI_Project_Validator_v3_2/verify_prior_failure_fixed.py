#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v3_2 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    write(root, "10_memory/m.haci", """? m alpha problem
m alpha evidence one >
m alpha evidence two >
""")
    r = validate_project(root, strict=True)
    assert r.ok, r.errors
    convs = [c for c in r.conversations if c["kind"] == "conversation" and c["start"]["outbound"] == "ask"]
    conv = convs[0]
    assert sum(1 for ret in conv["returns"] if ret["inbound"] == "observe") == 2, conv

print("PASS: prior v3.1 multi-evidence failure now preserves both > returns")
