# Ricky Interactive Page — Test Receipt

Branch: `containment-before-plasma`
Page: `stargate/ricky.html`

Checks performed on the standalone page:

```text
title:             PASS
canvas:            PASS
wander_button:     PASS
roll_button:       PASS
canonical_pattern: PASS
mandelbrot_rule:   PASS
escape_rule:       PASS
click_coordinate:  PASS
route_hash:        PASS
javascript compile PASS

TOTAL: 10 / 10 PASS
```

Page contract:

- canonical brick remains `{. . | | . . | . .}`
- WANDER repeats the witness stencil over a continuing Mandelbrot orbit
- ROLL rotates the nine-symbol stencil after each complete brick
- Mandelbrot recurrence remains `z(n+1) = z(n)^2 + c`
- escape remains `|z| > 2`
- clicking the field selects a new complex coordinate `c`
- route checkpoints are recorded at `|`
- a route digest is produced with browser SHA-256 when available

Local artifact SHA-256:

`eeeb6b76ff51b81f2505e5f4a4a3ef516ca425ea89dc7b9f0a40f8d18c42fd08`

Verdict: **PASS — full Ricky wander/roll page built.**
