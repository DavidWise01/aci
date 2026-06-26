#!/usr/bin/env python3
"""
haci2_stress.py — adversarial veracity test for the HACI v0.2 parser.

The question: does the prefix/suffix duality survive contact
with real English, real code, and real documents?

The big concern: English NATURALLY ends sentences with ! and ?
Does "Deploy now!" mean committed, or just emphatic?
Does "Is this ready?" mean pending, or just a question?
"""

import sys
sys.path.insert(0, '.')
from haci2 import parse_line, parse, classify_owner

# ═══════════════════════════════════════════════════════════════════════
# TEST FRAMEWORK
# ═══════════════════════════════════════════════════════════════════════

results = {'pass': 0, 'fail': 0, 'concern': 0}

def test(line, exp_intent, exp_status, exp_owner, desc, concern=False):
    node = parse_line(line)
    if node is None:
        print(f"  \033[31m✗\033[0m NULL: \"{line}\" — {desc}")
        results['fail'] += 1
        return

    ok_i = node['intent'] == exp_intent
    ok_s = node['status'] == exp_status
    ok_o = node['owner'] == exp_owner

    if ok_i and ok_s and ok_o:
        results['pass'] += 1
        if not concern:
            i = (node['intent'] or '-')[:3]
            s = (node['status'] or '-')[:3]
            o = (node['owner'] or '-')[:3]
            print(f"  \033[32m✓\033[0m {i}/{s}/{o:<4s} \"{line[:60]}\"")
    else:
        fails = []
        if not ok_i: fails.append(f"intent={node['intent']} want {exp_intent}")
        if not ok_s: fails.append(f"status={node['status']} want {exp_status}")
        if not ok_o: fails.append(f"owner={node['owner']} want {exp_owner}")
        results['fail'] += 1
        print(f"  \033[31m✗\033[0m \"{line[:60]}\"")
        print(f"       {'; '.join(fails)}")
        print(f"       {desc}")

def concern(line, got_intent, got_status, got_owner, desc):
    """Flag a case where the parser is TECHNICALLY correct but PRACTICALLY wrong."""
    node = parse_line(line)
    if node is None:
        return
    results['concern'] += 1
    i = (node['intent'] or '-')[:3]
    s = (node['status'] or '-')[:3]
    o = (node['owner'] or '-')[:3]
    print(f"  \033[33m⚠\033[0m {i}/{s}/{o:<4s} \"{line[:60]}\"")
    print(f"       {desc}")


# ═══════════════════════════════════════════════════════════════════════
print("=" * 64)
print("STRESS TEST 1: English punctuation collision")
print("  The killer question: ! and ? are natural English punctuation.")
print("=" * 64)

# These are NATURAL English — the ! and ? are punctuation, not operators
print("\n  Lines where suffix detection gives WRONG semantic meaning:\n")

concern("This is amazing!",
    None, "committed", "shared",
    "English exclamation → suffix ! → 'committed'. But the author just meant emphasis.")

concern("Is the deployment ready?",
    None, "pending", "shared",
    "English question → suffix ? → 'pending'. But this is documentation, not a status marker.")

concern("What happened to the server?",
    None, "pending", "shared",
    "Natural question → suffix ? → 'pending'. Author didn't mean 'unresolved task'.")

concern("The system crashed!",
    None, "committed", "shared",
    "Emphatic statement → suffix ! → 'committed'. Author didn't mean 'decided'.")

concern("Run the tests now!",
    None, "committed", "shared",
    "Imperative → suffix ! → 'committed'. Actually just documentation of a command.")

concern("Workers are ready!",
    None, "committed", "shared",
    "Exclamation → suffix ! → 'committed'. Author meant 'hooray', not 'decided'.")

concern("Should we use Redis?",
    None, "pending", "shared",
    "Natural question → suffix ? → 'pending'. It's documentation, not a tracked item.")

concern("allocate workers!",
    None, "committed", "machine",
    "Machine text with emphasis → suffix ! → 'committed'. But lowercase = AI proposal, not done.")

concern("is this the right approach?",
    None, "pending", "machine",
    "Machine question → suffix ? → 'pending'. Correct or accidental?")

# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 64}")
print("STRESS TEST 2: URLs, paths, and technical content")
print("=" * 64)

