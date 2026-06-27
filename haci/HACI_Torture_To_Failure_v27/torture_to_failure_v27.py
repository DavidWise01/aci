#!/usr/bin/env python3
"""
HACI Validator v2.7 — Torture to Failure

No new features.
Goal: find the next meaningful semantic/protocol failure in v2.7.
"""

from pathlib import Path
import tempfile, shutil, json, random, traceback
from haci_project_validator_v2_7 import validate_project

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

def has_warning(r, token):
    return any(token in w for w in r.warnings)

def ask_convs(r):
    return [c for c in r.conversations if c["kind"] == "conversation" and c["start"]["outbound"] == "ask"]

def check_prior_pending_parent_fixed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! m memory ?")
        write(root, "10_memory/m/parser/last.haci", "! last prior >")
        write(root, "20_runtime/runtime.haci", "? m.parser.last previous result >")
        r = validate_project(root, strict=False)
        child = r.symbols.get("memory.m.parser.last", {})
        if r.ok or child.get("meaning") == "prior":
            return save_failure(
                "prior v2.6 pending-parent failure still present",
                root, r,
                "Pending parent still allowed committed child authority.",
                "non-strict failure with child commit blocked"
            )
    return None

def check_return_question_disambiguation_with_multiple_asks():
    """
    v2.7 attaches suffix-? return-question only when exactly one open conversation exists for the object.
    That is too crude. A return-question can be payload-specific and should attach by unique payload relation,
    especially when a later answer closes the same ask.

    This project should pass:
      - first ask receives return-question + later answer
      - second ask receives its own answer
    """
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
                "payload-specific return-question not paired with matching ask",
                root, r,
                "A suffix-? return-question was treated as RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST because multiple asks existed, even though payload made it uniquely attachable.",
                "strict pass with alpha question attached to alpha ask"
            )
        # If it passed but lost the question, also fail.
        convs = ask_convs(r)
        alpha = [c for c in convs if "alpha problem" in c["start"]["payload"]][0]
        if not any(ret.get("inbound") == "ask" and "alpha clarify" in ret.get("payload","") for ret in alpha["returns"]):
            return save_failure(
                "payload-specific return-question was not preserved",
                root, r,
                "Project passed, but the alpha return-question was not attached/preserved on the alpha conversation.",
                "alpha conversation should contain suffix-? return"
            )
    return None

def check_return_question_order_after_answer():
    """
    Return-question after a complete answer should not reopen a completed ask unless explicitly unresolved.
    Existing behavior likely makes it unmatched return-question with no unique open request. That may be acceptable.
    Not failing unless strict incorrectly passes with dangling question hidden.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m alpha problem
m alpha answer >
m alpha clarify ?
""")
        r = validate_project(root, strict=True)
        if r.ok:
            # Since the question comes after completion and there is no open request, strict should flag it.
            return save_failure(
                "late return-question after completed ask accepted silently",
                root, r,
                "A suffix-? return-question after a completed ask was accepted with no open target.",
                "strict failure"
            )
    return None

def check_accepted_fallback_after_disambiguating_payload():
    """
    Already expected to pass in audit. Verify before moving on.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m approve deployment
? m report status
m report status >
m accepted !
""")
        r = validate_project(root, strict=True)
        if not r.ok:
            return save_failure(
                "accepted fallback failed after one payload match",
                root, r,
                "After one ask was resolved by payload, exactly one ask and one accepted return remained.",
                "strict pass"
            )
    return None

def check_committed_grandparent_pending_parent_committed_child():
    """
    Ensure pending nearest parent still blocks even if higher ancestor is committed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! m memory >")
        write(root, "10_memory/m/parser.haci", "! parser parser ?")
        write(root, "10_memory/m/parser/last.haci", "! last prior >")
        r = validate_project(root, strict=False)
        child = r.symbols.get("memory.m.parser.last", {})
        if r.ok or child.get("meaning") == "prior":
            return save_failure(
                "committed grandparent allowed child under pending parent",
                root, r,
                "A committed grandparent existed, but nearest parent memory.m.parser was pending; child still committed or project passed.",
                "failure with PENDING_PARENT_SCOPE"
            )
    return None

def check_pending_declaration_creates_dependency_edge():
    """
    Pending declarations should not produce dependency edges.
    Example: ! c pending ? in m.haci should not create memory.m -> code.c edge.
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
                "A pending declaration with suffix ? created a dependency edge as if committed.",
                "pending declarations should not add dependency edges"
            )
    return None

def check_objectless_return_question():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "clarify ?")
        r = validate_project(root, strict=True)
        if r.ok:
            return save_failure(
                "objectless return-question accepted",
                root, r,
                "A suffix-? protocol return with no declared object was accepted.",
                "strict failure"
            )
    return None

def check_identical_duplicate_asks_returns_still_fail():
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

def deterministic_heavy(rounds=10000, seed=27027027):
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
                # sometimes create intermediate parent
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
        check_prior_pending_parent_fixed,
        check_return_question_disambiguation_with_multiple_asks,
        check_return_question_order_after_answer,
        check_accepted_fallback_after_disambiguating_payload,
        check_committed_grandparent_pending_parent_committed_child,
        check_pending_declaration_creates_dependency_edge,
        check_objectless_return_question,
        check_identical_duplicate_asks_returns_still_fail,
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

    summary = {"failure": None, "message": "No failure found in current v2.7 torture-to-failure run."}
    Path("FAILURE_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
