# Containment Before Plasma — Test Receipt

Date: 2026-08-24
Branch: `containment-before-plasma`
Repository: `DavidWise01/aci`
Python: 3.13.5

Command:

```bash
python -m unittest discover -s tests -v
```

Result:

```text
test_aci_happy_path ... ok
test_cubis_happy_path ... ok
test_ledger_tamper_detected ... ok
test_mutation_after_arm_fault_locks ... ok
test_plasma_cannot_arm_before_containment ... ok
test_requires_full_three_witness_quorum ... ok
test_runtime_tamper_quenches ... ok

Ran 7 tests
OK
```

Verified properties:

- ACI containment happy path passes.
- CUBIS containment happy path passes.
- Plasma cannot arm before containment verification.
- Full 3-witness quorum is required and >=2 approvals are required.
- Containment mutation after plasma arm fault-locks.
- Runtime witness/seal tamper quenches.
- Hash-chained ledger tamper is detected.

Artifact hashes from the tested package:

```text
containment/core.py
cb5ffe2a7c113afb89f83b2b317132eab25d5913fc24e07b431f3977892fce71

tests/test_containment.py
3cb6e5a578b293e07d243cf519d64535e5828dade0023d45eb2ccdd7d7e8ce74
```

Verdict: **PASS — 7/7**
