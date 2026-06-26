#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator import validate_project, validate_merge

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

def test_clean_project_pass():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "00_core/root.haci", "! root CORE >")
        write(tmp, "10_memory/m.haci", "! m memory >")
        write(tmp, "20_runtime/runtime.haci", "? m previous parser result >\nallocate scheduler")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        assert "m" in r.symbols
        assert any(e["to"] == "m" for e in r.edges)

def test_cross_file_undeclared_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "20_runtime/runtime.haci", "? x previous parser result >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert any("UNDECLARED_OBJECT:x" in e for e in r.errors)

def test_empty_payload_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? m >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert any("EMPTY_PAYLOAD" in e for e in r.errors)

def test_duplicate_file_symbol_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >")
        write(tmp, "30_model/m.haci", "! m model >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert any("DUPLICATE_FILE_SYMBOL:m" in e for e in r.errors)

def test_cycle_detection_wired():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? c build helper >")
        write(tmp, "20_code/c.haci", "? m previous result >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert any("DEPENDENCY_CYCLE" in e for e in r.errors), r.errors

def test_code_fence_suspends_parser():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "20_runtime/runtime.haci", "```python\n? x ignored >\n```")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors

def test_merge_helper():
    errors = validate_merge(
        og={"m": "memory", "ROOT": "core"},
        fss={"m": "model", "ROOT": "changed"},
        bss_requires=["n"]
    )
    assert "FSS_CONFLICT:m" in errors
    assert "AUTHORITY_MUTATION:ROOT" in errors
    assert "BSS_MISSING:n" in errors

if __name__ == "__main__":
    for test in [
        test_clean_project_pass,
        test_cross_file_undeclared_fails,
        test_empty_payload_fails,
        test_duplicate_file_symbol_fails,
        test_cycle_detection_wired,
        test_code_fence_suspends_parser,
        test_merge_helper,
    ]:
        test()
    print("PASS: HACI Project Validator v1.1 tests passed")
