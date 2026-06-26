#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v2_0 import validate_project, validate_merge

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

def test_case_swap_lowercase_human():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        n = next(n for n in r.nodes if n["outbound"] == "declare")
        assert n["owner"] == "human"
        assert n["authority"] == "human"

def test_uppercase_ai_warning():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "20_code/c.haci", "! c CODE >")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        assert any("AI_DECLARATION_NOT_HUMAN_AUTHORITY" in w for w in r.warnings)

def test_scoped_duplicate_stems_allowed():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/cache.haci", "! cache memory cache >")
        write(tmp, "20_code/cache.haci", "! cache code cache >")
        r = validate_project(Path(tmp))
        # Bare alias "cache" is ambiguous only when referenced; declarations in their own files resolve canonical by creation/enrichment.
        assert r.ok, r.errors
        assert "memory.cache" in r.symbols
        assert "code.cache" in r.symbols

def test_ambiguous_bare_reference_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/cache.haci", "! cache memory cache >")
        write(tmp, "20_code/cache.haci", "! cache code cache >")
        write(tmp, "30_runtime/runtime.haci", "? cache status >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert any("AMBIGUOUS_OBJECT:cache" in e for e in r.errors), r.errors

def test_canonical_reference_passes():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/cache.haci", "! cache memory cache >")
        write(tmp, "20_code/cache.haci", "! cache code cache >")
        write(tmp, "30_runtime/runtime.haci", "? memory.cache status >")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        assert any(e["to"] == "memory.cache" for e in r.edges)

def test_body_after_dual_edge_preserved():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """! m memory >
? m previous result >
search index
rank context
""")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        convs = [c for c in r.conversations if c["start"]["outbound"] == "ask"]
        assert convs
        assert len(convs[0]["body"]) == 2

def test_cross_file_conversation_pairing():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? c helper")
        write(tmp, "20_code/c.haci", "c helper ready >")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        convs = [c for c in r.conversations if c["object"] == "code.c"]
        assert convs
        assert convs[0]["returns"], convs

def test_strict_mode_fails_open_conversation():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? m previous parser result")
        loose = validate_project(Path(tmp), strict=False)
        strict = validate_project(Path(tmp), strict=True)
        assert loose.ok, loose.errors
        assert not strict.ok
        assert any("OPEN_CONVERSATION" in e for e in strict.errors)

def test_cycle_still_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? c helper >")
        write(tmp, "20_code/c.haci", "? m memory >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert any("DEPENDENCY_CYCLE" in e for e in r.errors), r.errors

def test_code_fence_suspends_parser():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "30_runtime/runtime.haci", "```python\n? x ignored >\n```")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        assert len(r.conversations) == 0

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
    tests = [
        test_case_swap_lowercase_human,
        test_uppercase_ai_warning,
        test_scoped_duplicate_stems_allowed,
        test_ambiguous_bare_reference_fails,
        test_canonical_reference_passes,
        test_body_after_dual_edge_preserved,
        test_cross_file_conversation_pairing,
        test_strict_mode_fails_open_conversation,
        test_cycle_still_fails,
        test_code_fence_suspends_parser,
        test_merge_helper,
    ]
    for t in tests:
        t()
    print("PASS: HACI Project Validator v2.0 tests passed")
