#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v3_1 import validate_project, validate_merge

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

def q_count(conv):
    return sum(1 for ret in conv.get("returns", []) if ret.get("inbound") == "ask")

# v3.1 multi return-question tests

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
        assert q_count(conv) == 2, conv
        assert any(ret["inbound"] == "observe" and "alpha answer" in ret["payload"] for ret in conv["returns"]), conv

def test_multiple_cross_file_return_questions_same_ask_pass():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "00_scope/m.haci", "! m memory >")
        write(tmp, "10_runtime/ask.haci", "? m alpha problem")
        write(tmp, "20_returns/q1.haci", "m alpha clarify scope ?")
        write(tmp, "21_returns/q2.haci", "m alpha clarify detail ?")
        write(tmp, "30_returns/a.haci", "m alpha answer >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        conv = ask_convs(r)[0]
        assert q_count(conv) == 2, conv

def test_multiple_return_questions_distribute_to_unique_asks():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha scope problem
? m beta detail problem
m alpha scope clarify ?
m beta detail clarify ?
m alpha scope answer >
m beta detail answer >
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        convs = ask_convs(r)
        alpha = [c for c in convs if "alpha scope" in c["start"]["payload"]][0]
        beta = [c for c in convs if "beta detail" in c["start"]["payload"]][0]
        assert q_count(alpha) == 1, alpha
        assert q_count(beta) == 1, beta
        assert "alpha scope clarify" in alpha["returns"][0]["payload"], alpha
        assert "beta detail clarify" in beta["returns"][0]["payload"], beta

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

def test_zero_score_return_question_still_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha problem
m gamma clarify ?
m alpha answer >
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

def test_same_file_normal_order_still_passes():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha question
m alpha answer >
""")
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

# v2.8 return-question preservation

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
        convs = ask_convs(r)
        alpha = [c for c in convs if "alpha problem" in c["start"]["payload"]][0]
        beta = [c for c in convs if "beta problem" in c["start"]["payload"]][0]
        assert any(ret["inbound"] == "ask" and "alpha clarify" in ret["payload"] for ret in alpha["returns"]), alpha
        assert any(ret["inbound"] == "observe" and "alpha answer" in ret["payload"] for ret in alpha["returns"]), alpha
        assert any(ret["inbound"] == "observe" and "beta answer" in ret["payload"] for ret in beta["returns"]), beta

def test_return_question_after_answer_fails_strict():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha problem
m alpha answer >
m alpha clarify ?
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "LATE_RETURN_QUESTION_AFTER_COMPLETION"), r.errors

def test_return_question_before_answer_passes():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha problem
m alpha clarify ?
m alpha answer >
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors

# v2.7 pending-parent preservation

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
        assert child.get("commit_state") == "blocked_pending_parent", child

def test_committed_parent_allows_child_commit():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >")
        write(tmp, "10_memory/m/parser/last.haci", "! last prior >")
        write(tmp, "20_runtime/runtime.haci", "? m.parser.last previous result >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        child = r.symbols["memory.m.parser.last"]
        assert child.get("meaning") == "prior"
        assert child.get("commit_state") == "committed"

# v2.6 preservation

def test_single_accepted_return_no_overlap_closes_ask():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m approve deployment
m accepted !
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        conv = ask_convs(r)[0]
        assert has_diag(conv, "ACCEPTED_RETURN_PAIR"), conv

def test_duplicate_asks_single_accepted_return_does_not_guess():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m approve deployment
? m approve deployment
m accepted !
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "OPEN_CONVERSATION")
        assert has_error(r, "RETURN_WITHOUT_OPEN_REQUEST")

def test_single_unrelated_observe_does_not_blindly_close():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m approve deployment
m unrelated >
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "OPEN_CONVERSATION")
        assert has_error(r, "RETURN_WITHOUT_OPEN_REQUEST")

# v2.5 commit-gating preservation

def test_unresolved_question_declaration_does_not_commit_symbol_authority():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory ?")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "DECLARATION_PENDING_NOT_COMMITTED"), r.errors
        assert has_error(r, "INBOUND_QUESTION_UNRESOLVED"), r.errors
        sym = r.symbols["memory.m"]
        assert "meaning" not in sym, sym
        assert "authority" not in sym, sym
        assert sym.get("pending_declarations"), sym

def test_committed_observe_declaration_sets_symbol():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors
        sym = r.symbols["memory.m"]
        assert sym.get("meaning") == "memory"
        assert sym.get("authority") == "human"
        assert sym.get("commit_state") == "committed"

# v2.4 preservation

def test_inbound_question_does_not_complete_ask():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? m clarify this ?")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        assert has_error(r, "INBOUND_QUESTION_UNRESOLVED"), r.errors
        assert has_error(r, "OPEN_CONVERSATION"), r.errors
        assert has_error(r, "ASK_WITHOUT_RETURN"), r.errors

def test_inbound_observe_completes_ask():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? m clarify this >")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors

def test_inbound_commit_completes_ask():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? m commit this !")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors

def test_return_observe_completes_prior_ask():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m needle
m needle >
""")
        r = validate_project(Path(tmp), strict=True)
        assert r.ok, r.errors

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
        convs = ask_convs(r)
        first = [c for c in convs if "first question" in c["start"]["payload"]][0]
        second = [c for c in convs if "second question" in c["start"]["payload"]][0]
        assert "first answer" in first["returns"][0]["payload"]
        assert "second answer" in second["returns"][0]["payload"]

def test_ambiguous_positive_return_pairing_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha green >
m alpha yellow >
""")
        r = validate_project(Path(tmp), strict=True)
        assert not r.ok
        convs = ask_convs(r)
        assert any(has_diag(c, "AMBIGUOUS_RETURN_PAIR") for c in convs), convs

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
        test_multiple_return_questions_same_ask_pass,
        test_multiple_cross_file_return_questions_same_ask_pass,
        test_multiple_return_questions_distribute_to_unique_asks,
        test_ambiguous_return_question_still_fails_closed,
        test_zero_score_return_question_still_fails_closed,
        test_same_file_return_before_ask_rejected,
        test_same_file_accepted_return_before_ask_rejected,
        test_same_file_return_question_before_ask_rejected,
        test_cross_file_return_before_ask_allowed,
        test_same_file_normal_order_still_passes,
        test_pending_declaration_does_not_create_dependency_edge,
        test_pending_declarations_do_not_create_dependency_cycle,
        test_committed_declaration_still_creates_dependency_edge_without_conflict,
        test_real_ask_still_creates_dependency_edge,
        test_payload_specific_return_question_pairs_with_matching_ask,
        test_return_question_after_answer_fails_strict,
        test_return_question_before_answer_passes,
        test_pending_parent_blocks_child_commit_even_loose,
        test_committed_parent_allows_child_commit,
        test_single_accepted_return_no_overlap_closes_ask,
        test_duplicate_asks_single_accepted_return_does_not_guess,
        test_single_unrelated_observe_does_not_blindly_close,
        test_unresolved_question_declaration_does_not_commit_symbol_authority,
        test_committed_observe_declaration_sets_symbol,
        test_inbound_question_does_not_complete_ask,
        test_inbound_observe_completes_ask,
        test_inbound_commit_completes_ask,
        test_return_observe_completes_prior_ask,
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
    print("PASS: HACI Project Validator v3.1 tests passed")
