# HACI Torture Suite x2 for Validator v3.1

This package does **not** add HACI features.

It reruns x2 torture against `haci_project_validator_v3_1.py`:

1. Curated adversarial cases.
2. Seeded fuzz/property cases.

Both layers run:
- forward order
- reverse order

v3.1-specific expectations:
- multiple suffix `?` return-questions may attach to one open conversation
- each return-question still needs a positive unique conversation match
- return-questions still do not complete the conversation
- final suffix `>` or `!` still completes the conversation
- ambiguous/zero-score return-questions still fail closed

Run:

```bash
python torture_haci_v3_1_x2.py
```
