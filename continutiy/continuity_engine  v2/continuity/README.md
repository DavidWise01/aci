# CONTINUITY · CTY

The bridge of the ACI family — built **on** the duality-engine, not in place of it.

The duality-engine validates the two halves (HACI, MACI) to one standard.
CONTINUITY validates the **bridge between them** and the **chain through time**.

## The correction that shapes it

H and M do not convert into *each other*. They are two **exits** of one validated
**substrate** (the typed conversation DAG — the ACI Core made concrete). Nothing
crosses except through the substrate:

```
   skin_a → from_a → [ SUBSTRATE: validated first ] → to_b → skin_b
```

So the substrate is the first gate. "Both H and M exit together" is the
requirement that each skin be a **faithful exit** — `from_X(to_X(S)) == S`,
graph and all. The eskimo seam was H failing exactly that test.

## The six continuity properties (the suite = the standard, applied to the bridge)

| | property | meaning |
|---|---|---|
| C1 | substrate-valid | the pivot is a well-formed causal DAG |
| C2 | bridgeable | machine-only roles (DECISION/DELEGATE) are **detected, never dropped** |
| C3 | faithful-H | `from_H(to_H(S)) == S` — the human exit is lossless |
| C4 | faithful-M | `from_M(to_M(S)) == S` — the machine exit is lossless |
| C5 | co-exit agree | `to_M(from_H(to_H(S))) == to_M(S)` — both exits agree on S |
| C6 | round-trip both | `H→M→H == H` **and** `M→H→M == M` — the closed seam |

## Status (reproduced locally, hash matches)

- continuity suite: **14021/14021**, hash `070ec9a42e79` (curated + 2000 seeded fuzz × 7)
- brutal: FSS **12/12** (0 false negatives) · BSS **7/7** (0 false positives)
- mutation test: re-open the seam (drop refs in the human exit) → suite catches it on
  `nonlinear-graph (the eskimo break)/C6 M->H->M` — **non-vacuous**
- chain: Ed25519 signature + external RFC-3161 timestamp, `prev_root` lineage
- determinism: identical hash across runs; the top-level gate fails closed (exit 1) when broken

## The honest cost (two-layer)

To make the human skin a faithful exit, HACI-C carries the provenance
(`id|from|authority|role|refs`) in a visible tail — base HACI traded that away for
cleanliness and got the lossy seam. Continuity pays it back: the sentence stays
human on the left, the machine truth rides in the tail. Scope: content is
single-line; multi-line / CODE-fence bodies are a declared extension.

David Lee Wise / Bridge-Burners LLC · built on [[duality-engine]] / [[eskimo-brothers]].
