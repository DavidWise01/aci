# Ricky — First Stargate Brick

Ricky is the first deterministic software key layered after containment and before plasma.

Canonical brick:

```text
{. . | | . . | . .}
```

Interpretation:

- `.` — advance one Mandelbrot iteration.
- `|` — advance one Mandelbrot iteration **and record a gate checkpoint**.
- `roll` — cyclically rotate the nine-symbol mask before the walk.
- Mandelbrot recurrence remains unchanged: `z(n+1) = z(n)^2 + c`.
- Escape remains the ordinary `|z| > 2` test.
- The walk stops on escape or after all nine symbols.

Issuance order:

```text
CONTAINMENT_DEFINED
        ↓
3 witnesses / >=2 approve
        ↓
CONTAINMENT_VERIFIED
        ↓
issue Ricky
        ↓
RICKY KEY = SHA-256(
  name + canonical brick + rolled mask + c + route + containment seal
)
        ↓
PLASMA_ARMED
        ↓
PLASMA_ACTIVE
```

The key is valid only while its bound containment seal remains current.
