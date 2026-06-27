#!/usr/bin/env python3
"""
HACI Validator v3.3 — Audit to Failure + Core Status

No new HACI features.
Purpose:
- verify fixed cores still hold
- find the next actual invariant leak
- report which cores are complete
"""

from pathlib import Path
import tempfile, shutil, json
from haci_project_validator_v3_3 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

def has_error(r, token):
    return any(token in e for e in r.errors)

def has_warning(r, token):
    return any(token in w for w in r.warnings)

def edge_exists(r, src_suffix, dst_suffix):
    return any(e.get("from","").endswith(src_suffix) and e.get("to","").endswith(dst_suffix) for e in r.edges)

def ask_convs(r):
    return [c for c in r.conversations if c.get("kind") == "conversation" and c.get("start", {}).get("outbound") == "ask"]

def count_returns(conv, inbound):
    return sum(1 for ret in conv.get("returns", []) if ret.get("inbound") == inbound)

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

# Core checks

def check_syntax_parse_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "30_runtime/runtime.haci", "```python\n? x ignored >\n```")
        r = validate_project(Path(tmp), strict=True)
        return r.ok and len(r.conversations) == 0

def check_inbound_semantics_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? m clarify this ?")
        r = validate_project(Path(tmp), strict=True)
        return not r.ok and has_error(r, "INBOUND_QUESTION_UNRESOLVED") and has_error(r, "ASK_WITHOUT_RETURN")

def check_commit_gating_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory ?")
        r = validate_project(Path(tmp), strict=True)
        sym = r.symbols.get("memory.m", {})
        return not r.ok and "meaning" not in sym and "authority" not in sym

def check_accepted_return_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "? m approve deployment\nm accepted !\n")
        r = validate_project(Path(tmp), strict=True)
        convs = ask_convs(r)
        return bool(r.ok and convs and count_returns(convs[0], "declare") == 1)

def check_pending_parent_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! m memory ?")
        write(tmp, "10_memory/m/parser/last.haci", "! last prior >")
        write(tmp, "20_runtime/runtime.haci", "? m.parser.last previous result >")
        r = validate_project(Path(tmp), strict=False)
        child = r.symbols.get("memory.m.parser.last", {})
        return not r.ok and has_error(r, "PENDING_PARENT_SCOPE") and "meaning" not in child

def check_return_question_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha problem
? m beta problem
m alpha clarify ?
m beta answer >
m alpha answer >
""")
        r = validate_project(Path(tmp), strict=True)
        convs = ask_convs(r)
        alpha = [c for c in convs if "alpha problem" in c.get("start", {}).get("payload","")]
        return bool(r.ok and alpha and count_returns(alpha[0], "ask") == 1 and count_returns(alpha[0], "observe") == 1)

def check_graph_edge_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "! c pending ?")
        write(tmp, "20_code/c.haci", "! c code >")
        r = validate_project(Path(tmp), strict=False)
        return not edge_exists(r, "memory.m", "code.c")

def check_chronology_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", "m alpha answer >\n? m alpha question\n")
        r = validate_project(Path(tmp), strict=True)
        return not r.ok and has_error(r, "SAME_FILE_RETURN_BEFORE_ASK")

def check_multi_question_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha problem
m alpha clarify scope ?
m alpha clarify detail ?
m alpha answer >
""")
        r = validate_project(Path(tmp), strict=True)
        convs = ask_convs(r)
        return bool(r.ok and convs and count_returns(convs[0], "ask") == 2)

def check_multi_evidence_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha problem
m alpha evidence one >
m alpha evidence two >
""")
        r = validate_project(Path(tmp), strict=True)
        convs = ask_convs(r)
        return bool(r.ok and convs and count_returns(convs[0], "observe") == 2)

def check_multi_commit_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha approval
m alpha accepted !
m alpha committed !
""")
        r = validate_project(Path(tmp), strict=True)
        convs = ask_convs(r)
        return bool(r.ok and convs and count_returns(convs[0], "declare") == 2)

def check_cross_file_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "00_scope/m.haci", "! m memory >")
        write(tmp, "10_returns/returns.haci", "m alpha answer >")
        write(tmp, "20_runtime/ask.haci", "? m alpha question")
        r = validate_project(Path(tmp), strict=True)
        return r.ok

