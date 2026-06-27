#!/usr/bin/env python3
"""
HACI Torture Suite x2 for Validator v3.1

No new HACI features.
No validator changes.

x2:
1. Curated adversarial suite.
2. Seeded fuzz/property suite.

Both layers run:
- forward order
- reverse order

v3.1-specific:
- multiple suffix ? return-questions may attach to one open conversation
- each return-question still needs a positive unique conversation match
- return-questions still do not complete the conversation
- final suffix > or ! still completes the conversation
- ambiguous/zero-score return-questions still fail closed
- same-file returns may not pair backward to later asks
- same-file suffix > before ask fails
- same-file suffix ! before ask fails
- same-file suffix ? before ask fails
- cross-file return/ask pairing remains order-independent
- pending declarations do not create dependency edges
- pending declarations cannot create dependency cycles
- committed declarations still create dependency edges
- real asks/observes still create dependency edges
- payload-specific suffix ? return-question pairs with matching ask
- return-question does not complete ask
- later suffix > or ! completes it
- ambiguous return-question fails closed
- zero-score return-question fails closed
- late return-question after completed answer fails strict
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import random
import json
import traceback
import hashlib

from haci_project_validator_v3_1 import validate_project

PASS = 0
FAIL = 0
RESULTS = []

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

def stable_json(result):
    data = json.loads(json.dumps(result.__dict__, default=lambda o: o.__dict__))
    root = data.get("root", "")
    raw = json.dumps(data, sort_keys=True)
    if root:
        raw = raw.replace(root, "<ROOT>")
    return raw

def assert_true(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        RESULTS.append({"name": name, "status": "PASS"})
    else:
        FAIL += 1
        RESULTS.append({"name": name, "status": "FAIL", "detail": detail})
        raise AssertionError(f"{name}: {detail}")

def run_case(name, builder, checker, strict=False):
    with tempfile.TemporaryDirectory() as tmp:
        builder(Path(tmp))
        r1 = validate_project(Path(tmp), strict=strict)
        r2 = validate_project(Path(tmp), strict=strict)
        assert_true(name + " / deterministic", stable_json(r1) == stable_json(r2), "same input produced different output")
        checker(name, r1)

def has_error(r, token):
    return any(token in e for e in r.errors)

def ask_convs(r):
    return [c for c in r.conversations if c["kind"] == "conversation" and c["start"]["outbound"] == "ask"]

def has_diag(c, token):
    return token in c.get("diagnostics", [])

def edge_exists(r, src_suffix, dst_suffix):
    return any(e["from"].endswith(src_suffix) and e["to"].endswith(dst_suffix) for e in r.edges)

def q_count(conv):
    return sum(1 for ret in conv.get("returns", []) if ret.get("inbound") == "ask")

# -----------------------
# Curated adversarial cases
# -----------------------




def b_multiple_return_questions_same_ask(root):
    write(root, "10_memory/m.haci", """? m alpha problem
m alpha clarify scope ?
m alpha clarify detail ?
m alpha answer >
""")

def c_multiple_return_questions_same_ask(name, r):
    convs = ask_convs(r)
    conv = convs[0] if convs else {}
    ok = (
        r.ok
        and q_count(conv) == 2
        and any(ret.get("inbound") == "observe" and "alpha answer" in ret.get("payload", "") for ret in conv.get("returns", []))
    )
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_multiple_cross_file_return_questions_same_ask(root):
    write(root, "00_scope/m.haci", "! m memory >")
    write(root, "10_runtime/ask.haci", "? m alpha problem")
    write(root, "20_returns/q1.haci", "m alpha clarify scope ?")
    write(root, "21_returns/q2.haci", "m alpha clarify detail ?")
    write(root, "30_returns/a.haci", "m alpha answer >")

def c_multiple_cross_file_return_questions_same_ask(name, r):
    convs = ask_convs(r)
    conv = convs[0] if convs else {}
    ok = r.ok and q_count(conv) == 2
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_multiple_return_questions_distribute_to_unique_asks(root):
    write(root, "10_memory/m.haci", """? m alpha scope problem
? m beta detail problem
m alpha scope clarify ?
m beta detail clarify ?
m alpha scope answer >
m beta detail answer >
""")

def c_multiple_return_questions_distribute_to_unique_asks(name, r):
    convs = ask_convs(r)
    alpha = [c for c in convs if "alpha scope" in c.get("start", {}).get("payload", "")]
    beta = [c for c in convs if "beta detail" in c.get("start", {}).get("payload", "")]
    ok = (
        r.ok and alpha and beta
        and q_count(alpha[0]) == 1
        and q_count(beta[0]) == 1
        and any("alpha scope clarify" in ret.get("payload", "") for ret in alpha[0].get("returns", []))
        and any("beta detail clarify" in ret.get("payload", "") for ret in beta[0].get("returns", []))
    )
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_multiple_return_questions_then_accept(root):
    write(root, "10_memory/m.haci", """? m approve deployment
