#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_validator import validate_file, detect_cycles, validate_merge

def write(tmp, name, text):
    p = Path(tmp) / name
    p.write_text(text, encoding="utf-8")
    return p

def test_clean_pass():
    with tempfile.TemporaryDirectory() as tmp:
        p = write(tmp, "m.haci", """# Memory
! m memory >
? m previous parser result >
The runtime initializes.
allocate scheduler
""")
        r = validate_file(p)
        assert r.ok, r.errors
        assert "m" in r.symbols

def test_plain_machine_line_not_object():
    with tempfile.TemporaryDirectory() as tmp:
        p = write(tmp, "runtime.haci", "allocate scheduler")
        r = validate_file(p)
        assert r.ok, r.errors
        assert r.nodes[0]["object"] is None
        assert r.nodes[0]["owner"] == "machine"

def test_undeclared_object():
    with tempfile.TemporaryDirectory() as tmp:
        p = write(tmp, "runtime.haci", "? x previous parser result >")
        r = validate_file(p)
        assert not r.ok
        assert any("UNDECLARED_OBJECT:x" in e for e in r.errors)

def test_empty_payload():
    with tempfile.TemporaryDirectory() as tmp:
        p = write(tmp, "m.haci", "? m >")
        r = validate_file(p)
        assert not r.ok
        assert any("EMPTY_PAYLOAD" in e for e in r.errors)

def test_authority_mutation():
    with tempfile.TemporaryDirectory() as tmp:
        p = write(tmp, "m.haci", """! m MEMORY >
! m MODEL >
""")
        r = validate_file(p)
        assert not r.ok
        assert any("AUTHORITY_MUTATION:m" in e or "DUPLICATE_OR_CONFLICTING_SYMBOL:m" in e for e in r.errors)

def test_code_fence_suspends_parser():
    with tempfile.TemporaryDirectory() as tmp:
        p = write(tmp, "runtime.haci", """# Runtime
```python
? x should not parse >
```
""")
        r = validate_file(p)
        assert r.ok, r.errors

def test_cycle_detection():
    cycles = detect_cycles([("m", "c"), ("c", "m")])
    assert cycles

def test_merge_failures():
    errors = validate_merge(
        og={"m": "memory", "ROOT": "core"},
        fss={"m": "model", "ROOT": "changed"},
        bss_requires=["n"]
    )
    assert "FSS_CONFLICT:m" in errors
    assert "AUTHORITY_MUTATION:ROOT" in errors
    assert "BSS_MISSING:n" in errors

if __name__ == "__main__":
    tests = [
        test_clean_pass,
        test_plain_machine_line_not_object,
        test_undeclared_object,
        test_empty_payload,
        test_authority_mutation,
        test_code_fence_suspends_parser,
        test_cycle_detection,
        test_merge_failures,
    ]
    for t in tests:
        t()
    print("PASS: HACI Validator v1.0 tests passed")
