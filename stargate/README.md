# Ricky — Star-Gate Brick 001

The first passive key.

Source:

```text
{. . | | . . | . .}
```

Interpreted as the 3x3 brick:

```text
. . |
| . .
| . .
```

Name: **Ricky**  
Mode: **rolled**  
Domain: deterministic Mandelbrot contour wandering  
Energy state: **passive** — this module does not ignite plasma.

## Four-roll cycle

```text
R0          R1          R2          R3

. . |       | | .       . . |       | . .
| . .       . . .       . . |       . . .
| . .       . . |       | . .       . | |

       R4 == R0
```

The center remains open. The brick has three `|` walls and five open neighboring `.` exits. Each wander step evaluates only the currently open Moore-neighborhood cells, chooses deterministically toward a target Mandelbrot escape depth, records the step, then rolls Ricky one quarter-turn clockwise.

## Admission law

Ricky can exist and wander as a passive mathematical key at any time, but it cannot issue a star-gate admission token until ACI containment is in `CONTAINMENT_VERIFIED`.

```text
CONTAINMENT_DEFINED
      ↓
3 witnesses / >=2 approve
      ↓
CONTAINMENT_VERIFIED
      ↓
RICKY admission token
      ↓
future gate stages
      ↓
plasma remains downstream
```

The admission token binds Ricky's orientation seal to the active containment boundary seal with SHA-256.

## Test

```bash
python -m unittest discover -s tests -v
```

Ricky adds 7 tests to the existing 7 containment tests: 14 total.