m approve clarify scope ?
m approve clarify detail ?
m accepted !
""")

def c_multiple_return_questions_then_accept(name, r):
    convs = ask_convs(r)
    conv = convs[0] if convs else {}
    ok = (
        r.ok
        and q_count(conv) == 2
        and any(ret.get("inbound") == "declare" for ret in conv.get("returns", []))
        and has_diag(conv, "ACCEPTED_RETURN_PAIR")
    )
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_ambiguous_multi_return_question_still_fails(root):
    write(root, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha clarify ?
m alpha red >
m alpha blue >
""")

def c_ambiguous_multi_return_question_still_fails(name, r):
    ok = not r.ok and has_error(r, "RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST")
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_zero_score_multi_return_question_still_fails(root):
    write(root, "10_memory/m.haci", """? m alpha problem
m gamma clarify ?
m alpha answer >
""")

def c_zero_score_multi_return_question_still_fails(name, r):
    ok = not r.ok and has_error(r, "RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST")
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))


def b_same_file_return_before_ask(root):
    write(root, "10_memory/m.haci", """m alpha answer >
? m alpha question
""")

def c_same_file_return_before_ask(name, r):
    ok = (
        not r.ok
        and has_error(r, "SAME_FILE_RETURN_BEFORE_ASK")
        and has_error(r, "RETURN_WITHOUT_OPEN_REQUEST")
        and has_error(r, "OPEN_CONVERSATION")
    )
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_same_file_accepted_before_ask(root):
    write(root, "10_memory/m.haci", """m accepted !
? m approve deployment
""")

def c_same_file_accepted_before_ask(name, r):
    ok = not r.ok and has_error(r, "SAME_FILE_RETURN_BEFORE_ASK")
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_same_file_return_question_before_ask(root):
    write(root, "10_memory/m.haci", """m alpha clarify ?
? m alpha problem
m alpha answer >
""")

def c_same_file_return_question_before_ask(name, r):
    ok = not r.ok and has_error(r, "SAME_FILE_RETURN_BEFORE_ASK")
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_same_file_normal_order(root):
    write(root, "10_memory/m.haci", """? m alpha question
m alpha answer >
""")

def c_same_file_normal_order(name, r):
    assert_true(name, r.ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_cross_file_return_before_ask(root):
    write(root, "00_scope/m.haci", "! m memory >")
    write(root, "10_returns/returns.haci", "m alpha answer >")
    write(root, "20_runtime/ask.haci", "? m alpha question")

def c_cross_file_return_before_ask(name, r):
    assert_true(name, r.ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_cross_file_accepted_before_ask(root):
    write(root, "00_scope/m.haci", "! m memory >")
    write(root, "10_returns/returns.haci", "m accepted !")
    write(root, "20_runtime/ask.haci", "? m approve deployment")

def c_cross_file_accepted_before_ask(name, r):
    convs = ask_convs(r)
    ok = r.ok and convs and any(has_diag(c, "ACCEPTED_RETURN_PAIR") for c in convs)
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_cross_file_return_question_before_ask_then_answer(root):
    write(root, "00_scope/m.haci", "! m memory >")
    write(root, "10_returns/question.haci", "m alpha clarify ?")
    write(root, "20_runtime/ask.haci", "? m alpha problem")
    write(root, "30_returns/answer.haci", "m alpha answer >")

def c_cross_file_return_question_before_ask_then_answer(name, r):
    convs = ask_convs(r)
    alpha = [c for c in convs if "alpha problem" in c.get("start", {}).get("payload", "")]
    ok = (
        r.ok and alpha
        and any(ret.get("inbound") == "ask" and "alpha clarify" in ret.get("payload", "") for ret in alpha[0].get("returns", []))
        and any(ret.get("inbound") == "observe" and "alpha answer" in ret.get("payload", "") for ret in alpha[0].get("returns", []))
    )
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))


def b_pending_declaration_no_edge(root):
    write(root, "10_memory/m.haci", "! c pending ?")
    write(root, "20_code/c.haci", "! c code >")

def c_pending_declaration_no_edge(name, r):
    ok = (
        r.ok
        and not edge_exists(r, "memory.m", "code.c")
        and any("DECLARATION_PENDING_NOT_COMMITTED" in w for w in r.warnings)
    )
    assert_true(name, ok, str(r.errors) + str(r.warnings) + json.dumps(r.edges, indent=2))

def b_pending_declarations_no_cycle(root):
    write(root, "10_memory/m.haci", "! c pending ?")
    write(root, "20_code/c.haci", "! m pending ?")

def c_pending_declarations_no_cycle(name, r):
    ok = r.ok and not r.edges and not has_error(r, "DEPENDENCY_CYCLE")
    assert_true(name, ok, str(r.errors) + json.dumps(r.edges, indent=2))

