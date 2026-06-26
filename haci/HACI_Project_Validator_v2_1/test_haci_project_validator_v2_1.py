#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v2_1 import validate_project, validate_merge

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

def convs_for(r, obj=None, kind=None):
    out = r.conversations
    if obj is not None:
        out = [c for c in out if c["object"] == obj]
    if kind is not None:
        out = [c for c in out if c["kind"] == kind]
    return out

def test_dual_edge_complete_in_strict():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >\n? m previous result >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        asks = [c for c in r.conversations if c["start"]["outbound"] == "ask"]
        assert asks and asks[0]["complete"] is True and asks[0]["unresolved"] is False

def test_body_after_dual_edge_preserved_and_not_unresolved():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """! m memory >
? m previous result >
search index
rank context
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        asks = [c for c in r.conversations if c["start"]["outbound"] == "ask"]
        assert len(asks) == 1
        assert len(asks[0]["body"]) == 2
        assert asks[0]["complete"] is True
        assert asks[0]["unresolved"] is False

def test_declaration_does_not_remain_open():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        assert not any("OPEN_CONVERSATION" in w for w in r.warnings)
        decs = [c for c in r.conversations if c["kind"] == "declaration"]
        assert decs and decs[0]["complete"] is True and decs[0]["unresolved"] is False

def test_declaration_body_attaches_but_still_not_unresolved():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """! m memory >
The memory object stores prior context.
index prior sessions
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        dec = [c for c in r.conversations if c["kind"] == "declaration"][0]
        assert len(dec["body"]) == 2
        assert dec["unresolved"] is False

def test_cross_file_pairing_order_independent_return_first():
    with tempfile.TemporaryDirectory() as tmp:
        # Return sorts before request but must still pair.
        write(tmp, "05_code/c.haci", "c helper ready >")
        write(tmp, "10_memory/m.haci", "? c helper")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        matches = [c for c in r.conversations if c["object"] == "code.c" and c["start"]["outbound"] == "ask"]
        assert matches, r.conversations
        assert matches[0]["returns"], matches[0]
        assert matches[0]["complete"] is True

def test_cross_file_pairing_request_first():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? c helper")
        write(tmp, "20_code/c.haci", "c helper ready >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        matches = [c for c in r.conversations if c["object"] == "code.c" and c["start"]["outbound"] == "ask"]
        assert matches and matches[0]["returns"]

def test_unresolved_ask_warns_non_strict_fails_strict_once():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? m previous parser result")
        loose = validate_project(Path(tmp), strict=False)
        strict = validate_project(Path(tmp), strict=True)
        assert loose.ok, loose.errors
        assert not strict.ok
        assert sum(1 for e in strict.errors if "OPEN_CONVERSATION" in e) == 1
        assert len(strict.errors) == len(set(strict.errors))

def test_warnings_deduped():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? m previous parser result")
        r = validate_project(Path(tmp), strict=False)
        assert len(r.warnings) == len(set(r.warnings)), r.warnings

def test_lowercase_human_and_uppercase_ai():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >")
        write(tmp, "20_code/c.haci", "! c CODE >")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        m = next(n for n in r.nodes if n["object"] == "m")
        c = next(n for n in r.nodes if n["object"] == "c")
        assert m["owner"] == "human" and m["authority"] == "human"
        assert c["owner"] == "ai" and c["authority"] == "ai"
        assert any("AI_DECLARATION_NOT_HUMAN_AUTHORITY" in w for w in r.warnings)

def test_scoped_symbols_and_ambiguous_alias():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/cache.haci", "! cache memory cache >")
        write(tmp, "20_code/cache.haci", "! cache code cache >")
        ok = validate_project(Path(tmp))
        assert ok.ok, ok.errors
        assert "memory.cache" in ok.symbols
        assert "code.cache" in ok.symbols

        write(tmp, "30_runtime/runtime.haci", "? cache ambiguous >")
        bad = validate_project(Path(tmp))
        assert not bad.ok
        assert any("AMBIGUOUS_OBJECT:cache" in e for e in bad.errors)

def test_canonical_reference_passes():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/cache.haci", "! cache memory cache >")
        write(tmp, "20_code/cache.haci", "! cache code cache >")
        write(tmp, "30_runtime/runtime.haci", "? memory.cache status >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        assert any(e["to"] == "memory.cache" for e in r.edges)

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

def test_empty_payload_still_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? m >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert any("EMPTY_PAYLOAD" in e for e in r.errors)

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
        test_dual_edge_complete_in_strict,
        test_body_after_dual_edge_preserved_and_not_unresolved,
        test_declaration_does_not_remain_open,
        test_declaration_body_attaches_but_still_not_unresolved,
        test_cross_file_pairing_order_independent_return_first,
        test_cross_file_pairing_request_first,
        test_unresolved_ask_warns_non_strict_fails_strict_once,
        test_warnings_deduped,
        test_lowercase_human_and_uppercase_ai,
        test_scoped_symbols_and_ambiguous_alias,
        test_canonical_reference_passes,
        test_cycle_still_fails,
        test_code_fence_suspends_parser,
        test_empty_payload_still_fails,
        test_merge_helper,
    ]
    for t in tests:
        t()
    print("PASS: HACI Project Validator v2.1 tests passed")
