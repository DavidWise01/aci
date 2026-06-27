"""
THE CONTINUITY SUITE — the three-artifact standard applied to the BRIDGE.

Six properties, each a witness that the conversation survives a crossing:

  C1 substrate-valid   validate(S) == []                  (the pivot is well-formed)
  C2 bridgeable        residue(S) == [] OR named          (M-only content detected, never dropped)
  C3 faithful-H        from_H(to_H(S)) == S               (H is a lossless exit)
  C4 faithful-M        from_M(to_M(S)) == S               (M is a lossless exit)
  C5 co-exit agree     to_M(from_H(to_H(S))) == to_M(S)   (H and M exit together, agree on S)
  C6 round-trip both   H->M->H == H  AND  M->H->M == M    (text identity — the seam closed)

C6's second half (M->H->M) is the exact thing eskimo-brothers lost. The curated
set includes the non-linear ref graph that proved the loss; here it must hold.

Deterministic: a seeded generator, a stable result hash. Reproduce the hash =
reproduce the verdict.
"""
import random
from typing import List, Tuple
from .substrate import (Msg, BRIDGEABLE, ROLE_MIN_AUTHORITY, validate, equal,
                        residue, is_bridgeable)
from .projections import to_H, from_H, to_M, from_M
from .canonical import canon, sha


# ---- deterministic generator: valid, bridgeable substrates --------------
def gen_substrate(seed: int) -> List[Msg]:
    rng = random.Random(seed)
    n = rng.randint(1, 9)
    roles = sorted(BRIDGEABLE)
    S: List[Msg] = []
    for i in range(1, n + 1):
        role = rng.choice(roles)
        auth = rng.choice(sorted(ROLE_MIN_AUTHORITY[role]))
        frm = "human" if auth == "sovereign" else rng.choice(["ai-agent", "tool", "human"])
        # refs: a random subset of EARLIER ids (may be non-linear — the whole point)
        earlier = [m.id for m in S]
        k = rng.randint(0, min(2, len(earlier)))
        refs = rng.sample(earlier, k) if k else []
        S.append(Msg(id=f"h-{i:03d}", frm=frm, role=role, authority=auth,
                     content=f"line {i} {role.lower()}", refs=refs))
    return S


# ---- the six properties over one substrate ------------------------------
def properties(S: List[Msg]) -> List[Tuple[str, bool]]:
    r: List[Tuple[str, bool]] = []
    r.append(("C1 substrate-valid", validate(S) == []))
    r.append(("C2 bridgeable", is_bridgeable(S)))
    r.append(("C3 faithful-H", equal(from_H(to_H(S)), S)))
    r.append(("C4 faithful-M", equal(from_M(to_M(S)), S)))
    r.append(("C5 co-exit-agree", to_M(from_H(to_H(S))) == to_M(S)))
    # C6 round-trips, as TEXT identity through the other skin and back
    H0 = to_H(S); hmh = to_H(from_M(to_M(from_H(H0))))
    M0 = to_M(S); mhm = to_M(from_H(to_H(from_M(M0))))
    r.append(("C6 H->M->H", hmh == H0))
    r.append(("C6 M->H->M", mhm == M0))   # the seam that broke eskimo
    return r


# ---- curated cases (incl. the exact eskimo break) -----------------------
def curated() -> List[Tuple[str, List[Tuple[str, bool]]]]:
    cases = []

    # 1. the non-linear ref graph: h-003 refs h-001, SKIPPING h-002
    nonlinear = [
        Msg("h-001", "human", "COMMAND", "sovereign", "build scheduler"),
        Msg("h-002", "ai-agent", "PROPOSAL", "advisory", "use min-heap", ["h-001"]),
        Msg("h-003", "ai-agent", "EVIDENCE", "advisory", "benchmark", ["h-001"]),  # skips 002
    ]
    cases.append(("nonlinear-graph (the eskimo break)", properties(nonlinear)))

    # 2. a fan-in: h-003 refs BOTH h-001 and h-002
    fanin = [
        Msg("h-001", "human", "COMMAND", "sovereign", "do x"),
        Msg("h-002", "human", "COMMAND", "sovereign", "do y"),
        Msg("h-003", "ai-agent", "PROPOSAL", "advisory", "combine", ["h-001", "h-002"]),
    ]
    cases.append(("fan-in refs", properties(fanin)))

    # 3. content with the sugar chars (must still recover exactly)
    tricky = [Msg("h-001", "ai-agent", "PROPOSAL", "advisory", "! ? > not a prefix")]
    cases.append(("content-with-sugar-chars", properties(tricky)))
    return cases


