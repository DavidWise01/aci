# Ricky — Test Receipt

Date: 2026-08-24
Repository: `DavidWise01/aci`
Branch: `stargate-ricky`
Parent: `containment-before-plasma@07248991ff8fa906e5475b7241c1e9ef8e06dd1e`

## Integrated test

```bash
python -m unittest discover -s tests -v
```

```text
Containment suite: 7/7 PASS
Ricky suite:       7/7 PASS
TOTAL:            14/14 PASS
```

Ricky checks:

- source parses to `..||..|..`
- 3 wall cells
- 5 open neighboring exits
- center remains open
- four quarter-rolls return exactly to R0
- each intermediate orientation changes the key seal
- known Mandelbrot points classify correctly
- repeated walks are identical
- wander advances through mostly unvisited points
- admission token is denied before verified containment
- admission token is issued only after the 3-witness / >=2-approve containment quorum

## Roll seals

```text
R0 ..||..|..  894b12a40312ca95002019dea1364785ad942d8d04130a266ed67c835d1353f4
R1 ||......|  b4e511e666042b797dc17a50b94cd39ef0ed5f0f3dc1590b8718e68e5a102ee1
R2 ..|..||..  4660e094f37257b3de8487f746b9125f1abf42656e427ede6858ee96b69a48c3
R3 |......||  d54745744aa3a4d8d68df729a710e92e1c7f4787f01562a35dd1716cb2343252
R4 == R0
```

## First deterministic wander sample

```text
0  -0.75000+0.09000i  escape=36  roll=0
1  -0.75000+0.08000i  escape=41  roll=1
2  -0.75000+0.07000i  escape=46  roll=2
3  -0.74000+0.08000i  escape=64  roll=3
4  -0.74000+0.09000i  escape=64  roll=0
5  -0.73000+0.10000i  escape=64  roll=1
```

Verdict: **PASS — Ricky Brick 001 is deterministic, roll-stable, containment-gated, and passive.**
