#!/usr/bin/env python3
from pathlib import Path
import tempfile, json, random, shutil, traceback, hashlib
from haci_project_validator_v2_2 import validate_project

def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

def stable(r):
    data = json.loads(json.dumps(r.__dict__, default=lambda o: o.__dict__))
    root = data.get("root","")
    s = json.dumps(data, sort_keys=True)
    return s.replace(root, "<ROOT>")

def save_failure(name, root, result, reason):
    out = Path("FAILURE_FOUND")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    shutil.copytree(root, out/"project")
    (out/"reason.txt").write_text(reason, encoding="utf-8")
    (out/"result.json").write_text(json.dumps(result.__dict__, default=lambda o: o.__dict__, indent=2), encoding="utf-8")
    return {
        "failure": name,
        "reason": reason,
        "saved_to": str(out),
        "errors": result.errors,
        "warnings": result.warnings,
    }

def protocol_pairing_tie_hunt():
    """
    Hunt a semantic weakness:
    multiple unresolved asks share one object and positive-overlap returns.
    The current validator uses greedy positive overlap. Equal positive scores can silently pair wrong.
    We define a stricter property for this hunt:
    If every return has equal score against multiple asks, pairing should be ambiguous, not accepted.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m alpha one
? m alpha two
m alpha two >
m alpha one >
""")
        r = validate_project(root, strict=True)
        # Scores are not all equal here, so should pass.
        if not r.ok:
            return save_failure("pairing regression obvious positive match", root, r, "clear positive token match failed")

    # Equal positive overlap ambiguous case.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m alpha red
? m alpha blue
m alpha green >
m alpha yellow >
""")
        r = validate_project(root, strict=True)
        # Existing validator accepts this because positive alpha overlap is enough.
        # For torture-to-failure, this is a real protocol failure: ambiguous equal-score returns should not commit.
        if r.ok:
            return save_failure(
                "ambiguous positive return pairing accepted",
                root,
                r,
                "Validator accepted ambiguous positive-overlap returns. Object+payload scoring is too weak when all candidate scores tie."
            )
    return None

def dot_path_local_hunt():
    # Dotted declaration should not create virtual path.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", "! m memory >\n! m.parser phantom >\n")
        r = validate_project(root, strict=True)
        if r.ok:
            return save_failure("phantom dotted declaration accepted", root, r, "Dotted declaration created/accepted nonexistent path.")
    return None

def boundary_hunt():
    # Boundary should stop body, but return should still pair with unresolved ask.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "10_memory/m.haci", """? m previous result

# section
not body
m previous result >
""")
        r = validate_project(root, strict=True)
        if not r.ok:
            return save_failure("boundary valid return failed", root, r, "Boundary stopped body but also broke valid later return.")
        conv = [c for c in r.conversations if c["kind"]=="conversation"][0]
        if conv["body"]:
            return save_failure("boundary body leakage", root, r, "Heading/blank boundary leaked loose note into previous conversation body.")
    return None

def determinism_hunt(rounds=2000, seed=20260626):
    rng = random.Random(seed)
    objs = ["m","c","n","cache","state"]
    folders = {"m":"10_memory", "c":"20_code", "n":"30_network", "cache":"10_memory", "state":"00_core"}
    words = ["alpha","beta","gamma","delta","red","blue","green","yellow","first","second","memory","code","last","parser"]
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
            lines = []
            for _ in range(rng.randint(1,15)):
                obj = rng.choice(objs if rng.random()<0.4 else declared)
                if rng.random() < 0.1 and obj == "m":
                    obj = "m.parser.last"
                payload = " ".join(rng.sample(words, rng.randint(1,3)))
                kind = rng.choice(["ask","return","dual","declare","body","heading","blank"])
                if kind == "ask":
                    lines.append(f"? {obj} {payload}")
                elif kind == "return":
                    lines.append(f"{obj} {payload} >")
                elif kind == "dual":
                    lines.append(f"? {obj} {payload} >")
                elif kind == "declare":
                    lines.append(f"! {obj} {payload} >")
                elif kind == "body":
                    lines.append(payload)
                elif kind == "heading":
                    lines.append("# section")
                else:
                    lines.append("")
            write(root, "90_runtime/runtime.haci", "\n".join(lines)+"\n")
            strict = bool(i % 2)
            r1 = validate_project(root, strict=strict)
            r2 = validate_project(root, strict=strict)
            if stable(r1) != stable(r2):
                return save_failure("non deterministic fuzz", root, r1, f"Same project produced different outputs at round {i}.")
    return None

def main():
    checks = [
        protocol_pairing_tie_hunt,
        dot_path_local_hunt,
        boundary_hunt,
        lambda: determinism_hunt(2000),
    ]
    for check in checks:
        found = check()
        if found:
            Path("FAILURE_SUMMARY.json").write_text(json.dumps(found, indent=2), encoding="utf-8")
            print(json.dumps(found, indent=2))
            return 1
    ok = {"failure": None, "message": "No failure found in current targeted hunt."}
    Path("FAILURE_SUMMARY.json").write_text(json.dumps(ok, indent=2), encoding="utf-8")
    print(json.dumps(ok, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
