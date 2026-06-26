#!/usr/bin/env python3
from pathlib import Path
import tempfile
from haci_project_validator_v1_2 import validate_project, group_conversations, parse_file

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

def test_dual_operator_self_closed_conversation():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory >")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        assert len(r.conversations) == 1
        assert r.conversations[0]["opener"]["outbound"] == "declare"
        assert r.conversations[0]["opener"]["inbound"] == "observe"

def test_conversation_with_body():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """! m memory
The memory object stores prior context.
allocate index
> m memory initialized >
""")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        assert len(r.conversations) == 2  # opener conversation + return/evidence conversation under v1.2 close behavior
        assert any(c["body"] for c in r.conversations)

def test_ask_without_return_warns():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? m previous parser result")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        assert any("OPEN_CONVERSATION" in w or "ASK_WITHOUT_RETURN" in w for w in r.warnings)

def test_unrelated_nodes_no_longer_are_all_top_level_only():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m previous parser result
search memory index
rank nearest context
""")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        assert len(r.conversations) == 1
        assert len(r.conversations[0]["body"]) == 2

def test_undeclared_still_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "20_runtime/runtime.haci", "? x missing >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert any("UNDECLARED_OBJECT:x" in e for e in r.errors)

def test_cycle_still_fails():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? c helper >")
        write(tmp, "20_code/c.haci", "? m memory >")
        r = validate_project(Path(tmp))
        assert not r.ok
        assert any("DEPENDENCY_CYCLE" in e for e in r.errors)

def test_code_fence_suspends_conversation():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "20_runtime/runtime.haci", "```python\n? x ignored >\n```")
        r = validate_project(Path(tmp))
        assert r.ok, r.errors
        assert len(r.conversations) == 0

if __name__ == "__main__":
    for t in [
        test_dual_operator_self_closed_conversation,
        test_conversation_with_body,
        test_ask_without_return_warns,
        test_unrelated_nodes_no_longer_are_all_top_level_only,
        test_undeclared_still_fails,
        test_cycle_still_fails,
        test_code_fence_suspends_conversation,
    ]:
        t()
    print("PASS: HACI Project Validator v1.2 conversation tests passed")
