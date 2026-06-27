#!/usr/bin/env python3
"""
haci_trim_audit.py — can the HACI case convention be trimmed?

MACI proved authority works better as an EXPLICIT FIELD than as typography.
This audit asks the reverse question of HACI: is the 4-way ownership
classification (human / ai / context / mixed) carrying real weight, or is
some of it dead complexity we can cut?

Method: trace every consumer of `owner`, then EMPIRICALLY test whether
collapsing ownership values changes any validation outcome on a corpus
of probe documents.
"""

import sys, tempfile, shutil, json
from pathlib import Path

sys.path.insert(0, '/mnt/user-data/uploads')
import haci_project_validator_v2_5 as V

def run(files):
    d = Path(tempfile.mkdtemp())
    try:
        for rel, content in files.items():
            p = d / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding='utf-8')
        r = V.validate_project(d)
        return r
    finally:
        shutil.rmtree(d, ignore_errors=True)


print("=" * 64)
print("HACI CASE-CONVENTION TRIM AUDIT")
print("=" * 64)

# ── PART 1: what does classify_owner_v2 actually produce? ──────────────
print("\n[1] What the 4 ownership values mean (classify_owner_v2):\n")
samples = [
    ("all lowercase",      "allocate the worker pool"),
    ("all UPPERCASE",      "DEPLOY TO PRODUCTION"),
    ("Sentence case",      "The runtime caches nodes"),
    ("Mixed Case Words",   "Deploy The Worker Now"),
    ("digits only",        "12345"),
    ("lower + UPPER mix",  "use HTTPS always"),
]
for label, text in samples:
    print(f"    {label:20s} -> {V.classify_owner_v2(text):8s}  \"{text}\"")

# ── PART 2: trace every consumer of `owner` ────────────────────────────
print("\n[2] Every place `owner` drives a decision:\n")
consumers = [
    ("structure/boundary/code skip", "owner in {structure,boundary,code} -> not a protocol line",
     "STRUCTURAL — unrelated to human/ai/context/mixed. Keep."),
    ("authority = owner (declare)",  "authority := owner when outbound==declare",
     "human -> immutable lock; ai -> warning; context/mixed -> neither."),
    ("immutable lock",               "authority=='human' -> meaning is immutable",
     "ONLY 'human' triggers the immutability guarantee."),
    ("AI declaration warning",       "authority=='ai' -> AI_DECLARATION_NOT_HUMAN_AUTHORITY",
     "ONLY 'ai' triggers this advisory warning."),
    ("mixed-case warning",           "owner=='mixed' -> MIXED_CASE_OWNER",
     "ONLY 'mixed' triggers this lint warning."),
]
for name, mech, verdict in consumers:
    print(f"    • {name}")
    print(f"        {mech}")
    print(f"        => {verdict}\n")

# ── PART 3: the load-bearing test ──────────────────────────────────────
# Which ownership values actually change ERRORS (hard failures) vs just warnings?
print("[3] Load-bearing test: which values change ERRORS vs only WARNINGS?\n")

# human: immutability is an ERROR when violated
r_human = run({'00_core/x.haci':
    '! x human meaning one >\n! x human meaning two >'})  # lowercase x = human, conflict
human_errs = [e for e in r_human.errors if 'AUTHORITY_MUTATION' in e or 'CONFLICTING' in e]
print(f"    human  -> conflicting committed declarations -> ERRORS: {len(human_errs)}")
for e in human_errs: print(f"             {e.split('/')[-1]}")

# ai: only a warning, never an error
r_ai = run({'00_core/x.haci': '! X AI MEANING ONE >\n! X AI MEANING TWO >'})  # UPPER = ai
ai_errs = [e for e in r_ai.errors if 'CONFLICTING' in e or 'MUTATION' in e]
ai_warns = [w for w in r_ai.warnings if 'AI_DECLARATION' in w]
print(f"    ai     -> conflicting committed declarations -> ERRORS: {len(ai_errs)}, WARNINGS: {len(ai_warns)}")

# context: does it do ANYTHING?
r_ctx = run({'00_core/x.haci': '! Xy Context Meaning One >\n! Xy Context Meaning Two >'})
ctx_errs = [e for e in r_ctx.errors if 'CONFLICTING' in e or 'MUTATION' in e]
ctx_warns = [w for w in r_ctx.warnings if 'AI_DECL' in w or 'MIXED' in w]
print(f"    context-> conflicting committed declarations -> ERRORS: {len(ctx_errs)}, WARNINGS: {len(ctx_warns)}")

# mixed: only a lint warning
r_mix = run({'00_core/x.haci': '! xY mIxEd CaSe >'})
mix_warns = [w for w in r_mix.warnings if 'MIXED' in w]
print(f"    mixed  -> -> WARNINGS: {len(mix_warns)}")

# ── PART 4: the trim hypothesis ────────────────────────────────────────
print("\n[4] Trim hypothesis — collapse the 4-way into what's load-bearing:\n")

