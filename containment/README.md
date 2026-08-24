# Containment Before Plasma — ACI + CUBIS

A fail-closed software admission gate. **Plasma is a runtime phase label, not a physical plasma model.**

```text
EVENT
  ↓
CONTAINMENT_DEFINED
  ↓  3 witnesses present / >=2 approve
CONTAINMENT_VERIFIED
  ↓  immutable boundary seal
PLASMA_ARMED
  ↓  seal re-check
PLASMA_ACTIVE
  ↓  continuous guard
QUENCH / FAULT_LOCKED
```

Profiles:

- `ACI`: minimum 4 logical boundary nodes.
- `CUBIS`: minimum 6 logical boundary nodes (one logical face per node).
- Both: 3 witness slots, 2 approvals required, 1 admitted transition.

Hard properties:

1. Plasma cannot arm from `EMPTY` or merely `CONTAINMENT_DEFINED`.
2. All 3 witness slots must be populated before verification; at least 2 must approve.
3. The boundary is SHA-256 sealed before arm.
4. Boundary mutation after arm is a fault-lock condition.
5. Runtime loss of quorum or seal integrity quenches the active phase.
6. Every transition is written to a hash-chained audit ledger.
7. Reset is only permitted after quench/fault.

Run tests:

```bash
python -m unittest discover -s tests -v
```
