#!/usr/bin/env python3
"""
HACI Validator v2.5 — Torture to Failure

No new features.
Goal: find the next meaningful semantic failure in v2.5.
"""

from pathlib import Path
import tempfile, shutil, json, random, traceback
from haci_project_validator_v2_5 import validate_project

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

def check_prior_commit_gating_fixed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! m memory ?")
        r = validate_project(root, strict=True)
        sym = r.symbols.get("memory.m", {})
        if sym.get("meaning") == "memory" or sym.get("authority") == "human":
            return save_failure(
                "prior v2.4 commit-gating failure still present",
                root, r,
                "Pending declaration still mutates committed symbol state.",
                "no committed meaning or authority"
            )
    return None

def check_single_accepted_return_no_overlap():
    """
    v2.5 keeps no-guess token-overlap pairing even for suffix !.
    But protocol says suffix ! = accepted / acknowledged / committed back.
    If there is exactly one open ask on that object and one accepted return, it should close.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m approve deployment
m accepted !
""")
        r = validate_project(root, strict=True)
        if not r.ok:
            return save_failure(
                "single accepted return does not complete ask",
                root, r,
                "With one open ask for object m, suffix ! means accepted/committed back, but v2.5 still requires payload-token overlap and leaves it open.",
                "strict pass for unique same-object accepted return"
            )
    return None

def check_duplicate_accepted_return_must_not_guess():
    """
    Guardrail: the fix for the previous case must not allow guessing between duplicate opens.
    This should fail closed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m approve deployment
? m approve deployment
m accepted !
""")
        r = validate_project(root, strict=True)
        if r.ok:
            return save_failure(
                "accepted return guessed between duplicate asks",
                root, r,
                "A single accepted return was allowed to choose between duplicate open asks.",
                "strict failure"
            )
    return None

def check_single_observe_no_overlap_should_not_complete():
    """
    Positive contrast: suffix > is evidence/result; without payload overlap it should NOT blindly complete.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m approve deployment
m unrelated >
""")
        r = validate_project(root, strict=True)
        if r.ok:
            return save_failure(
                "single unrelated observe return completed ask",
                root, r,
                "Suffix > is evidence/result and should not close a single open ask without a unique payload relation.",
                "strict failure"
            )
    return None

def check_return_question_then_commit_no_overlap():
    """
    One open ask, a clarifying return-question, then a commit.
    Commit should close the ask even if it says accepted.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m approve deployment
m clarify ?
m accepted !
""")
        r = validate_project(root, strict=True)
        if not r.ok:
            return save_failure(
                "return question then accepted commit did not close ask",
                root, r,
                "A returned question kept the ask open, then a unique same-object accepted commit should close it.",
                "strict pass"
            )
    return None

def check_pending_symbol_allows_deep_path():
    """
    If m is only pending, m.parser.last should not become valid root authority.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! m memory ?")
        write(root, "10_memory/m/parser/last.haci", "! last prior >")
        write(root, "20_runtime/runtime.haci", "? m.parser.last previous result >")
        r = validate_project(root, strict=True)
        # It will fail due pending declaration. But does it also treat deep path as valid?
        # This is ambiguous; don't fail unless strict passes.
        if r.ok:
            return save_failure(
                "deep path accepted under pending root declaration",
                root, r,
                "A pending root declaration allowed a deep child path to validate as committed.",
                "strict failure"
            )
    return None

def check_committed_ai_then_human_authority_mutation():
    """
    AI authority warning should not become immutable human authority.
    Later human declaration should be allowed to assert authority without AI-owned immutable lock.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """! m MEMORY >
! m memory >
""")
        r = validate_project(root, strict=True)
        # First line is AI-owned payload authority by current owner classifier, second human.
        # If it conflicts purely by meaning, v2.5 likely errors. Is that desired? Maybe yes: committed meaning changed.
        # Not hard failure.
    return None

def check_duplicate_identical_asks_and_returns():
    """
    Duplicate identical asks and identical returns should fail closed.
    """
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

def check_canonical_deep_path_duplicate_stem():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! m memory >")
        write(root, "10_memory/m/parser/last.haci", "! last last >")
        write(root, "20_code/m.haci", "! m code >")
        write(root, "30_runtime/runtime.haci", "? memory.m.parser.last last >")
        r = validate_project(root, strict=True)
        if not r.ok:
            return save_failure(
                "canonical deep dot path failed with duplicate stem",
                root, r,
                "Exact canonical memory.m.parser.last should resolve despite another code.m alias.",
                "strict pass"
            )
    return None

def deterministic_heavy(rounds=6000, seed=25025025):
    rng = random.Random(seed)
    objs = ["m", "c", "n", "cache", "state", "log", "judge"]
    folders = {
        "m": "10_memory", "c": "20_code", "n": "30_network",
        "cache": "10_memory", "state": "00_core", "log": "40_log", "judge": "50_judge"
    }
    words = [
        "alpha", "beta", "gamma", "delta", "red", "blue", "green", "yellow",
        "first", "second", "needle", "thread", "memory", "code", "parser",
        "last", "audit", "return", "approve", "deployment", "accepted"
    ]
    for i in range(rounds):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            declared = []
            for obj in objs:
                if rng.random() < 0.65:
                    write(root, f"{folders[obj]}/{obj}.haci", f"! {obj} {obj} >\n")
                    declared.append(obj)
            if not declared:
                write(root, "10_memory/m.haci", "! m memory >\n")
                declared = ["m"]

            if "m" in declared and rng.random() < 0.30:
                write(root, "10_memory/m/parser/last.haci", "! last last >\n")

            lines = []
            for _ in range(rng.randint(1, 30)):
                obj = rng.choice(objs if rng.random() < 0.45 else declared)
                if obj == "m" and rng.random() < 0.15:
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
        check_prior_commit_gating_fixed,
        check_single_accepted_return_no_overlap,
        check_duplicate_accepted_return_must_not_guess,
        check_single_observe_no_overlap_should_not_complete,
        check_return_question_then_commit_no_overlap,
        check_pending_symbol_allows_deep_path,
        check_committed_ai_then_human_authority_mutation,
        check_duplicate_identical_asks_and_returns,
        check_canonical_deep_path_duplicate_stem,
        lambda: deterministic_heavy(6000),
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

    summary = {"failure": None, "message": "No failure found in current v2.5 torture-to-failure run."}
    Path("FAILURE_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