def check_ambiguity_core():
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha green >
m alpha yellow >
""")
        r = validate_project(Path(tmp), strict=True)
        return not r.ok

CORE_CHECKS = [
    ("syntax_parse_core", "code fences and basic protocol parsing hold", check_syntax_parse_core),
    ("inbound_semantics_core", "suffix ? remains open; > and ! complete", check_inbound_semantics_core),
    ("commit_gating_core", "pending declarations do not mutate committed symbol authority", check_commit_gating_core),
    ("accepted_return_core", "unique no-token accepted ! fallback works", check_accepted_return_core),
    ("pending_parent_scope_core", "pending parent blocks child commit", check_pending_parent_core),
    ("return_question_pairing_core", "payload-specific ? return-question pairing works", check_return_question_core),
    ("graph_edge_core", "pending declarations create no dependency edges", check_graph_edge_core),
    ("same_file_chronology_core", "same-file returns cannot pair backward", check_chronology_core),
    ("multi_return_question_core", "multiple ? return-questions attach", check_multi_question_core),
    ("multi_evidence_return_core", "multiple > evidence/result returns attach", check_multi_evidence_core),
    ("multi_commit_return_core", "multiple positive ! commit returns attach", check_multi_commit_core),
    ("cross_file_merge_core", "cross-file return-before-ask remains order-independent", check_cross_file_core),
    ("ambiguity_rejection_core", "ambiguous pairings fail closed", check_ambiguity_core),
]

def run_core_status():
    rows = []
    for core, why, fn in CORE_CHECKS:
        try:
            ok = bool(fn())
        except Exception as e:
            ok = False
            why = why + f" EXCEPTION:{type(e).__name__}"
        rows.append({
            "core": core,
            "status": "COMPLETE" if ok else "REGRESSION",
            "holds_in_v3_3": ok,
            "why": why,
        })
    return rows

# Targeted audit-to-failure

def check_missing_parent_scope_leak():
    """
    v2.7 blocked child commit under a pending parent, but only if the parent symbol exists.
    A deep child file can still commit under a missing parent chain.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m/parser/last.haci", "! last prior >")
        r = validate_project(root, strict=True)
        child = r.symbols.get("memory.m.parser.last", {})
        if r.ok and child.get("commit_state") == "committed":
            return save_failure(
                "missing parent scope allows child commit",
                root, r,
                "A child scope committed even though its parent scopes `memory.m` and `memory.m.parser` do not exist. v2.7 blocked pending parents, but missing parents are still not gated.",
                "strict failure with MISSING_PARENT_SCOPE and no committed child meaning/authority"
            )
    return None

def check_missing_parent_referenced_child_leak():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m/parser/last.haci", "! last prior >")
        write(root, "20_runtime/runtime.haci", "? m.parser.last previous result >")
        r = validate_project(root, strict=True)
        child = r.symbols.get("memory.m.parser.last", {})
        if child.get("commit_state") == "committed" and "meaning" in child:
            return save_failure(
                "referenced missing parent child remains committed",
                root, r,
                "Referencing the missing-parent child produced an undeclared alias error, but the child symbol itself remained committed under a missing parent chain.",
                "child commit blocked or demoted when parent path is missing"
            )
    return None

def check_foreign_conflict_still_fails():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! c model >")
        write(root, "20_code/c.haci", "! c code >")
        r = validate_project(root, strict=False)
        if r.ok:
            return save_failure(
                "foreign conflicting declaration accepted",
                root, r,
                "A foreign committed declaration conflicted with target symbol meaning without failing.",
                "DUPLICATE_OR_CONFLICTING_SYMBOL or AUTHORITY_MUTATION"
            )
    return None

def check_multi_question_evidence_commit_combined():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m alpha approval problem
m alpha clarify scope ?
m alpha evidence one >
m alpha accepted !
m alpha committed !
""")
        r = validate_project(root, strict=True)
        convs = ask_convs(r)
        conv = convs[0] if convs else {}
        ok = r.ok and count_returns(conv, "ask") == 1 and count_returns(conv, "observe") == 1 and count_returns(conv, "declare") == 2
        if not ok:
            return save_failure(
                "combined return channels regressed",
                root, r,
                "A single ask could not preserve ? + > + multiple ! returns together.",
                "strict pass with all return channels preserved"
            )
    return None

def main():
    core_rows = run_core_status()
    Path("CORE_STATUS_v3_3.json").write_text(json.dumps(core_rows, indent=2), encoding="utf-8")

    checks = [
        check_missing_parent_scope_leak,
        check_missing_parent_referenced_child_leak,
        check_foreign_conflict_still_fails,
        check_multi_question_evidence_commit_combined,
    ]

    failure = None
    for check in checks:
        found = check()
        if found:
            failure = found
            break

    if failure is None:
        failure = {"failure": None, "message": "No failure found in current v3.3 targeted audit run."}
        Path("FAILURE_SUMMARY.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")

    report = {
        "latest": "v3.3",
        "complete_cores": [r["core"] for r in core_rows if r["status"] == "COMPLETE"],
        "regressed_cores": [r["core"] for r in core_rows if r["status"] != "COMPLETE"],
        "core_status": core_rows,
        "failure": failure,
        "recommended_next_patch": "v3.4 — Missing Parent Scope Gate" if failure.get("failure") else None,
    }
    Path("AUDIT_SUMMARY_v3_3.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = []
    md.append("# HACI v3.3 Audit to Failure + Core Status\\n\\n")
    md.append("## Core status\\n\\n")
    md.append("| Core | Status | Why |\\n|---|---:|---|\\n")
    for r in core_rows:
        md.append(f"| `{r['core']}` | **{r['status']}** | {r['why']} |\\n")
    md.append("\\n## Failure\\n\\n")
    if failure.get("failure"):
        md.append(f"- Failure: **{failure['failure']}**\\n")
        md.append(f"- Reason: {failure.get('reason')}\\n")
        md.append(f"- Expected: {failure.get('expected')}\\n")
        md.append("\\n## Next patch\\n\\n")
        md.append("`v3.4 — Missing Parent Scope Gate`\\n")
    else:
        md.append("- No failure found in this targeted run.\\n")
    Path("AUDIT_REPORT_v3_3.md").write_text("".join(md), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 1 if failure.get("failure") else 0

if __name__ == "__main__":
    raise SystemExit(main())
