# Ricky — Test Receipt

Date: 2026-08-24
Branch: `containment-before-plasma`
Repository: `DavidWise01/aci`

Canonical brick:

```text
{. . | | . . | . .}
```

Command:

```bash
python -m unittest discover -s tests -v
```

Result:

```text
Ricky tests:        8 / 8 PASS
Containment tests:  7 / 7 PASS
TOTAL:             15 / 15 PASS
```

Verified:
- exact nine-symbol brick
- three gate checkpoints
- cyclic roll / inverse roll
- bounded nine-hop Mandelbrot wander
- ordinary escape termination
- no key issuance before verified containment
- key bound to containment seal
- key remains valid through arm/active only with unchanged seal
- identical inputs produce identical SHA-256 key
- full containment regression remains green

Verdict: **PASS — 15/15**
