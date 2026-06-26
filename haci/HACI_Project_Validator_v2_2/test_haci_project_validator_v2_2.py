#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v2_2 import validate_project, validate_merge

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

def ask_convs(r):
    return [c for c in r.conversations if c["kind"] == "conversation" and c["start"]["outbound"] == "ask"]

# Baseline v2.1 preservation tests.
def test_dual_edge_complete_in_strict():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >\n? m previous result >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        asks = ask_convs(r)
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
        asks = ask_convs(r)
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

def test_cross_file_pairing_order_independent_return_first():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "05_code/c.haci", "c helper ready >")
        write(tmp, "10_memory/m.haci", "? c helper")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        matches = [c for c in r.conversations if c["object"] == "code.c" and c["start"]["outbound"] == "ask"]
        assert matches and matches[0]["returns"]

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

# New v2.2 tests.
def test_phantom_dot_path_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >\n? m.parser.last previous result >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert any("DOT_PATH_NOT_FOUND:memory.m.parser.last" in e for e in r.errors), r.errors

def test_real_dot_path_passes():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >")
        write(tmp, "10_memory/m/parser/last.haci", "! last prior result >")
        write(tmp, "20_runtime/runtime.haci", "? m.parser.last previous result >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        assert "memory.m.parser.last" in r.symbols

def test_multiple_asks_pair_by_payload_not_fifo():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m first question
? m second question
m second answer >
m first answer >
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        convs = ask_convs(r)
        first = [c for c in convs if "first question" in c["start"]["payload"]][0]
        second = [c for c in convs if "second question" in c["start"]["payload"]][0]
        assert "first answer" in first["returns"][0]["payload"]
        assert "second answer" in second["returns"][0]["payload"]

def test_ambiguous_zero_score_returns_do_not_pair_silently():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha
? m beta
m gamma >
m delta >
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert any("OPEN_CONVERSATION" in e for e in r.errors)
        assert any("RETURN_WITHOUT_OPEN_REQUEST" in e for e in r.errors)

def test_strict_unmatched_return_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >\nm extra result >")
        loose = validate_project(Path(tmp), strict=False)
        strict = validate_project(Path(tmp), strict=True)
        assert loose.ok, loose.errors
        assert not strict.ok
        assert any("RETURN_WITHOUT_OPEN_REQUEST" in e for e in strict.errors), strict.errors

def test_heading_breaks_body_attachment():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m previous result >

# New Section
loose note
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        conv = ask_convs(r)[0]
        assert len(conv["body"]) == 0, conv["body"]

def test_blank_line_breaks_body_attachment():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m previous result >

loose note
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        conv = ask_convs(r)[0]
        assert len(conv["body"]) == 0, conv["body"]

def test_objectless_return_fails_cleanly():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "done >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert any("UNDECLARED_OBJECT:done" in e for e in r.errors)
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
        test_cross_file_pairing_order_independent_return_first,
        test_lowercase_human_and_uppercase_ai,
        test_scoped_symbols_and_ambiguous_alias,
        test_cycle_still_fails,
        test_code_fence_suspends_parser,
        test_empty_payload_still_fails,
        test_phantom_dot_path_fails,
        test_real_dot_path_passes,
        test_multiple_asks_pair_by_payload_not_fifo,
        test_ambiguous_zero_score_returns_do_not_pair_silently,
        test_strict_unmatched_return_fails,
        test_heading_breaks_body_attachment,
        test_blank_line_breaks_body_attachment,
        test_objectless_return_fails_cleanly,
        test_merge_helper,
    ]
    for t in tests:
        t()
    print("PASS: HACI Project Validator v2.2 tests passed")
