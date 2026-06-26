#!/usr/bin/env python3
"""
HACI Torture Suite x2

No new HACI features.
No validator changes.
This harness stress-tests haci_project_validator_v2_2.py.

x2:
1. Curated adversarial suite.
2. Seeded fuzz/property suite.

Both layers run forward and reverse to catch order dependence.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import random
import json
import traceback
import hashlib

from haci_project_validator_v2_2 import validate_project

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

def has_warning(r, token):
    return any(token in w for w in r.warnings)

def ask_convs(r):
    return [c for c in r.conversations if c["kind"] == "conversation" and c["start"]["outbound"] == "ask"]

# Curated adversarial cases

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

def b_unmatched_return(root):
    write(root, "10_memory/m.haci", "! m memory >\nm extra result >")

def c_unmatched_return_strict(name, r):
    assert_true(name, not r.ok and has_error(r, "RETURN_WITHOUT_OPEN_REQUEST"), str(r.errors))

def b_heading_boundary(root):
    write(root, "10_memory/m.haci", """? m previous result

# New Section
loose note
m previous result >
""")

def c_heading_boundary(name, r):
    convs = ask_convs(r)
    assert_true(name, r.ok and convs and len(convs[0]["body"]) == 0, str(r.errors) + json.dumps(r.conversations, indent=2))

def b_blank_boundary(root):
    write(root, "10_memory/m.haci", """? m previous result

loose note
m previous result >
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
    ("clean deep dot", b_clean_deep_dot, c_clean_deep_dot, True),
    ("phantom dot fails", b_phantom_dot, c_phantom_dot, True),
    ("ambiguous alias fails", b_ambiguous_alias, c_ambiguous_alias, False),
    ("canonical alias passes", b_canonical_alias, c_canonical_alias, True),
    ("pair first second", b_pairing_first_second, c_pairing_first_second, True),
    ("ambiguous zero score", b_ambiguous_zero_score, c_ambiguous_zero_score, True),
    ("unmatched return strict", b_unmatched_return, c_unmatched_return_strict, True),
    ("heading boundary", b_heading_boundary, c_heading_boundary, True),
    ("blank boundary", b_blank_boundary, c_blank_boundary, True),
    ("code fence", b_code_fence, c_code_fence, True),
    ("cycle detection", b_cycle, c_cycle, False),
    ("objectless protocol", b_objectless_protocol, c_objectless_protocol, True),
    ("case swap", b_case_swap, c_case_swap, False),
]

# Fuzz/property suite

OBJECTS = ["m", "c", "n", "cache", "state"]
FOLDERS = {
    "m": "10_memory",
    "c": "20_code",
    "n": "30_network",
    "cache": "10_memory",
    "state": "00_core",
}
WORDS = ["alpha", "beta", "gamma", "delta", "first", "second", "status", "memory", "code", "network", "parser", "last"]

def build_random_project(root: Path, rng: random.Random, valid_bias=True):
    declared = []
    for obj in OBJECTS:
        if rng.random() < 0.7:
            folder = FOLDERS[obj]
            write(root, f"{folder}/{obj}.haci", f"! {obj} {obj} >\n")
            declared.append(obj)

    if not declared:
        write(root, "10_memory/m.haci", "! m memory >\n")
        declared.append("m")

    lines = []
    for _ in range(rng.randint(3, 10)):
        obj = rng.choice(OBJECTS if not valid_bias or rng.random() < 0.25 else declared)
        word = rng.choice(WORDS)
        op = rng.choice(["?", "!", ">"])
        suffix = rng.choice([">", "?", "!", ""])
        if op == ">":
            line = f"{obj} {word} {suffix}".rstrip()
        else:
            line = f"{op} {obj} {word} {suffix}".rstrip()
        lines.append(line)
        if rng.random() < 0.15:
            lines.append("")
        if rng.random() < 0.10:
            lines.append("# boundary")
        if rng.random() < 0.10:
            lines.append("plain body line")
    write(root, "90_runtime/runtime.haci", "\n".join(lines) + "\n")

def fuzz_no_crash_and_deterministic(seed: int, count: int = 100):
    rng = random.Random(seed)
    for i in range(count):
        with tempfile.TemporaryDirectory() as tmp:
            build_random_project(Path(tmp), rng, valid_bias=(i % 2 == 0))
            strict = bool(i % 3 == 0)
            r1 = validate_project(Path(tmp), strict=strict)
            r2 = validate_project(Path(tmp), strict=strict)
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
                assert_true(f"strict monotonic {seed}:{i}", len(strict.errors) >= len(loose.errors), f"loose={loose.errors} strict={strict.errors}")
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
            "suite": "HACI Torture Suite x2",
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
