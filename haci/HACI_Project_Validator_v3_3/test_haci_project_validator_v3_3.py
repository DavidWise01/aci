#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v3_3 import validate_project, validate_merge

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

def ask_convs(r):
    return [c for c in r.conversations if c["kind"] == "conversation" and c["start"]["outbound"] == "ask"]

def has_error(r, token):
    return any(token in e for e in r.errors)

def has_warning(r, token):
    return any(token in w for w in r.warnings)

def has_diag(c, token):
    return token in c.get("diagnostics", [])

def edge_exists(r, src_suffix, dst_suffix):
    return any(e["from"].endswith(src_suffix) and e["to"].endswith(dst_suffix) for e in r.edges)

def count_returns(conv, inbound):
    return sum(1 for ret in conv.get("returns", []) if ret.get("inbound") == inbound)

# v3.3 multi commit-return tests

def test_multiple_commit_returns_same_ask_pass():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha approval
m alpha accepted !
m alpha committed !
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        conv = ask_convs(r)[0]
        assert count_returns(conv, "declare") == 2, conv
        assert has_diag(conv, "COMMIT_RETURN_PAIR"), conv

def test_multiple_cross_file_commit_returns_same_ask_pass():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "00_scope/m.haci", "! m memory >")
        write(tmp, "10_runtime/ask.haci", "? m alpha approval")
        write(tmp, "20_returns/c1.haci", "m alpha accepted !")
        write(tmp, "21_returns/c2.haci", "m alpha committed !")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        conv = ask_convs(r)[0]
        assert count_returns(conv, "declare") == 2, conv

def test_commit_returns_distribute_to_unique_asks():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha red approval
? m beta blue approval
m alpha red accepted !
m beta blue committed !
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        convs = ask_convs(r)
        alpha = [c for c in convs if "alpha red" in c["start"]["payload"]][0]
        beta = [c for c in convs if "beta blue" in c["start"]["payload"]][0]
        assert count_returns(alpha, "declare") == 1, alpha
        assert count_returns(beta, "declare") == 1, beta

def test_ambiguous_commit_return_still_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha red approval
? m alpha blue approval
m alpha approved !
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "RETURN_WITHOUT_OPEN_REQUEST"), r.errors

def test_zero_score_single_accepted_fallback_still_passes():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m approve deployment
m accepted !
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        conv = ask_convs(r)[0]
        assert count_returns(conv, "declare") == 1, conv
        assert has_diag(conv, "ACCEPTED_RETURN_PAIR"), conv

def test_zero_score_multiple_accepted_fallback_still_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m approve deployment
m accepted !
m committed !
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "RETURN_WITHOUT_OPEN_REQUEST"), r.errors

# v3.2 multi evidence preservation

def test_multiple_evidence_returns_same_ask_pass():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha problem
m alpha evidence one >
m alpha evidence two >
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        conv = ask_convs(r)[0]
        assert count_returns(conv, "observe") == 2, conv

def test_multiple_cross_file_evidence_returns_same_ask_pass():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "00_scope/m.haci", "! m memory >")
        write(tmp, "10_runtime/ask.haci", "? m alpha problem")
        write(tmp, "20_returns/e1.haci", "m alpha evidence one >")
        write(tmp, "21_returns/e2.haci", "m alpha evidence two >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        conv = ask_convs(r)[0]
        assert count_returns(conv, "observe") == 2, conv

def test_ambiguous_evidence_return_still_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha evidence >
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "RETURN_WITHOUT_OPEN_REQUEST"), r.errors

# v3.1 multi question preservation

def test_multiple_return_questions_same_ask_pass():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha problem
m alpha clarify scope ?
m alpha clarify detail ?
m alpha answer >
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        conv = ask_convs(r)[0]
        assert count_returns(conv, "ask") == 2, conv
        assert count_returns(conv, "observe") == 1, conv

def test_multiple_question_evidence_commit_same_ask_pass():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha approval problem
m alpha clarify scope ?
m alpha evidence one >
m alpha accepted !
m alpha committed !
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        conv = ask_convs(r)[0]
        assert count_returns(conv, "ask") == 1, conv
        assert count_returns(conv, "observe") == 1, conv
        assert count_returns(conv, "declare") == 2, conv

def test_ambiguous_return_question_still_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha clarify ?
m alpha red >
m alpha blue >
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST"), r.errors

# v3.0 chronology preservation

def test_same_file_return_before_ask_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """m alpha answer >
? m alpha question
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "SAME_FILE_RETURN_BEFORE_ASK"), r.errors

def test_same_file_accepted_return_before_ask_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """m accepted !
? m approve deployment
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "SAME_FILE_RETURN_BEFORE_ASK"), r.errors

