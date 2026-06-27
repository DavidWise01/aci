#!/usr/bin/env python3
"""
HACI Validator v3.4 — Torture to Failure

No new features.
Goal: find the next meaningful semantic/protocol failure after Missing Parent Scope Gate.
"""

from pathlib import Path
import tempfile, shutil, json, random, traceback
from haci_project_validator_v3_4 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

def stable(r):
    data = json.loads(json.dumps(r.__dict__, default=lambda o: o.__dict__))
    root = data.get("root", "")
    return json.dumps(data, sort_keys=True).replace(root, "<ROOT>")

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

def edge_exists(r, src_suffix, dst_suffix):
    return any(e["from"].endswith(src_suffix) and e["to"].endswith(dst_suffix) for e in r.edges)

def edges_to(r, dst_suffix):
    return [e for e in r.edges if e["to"].endswith(dst_suffix)]

def ask_convs(r):
    return [c for c in r.conversations if c.get("kind") == "conversation" and c.get("start", {}).get("outbound") == "ask"]

def count_returns(conv, inbound=None):
    if inbound is None:
        return len(conv.get("returns", []))
    return sum(1 for ret in conv.get("returns", []) if ret.get("inbound") == inbound)

# Prior fix check

def check_prior_v33_missing_parent_fixed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m/parser/last.haci", "! last prior >")
        r = validate_project(root, strict=True)
        child = r.symbols.get("memory.m.parser.last", {})
        if r.ok or not has_error(r, "MISSING_PARENT_SCOPE") or child.get("commit_state") != "blocked_missing_parent" or "meaning" in child:
            return save_failure(
                "prior v3.3 missing-parent failure still present",
                root, r,
                "Missing parent child still committed or was not diagnosed.",
                "strict failure with MISSING_PARENT_SCOPE and demoted child symbol"
            )
    return None

def check_committed_parent_chain_still_passes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! m memory >")
        write(root, "10_memory/m/parser.haci", "! parser parser >")
        write(root, "10_memory/m/parser/last.haci", "! last prior >")
        r = validate_project(root, strict=True)
        if not r.ok:
            return save_failure(
                "committed parent chain rejected",
                root, r,
                "A complete committed parent chain was rejected.",
                "strict pass"
            )
    return None

def check_blocked_missing_parent_reference_creates_edge():
    """
    v3.4 demotes a child symbol under missing parent, but edges were created before scope gate.
    If a runtime asks the blocked child, the graph can still contain an edge to a blocked/uncommitted symbol.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m/parser/last.haci", "! last prior >")
        write(root, "20_runtime/runtime.haci", "? memory.m.parser.last previous result >")
        r = validate_project(root, strict=True)
        child = r.symbols.get("memory.m.parser.last", {})
        leaked_edges = edges_to(r, "memory.m.parser.last")
        if child.get("commit_state") == "blocked_missing_parent" and leaked_edges:
            return save_failure(
                "blocked missing-parent child still receives dependency edge",
                root, r,
                "The scope gate demoted the child symbol, but graph edges created earlier still point to that blocked child.",
                "no dependency edges to symbols whose commit_state is blocked_missing_parent"
            )
    return None

def check_blocked_pending_parent_reference_creates_edge():
    """
    Same graph topology leak, but for pending parent rather than missing parent.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! m memory ?")
        write(root, "10_memory/m/parser.haci", "! parser parser >")
        write(root, "20_runtime/runtime.haci", "? memory.m.parser parser status >")
        r = validate_project(root, strict=True)
        child = r.symbols.get("memory.m.parser", {})
        leaked_edges = edges_to(r, "memory.m.parser")
        if child.get("commit_state") == "blocked_pending_parent" and leaked_edges:
            return save_failure(
                "blocked pending-parent child still receives dependency edge",
                root, r,
                "The pending-parent gate demoted the child symbol, but graph edges still point to that blocked child.",
                "no dependency edges to symbols whose commit_state is blocked_pending_parent"
            )
    return None

def check_blocked_child_conversation_still_pairs():
    """
    Conversation pairing may still treat a blocked child symbol as a valid resolved object.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m/parser/last.haci", "! last prior >")
        write(root, "20_runtime/runtime.haci", """? memory.m.parser.last alpha problem