def b_committed_declaration_edge(root):
    write(root, "10_memory/m.haci", "! c code >")
    write(root, "20_code/c.haci", "! c code >")

def c_committed_declaration_edge(name, r):
    ok = r.ok and edge_exists(r, "memory.m", "code.c")
    assert_true(name, ok, str(r.errors) + json.dumps(r.edges, indent=2))

def b_real_ask_edge(root):
    write(root, "10_memory/m.haci", "? c status >")
    write(root, "20_code/c.haci", "! c code >")

def c_real_ask_edge(name, r):
    ok = r.ok and edge_exists(r, "memory.m", "code.c")
    assert_true(name, ok, str(r.errors) + json.dumps(r.edges, indent=2))

def b_pending_declaration_strict_no_edge(root):
    write(root, "10_memory/m.haci", "! c pending ?")
    write(root, "20_code/c.haci", "! c code >")

def c_pending_declaration_strict_no_edge(name, r):
    ok = (
        not r.ok
        and has_error(r, "DECLARATION_PENDING_NOT_COMMITTED")
        and not edge_exists(r, "memory.m", "code.c")
    )
    assert_true(name, ok, str(r.errors) + json.dumps(r.edges, indent=2))


def b_payload_specific_return_question(root):
    write(root, "10_memory/m.haci", """? m alpha problem
? m beta problem
m alpha clarify ?
m beta answer >
m alpha answer >
""")

