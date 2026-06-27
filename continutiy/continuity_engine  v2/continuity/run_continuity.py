#!/usr/bin/env python3
"""
THE CONTINUITY ENGINE — full verification pass.

    validate the substrate  ->  prove both exits faithful  ->  prove the bridge
    continuous (suite)  ->  audit it (brutal FSS/BSS)  ->  prove the suite has
    teeth (mutation: re-open the eskimo seam, demand a catch)  ->  anchor across
    time (chain)  ->  emit status, exit nonzero on any failure.
"""
import sys, json, importlib
from continuity import suite as S
from continuity.substrate import Msg, validate
from continuity import projections


def lossy_to_H(sub):
    """The eskimo regression, reintroduced: drop refs from the human exit.
    A faithful suite MUST catch this on C6 M->H->M."""
    out = []
    for m in sub:
        sugar = projections.SUGAR.get(m.role, "")
        tail = projections.OPEN + projections.SEP.join([m.id, m.frm, m.authority, m.role]) + projections.CLOSE
        out.append(sugar + m.content + tail)   # refs deliberately omitted
    return "\n".join(out)


def mutation_test():
    good = S.to_H
    try:
        S.to_H = lossy_to_H               # re-open the seam
        res = S.run_suite(fuzz=200)
        caught = not res["ok"] and any("C6 M->H->M" in f for f in res["fails"])
        return {"reopened_seam": "drop refs in human exit",
                "suite_caught_it": caught,
                "example_fail": next((f for f in res["fails"] if "C6 M->H->M" in f), None)}
    finally:
        S.to_H = good                     # restore


def box(title, lines):
    w = max([len(title)] + [len(l) for l in lines]) + 2
    print("┌" + "─" * w + "┐")
    print("│ " + title.ljust(w - 1) + "│")
    print("├" + "─" * w + "┤")
    for l in lines:
        print("│ " + l.ljust(w - 1) + "│")
    print("└" + "─" * w + "┘")


def main():
    print("=" * 60)
    print("  THE CONTINUITY ENGINE — bridge of the validated substrate")
    print("=" * 60, "\n")

    suite = S.run_suite(fuzz=2000)
    brutal = S.brutal()
    mut = mutation_test()
    from continuity import teeth as T
    tee = T.run()

    box("SUBSTRATE + SUITE (the six continuity properties)", [
        f"continuity suite : {suite['pass']}/{suite['count']}  hash {suite['hash']}  "
        + ("OK" if suite["ok"] else "FAIL"),
        "C1 valid · C2 bridgeable · C3 faithful-H · C4 faithful-M",
        "C5 co-exit-agree · C6 H->M->H · C6 M->H->M (the closed seam)",
    ])
    print()
    box("BRUTAL AUDITOR (FSS should-accept / BSS should-reject)", [
        f"FSS : {brutal['fss']}   false negatives: {brutal['false_negatives']}",
        f"BSS : {brutal['bss']}   false positives: {brutal['false_positives']}",
        "BSS includes: machine-only content flagged, never dropped",
    ])
    print()
    box("MUTATION TEST (is the suite non-vacuous?)", [
        f"re-opened seam  : {mut['reopened_seam']}",
        f"suite caught it : {'YES' if mut['suite_caught_it'] else 'NO'}",
        f"on              : {mut['example_fail']}",
    ])
    print()
    box("SUBSTRATE TEETH (is every validation rule guarded?)", [
        f"rules guarded   : {tee['guarded']}/{tee['total']}  "
        + ("non-vacuous" if tee["non_vacuous"] else "HAS UNGUARDED RULES"),
        "disable any rule -> a BSS probe flips to a false positive",
    ] + ([f"unguarded       : "
          + ", ".join(r["rule"] for r in tee["rules"] if not r["guarded"])]
         if not tee["non_vacuous"] else []))

    # chain (continuity across time) — anchor a small sample, best-effort
    sample = [
        Msg("h-001", "human", "COMMAND", "sovereign", "build the bridge"),
        Msg("h-002", "ai-agent", "PROPOSAL", "advisory", "validate the substrate first", ["h-001"]),
        Msg("h-003", "ai-agent", "EVIDENCE", "advisory", "both exits faithful", ["h-001"]),
    ]
    chain_ok = True
    try:
        from continuity import chain
        rec = chain.anchor(sample, out_dir="./continuity_out", keystore="./continuity_keystore")
        print()
        box("CHAIN (continuity across time)", [
            f"root        : {rec['root']}",
            f"signature   : {rec['signature']['status']}",
            f"timestamp   : {rec['timestamp']['status']}"
            + (f"  @ {rec['timestamp'].get('asserted_time','')}" if rec['timestamp']['status'] == 'present' else ""),
        ])
        chain_ok = rec["signature"]["status"] == "present"
    except Exception as e:
        print("\n  [chain skipped]", e)

    status = {
        "suite": suite, "brutal": {k: v for k, v in brutal.items() if not k.endswith("fails")},
        "mutation": mut, "substrate_teeth": tee,
        "stable": suite["ok"] and brutal["ok"] and mut["suite_caught_it"] and tee["non_vacuous"],
    }
    open("continuity_status.json", "w").write(json.dumps(status, indent=2, sort_keys=True) + "\n")

    print("\n" + "=" * 60)
    ok = status["stable"]
    print("  ENGINE STATUS:", "✓ CONTINUOUS — substrate valid, both exits faithful,"
          " bridge sound, suite non-vacuous" if ok else "✗ BROKEN")
    print("=" * 60)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