# ---- the suite: curated + seeded fuzz, deterministic hash ----------------
def run_suite(fuzz: int = 2000) -> dict:
    results: List[Tuple[str, bool]] = []
    for name, props in curated():
        for pname, ok in props:
            results.append((f"curated/{name}/{pname}", ok))
    for seed in range(fuzz):
        for pname, ok in properties(gen_substrate(seed)):
            results.append((f"fuzz/{seed}/{pname}", ok))
    passed = sum(1 for _, ok in results if ok)
    h = sha(canon([[n, ok] for n, ok in results]))[:12]
    fails = [n for n, ok in results if not ok]
    return {"pass": passed, "count": len(results), "hash": h,
            "ok": passed == len(results), "fails": fails[:8]}


# ---- brutal auditor: FSS (should-accept) / BSS (should-reject) -----------
def brutal() -> dict:
    fss, bss = [], []

    # FSS — valid bridgeable substrates must validate AND round-trip both ways
    for seed in range(12):
        S = gen_substrate(1000 + seed)
        ok = (validate(S) == [] and equal(from_H(to_H(S)), S)
              and to_M(from_H(to_H(S))) == to_M(S))
        fss.append((f"valid#{seed} accepted+continuous", ok))

    # BSS — these MUST be rejected/flagged; silent acceptance is the audit killer
    def rej(S):  # should fail substrate validity
        return validate(S) != []
    bss.append(("forward ref rejected",
                rej([Msg("h-001", "ai", "EVIDENCE", "advisory", "x", ["h-002"]),
                     Msg("h-002", "ai", "EVIDENCE", "advisory", "y")])))
    bss.append(("dangling ref rejected",
                rej([Msg("h-001", "ai", "EVIDENCE", "advisory", "x", ["h-999"])])))
    bss.append(("authority exceeded rejected",
                rej([Msg("h-001", "ai", "COMMAND", "observer", "x")])))
    bss.append(("duplicate id rejected",
                rej([Msg("h-001", "h", "COMMAND", "sovereign", "x"),
                     Msg("h-001", "h", "COMMAND", "sovereign", "y")])))
    bss.append(("empty content rejected",
                rej([Msg("h-001", "h", "COMMAND", "sovereign", "")])))
    bss.append(("invalid role rejected",
                rej([Msg("h-001", "h", "BOGUS", "sovereign", "x")])))
    # the crucial one: M-only content must be DETECTED as non-bridgeable, not dropped
    monly = [Msg("h-001", "human", "DECISION", "sovereign", "approve", []),]
    bss.append(("machine-only flagged non-bridgeable (not dropped)",
                not is_bridgeable(monly) and residue(monly) == ["h-001"]))

    fss_ok = sum(1 for _, ok in fss if ok)
    bss_ok = sum(1 for _, ok in bss if ok)
    return {
        "fss": f"{fss_ok}/{len(fss)}", "fss_ok": fss_ok == len(fss),
        "bss": f"{bss_ok}/{len(bss)}", "bss_ok": bss_ok == len(bss),
        "false_negatives": len(fss) - fss_ok,
        "false_positives": len(bss) - bss_ok,
        "ok": fss_ok == len(fss) and bss_ok == len(bss),
        "fss_fails": [n for n, ok in fss if not ok],
        "bss_fails": [n for n, ok in bss if not ok],
    }