def c_payload_specific_return_question(name, r):
    convs = ask_convs(r)
    alpha = [c for c in convs if "alpha problem" in c["start"]["payload"]][0] if convs else None
    beta = [c for c in convs if "beta problem" in c["start"]["payload"]][0] if convs else None
    ok = (
        r.ok and alpha and beta
        and any(ret["inbound"] == "ask" and "alpha clarify" in ret["payload"] for ret in alpha["returns"])
        and any(ret["inbound"] == "observe" and "alpha answer" in ret["payload"] for ret in alpha["returns"])
        and any(ret["inbound"] == "observe" and "beta answer" in ret["payload"] for ret in beta["returns"])
    )
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_ambiguous_return_question(root):
    write(root, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha clarify ?
m alpha red >
m alpha blue >
""")

def c_ambiguous_return_question(name, r):
    ok = not r.ok and has_error(r, "RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST")
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_zero_score_return_question(root):
    write(root, "10_memory/m.haci", """? m alpha problem
? m beta problem
m gamma clarify ?
m alpha problem >
m beta problem >
""")

def c_zero_score_return_question(name, r):
    ok = not r.ok and has_error(r, "RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST")
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_late_return_question_after_answer(root):
    write(root, "10_memory/m.haci", """? m alpha problem
m alpha answer >
m alpha clarify ?
""")

def c_late_return_question_after_answer(name, r):
    ok = not r.ok and has_error(r, "LATE_RETURN_QUESTION_AFTER_COMPLETION")
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_return_question_before_answer(root):
    write(root, "10_memory/m.haci", """? m alpha problem
m alpha clarify ?
m alpha answer >
""")

def c_return_question_before_answer(name, r):
    convs = ask_convs(r)
    ok = r.ok and convs and any(ret["inbound"] == "ask" for ret in convs[0]["returns"]) and any(ret["inbound"] == "observe" for ret in convs[0]["returns"])
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_pending_parent_child_loose(root):
    write(root, "10_memory/m.haci", "! m memory ?")
    write(root, "10_memory/m/parser/last.haci", "! last prior >")
    write(root, "20_runtime/runtime.haci", "? m.parser.last previous result >")

def c_pending_parent_child_loose(name, r):
    parent = r.symbols.get("memory.m", {})
    child = r.symbols.get("memory.m.parser.last", {})
    ok = (
        not r.ok
        and has_error(r, "PENDING_PARENT_SCOPE")
        and "meaning" not in parent
        and "meaning" not in child
        and child.get("commit_state") == "blocked_pending_parent"
        and bool(child.get("blocked_commits"))
    )
    assert_true(name, ok, str(r.errors) + json.dumps({"parent": parent, "child": child}, indent=2))

def b_uncommitted_parent_child(root):
    write(root, "10_memory/m.haci", "plain body only")
    write(root, "10_memory/m/parser/last.haci", "! last prior >")

def c_uncommitted_parent_child(name, r):
    child = r.symbols.get("memory.m.parser.last", {})
    ok = (
        not r.ok
        and has_error(r, "PENDING_PARENT_SCOPE")
        and "meaning" not in child
        and child.get("commit_state") == "blocked_pending_parent"
    )
    assert_true(name, ok, str(r.errors) + json.dumps(child, indent=2))

def b_committed_parent_child(root):
    write(root, "10_memory/m.haci", "! m memory >")
    write(root, "10_memory/m/parser/last.haci", "! last prior >")
    write(root, "20_runtime/runtime.haci", "? m.parser.last previous result >")

def c_committed_parent_child(name, r):
    child = r.symbols.get("memory.m.parser.last", {})
    ok = r.ok and child.get("meaning") == "prior" and child.get("commit_state") == "committed"
    assert_true(name, ok, str(r.errors) + json.dumps(child, indent=2))

def b_committed_parent_pending_sibling_child(root):
    write(root, "10_memory/m.haci", "! m memory >\n! m maybe ?")
    write(root, "10_memory/m/parser/last.haci", "! last prior >")

def c_committed_parent_pending_sibling_child(name, r):
    parent = r.symbols.get("memory.m", {})
    child = r.symbols.get("memory.m.parser.last", {})
    ok = (
        not r.ok
        and not has_error(r, "PENDING_PARENT_SCOPE")
        and parent.get("commit_state") == "committed"
        and child.get("commit_state") == "committed"
        and child.get("meaning") == "prior"
    )
    assert_true(name, ok, str(r.errors) + json.dumps({"parent": parent, "child": child}, indent=2))

def b_unique_accepted_return(root):
    write(root, "10_memory/m.haci", """? m approve deployment
m accepted !
""")

def c_unique_accepted_return(name, r):
    convs = ask_convs(r)
    ok = r.ok and convs and has_diag(convs[0], "ACCEPTED_RETURN_PAIR")
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_duplicate_asks_accepted_return(root):
    write(root, "10_memory/m.haci", """? m approve deployment
? m approve deployment
m accepted !
""")

def c_duplicate_asks_accepted_return(name, r):
    ok = not r.ok and has_error(r, "OPEN_CONVERSATION") and has_error(r, "RETURN_WITHOUT_OPEN_REQUEST")
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_unrelated_observe_no_blind_close(root):
    write(root, "10_memory/m.haci", """? m approve deployment
m unrelated >
""")

def c_unrelated_observe_no_blind_close(name, r):
    ok = not r.ok and has_error(r, "OPEN_CONVERSATION") and has_error(r, "RETURN_WITHOUT_OPEN_REQUEST")
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_return_question_then_accept(root):
    write(root, "10_memory/m.haci", """? m approve deployment
m approve clarify ?
m accepted !
""")

def c_return_question_then_accept(name, r):
    convs = ask_convs(r)
    ok = (
        r.ok and convs
        and has_diag(convs[0], "ACCEPTED_RETURN_PAIR")
        and any(ret["inbound"] == "ask" for ret in convs[0]["returns"])
        and any(ret["inbound"] == "declare" for ret in convs[0]["returns"])
    )
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_multiple_remaining_returns_accept(root):
    write(root, "10_memory/m.haci", """? m approve deployment
m accepted !
m unrelated >
""")

def c_multiple_remaining_returns_accept(name, r):
    ok = not r.ok and (has_error(r, "OPEN_CONVERSATION") or has_error(r, "RETURN_WITHOUT_OPEN_REQUEST"))
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_pending_question_decl(root):
    write(root, "10_memory/m.haci", "! m memory ?")

def c_pending_question_decl(name, r):
    sym = r.symbols.get("memory.m", {})
    ok = (
        not r.ok
        and has_error(r, "DECLARATION_PENDING_NOT_COMMITTED")
        and has_error(r, "INBOUND_QUESTION_UNRESOLVED")
        and "meaning" not in sym
        and "authority" not in sym
        and bool(sym.get("pending_declarations"))
    )
    assert_true(name, ok, str(r.errors) + json.dumps(sym, indent=2))

def b_pending_no_suffix_decl(root):
    write(root, "10_memory/m.haci", "! m memory")

def c_pending_no_suffix_decl(name, r):
    sym = r.symbols.get("memory.m", {})
    ok = (
        not r.ok
        and has_error(r, "DECLARATION_PENDING_NOT_COMMITTED")
        and "meaning" not in sym
        and "authority" not in sym
        and bool(sym.get("pending_declarations"))
    )
    assert_true(name, ok, str(r.errors) + json.dumps(sym, indent=2))

def b_committed_observe_decl(root):
    write(root, "10_memory/m.haci", "! m memory >")

def c_committed_observe_decl(name, r):
    sym = r.symbols.get("memory.m", {})
    ok = r.ok and sym.get("meaning") == "memory" and sym.get("authority") == "human" and sym.get("commit_state") == "committed"
    assert_true(name, ok, str(r.errors) + json.dumps(sym, indent=2))

def b_committed_bang_decl(root):
    write(root, "10_memory/m.haci", "! m memory !")

def c_committed_bang_decl(name, r):
    sym = r.symbols.get("memory.m", {})
    ok = r.ok and sym.get("meaning") == "memory" and sym.get("authority") == "human"
    assert_true(name, ok, str(r.errors) + json.dumps(sym, indent=2))

def b_pending_then_commit_different(root):
    write(root, "10_memory/m.haci", """! m memory ?
! m model >
""")

def c_pending_then_commit_different(name, r):
    sym = r.symbols.get("memory.m", {})
    ok = (
        not r.ok
        and has_error(r, "DECLARATION_PENDING_NOT_COMMITTED")
        and not has_error(r, "DUPLICATE_OR_CONFLICTING_SYMBOL")
        and not has_error(r, "AUTHORITY_MUTATION")
        and sym.get("meaning") == "model"
        and bool(sym.get("pending_declarations"))
    )
    assert_true(name, ok, str(r.errors) + json.dumps(sym, indent=2))

def b_inbound_question_open(root):
    write(root, "10_memory/m.haci", "? m clarify this ?")

def c_inbound_question_open(name, r):
    ok = (
        not r.ok
        and has_error(r, "INBOUND_QUESTION_UNRESOLVED")
        and has_error(r, "OPEN_CONVERSATION")
        and has_error(r, "ASK_WITHOUT_RETURN")
    )
    assert_true(name, ok, str(r.errors))

def b_inbound_observe_complete(root):
    write(root, "10_memory/m.haci", "? m clarify this >")

def c_inbound_observe_complete(name, r):
    assert_true(name, r.ok, str(r.errors))

def b_inbound_commit_complete(root):
    write(root, "10_memory/m.haci", "? m commit this !")

def c_inbound_commit_complete(name, r):
    assert_true(name, r.ok, str(r.errors))

def b_return_question_open(root):
    write(root, "10_memory/m.haci", """? m needle
m needle ?
""")

def c_return_question_open(name, r):
    ok = not r.ok and has_error(r, "OPEN_CONVERSATION") and has_error(r, "ASK_WITHOUT_RETURN")
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_return_question_then_answer(root):
    write(root, "10_memory/m.haci", """? m needle
m needle ?
m needle >
""")

def c_return_question_then_answer(name, r):
    convs = ask_convs(r)
    ok = r.ok and convs and any(ret["inbound"] == "ask" for ret in convs[0]["returns"]) and any(ret["inbound"] == "observe" for ret in convs[0]["returns"])
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_return_observe_complete(root):
    write(root, "10_memory/m.haci", """? m needle
m needle >
""")

def c_return_observe_complete(name, r):
    assert_true(name, r.ok, str(r.errors))

def b_clean_deep_dot(root):
    write(root, "10_memory/m.haci", "! m memory >")
    write(root, "10_memory/m/parser/last.haci", "! last prior result >")
    write(root, "20_runtime/runtime.haci", "? m.parser.last previous result >")

def c_clean_deep_dot(name, r):
    assert_true(name, r.ok, str(r.errors))

def b_phantom_dot(root):
    write(root, "10_memory/m.haci", "! m memory >")
    write(root, "20_runtime/runtime.haci", "? m.parser.last previous result >")

def c_phantom_dot(name, r):
    assert_true(name, not r.ok and has_error(r, "DOT_PATH_NOT_FOUND"), str(r.errors))

def b_ambiguous_alias(root):
    write(root, "10_memory/cache.haci", "! cache memory cache >")
    write(root, "20_code/cache.haci", "! cache code cache >")
    write(root, "30_runtime/runtime.haci", "? cache status >")

def c_ambiguous_alias(name, r):
    assert_true(name, not r.ok and has_error(r, "AMBIGUOUS_OBJECT:cache"), str(r.errors))

def b_canonical_alias(root):
    write(root, "10_memory/cache.haci", "! cache memory cache >")
    write(root, "20_code/cache.haci", "! cache code cache >")
    write(root, "30_runtime/runtime.haci", "? memory.cache status >")

def c_canonical_alias(name, r):
    assert_true(name, r.ok, str(r.errors))

def b_pairing_first_second(root):
    write(root, "10_memory/m.haci", """? m first question
? m second question
m second answer >
m first answer >
""")

def c_pairing_first_second(name, r):
    convs = ask_convs(r)
    first = [c for c in convs if "first question" in c["start"]["payload"]][0]
    second = [c for c in convs if "second question" in c["start"]["payload"]][0]
    ok = "first answer" in first["returns"][0]["payload"] and "second answer" in second["returns"][0]["payload"]
    assert_true(name, r.ok and ok, json.dumps(r.conversations, indent=2))

def b_ambiguous_zero_score(root):
    write(root, "10_memory/m.haci", """? m alpha
? m beta
m gamma >
m delta >
""")

def c_ambiguous_zero_score(name, r):
    assert_true(name, not r.ok and has_error(r, "OPEN_CONVERSATION") and has_error(r, "RETURN_WITHOUT_OPEN_REQUEST"), str(r.errors))

def b_ambiguous_positive_tie(root):
    write(root, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha green >
m alpha yellow >
""")

