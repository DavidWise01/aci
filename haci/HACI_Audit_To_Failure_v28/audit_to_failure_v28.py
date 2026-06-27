#!/usr/bin/env python3
"""
HACI Validator v2.8 — Audit to Failure

No new features.
Goal: find the next meaningful semantic/protocol failure in v2.8.
"""

from pathlib import Path
import tempfile, shutil, json, random, traceback
from haci_project_validator_v2_8 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

def stable(r):
    data = json.loads(json.dumps(r.__dict__, default=lambda o: o.__dict__))
    root = data.get("root", "")
    s = json.dumps(data, sort_keys=True)
    return s.replace(root, "<ROOT>")

def save_failure(name, root, result, reason, expected=None):
    out = Path("FAILURE_FOUND")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    shutil.copytree(root, out / "project")
    (out / "reason.txt").write_text(reason, encoding="utf-8")
    (out / "result.json").write_text(json.dumps(result.__dict__, default=lambda o: o.__dict__, indent=2), encoding="utf-8")
    summary = {
        "failure": name,
        "reason": reason,
        "expected": expected,
        "saved_to": str(out),
        "errors": result.errors,
        "warnings": result.warnings,
    }
    Path("FAILURE_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

def has_error(r, token):
    return any(token in e for e in r.errors)

def ask_convs(r):
    return [c for c in r.conversations if c["kind"] == "conversation" and c["start"]["outbound"] == "ask"]

def check_prior_v27_return_question_fixed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m alpha problem
? m beta problem
m alpha clarify ?
m beta answer >
m alpha answer >
""")
        r = validate_project(root, strict=True)
        if not r.ok:
            return save_failure(
                "prior v2.7 return-question failure still present",
                root, r,
                "Payload-specific suffix ? return-question still failed to pair with matching ask.",
                "strict pass"
            )
    return None

def check_pending_declaration_creates_dependency_edge():
    """
    v2.8 still adds dependency edges after resolution regardless of declaration commit state.
    A pending/questioned declaration must not mutate dependency graph authority.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! c pending ?")
        write(root, "20_code/c.haci", "! c code >")
        r = validate_project(root, strict=False)
        edges = r.edges
        if any(e["from"].endswith("memory.m") and e["to"].endswith("code.c") for e in edges):
            return save_failure(
                "pending declaration creates dependency edge",
                root, r,
                "A pending declaration with suffix ? created a dependency edge as if the declaration were committed.",
                "pending declarations should not add dependency edges"
            )
    return None

def check_pending_declaration_creates_cycle():
    """
    Worse version: two pending declarations can create a dependency cycle and fail a project,
    even though neither side committed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! c pending ?")
        write(root, "20_code/c.haci", "! m pending ?")
        r = validate_project(root, strict=False)
        if has_error(r, "DEPENDENCY_CYCLE"):
            return save_failure(
                "pending declarations create dependency cycle",
                root, r,
                "Two pending declarations created a dependency cycle, allowing uncommitted text to mutate graph topology.",
                "pending declarations should not create graph edges or cycles"
            )
    return None

def check_ask_dependency_edge_still_exists():
    """
    Positive control: non-declaration references may still create dependency edges.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "? c status >")
        write(root, "20_code/c.haci", "! c code >")
        r = validate_project(root, strict=False)
        if not any(e["from"].endswith("memory.m") and e["to"].endswith("code.c") for e in r.edges):
            return save_failure(
                "ask dependency edge missing",
                root, r,
                "A real ask reference no longer produced a dependency edge.",
                "ask/reference edge should exist"
            )
    return None

def check_late_return_question_cross_file():
    """
    v2.8 late-return-question guard is same-file line-order only.
    Cross-file order is intentionally weak, so do not fail unless it silently hides same-file ordering.
    """
    return None

def check_answer_before_ask_same_file_temporal():
    """
    Same-file answer before ask is currently likely accepted because pairing is order-independent.
    Cross-file order independence is required, but same-file reverse return is a possible protocol leak.
    Mark as failure only if strict passes and no diagnostic is present.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """m alpha answer >