memory.m.parser.last alpha answer >
""")
        r = validate_project(root, strict=True)
        child = r.symbols.get("memory.m.parser.last", {})
        convs = ask_convs(r)
        paired = bool(convs and any(ret.get("payload") == "alpha answer" for ret in convs[0].get("returns", [])))
        if child.get("commit_state") == "blocked_missing_parent" and paired:
            return save_failure(
                "blocked missing-parent child still used for conversation pairing",
                root, r,
                "A blocked missing-parent symbol still served as the resolved object for a complete ask/return conversation.",
                "blocked symbols should not be usable as valid conversation objects"
            )
    return None

def check_multi_return_cores_still_hold():
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
                "multi-return cores regressed",
                root, r,
                "Combined ?/>/! returns no longer preserve on one ask.",
                "strict pass with all return channels"
            )
    return None

def check_same_file_chronology_still_fixed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "m alpha answer >\n? m alpha question\n")
        r = validate_project(root, strict=True)
        if r.ok or not has_error(r, "SAME_FILE_RETURN_BEFORE_ASK"):
            return save_failure(
                "same-file chronology regression",
                root, r,
                "Same-file return before ask was accepted again.",
                "strict failure"
            )
    return None

def check_pending_decl_edge_still_fixed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! c pending ?")
        write(root, "20_code/c.haci", "! c code >")
        r = validate_project(root, strict=False)
        if edge_exists(r, "memory.m", "code.c"):
            return save_failure(
                "pending declaration edge regression",
                root, r,
                "Pending declaration created dependency edge again.",
                "no graph edge"
            )
    return None

def deterministic_light(rounds=4000, seed=34034034):
    rng = random.Random(seed)
    objs = ["m", "c", "n", "cache", "state", "log", "judge"]
    folders = {
        "m": "10_memory", "c": "20_code", "n": "30_network",
        "cache": "10_memory", "state": "00_core", "log": "40_log", "judge": "50_judge"
    }
    words = [
        "alpha", "beta", "gamma", "delta", "red", "blue", "green", "yellow",
        "first", "second", "needle", "thread", "memory", "code", "parser",
        "last", "audit", "return", "approve", "approval", "deployment", "accepted",
        "committed", "clarify", "problem", "answer", "scope", "detail", "evidence"
    ]
    for i in range(rounds):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            declared = []
            for obj in objs:
                if rng.random() < 0.6:
                    suffix = ">" if rng.random() < 0.88 else "?"
                    write(root, f"{folders[obj]}/{obj}.haci", f"! {obj} {obj} {suffix}\n")
                    declared.append(obj)
            if not declared:
                write(root, "10_memory/m.haci", "! m memory >\n")
                declared = ["m"]

            # Sometimes make full parent chain, sometimes intentionally omit intermediate.
            if "m" in declared and rng.random() < 0.25:
                if rng.random() < 0.55:
                    write(root, "10_memory/m/parser.haci", "! parser parser >\n")
                write(root, "10_memory/m/parser/last.haci", "! last last >\n")

            lines = []
            for _ in range(rng.randint(1, 22)):
                obj = rng.choice(objs if rng.random() < 0.5 else declared)
                if obj == "m" and rng.random() < 0.15:
                    obj = "memory.m.parser.last"
                payload = " ".join(rng.sample(words, rng.randint(1, 3)))
                kind = rng.choice(["ask", "return_obs", "return_q", "return_commit", "dual_obs", "dual_q", "dual_commit", "body", "heading", "blank"])
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
                    "non deterministic light fuzz",
                    root, r1,
                    f"Same input produced different outputs at fuzz round {i}.",
                    "identical output"
                )
    return None

def main():
    checks = [
        check_prior_v33_missing_parent_fixed,
        check_committed_parent_chain_still_passes,
        check_blocked_missing_parent_reference_creates_edge,
        check_blocked_pending_parent_reference_creates_edge,
        check_blocked_child_conversation_still_pairs,
        check_multi_return_cores_still_hold,
        check_same_file_chronology_still_fixed,
        check_pending_decl_edge_still_fixed,
        lambda: deterministic_light(4000),
    ]

    for check in checks:
        try:
            found = check()
        except Exception:
            summary = {
                "failure": "uncaught exception",
                "reason": traceback.format_exc(),
                "expected": "no exception",
                "saved_to": None,
                "errors": [],
                "warnings": [],
            }
            Path("FAILURE_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(json.dumps(summary, indent=2))
            return 1

        if found:
            print(json.dumps(found, indent=2))
            return 1

    summary = {"failure": None, "message": "No failure found in current v3.4 torture-to-failure run."}
    Path("FAILURE_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
