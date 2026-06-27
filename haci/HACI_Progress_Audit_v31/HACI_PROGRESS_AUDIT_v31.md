# HACI Progress Audit through v3.1

## Verdict

- Latest audited version: **v3.1**
- Regressions against fixed layers: **0**
- Open failures: **1**

## Fixed layers

### v2.4 — Inbound suffix ? semantics
- Why: A returned question was being treated like a completed answer. That let unresolved asks/declarations look complete.
- Invariant: suffix ? means returned-as-question / still open; suffix > or ! completes.
- v3.1 status: **PASS**

### v2.5 — Commit gating for declarations
- Why: A declaration ending in ? could still mutate symbol meaning/authority even while conversation layer said unresolved.
- Invariant: only declarations confirmed by > or ! commit symbol authority.
- v3.1 status: **PASS**

### v2.6 — Unique accepted-return fallback
- Why: m accepted ! could not close a single open ask unless payload tokens overlapped.
- Invariant: a single same-object ! return may close one single open ask; never guess among multiples.
- v3.1 status: **PASS**

### v2.7 — Pending parent scope gate
- Why: A child object could commit under a pending/uncommitted parent, making the child stronger than its parent.
- Invariant: children cannot commit beneath pending/uncommitted existing parents.
- v3.1 status: **PASS**

### v2.8 — Payload-specific return-question pairing
- Why: A suffix ? clarification failed when more than one ask was open, even if payload uniquely identified the target ask.
- Invariant: return-questions pair by unique positive object/payload match, but do not complete.
- v3.1 status: **PASS**

### v2.9 — Pending declaration graph edge gate
- Why: A pending declaration no longer committed symbol authority, but still created dependency graph edges/cycles.
- Invariant: pending declarations cannot mutate graph topology.
- v3.1 status: **PASS**

### v3.0 — Same-file chronology gate
- Why: Order-independent pairing was correct across files, but inside one file it allowed a return to answer a later ask.
- Invariant: same-file returns cannot pair backward; cross-file pairing stays order-independent.
- v3.1 status: **PASS**

### v3.1 — Multi return-question attachment
- Why: Only one clarification question could attach to an ask; a second valid clarification became unmatched.
- Invariant: multiple suffix ? clarifications can attach to one ask; each still needs a unique positive match.
- v3.1 status: **PASS**

## Current open gap

- **Multiple suffix > evidence/result returns for one ask** still fail.
- This appears to be an older latent limitation exposed after the same multi-attachment rule was fixed for suffix `?` clarifications.

## Comparison matrix

| Invariant | v2.4 | v2.5 | v2.6 | v2.7 | v2.8 | v2.9 | v3.0 | v3.1 |
|---|---|---|---|---|---|---|---|---|
| Inbound ? stays open | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| Pending declaration does not commit symbol authority | FAIL | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| Unique accepted ! return closes ask | FAIL | FAIL | PASS | PASS | PASS | PASS | PASS | PASS |
| Pending parent blocks child commit | FAIL | FAIL | FAIL | PASS | PASS | PASS | PASS | PASS |
| Payload-specific return-question pairs | FAIL | FAIL | FAIL | FAIL | PASS | PASS | PASS | PASS |
| Pending declaration creates no graph edge | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | PASS | PASS |
| Same-file return-before-ask rejected | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | PASS |
| Multiple return-questions attach to one ask | PASS | PASS | PASS | PASS | FAIL | FAIL | FAIL | PASS |
| Multiple evidence > returns attach to one ask | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| Cross-file return-before-ask still allowed | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |

## Interpretation

This pattern shows progress, not random breakage. Each patched invariant remains passing in v3.1. The latest failure is the next adjacent generalization: after allowing multiple `?` clarifications, the engine still lacks the parallel rule for multiple `>` evidence/result returns.
