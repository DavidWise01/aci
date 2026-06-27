#!/usr/bin/env python3
"""
HACI Validator v2.9 — Audit to Failure

No new features.
Goal: find the next meaningful semantic/protocol failure in v2.9.
"""

from pathlib import Path
import tempfile, shutil, json, random, traceback
from haci_project_validator_v2_9 import validate_project

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

def edge_exists(r, src_suffix, dst_suffix):
    return any(e["from"].endswith(src_suffix) and e["to"].endswith(dst_suffix) for e in r.edges)

def ask_convs(r):
    return [c for c in r.conversations if c["kind"] == "conversation" and c["start"]["outbound"] == "ask"]

def check_prior_v28_pending_edge_fixed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! c pending ?")
        write(root, "20_code/c.haci", "! c code >")
        r = validate_project(root, strict=False)
        if edge_exists(r, "memory.m", "code.c"):
            return save_failure(
                "prior v2.8 pending-declaration edge failure still present",
                root, r,
                "Pending declaration still created dependency edge.",
                "no edge from memory.m to code.c"
            )
    return None

def check_same_file_return_before_ask_temporal_inversion():
    """
    Cross-file pairing should be order-independent, but same-file chronology should not silently invert:
      return appears before ask in the same file.
    v2.9 likely pairs it anyway.
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
                "A return appearing before its ask in the same HACI file was accepted. Cross-file pairing needs order-independence, but same-file chronology should not silently invert.",
                "strict failure or SAME_FILE_RETURN_BEFORE_ASK diagnostic"
            )
    return None

def check_same_file_accepted_return_before_ask_temporal_inversion():
    """
    Accepted fallback must not allow same-file accepted return before ask.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """m accepted !
? m approve deployment
""")
        r = validate_project(root, strict=True)
        if r.ok:
            return save_failure(
                "same-file accepted return before ask accepted",
                root, r,
                "A suffix ! accepted return before the ask was accepted by the pairing engine.",
                "strict failure or SAME_FILE_RETURN_BEFORE_ASK diagnostic"
            )
    return None

def check_cross_file_return_before_ask_still_allowed():
    """
    Cross-file order-independent pairing is required by earlier design.
    This should pass, otherwise a chronology patch would be too broad.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/returns.haci", "m alpha answer >")
        write(root, "20_runtime/ask.haci", "? m alpha question")
        write(root, "00_scope/m.haci", "! m memory >")
        r = validate_project(root, strict=True)
        if not r.ok:
            return save_failure(
                "cross-file return before ask rejected",
                root, r,
                "Cross-file pairing became order-dependent, which breaks required cross-file merge behavior.",
                "strict pass"
            )
    return None

def check_same_file_return_question_before_ask():
    """
    Same-file return-question before ask should not attach backward either.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """m alpha clarify ?
? m alpha problem
m alpha answer >
""")
        r = validate_project(root, strict=True)
        if r.ok:
            return save_failure(
                "same-file return-question before ask accepted",
                root, r,
                "A suffix ? return-question before its ask was accepted/hidden in the later conversation.",
                "strict failure or SAME_FILE_RETURN_BEFORE_ASK diagnostic"
            )
    return None

def check_pending_declarations_do_not_create_cycle():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! c pending ?")
        write(root, "20_code/c.haci", "! m pending ?")
        r = validate_project(root, strict=False)
        if has_error(r, "DEPENDENCY_CYCLE") or r.edges:
            return save_failure(
                "pending declarations still affect graph topology",
                root, r,
                "Pending declarations still created edges/cycle after v2.9.",
                "no edges and no cycle"
            )
    return None

def check_committed_declaration_edge_still_exists():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! c code >")
        write(root, "20_code/c.haci", "! c code >")
        r = validate_project(root, strict=False)
        if not r.ok or not edge_exists(r, "memory.m", "code.c"):
            return save_failure(
                "committed declaration edge missing",
                root, r,
                "Committed declaration no longer creates expected dependency edge.",
                "ok with edge memory.m -> code.c"
            )
    return None

def check_late_return_question_after_completion_still_fails():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m alpha problem
m alpha answer >
m alpha clarify ?
""")
        r = validate_project(root, strict=True)
        if r.ok:
            return save_failure(
                "late return-question accepted",
                root, r,
                "Return-question after a completed answer was accepted.",
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

def deterministic_heavy(rounds=12000, seed=29029029):
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
            for _ in range(rng.randint(1, 36)):
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
        check_prior_v28_pending_edge_fixed,
        check_same_file_return_before_ask_temporal_inversion,
        check_same_file_accepted_return_before_ask_temporal_inversion,
        check_cross_file_return_before_ask_still_allowed,
        check_same_file_return_question_before_ask,
        check_pending_declarations_do_not_create_cycle,
        check_committed_declaration_edge_still_exists,
        check_late_return_question_after_completion_still_fails,
        check_duplicate_identical_asks_returns_still_fail,
        lambda: deterministic_heavy(12000),
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

    summary = {"failure": None, "message": "No failure found in current v2.9 audit-to-failure run."}
    Path("FAILURE_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