def test_same_file_return_question_before_ask_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """m alpha clarify ?
? m alpha problem
m alpha answer >
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "SAME_FILE_RETURN_BEFORE_ASK"), r.errors

def test_cross_file_return_before_ask_allowed():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "00_scope/m.haci", "! m memory >")
        write(tmp, "10_returns/returns.haci", "m alpha answer >")
        write(tmp, "20_runtime/ask.haci", "? m alpha question")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors

# v2.9 graph gate preservation

def test_pending_declaration_does_not_create_dependency_edge():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! c pending ?")
        write(tmp, "20_code/c.haci", "! c code >")
        r = validate_project(Path(tmp), strict=False)
        assert not edge_exists(r, "memory.m", "code.c"), r.edges
        assert has_warning(r, "DECLARATION_PENDING_NOT_COMMITTED"), r.warnings
        assert r.ok, r.errors

def test_pending_declarations_do_not_create_dependency_cycle():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! c pending ?")
        write(tmp, "20_code/c.haci", "! m pending ?")
        r = validate_project(Path(tmp), strict=False)
        assert not has_error(r, "DEPENDENCY_CYCLE"), r.errors
        assert not r.edges, r.edges
        assert r.ok, r.errors

def test_committed_declaration_still_creates_dependency_edge_without_conflict():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! c code >")
        write(tmp, "20_code/c.haci", "! c code >")
        r = validate_project(Path(tmp), strict=False)
        assert edge_exists(r, "memory.m", "code.c"), r.edges
        assert r.ok, r.errors

def test_real_ask_still_creates_dependency_edge():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? c status >")
        write(tmp, "20_code/c.haci", "! c code >")
        r = validate_project(Path(tmp), strict=False)
        assert edge_exists(r, "memory.m", "code.c"), r.edges

# v2.8/v2.7/v2.5/v2.4 preservation

def test_payload_specific_return_question_pairs_with_matching_ask():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha problem
? m beta problem
m alpha clarify ?
m beta answer >
m alpha answer >
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors

def test_pending_parent_blocks_child_commit_even_loose():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory ?")
        write(tmp, "10_memory/m/parser/last.haci", "! last prior >")
        write(tmp, "20_runtime/runtime.haci", "? m.parser.last previous result >")
        r = validate_project(Path(tmp), strict=False)
        assert not r.ok, r.errors
        assert has_error(r, "PENDING_PARENT_SCOPE"), r.errors
        child = r.symbols["memory.m.parser.last"]
        assert "meaning" not in child, child

def test_unresolved_question_declaration_does_not_commit_symbol_authority():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory ?")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        sym = r.symbols["memory.m"]
        assert "meaning" not in sym, sym
        assert "authority" not in sym, sym

def test_inbound_question_does_not_complete_ask():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? m clarify this ?")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "INBOUND_QUESTION_UNRESOLVED"), r.errors

# v2.3/v2.2 preservation

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

def test_ambiguous_positive_return_pairing_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha green >
m alpha yellow >
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "RETURN_WITHOUT_OPEN_REQUEST"), r.errors

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
        test_multiple_commit_returns_same_ask_pass,
        test_multiple_cross_file_commit_returns_same_ask_pass,
        test_commit_returns_distribute_to_unique_asks,
        test_ambiguous_commit_return_still_fails_closed,
        test_zero_score_single_accepted_fallback_still_passes,
        test_zero_score_multiple_accepted_fallback_still_fails,
        test_multiple_evidence_returns_same_ask_pass,
        test_multiple_cross_file_evidence_returns_same_ask_pass,
        test_ambiguous_evidence_return_still_fails_closed,
        test_multiple_return_questions_same_ask_pass,
        test_multiple_question_evidence_commit_same_ask_pass,
        test_ambiguous_return_question_still_fails_closed,
        test_same_file_return_before_ask_rejected,
        test_same_file_accepted_return_before_ask_rejected,
        test_same_file_return_question_before_ask_rejected,
        test_cross_file_return_before_ask_allowed,
        test_pending_declaration_does_not_create_dependency_edge,
        test_pending_declarations_do_not_create_dependency_cycle,
        test_committed_declaration_still_creates_dependency_edge_without_conflict,
        test_real_ask_still_creates_dependency_edge,
        test_payload_specific_return_question_pairs_with_matching_ask,
        test_pending_parent_blocks_child_commit_even_loose,
        test_unresolved_question_declaration_does_not_commit_symbol_authority,
        test_inbound_question_does_not_complete_ask,
        test_phantom_dot_path_fails,
        test_real_dot_path_passes,
        test_multiple_asks_pair_by_payload_not_fifo,
        test_ambiguous_positive_return_pairing_fails,
        test_scoped_symbols_ambiguity,
        test_cycle_still_fails,
        test_code_fence_suspends_parser,
        test_merge_helper,
    ]
    for t in tests:
        t()
    print("PASS: HACI Project Validator v3.3 tests passed")