print()
test("See https://example.com/path?query=1",
     None, None, "shared",
     "URL with ? — should NOT trigger suffix (? not last char)", concern=False)

test("Visit https://example.com/page!",
     None, "committed", "shared",
     "URL ending with ! — WILL trigger suffix (! IS last char)")

concern("Check https://example.com/page!",
    None, "committed", "shared",
    "URL ending ! → false suffix. The ! is part of the URL or just emphasis.")

test("output > /dev/null",
     None, None, "machine",
     "Shell redirect — middle > is literal (ambiguity rule)")

test("if (x > 0) return true",
     None, None, "machine",
     "Comparison operator — middle > is literal")

test("error code: 404!",
     None, "committed", "machine",
     "Error with emphasis — suffix ! fires")

concern("error code: 404!",
    None, "committed", "machine",
    "Technical content with ! → false committed status")

test("pipe: stdin | grep 'pattern' > output.txt",
     None, None, "machine",
    "Shell pipeline — last char is 't', no suffix")

# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 64}")
print("STRESS TEST 3: ownership classification edge cases")
print("=" * 64)

print()
test("API endpoint configured",
     None, None, "human",
     "ALL CAPS acronym 'API' → first alpha upper → human? Actually shared doc.")

concern("API endpoint configured",
    None, None, "human",
    "Starts with acronym 'API' → classified as human. But this is documentation.")

test("macOS needs configuration",
     None, None, "machine",
     "Brand starts lowercase → classified as machine. Actually documentation.")

test("iOS deployment complete",
     None, None, "machine",
     "Brand starts lowercase 'i' → machine. Wrong — it's documentation.")

test("TCP/IP stack verified",
     None, None, "human",
     "Acronym starts upper → human. Actually shared documentation.")

test("x86 architecture",
     None, None, "machine",
     "Starts with x (lower) → machine. Actually documentation.")

test("3rd party integration",
     None, None, "machine",
     "Starts with digit, first alpha 'r' is lower → machine. Could be doc.")

test("README updated",
     None, None, "human",
     "ALL CAPS word → human. It's actually documentation.")

# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 64}")
print("STRESS TEST 4: operator combinations and edge cases")
print("=" * 64)

print()
test("!",       "declare", None,       "human",   "bare !")
test("?",       "inquire", None,       "machine", "bare ? — no alpha → default")
test(">",       "observe", None,       "machine", "bare >")
test("! !",     "declare", "committed","human",   "! space ! — prefix+suffix, no content")
test("? ?",     "inquire", "pending",  "machine", "? space ? — prefix+suffix, no content")
test("> >",     "observe", "verified", "machine", "> space > — prefix+suffix, no content")
test("! ? >",   "declare", "verified", "machine", "! prefix, > suffix, ? is content")
test("> test >","observe", "verified", "machine", "observe + verified, content='test'")
test("!!",      "declare", "committed","human",   "!! — prefix ! suffix ! no content")
test("??",      "inquire", "pending",  "machine", "?? — prefix ? suffix ?")
test(">>",      "observe", "verified", "machine", ">> — prefix > suffix >")
test("!>",      "declare", "verified", "human",   "!> — declare+verified no content")
test("?!",      "inquire", "committed","machine", "?! — inquire+committed")
test(">!",      "observe", "committed","machine", ">! — observe+committed")

# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 64}")
print("STRESS TEST 5: multi-line document parse coherence")
print("=" * 64)

doc = """<!-- HACI v0.2 -->

# Test Document

! DEPLOY THE APPLICATION

The application serves HTTP on port 8080.
Is this the right port?

allocate memory pool
initialize connection handler

? should we enable TLS

> TLS adds 2ms latency

! USE TLS

enable TLS with Let's Encrypt !
configure auto-renewal >

> certificate provisioned
> all endpoints HTTPS

! DEPLOYMENT COMPLETE !
"""

nodes, warnings = parse(doc)
print(f"\n  Parsed {len(nodes)} nodes from test document\n")

# count by intent/status/owner
from collections import Counter
intents = Counter(n.get('intent') for n in nodes)
statuses = Counter(n.get('status') for n in nodes)
owners = Counter(n.get('owner') for n in nodes)

print(f"  Intents:  {dict(intents)}")
print(f"  Statuses: {dict(statuses)}")
print(f"  Owners:   {dict(owners)}")

