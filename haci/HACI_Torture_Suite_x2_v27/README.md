# HACI Torture Suite x2 for Validator v2.7

This package does **not** add HACI features.

It reruns x2 torture against `haci_project_validator_v2_7.py`:

1. Curated adversarial cases.
2. Seeded fuzz/property cases.

Both layers run:
- forward order
- reverse order

v2.7-specific expectations:
- pending/uncommitted parent blocks child commit
- pending-parent scope gate is structural, not strict-only
- committed parent allows committed child

Run:

```bash
python torture_haci_v2_7_x2.py
```