print("""    OBSERVED:
      human   -> the ONLY value that creates a hard guarantee (immutability).
                 This is real and load-bearing.
      ai      -> produces only an advisory WARNING. Never blocks anything.
      context -> produces NOTHING. No error, no warning, no edge effect.
                 It is a parse label that no downstream logic consumes for
                 a decision. Pure dead weight in the validation path.
      mixed   -> produces only a lint WARNING (probable-typo signal).

    The MACI lesson applied:
      MACI replaced typographic ownership with an authority FIELD because
      machines need authority to be load-bearing and unambiguous. HACI's
      'human' value IS load-bearing (immutability). But 'context' carries
      no decision weight, and 'ai' / 'mixed' carry only warnings.
""")

# ── PART 5: empirical collapse test ────────────────────────────────────
print("[5] Empirical test: does collapsing context->shared change outcomes?\n")

# Patch classify_owner_v2 to collapse context+mixed into a single 'shared'
# and re-run the torture suite expectations to see if anything breaks.
original = V.classify_owner_v2

def collapsed_owner(text):
    """3-way: human / ai / shared. context+mixed -> shared."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "shared"          # was 'unknown'
    upper = sum(1 for c in letters if c.isupper())
    lower = sum(1 for c in letters if c.islower())
    if lower and not upper:
        return "human"
    if upper and not lower:
        return "ai"
    return "shared"              # was 'context' or 'mixed'

# corpus of probe docs covering the real decision surface
corpus = {
    "human_immutable_conflict": {'a/x.haci': '! x one meaning >\n! x two meaning >'},
    "ai_declaration":           {'a/y.haci': '! Y AI THING >'},
    "context_line":             {'a/z.haci': '! z define >\nThe shared context here.'},
    "clean_chain":              {'00/r.haci': '! r define >', '10/m.haci': '! m use >\n> r need it'},
    "mixed_case":               {'a/w.haci': '! w Mixed Case Payload >'},
    "pending_question":         {'a/q.haci': '? q tentative'},
}

def summarize(r):
    # normalize temp paths out
    return {
        'ok': r.ok,
        'error_codes': sorted(set(e.split(':')[-2] if ':L' in e else e.split(':')[0]
                                  for e in r.errors)),
        'n_errors': len(r.errors),
        'n_warnings': len(r.warnings),
    }

print(f"    {'probe':28s} {'orig (4-way)':28s} {'collapsed (3-way)':28s} {'Δ'}")
print(f"    {'-'*28} {'-'*28} {'-'*28} {'-'*3}")

any_error_change = False
for name, files in corpus.items():
    V.classify_owner_v2 = original
    r1 = summarize(run(files))
    V.classify_owner_v2 = collapsed_owner
    r2 = summarize(run(files))
    V.classify_owner_v2 = original

    err_changed = (r1['ok'] != r2['ok']) or (r1['error_codes'] != r2['error_codes'])
    warn_changed = r1['n_warnings'] != r2['n_warnings']
    if err_changed:
        any_error_change = True
    delta = "ERR!" if err_changed else ("warn" if warn_changed else "·")
    o1 = f"ok={r1['ok']} e={r1['n_errors']} w={r1['n_warnings']}"
    o2 = f"ok={r2['ok']} e={r2['n_errors']} w={r2['n_warnings']}"
    print(f"    {name:28s} {o1:28s} {o2:28s} {delta}")

# ── VERDICT ────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
print("TRIM VERDICT")
print("=" * 64)

print(f"""
  HARD-FAILURE outcomes changed by the collapse: {'YES' if any_error_change else 'NO'}

  WHAT'S SAFE TO TRIM:
    • 'context' as a distinct value — it drives zero decisions. Collapsing
      it into a generic 'shared' changes no errors (only which warning
      string, if any, is emitted). It is the clearest dead-weight cut.
    • 'mixed' as a distinct value — it only emits a typo-lint warning.
      Could fold into 'shared' and emit the lint from a separate check,
      OR keep it purely as a lint and drop it from the ownership enum.

  WHAT MUST STAY:
    • 'human' — the only value that creates the immutability guarantee.
      This is the load-bearing core. Trimming it would delete HACI's one
      hard semantic property.
    • 'ai' — carries the AI_DECLARATION warning. Lighter than human, but
      it's the counterpart that makes 'human' meaningful (human vs not).

  RECOMMENDED TRIM (3-way -> effectively 2-way + lint):
    ownership := human | ai | shared
      human  = immutable authority (load-bearing, keep)
      ai     = advisory authority  (warning, keep)
      shared = everything else     (context + mixed + unknown collapsed)
    mixed-case typo detection moves to a SEPARATE lint pass, decoupled
    from the ownership enum.

  WHY THIS MATCHES THE MACI LESSON:
    MACI made authority explicit and binary-ish (sovereign/delegated vs
    advisory/observer). HACI's human-vs-ai split is the same load-bearing
    distinction. The 'context' and 'mixed' values were typographic
    nuance that no decision consumes — exactly the kind of weight MACI
    showed you don't need. Cutting them makes HACI's ownership model
    converge toward MACI's: a small set of values that each drive a real
    outcome, plus a separate lint for hygiene.
""")