# check the critical lines
critical = []
for n in nodes:
    if n['type'] == 'line':
        critical.append((n['content'][:40], n.get('intent'), n.get('status'), n.get('owner')))

print(f"\n  Critical line classifications:")
for content, intent, status, owner in critical:
    i = (intent or '-')[:3]
    s = (status or '-')[:3]
    o = (owner or '-')[:3]
    print(f"    {i}/{s}/{o}  {content}")

# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 64}")
print("STRESS TEST 6: the false-positive rate")
print("=" * 64)

# feed in 20 lines of normal English prose and count false suffix triggers
prose = [
    "The server is running.",
    "We need to fix this bug.",
    "The deployment was successful!",        # false ! suffix
    "Can we meet tomorrow?",                  # false ? suffix
    "Performance improved by 40%.",
    "The team worked overtime.",
    "Is the backup ready?",                   # false ? suffix
    "Everything looks good!",                 # false ! suffix
    "Check the logs for errors.",
    "The API returns JSON.",
    "Why did the test fail?",                 # false ? suffix
    "Great work on the release!",             # false ! suffix
    "Memory usage is stable.",
    "The cache hit ratio is 94%.",
    "Should we add more workers?",            # false ? suffix
    "The migration completed!",               # false ! suffix
    "Review the pull request.",
    "All systems operational.",
    "What is the current latency?",           # false ? suffix
    "Ship it!",                               # false ! suffix
]

false_suffix = 0
for line in prose:
    node = parse_line(line)
    if node and node.get('status'):
        false_suffix += 1

rate = false_suffix / len(prose) * 100
print(f"\n  {len(prose)} lines of normal English prose")
print(f"  {false_suffix} false suffix triggers ({rate:.0f}% false-positive rate)")

# list the false positives
print(f"\n  False positives:")
for line in prose:
    node = parse_line(line)
    if node and node.get('status'):
        print(f"    \033[33m⚠\033[0m \"{line}\" → status={node['status']}")

# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 64}")
print("VERDICT")
print(f"{'=' * 64}")

print(f"""
  Parser mechanics:     {results['pass']} tests passed, {results['fail']} failed
  Design concerns:      {results['concern']} semantic false-positives flagged

  THE CORE PROBLEM:
    English uses ! and ? as natural sentence punctuation.
    The suffix rule CANNOT distinguish:
      "Deploy now!"    (HACI: committed)  vs  "This is great!" (English: emphasis)
      "Is this ready?" (HACI: pending)    vs  "What happened?" (English: question)

    The false-positive rate on normal prose is {rate:.0f}%.
    That means {false_suffix} out of every {len(prose)} lines of English will get
    a WRONG status classification.

  WHAT'S STRONG:
    ✓ prefix detection is unambiguous (first char, no collision)
    ✓ dual-mode (prefix+suffix) is genuinely useful for status tracking
    ✓ the ambiguity rule (middle operators = literal) works
    ✓ ownership by casing is consistent with v0.1
    ✓ operator combinations (!>, ?!, etc.) parse cleanly

  WHAT'S FRAGILE:
    ⚠ suffix detection has a ~{rate:.0f}% false-positive rate on English text
    ⚠ acronyms (API, TCP, README) misclassify ownership
    ⚠ URLs ending in ! or ? trigger false suffixes

  POSSIBLE FIXES:
    a) require a SPACE before suffix operator:
       "Deploy now !" = committed (space before !)
       "Deploy now!"  = just English (no space before !)
       This one change drops false positives to near zero.

    b) require suffix operator to be on its own at the end:
       "task completed >" = verified
       "task completed>"  = literal
       Same principle: whitespace separates intent from punctuation.

    c) accept the false positives as a writing discipline issue:
       "if you're writing HACI, don't end documentation with ! or ?"
       This works but is a higher cognitive load than prefix-only.

  RECOMMENDATION:
    Fix (a) — space-before-suffix — is a one-line parser change
    that preserves the entire prefix/suffix architecture while
    eliminating the English punctuation collision. The rule becomes:

      prefix: first non-space character IS an operator
      suffix: last non-space character IS an operator
              AND preceded by whitespace

    That's still deterministic, still one-pass, still zero lookahead.
""")
