# Cysaphis — The Roller

Cysaphis is Brick 1 in the stargate key chain. Ricky establishes the first Mandelbrot brick; Cysaphis keeps the same orbit moving by rolling the canonical mask one position per brick.

Canonical mask inherited from Ricky:

```text
{. . | | . . | . .}
```

Forward cycle from Ricky roll 0:

```text
Ricky: 0
  ↓
Cysaphis: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 0
```

Rules:

- Each brick starts from the previous brick's final `z`; the Mandelbrot recurrence is never reset.
- Each roll uses the unchanged recurrence `z(n+1) = z(n)^2 + c`.
- `.` advances the wander; `|` advances and records a checkpoint.
- Every Cysaphis brick SHA-256-links to Ricky or the immediately preceding Cysaphis brick.
- The default cycle is 9 rolls. A bounded orbit returns the mask to its originating roll.
- Escape (`|z| > 2`) terminates the roll chain immediately.
- Cysaphis can only be issued while containment is verified and before plasma arm.
- Once issued, the chain remains valid through plasma arm/active only while the same containment seal remains intact.
- Reverse rolling is supported with `direction=-1` and must also return home after 9 bounded rolls.

Stack:

```text
CONTAINMENT
    ↓
RICKY / brick 0
    ↓ parent hash
CYSAPHIS / brick 1..9
    ↓ hash-linked rolling chain
HOME or ESCAPE
    ↓
PLASMA ARM
```
