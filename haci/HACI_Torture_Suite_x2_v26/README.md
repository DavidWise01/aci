# HACI Torture Suite x2 for Validator v2.6

This package does **not** add HACI features.

It reruns x2 torture against `haci_project_validator_v2_6.py`:

1. Curated adversarial cases.
2. Seeded fuzz/property cases.

Both layers run:
- forward order
- reverse order

v2.6-specific expectations:
- unique suffix `!` return may close one same-object ask without payload overlap
- duplicate/multiple asks still fail closed
- multiple remaining returns still fail closed
- suffix `>` still requires payload relation

Run:

```bash
python torture_haci_v2_6_x2.py
```