? m alpha question
""")
        r = validate_project(root, strict=True)
        if r.ok:
            return save_failure(
                "same-file return before ask accepted",
                root, r,
                "A return appearing before its ask in the same HACI file was accepted. Cross-file pairing may be order-independent, but same-file chronology should not silently invert.",
                "strict failure or chronology diagnostic"
            )
    return None

def check_deep_grandchild_under_pending_intermediate():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! m memory >")
        write(root, "10_memory/m/parser.haci", "! parser parser ?")
        write(root, "10_memory/m/parser/last.haci", "! last prior >")
        r = validate_project(root, strict=False)
        child = r.symbols.get("memory.m.parser.last", {})
        if r.ok or child.get("meaning") == "prior":
            return save_failure(
                "grandchild committed under pending intermediate parent",
                root, r,
                "Committed root existed, but nearest intermediate parent was pending; child committed or project passed.",
                "PENDING_PARENT_SCOPE with child commit blocked"
            )
    return None

def check_ambiguous_return_question_still_fails():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha clarify ?
m alpha red >
m alpha blue >
""")
        r = validate_project(root, strict=True)
        if r.ok:
            return save_failure(
                "ambiguous return-question accepted",
                root, r,
                "Ambiguous suffix ? return-question was accepted.",
                "strict failure"
            )
    return None

def check_duplicate_identical_asks_returns_still_fail():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m alpha
? m alpha
m alpha >
m alpha >
""")
        r = validate_project(root, strict=True)
        if r.ok:
            return save_failure(
                "duplicate identical asks and returns accepted",
                root, r,
                "Indistinguishable duplicate conversations were accepted; pairing is unknowable.",
                "strict failure"
            )
    return None

def deterministic_heavy(rounds=10000, seed=28028028):
    rng = random.Random(seed)
    objs = ["m", "c", "n", "cache", "state", "log", "judge"]
    folders = {
        "m": "10_memory", "c": "20_code", "n": "30_network",
        "cache": "10_memory", "state": "00_core", "log": "40_log", "judge": "50_judge"
    }
    words = [
        "alpha", "beta", "gamma", "delta", "red", "blue", "green", "yellow",
        "first", "second", "needle", "thread", "memory", "code", "parser",
        "last", "audit", "return", "approve", "deployment", "accepted",
        "clarify", "problem", "answer"
    ]
    for i in range(rounds):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            declared = []
            for obj in objs:
                if rng.random() < 0.65:
                    suffix = ">" if rng.random() < 0.9 else "?"
                    write(root, f"{folders[obj]}/{obj}.haci", f"! {obj} {obj} {suffix}\n")
                    declared.append(obj)
            if not declared:
                write(root, "10_memory/m.haci", "! m memory >\n")
                declared = ["m"]

            if "m" in declared and rng.random() < 0.35:
                if rng.random() < 0.35:
                    mid_suffix = ">" if rng.random() < 0.7 else "?"
                    write(root, "10_memory/m/parser.haci", f"! parser parser {mid_suffix}\n")
                write(root, "10_memory/m/parser/last.haci", "! last last >\n")

            lines = []
            for _ in range(rng.randint(1, 34)):
                obj = rng.choice(objs if rng.random() < 0.45 else declared)
                if obj == "m" and rng.random() < 0.18:
                    obj = "m.parser.last"
                payload = " ".join(rng.sample(words, rng.randint(1, 4)))
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
                    lines.append("# section")
                else:
                    lines.append("")
            write(root, "90_runtime/runtime.haci", "\n".join(lines) + "\n")
            strict = bool(i % 2)
            r1 = validate_project(root, strict=strict)
            r2 = validate_project(root, strict=strict)
            if stable(r1) != stable(r2):
                return save_failure(
                    "non deterministic heavy fuzz",
                    root, r1,
                    f"Same input produced different outputs at fuzz round {i}.",
                    "identical output"
                )
    return None

def main():
    checks = [
        check_prior_v27_return_question_fixed,
        check_pending_declaration_creates_dependency_edge,
        check_pending_declaration_creates_cycle,
        check_ask_dependency_edge_still_exists,
        check_answer_before_ask_same_file_temporal,
        check_deep_grandchild_under_pending_intermediate,
        check_ambiguous_return_question_still_fails,
        check_duplicate_identical_asks_returns_still_fail,
        lambda: deterministic_heavy(10000),
    ]

    for check in checks:
        try:
            found = check()
        except Exception:
            summary = {
                "failure": "uncaught exception",
                "reason": traceback.format_exc(),
            }
            Path("FAILURE_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(json.dumps(summary, indent=2))
            return 1
        if found:
            print(json.dumps(found, indent=2))
            return 1

    summary = {"failure": None, "message": "No failure found in current v2.8 audit-to-failure run."}
    Path("FAILURE_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
