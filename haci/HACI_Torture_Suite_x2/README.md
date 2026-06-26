# HACI Torture Suite x2

This package does **not** add HACI features.

It stress-tests `haci_project_validator_v2_2.py` with two layers:

1. Curated adversarial cases.
2. Seeded fuzz/property cases.

Both layers run twice:
- forward order
- reverse order

Run:

```bash
python torture_haci_v2_2_x2.py
```

Expected result:

```text
fail = 0
```
