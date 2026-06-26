# HACI Torture Suite x2 for Validator v2.4

This package does **not** add HACI features.

It reruns x2 torture against `haci_project_validator_v2_4.py`:

1. Curated adversarial cases.
2. Seeded fuzz/property cases.

Both layers run:
- forward order
- reverse order

v2.4-specific expectations:
- suffix `>` completes as answer/evidence/result
- suffix `!` completes as accepted/committed
- suffix `?` remains unresolved/open

Run:

```bash
python torture_haci_v2_4_x2.py
```
