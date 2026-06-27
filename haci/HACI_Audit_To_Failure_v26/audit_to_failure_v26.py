#!/usr/bin/env python3
"""
HACI Validator v2.6 — Audit to Failure

No features.
Goal: find the next meaningful semantic failure in v2.6.
"""

from pathlib import Path
import tempfile, shutil, json, random, traceback
from haci_project_validator_v2_6 import validate_project

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

def check_prior_v25_accept_fixed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "? m approve deployment\nm accepted !\n")
        r = validate_project(root, strict=True)
        if not r.ok:
            return save_failure(
                "prior v2.5 accepted-return failure still present",
                root, r,
                "Unique same-object accepted return still failed to close ask.",
                "strict pass"
            )
    return None

def check_pending_root_deep_path_loose_passes():
    """
    Critical scope/authority audit:
    A pending/questioned root declaration should not make child paths reliable.
    In v2.6, file symbols exist before committed declarations, so a pending root can still support deep path resolution.
    In non-strict mode this may pass with warnings, producing a usable child path under an uncommitted parent.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! m memory ?")
        write(root, "10_memory/m/parser/last.haci", "! last prior >")
        write(root, "20_runtime/runtime.haci", "? m.parser.last previous result >")
        r = validate_project(root, strict=False)
        sym_parent = r.symbols.get("memory.m", {})
        sym_child = r.symbols.get("memory.m.parser.last", {})
        if r.ok and "meaning" not in sym_parent and sym_child.get("meaning") == "prior":
            return save_failure(
                "deep child path accepted under pending parent in loose mode",
                root, r,
                "The parent object m is pending/uncommitted, but child path m.parser.last resolved and the project passed in non-strict mode.",
                "non-strict should still block committed child authority under a pending parent, or mark project not ok"
            )
    return None

def check_pending_parent_child_commits_strict_error_specific():
    """
    Same project in strict should not merely fail because the parent declaration is open.
    It should also identify that a committed child depends on a pending parent.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! m memory ?")
        write(root, "10_memory/m/parser/last.haci", "! last prior >")
        r = validate_project(root, strict=True)
        if r.symbols.get("memory.m.parser.last", {}).get("meaning") == "prior" and not has_error(r, "PENDING_PARENT"):
            return save_failure(
                "committed child lacks pending-parent diagnostic",
                root, r,
                "A child symbol committed beneath pending parent memory.m, but validator has no pending-parent diagnostic.",
                "PENDING_PARENT error/warning"
            )
    return None

def check_accepted_return_after_one_payload_match_should_close_remaining():
    """
    Positive control: two asks, one payload answer, one accepted commit. Should pass because after payload match only one open ask remains.
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
                "accepted fallback failed after payload match",
                root, r,
                "After one ask is resolved by payload, exactly one ask and one accepted return remain; v2.6 should close it.",
                "strict pass"
            )
    return None

def check_accepted_return_wrongly_closes_after_unrelated_observe_extra():
    """
    Multiple remaining returns should prevent accepted fallback.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m approve deployment
m unrelated >
m accepted !
""")
        r = validate_project(root, strict=True)
        if r.ok:
            return save_failure(
                "accepted fallback ignored competing unrelated return",
                root, r,
                "Accepted fallback closed while another same-object return was still present.",
                "strict failure"
            )
    return None

def check_pending_declaration_edges_create_dependencies():
    """
    Pending declarations should not act as committed dependency edges.
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

def deterministic_heavy(rounds=8000, seed=26026026):
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
                    suffix = ">" if rng.random() < 0.9 else "?"
                    write(root, f"{folders[obj]}/{obj}.haci", f"! {obj} {obj} {suffix}\n")
                    declared.append(obj)
            if not declared:
                write(root, "10_memory/m.haci", "! m memory >\n")
                declared = ["m"]

            if "m" in declared and rng.random() < 0.35:
                write(root, "10_memory/m/parser/last.haci", "! last last >\n")

            lines = []
            for _ in range(rng.randint(1, 32)):
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
        check_prior_v25_accept_fixed,
        check_pending_root_deep_path_loose_passes,
        check_pending_parent_child_commits_strict_error_specific,
        check_accepted_return_after_one_payload_match_should_close_remaining,
        check_accepted_return_wrongly_closes_after_unrelated_observe_extra,
        check_pending_declaration_edges_create_dependencies,
        check_identical_duplicate_asks_returns_still_fail,
        lambda: deterministic_heavy(8000),
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

    summary = {"failure": None, "message": "No failure found in current v2.6 audit-to-failure run."}
    Path("FAILURE_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
