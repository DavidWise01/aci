# HACI Torture Suite x2 for Validator v2.5

This package does **not** add HACI features.

It reruns x2 torture against `haci_project_validator_v2_5.py`:

1. Curated adversarial cases.
2. Seeded fuzz/property cases.

Both layers run:
- forward order
- reverse order

v2.5-specific expectations:
- declaration + `>` commits
- declaration + `!` commits
- declaration + `?` is pending, not committed
- declaration with no suffix is pending, not committed
- pending declarations do not mutate committed meaning/authority

Run:

```bash
python torture_haci_v2_5_x2.py
```
