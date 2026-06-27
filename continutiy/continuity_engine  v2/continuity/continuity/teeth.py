"""
SUBSTRATE TEETH — is every validation rule actually guarded?

The seam mutation proved the bridge suite has teeth. This proves the SUBSTRATE
validator does, rule by rule. For each rule we strip its error code from the
validator's output (the validator now wrongly ACCEPTS that violation) and re-run
the brutal BSS tier. A guarded rule = some should-reject probe flips to a false
positive. A rule that can be disabled with NO probe firing is unguarded — a
silent-acceptance hole, the dangerous direction. That is the exact gap the
duality-engine's brutal auditor had (cycle / ambiguous-object slipped through);
this harness refuses to let Continuity ship with it.
"""
from continuity import suite as S
from continuity import substrate as sub

# rule code -> human label. C2 (bridgeable) is guarded by is_bridgeable, not validate.
RULES = ["FORWARD_REF", "REF_NOT_FOUND", "AUTHORITY_EXCEEDED",
         "DUPLICATE_ID", "EMPTY_CONTENT", "INVALID_ROLE"]


def _strip(code):
    real = sub.validate
    def patched(Sx):
        return [e for e in real(Sx) if not e.startswith(code)]
    return real, patched


def run():
    # baseline must be clean
    base = S.brutal()
    results = []

    for code in RULES:
        real, patched = _strip(code)
        S.validate = patched          # suite.brutal() calls validate via this name
        try:
            b = S.brutal()
            guarded = not b["bss_ok"]   # a BSS probe should now fail (false positive surfaced)
            results.append((code, guarded, b["bss"]))
        finally:
            S.validate = real

    # C2 residue: disable bridgeability detection, the machine-only probe must fire
    real_bridge = sub.is_bridgeable
    S_real = S.is_bridgeable
    try:
        S.is_bridgeable = lambda Sx: True   # pretend everything bridges
        b = S.brutal()
        residue_guarded = not b["bss_ok"]
    finally:
        S.is_bridgeable = S_real

    all_guarded = base["ok"] and all(g for _, g, _ in results) and residue_guarded
    return {
        "baseline_ok": base["ok"],
        "rules": [{"rule": c, "guarded": g, "bss_when_disabled": bss} for c, g, bss in results],
        "residue_detection_guarded": residue_guarded,
        "guarded": sum(1 for _, g, _ in results if g) + (1 if residue_guarded else 0),
        "total": len(RULES) + 1,
        "non_vacuous": all_guarded,
    }


if __name__ == "__main__":
    import json, sys
    r = run()
    print(json.dumps(r, indent=2))
    sys.exit(0 if r["non_vacuous"] else 1)
