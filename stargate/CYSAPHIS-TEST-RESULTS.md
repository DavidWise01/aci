# Cysaphis — Test Receipt

Date: 2026-08-24
Branch: `containment-before-plasma`
Repository: `DavidWise01/aci`

Fresh stargate run:

```text
Cysaphis new tests: 10 / 10 PASS
Ricky regression:    8 /  8 PASS
--------------------------------
Fresh stargate:     18 / 18 PASS
```

Existing containment receipt on the same branch remains unchanged:

```text
Containment:         7 / 7 PASS
```

Aggregate stack evidence:

```text
Containment + Ricky + Cysaphis = 25 / 25 green
```

Cysaphis checks:

- bounded nine-roll cycle returns the mask home
- forward roll order `1,2,3,4,5,6,7,8,0`
- reverse roll order returns home
- first Cysaphis brick starts from Ricky's final `z`
- every brick hash-links to its parent
- middle-brick tamper invalidates the chain
- containment redefinition invalidates the chain
- Mandelbrot escape terminates rolling early
- escaped Ricky cannot seed Cysaphis
- Cysaphis must be issued before plasma arm
- issued chain remains valid through arm/active while the containment seal is unchanged

Verdict: **PASS**
