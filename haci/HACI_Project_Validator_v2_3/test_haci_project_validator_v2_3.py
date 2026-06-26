#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v2_3 import validate_project, validate_merge

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

def ask_convs(r):
    return [c for c in r.conversations if c["kind"] == "conversation" and c["start"]["outbound"] == "ask"]

def has_error(r, token):
    return any(token in e for e in r.errors)

def has_diag(c, token):
    return token in c.get("diagnostics", [])

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

def test_declaration_does_not_remain_open():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        decs = [c for c in r.conversations if c["kind"] == "declaration"]
        assert decs and decs[0]["complete"] is True

def test_cross_file_pairing_positive_unique_return_first():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "05_code/c.haci", "c helper ready >")
        write(tmp, "10_memory/m.haci", "? c helper")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        matches = [c for c in ask_convs(r) if c["object"] == "code.c"]
        assert matches and matches[0]["returns"]

def test_phantom_dot_path_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >\n? m.parser.last previous result >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert has_error(r, "DOT_PATH_NOT_FOUND"), r.errors

def test_real_dot_path_passes():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >")
        write(tmp, "10_memory/m/parser/last.haci", "! last prior result >")
        write(tmp, "20_runtime/runtime.haci", "? m.parser.last previous result >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors

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
        assert has_error(r, "OPEN_CONVERSATION")
        assert has_error(r, "RETURN_WITHOUT_OPEN_REQUEST")

def test_strict_unmatched_return_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >\nm extra result >")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "RETURN_WITHOUT_OPEN_REQUEST"), r.errors

def test_heading_and_blank_break_body_attachment_with_real_match_token():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m needle

# New Section
loose note
m needle >
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        assert len(ask_convs(r)[0]["body"]) == 0

def test_scoped_symbols_ambiguity():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/cache.haci", "! cache memory cache >")
        write(tmp, "20_code/cache.haci", "! cache code cache >")
        write(tmp, "30_runtime/runtime.haci", "? cache ambiguous >")
        r = validate_project(Path(tmp))
        assert not r.ok and has_error(r, "AMBIGUOUS_OBJECT:cache"), r.errors

def test_cycle_still_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? c helper >")
        write(tmp, "20_code/c.haci", "? m memory >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert has_error(r, "DEPENDENCY_CYCLE"), r.errors

def test_code_fence_suspends_parser():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "30_runtime/runtime.haci", "```python\n? x ignored >\n```")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok and len(r.conversations) == 0, r.errors

def test_ambiguous_positive_return_pairing_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha green >
m alpha yellow >
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok, "ambiguous tie should not pass strict mode"
        convs = ask_convs(r)
        assert any(has_diag(c, "AMBIGUOUS_RETURN_PAIR") for c in convs), convs
        assert has_error(r, "OPEN_CONVERSATION")
        assert has_error(r, "RETURN_WITHOUT_OPEN_REQUEST")

def test_mutual_unique_best_still_pairs():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha blue >
m alpha red >
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        convs = ask_convs(r)
        red = [c for c in convs if "red" in c["start"]["payload"]][0]
        blue = [c for c in convs if "blue" in c["start"]["payload"]][0]
        assert "red" in red["returns"][0]["payload"]
        assert "blue" in blue["returns"][0]["payload"]

def test_single_no_overlap_does_not_weak_pair_anymore():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha
m zulu >
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "OPEN_CONVERSATION")
        assert has_error(r, "RETURN_WITHOUT_OPEN_REQUEST")

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
        test_cross_file_pairing_positive_unique_return_first,
        test_phantom_dot_path_fails,
        test_real_dot_path_passes,
        test_multiple_asks_pair_by_payload_not_fifo,
        test_ambiguous_zero_score_returns_do_not_pair_silently,
        test_strict_unmatched_return_fails,
        test_heading_and_blank_break_body_attachment_with_real_match_token,
        test_scoped_symbols_ambiguity,
        test_cycle_still_fails,
        test_code_fence_suspends_parser,
        test_ambiguous_positive_return_pairing_fails,
        test_mutual_unique_best_still_pairs,
        test_single_no_overlap_does_not_weak_pair_anymore,
        test_merge_helper,
    ]
    for t in tests:
        t()
    print("PASS: HACI Project Validator v2.3 tests passed")