def c_ambiguous_positive_tie(name, r):
    convs = ask_convs(r)
    ok = (
        not r.ok
        and has_error(r, "OPEN_CONVERSATION")
        and has_error(r, "RETURN_WITHOUT_OPEN_REQUEST")
        and any(has_diag(c, "AMBIGUOUS_RETURN_PAIR") for c in convs)
    )
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_mutual_unique_pair(root):
    write(root, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha blue >
m alpha red >
""")

def c_mutual_unique_pair(name, r):
    convs = ask_convs(r)
    red = [c for c in convs if "red" in c["start"]["payload"]][0]
    blue = [c for c in convs if "blue" in c["start"]["payload"]][0]
    ok = r.ok and "red" in red["returns"][0]["payload"] and "blue" in blue["returns"][0]["payload"]
    assert_true(name, ok, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_single_no_overlap(root):
    write(root, "10_memory/m.haci", """? m alpha
m zulu >
""")

def c_single_no_overlap(name, r):
    assert_true(name, not r.ok and has_error(r, "OPEN_CONVERSATION") and has_error(r, "RETURN_WITHOUT_OPEN_REQUEST"), str(r.errors))

def b_unmatched_return(root):
    write(root, "10_memory/m.haci", "! m memory >\nm extra result >")

def c_unmatched_return_strict(name, r):
    assert_true(name, not r.ok and has_error(r, "RETURN_WITHOUT_OPEN_REQUEST"), str(r.errors))

def b_heading_boundary(root):
    write(root, "10_memory/m.haci", """? m needle

# New Section
loose note
m needle >
""")

def c_heading_boundary(name, r):
    convs = ask_convs(r)
    assert_true(name, r.ok and convs and len(convs[0]["body"]) == 0, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_blank_boundary(root):
    write(root, "10_memory/m.haci", """? m needle

loose note
m needle >
""")

def c_blank_boundary(name, r):
    convs = ask_convs(r)
    assert_true(name, r.ok and convs and len(convs[0]["body"]) == 0, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_code_fence(root):
    write(root, "10_memory/m.haci", """```python
? x ignored >
```
""")

def c_code_fence(name, r):
    assert_true(name, r.ok and len(r.conversations) == 0, str(r.errors))

def b_cycle(root):
    write(root, "10_memory/m.haci", "? c helper >")
    write(root, "20_code/c.haci", "? m memory >")

def c_cycle(name, r):
    assert_true(name, not r.ok and has_error(r, "DEPENDENCY_CYCLE"), str(r.errors))

def b_objectless_protocol(root):
    write(root, "10_memory/m.haci", "done >")

def c_objectless_protocol(name, r):
    assert_true(name, not r.ok and (has_error(r, "UNDECLARED_OBJECT:done") or has_error(r, "OBJECT_REQUIRED")), str(r.errors))

def b_case_swap(root):
    write(root, "10_memory/m.haci", "! m memory >")
    write(root, "20_code/c.haci", "! c CODE >")

def c_case_swap(name, r):
    m = next(n for n in r.nodes if n.get("object") == "m")
    c = next(n for n in r.nodes if n.get("object") == "c")
    ok = m["owner"] == "human" and c["owner"] == "ai"
    assert_true(name, r.ok and ok, str(r.errors) + json.dumps(r.nodes, indent=2))

CURATED = [
    ("multiple return questions same ask", b_multiple_return_questions_same_ask, c_multiple_return_questions_same_ask, True),
    ("multiple cross-file return questions same ask", b_multiple_cross_file_return_questions_same_ask, c_multiple_cross_file_return_questions_same_ask, True),
    ("multiple return questions distribute to unique asks", b_multiple_return_questions_distribute_to_unique_asks, c_multiple_return_questions_distribute_to_unique_asks, True),
    ("multiple return questions then accept", b_multiple_return_questions_then_accept, c_multiple_return_questions_then_accept, True),
    ("ambiguous multi return question still fails", b_ambiguous_multi_return_question_still_fails, c_ambiguous_multi_return_question_still_fails, True),
    ("zero score multi return question still fails", b_zero_score_multi_return_question_still_fails, c_zero_score_multi_return_question_still_fails, True),
    ("same file return before ask", b_same_file_return_before_ask, c_same_file_return_before_ask, True),
    ("same file accepted before ask", b_same_file_accepted_before_ask, c_same_file_accepted_before_ask, True),
    ("same file return question before ask", b_same_file_return_question_before_ask, c_same_file_return_question_before_ask, True),
    ("same file normal order", b_same_file_normal_order, c_same_file_normal_order, True),
    ("cross file return before ask", b_cross_file_return_before_ask, c_cross_file_return_before_ask, True),
    ("cross file accepted before ask", b_cross_file_accepted_before_ask, c_cross_file_accepted_before_ask, True),
    ("cross file return question before ask then answer", b_cross_file_return_question_before_ask_then_answer, c_cross_file_return_question_before_ask_then_answer, True),
    ("pending declaration no edge", b_pending_declaration_no_edge, c_pending_declaration_no_edge, False),
    ("pending declarations no cycle", b_pending_declarations_no_cycle, c_pending_declarations_no_cycle, False),
    ("committed declaration edge", b_committed_declaration_edge, c_committed_declaration_edge, False),
    ("real ask edge", b_real_ask_edge, c_real_ask_edge, False),
    ("pending declaration strict no edge", b_pending_declaration_strict_no_edge, c_pending_declaration_strict_no_edge, True),
    ("payload-specific return question", b_payload_specific_return_question, c_payload_specific_return_question, True),
    ("ambiguous return question", b_ambiguous_return_question, c_ambiguous_return_question, True),
    ("zero score return question", b_zero_score_return_question, c_zero_score_return_question, True),
    ("late return question after answer", b_late_return_question_after_answer, c_late_return_question_after_answer, True),
    ("return question before answer", b_return_question_before_answer, c_return_question_before_answer, True),
    ("pending parent child loose", b_pending_parent_child_loose, c_pending_parent_child_loose, False),
    ("pending parent child strict", b_pending_parent_child_loose, c_pending_parent_child_loose, True),
    ("uncommitted parent child", b_uncommitted_parent_child, c_uncommitted_parent_child, False),
    ("committed parent child", b_committed_parent_child, c_committed_parent_child, True),
    ("committed parent pending sibling child", b_committed_parent_pending_sibling_child, c_committed_parent_pending_sibling_child, True),
    ("unique accepted return", b_unique_accepted_return, c_unique_accepted_return, True),
    ("duplicate asks accepted return", b_duplicate_asks_accepted_return, c_duplicate_asks_accepted_return, True),
    ("unrelated observe no blind close", b_unrelated_observe_no_blind_close, c_unrelated_observe_no_blind_close, True),
    ("return question then accept", b_return_question_then_accept, c_return_question_then_accept, True),
    ("multiple remaining returns accept", b_multiple_remaining_returns_accept, c_multiple_remaining_returns_accept, True),
    ("pending question declaration", b_pending_question_decl, c_pending_question_decl, True),
    ("pending no suffix declaration", b_pending_no_suffix_decl, c_pending_no_suffix_decl, True),
    ("committed observe declaration", b_committed_observe_decl, c_committed_observe_decl, True),
    ("committed bang declaration", b_committed_bang_decl, c_committed_bang_decl, True),
    ("pending then commit different", b_pending_then_commit_different, c_pending_then_commit_different, True),
    ("inbound question open", b_inbound_question_open, c_inbound_question_open, True),
    ("inbound observe complete", b_inbound_observe_complete, c_inbound_observe_complete, True),
    ("inbound commit complete", b_inbound_commit_complete, c_inbound_commit_complete, True),
    ("return question open", b_return_question_open, c_return_question_open, True),
    ("return question then answer", b_return_question_then_answer, c_return_question_then_answer, True),
    ("return observe complete", b_return_observe_complete, c_return_observe_complete, True),
    ("clean deep dot", b_clean_deep_dot, c_clean_deep_dot, True),
    ("phantom dot fails", b_phantom_dot, c_phantom_dot, True),
    ("ambiguous alias fails", b_ambiguous_alias, c_ambiguous_alias, False),
    ("canonical alias passes", b_canonical_alias, c_canonical_alias, True),
    ("pair first second", b_pairing_first_second, c_pairing_first_second, True),
    ("ambiguous zero score", b_ambiguous_zero_score, c_ambiguous_zero_score, True),
    ("ambiguous positive tie", b_ambiguous_positive_tie, c_ambiguous_positive_tie, True),
    ("mutual unique pair", b_mutual_unique_pair, c_mutual_unique_pair, True),
    ("single no overlap fails", b_single_no_overlap, c_single_no_overlap, True),
    ("unmatched return strict", b_unmatched_return, c_unmatched_return_strict, True),
    ("heading boundary", b_heading_boundary, c_heading_boundary, True),
    ("blank boundary", b_blank_boundary, c_blank_boundary, True),
    ("code fence", b_code_fence, c_code_fence, True),
    ("cycle detection", b_cycle, c_cycle, False),
    ("objectless protocol", b_objectless_protocol, c_objectless_protocol, True),
    ("case swap", b_case_swap, c_case_swap, False),
]

# -----------------------
# Fuzz/property suite
# -----------------------

OBJECTS = ["m", "c", "n", "cache", "state"]
FOLDERS = {
    "m": "10_memory",
    "c": "20_code",
    "n": "30_network",
    "cache": "10_memory",
    "state": "00_core",
}
WORDS = [
    "alpha", "beta", "gamma", "delta", "first", "second", "status",
    "memory", "code", "network", "parser", "last", "red", "blue", "green",
    "needle", "thread", "model", "approve", "deployment", "accepted", "clarify",
    "problem", "answer"
]

def build_random_project(root: Path, rng: random.Random, valid_bias=True):
    declared = []
    for obj in OBJECTS:
        if rng.random() < 0.7:
            folder = FOLDERS[obj]
            suffix = ">" if rng.random() < 0.9 else "?"
            write(root, f"{folder}/{obj}.haci", f"! {obj} {obj} {suffix}\n")
            declared.append(obj)

    if not declared:
        write(root, "10_memory/m.haci", "! m memory >\n")
        declared.append("m")

    if "m" in declared and rng.random() < 0.25:
        write(root, "10_memory/m/parser/last.haci", "! last last >\n")

    lines = []
    for _ in range(rng.randint(3, 10)):
        obj = rng.choice(OBJECTS if not valid_bias or rng.random() < 0.25 else declared)
        if obj == "m" and rng.random() < 0.10:
            obj = "m.parser.last"
        payload = " ".join(rng.sample(WORDS, rng.randint(1, 3)))
        kind = rng.choice([
            "ask", "return_obs", "return_q", "return_commit",
            "dual_obs", "dual_q", "dual_commit",
            "declare_obs", "declare_q", "declare_pending",
            "body", "heading", "blank"
        ])
        if kind == "ask":
            lines.append(f"? {obj} {payload}")
        elif kind == "return_obs":
            lines.append(f"{obj} {payload} >")
        elif kind == "return_q":
            lines.append(f"{obj} {payload} ?")
        elif kind == "return_commit":
            lines.append(f"{obj} {payload} !")
        elif kind == "dual_obs":
            lines.append(f"? {obj} {payload} >")
        elif kind == "dual_q":
            lines.append(f"? {obj} {payload} ?")
        elif kind == "dual_commit":
            lines.append(f"? {obj} {payload} !")
        elif kind == "declare_obs":
            lines.append(f"! {obj} {payload} >")
        elif kind == "declare_q":
            lines.append(f"! {obj} {payload} ?")
        elif kind == "declare_pending":
            lines.append(f"! {obj} {payload}")
        elif kind == "body":
            lines.append(payload)
        elif kind == "heading":
            lines.append("# boundary")
        else:
            lines.append("")

    write(root, "90_runtime/runtime.haci", "\n".join(lines) + "\n")

def fuzz_no_crash_and_deterministic(seed: int, count: int = 100):
    rng = random.Random(seed)
    for i in range(count):
        with tempfile.TemporaryDirectory() as tmp:
            build_random_project(Path(tmp), rng, valid_bias=(i % 2 == 0))
            r1 = validate_project(Path(tmp), strict=bool(i % 3 == 0))
            r2 = validate_project(Path(tmp), strict=bool(i % 3 == 0))
            assert_true(f"fuzz {seed}:{i} no crash", True)
            assert_true(f"fuzz {seed}:{i} deterministic", stable_json(r1) == stable_json(r2), "non-deterministic fuzz output")

def fuzz_monotonic_strict(seed: int, count: int = 50):
    rng = random.Random(seed)
    for i in range(count):
        with tempfile.TemporaryDirectory() as tmp:
            build_random_project(Path(tmp), rng, valid_bias=False)
            loose = validate_project(Path(tmp), strict=False)
            strict = validate_project(Path(tmp), strict=True)
            if not loose.ok:
                assert_true(
                    f"strict monotonic {seed}:{i}",
                    len(strict.errors) >= len(loose.errors),
                    f"loose={loose.errors} strict={strict.errors}"
                )
            else:
                assert_true(f"strict monotonic {seed}:{i}", True)

def run_all(order="forward"):
    cases = CURATED if order == "forward" else list(reversed(CURATED))
    for name, builder, checker, strict in cases:
        run_case(f"{order} curated / {name}", builder, checker, strict=strict)

    seeds = [1337, 7331] if order == "forward" else [7331, 1337]
    for seed in seeds:
        fuzz_no_crash_and_deterministic(seed, count=100)
        fuzz_monotonic_strict(seed, count=50)

def main():
    global PASS, FAIL
    try:
        run_all("forward")
        run_all("reverse")
    except Exception:
        FAIL += 1
        RESULTS.append({"name": "uncaught exception", "status": "FAIL", "traceback": traceback.format_exc()})
        raise
    finally:
        report = {
            "suite": "HACI Torture Suite x2 for v3.1",
            "pass": PASS,
            "fail": FAIL,
            "result_count": len(RESULTS),
            "results_hash": hashlib.sha256(json.dumps(RESULTS, sort_keys=True).encode()).hexdigest(),
            "results": RESULTS,
        }
        Path("TORTURE_RESULTS.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k: report[k] for k in ["suite", "pass", "fail", "result_count", "results_hash"]}, indent=2))
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
