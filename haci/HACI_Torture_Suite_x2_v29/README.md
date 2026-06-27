# HACI Torture Suite x2 for Validator v2.9

This package does **not** add HACI features.

It reruns x2 torture against `haci_project_validator_v2_9.py`:

1. Curated adversarial cases.
2. Seeded fuzz/property cases.

Both layers run:
- forward order
- reverse order

v2.9-specific expectations:
- pending declarations do not create dependency edges
- pending declarations cannot create dependency cycles
- committed declarations still create dependency edges
- real asks/observes still create dependency edges

Run:

```bash
python torture_haci_v2_9_x2.py
```
