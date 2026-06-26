#!/usr/bin/env python3
"""
dialect_parser.py — parse the H/D/A/C/R semantic Markdown dialect.

The test: is the format parseable by a trivial parser, or does it
need special-casing that kills simplicity?

Roles:
  [H] = Human authority / directive
  [D] = Documentation / narrative
  [A] = AI proposal / suggestion
  [C] = Code (executable)
  [R] = Runtime output
"""

import re, json, sys

ROLES = {
    'H': 'human',
    'D': 'documentation',
    'A': 'ai_proposal',
    'C': 'code',
    'R': 'runtime',
}

TAG_RE = re.compile(r'^\[([HDACR])\]\s*$')

def parse(text):
    """Parse dialect text into a list of {role, content, line} blocks."""
    blocks = []
    current_role = None
    current_lines = []
    current_start = 0
    in_fence = False

    for i, line in enumerate(text.split('\n'), 1):
        stripped = line.strip()
        # track code fence state (``` or ~~~)
        if stripped.startswith('```') or stripped.startswith('~~~'):
            in_fence = not in_fence

        m = TAG_RE.match(stripped)
        if m and not in_fence:
            # flush previous block
            if current_role is not None:
                content = '\n'.join(current_lines).strip()
                if content:  # skip empty blocks
                    blocks.append({
                        'role': ROLES[current_role],
                        'tag': current_role,
                        'content': content,
                        'line': current_start,
                    })
            current_role = m.group(1)
            current_lines = []
            current_start = i
        else:
            current_lines.append(line)

    # flush last block
    if current_role is not None:
        content = '\n'.join(current_lines).strip()
        if content:
            blocks.append({
                'role': ROLES[current_role],
                'tag': current_role,
                'content': content,
                'line': current_start,
            })

    return blocks


def stats(blocks):
    """Summarise block counts by role."""
    counts = {}
    chars = {}
    for b in blocks:
        r = b['role']
        counts[r] = counts.get(r, 0) + 1
        chars[r] = chars.get(r, 0) + len(b['content'])
    return {'counts': counts, 'chars': chars}


# ── run against the test document ──────────────────────────────────────
print("=" * 60)
print("TEST 1: parse the load-bearing dialect document")
print("=" * 60)

with open('test-dialect.md') as f:
    doc = f.read()

blocks = parse(doc)
print(f"\nParsed {len(blocks)} blocks:")
for b in blocks:
    preview = b['content'][:72].replace('\n', ' ↵ ')
    if len(b['content']) > 72:
        preview += '…'
    print(f"  [{b['tag']}] L{b['line']:>3}  {preview}")

s = stats(blocks)
print(f"\nBlock counts: {json.dumps(s['counts'], indent=2)}")
print(f"Char counts:  {json.dumps(s['chars'], indent=2)}")


# ── edge case tests ────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 2: edge cases — does the format break?")
print("=" * 60)

EDGE_CASES = {
    "empty_block": """[H]

[D]
Some docs.
""",
    "consecutive_same_role": """[H]
DO THIS
[H]
AND THIS TOO
""",
    "markdown_inside_block": """[D]
This has **bold** and [a link](http://x.com) and:
- a list
- inside a doc block

That should survive.
""",
    "code_with_brackets": """[C]
const arr = [1, 2, 3];
if (arr[0] === 1) {
  console.log("[H] looks like a tag but isn't");
}
""",
    "collision_link_ref": """[H]
IMPORTANT DIRECTIVE
[D]
See [H] for the original instruction.
The text [A] here is a markdown link ref, not a tag.
""",
    "no_tags_at_all": """Just some plain markdown.
No dialect tags here.
""",
    "tag_in_middle_of_line": """[H]
DIRECTIVE
[D]
This line mentions [C] inline, not as a block tag.
""",
    "nested_code_fence": """[C]
```python
def foo():
    return [H]  # not a tag
```
""",
    "whitespace_tag": """  [H]  
DIRECTIVE WITH PADDED TAG
""",
}

all_pass = True
for name, text in EDGE_CASES.items():
    blocks = parse(text)
    roles = [b['tag'] for b in blocks]
    contents = [b['content'][:50] for b in blocks]

    # determine expected behavior and check
    ok = True
    note = ""

    if name == "empty_block":
        # empty [H] should be skipped, only [D] block produced
        ok = len(blocks) == 1 and blocks[0]['tag'] == 'D'
        note = "empty block correctly skipped" if ok else "FAIL: empty block not skipped"

    elif name == "consecutive_same_role":
        ok = len(blocks) == 2 and all(b['tag'] == 'H' for b in blocks)
        note = "consecutive same-role = two separate blocks" if ok else "FAIL: merged or lost"

    elif name == "markdown_inside_block":
        ok = len(blocks) == 1 and '**bold**' in blocks[0]['content'] and '- a list' in blocks[0]['content']
        note = "markdown preserved inside block" if ok else "FAIL: markdown stripped"

    elif name == "code_with_brackets":
        # [H] inside a string in code should NOT start a new block
        # because it's not on its own line
        ok = len(blocks) == 1 and blocks[0]['tag'] == 'C'
        has_fake = '[H] looks like a tag' in blocks[0]['content']
        ok = ok and has_fake
        note = "inline [H] in code survived (not parsed as tag)" if ok else "FAIL: false tag split"

    elif name == "collision_link_ref":
        # [H] and [A] in prose should NOT be parsed as tags (not on own line)
        ok = len(blocks) == 2
        note = "inline [H]/[A] refs not confused with tags" if ok else f"FAIL: got {len(blocks)} blocks"

    elif name == "no_tags_at_all":
        ok = len(blocks) == 0
        note = "no tags = no blocks (graceful)" if ok else "FAIL: phantom blocks"

    elif name == "tag_in_middle_of_line":
        ok = len(blocks) == 2
        has_inline = '[C]' in blocks[1]['content']
        ok = ok and has_inline
        note = "inline [C] in prose survived as text" if ok else "FAIL: false split"

    elif name == "nested_code_fence":
        ok = len(blocks) == 1 and '[H]' in blocks[0]['content']
        note = "code fence with [H] inside preserved" if ok else "FAIL: code fence broke"

    elif name == "whitespace_tag":
        ok = len(blocks) == 1 and blocks[0]['tag'] == 'H'
        note = "whitespace-padded tag parsed OK" if ok else "FAIL: whitespace broke tag"

    status = "✓" if ok else "✗"
    if not ok:
        all_pass = False
    print(f"  {status} {name:30s} blocks={len(blocks):1d}  roles={roles}  {note}")

print(f"\n{'ALL EDGE CASES PASSED' if all_pass else 'SOME EDGE CASES FAILED'}")


# ── collision analysis ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 3: Markdown collision analysis")
print("=" * 60)

collisions = [
    ("[H] is a valid Markdown link reference definition syntax", True),
    ("[C] at line start could be a footnote-style ref", True),
    ("The tag regex requires ONLY the tag on the line (^[X]$), so [H] in prose is safe", False),
    ("Code fences (```) are NOT handled — a [H] inside a fenced block on its own line WILL false-trigger", True),
]
print("\nKnown collision points:")
for desc, is_problem in collisions:
    icon = "⚠" if is_problem else "✓"
    print(f"  {icon} {desc}")


# ── parser complexity audit ────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 4: complexity audit")
print("=" * 60)

import inspect
source = inspect.getsource(parse)
lines = [l for l in source.split('\n') if l.strip() and not l.strip().startswith('#')]
print(f"  parser function: {len(lines)} non-blank, non-comment lines")
print(f"  regex patterns:  1")
print(f"  special cases:   0 (no if/elif branches for specific roles)")
print(f"  verdict:         {'SIMPLE — viable scaffold' if len(lines) < 30 else 'COMPLEX — reconsider'}")


# ── the fatal flaw test ───────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 5: the fatal flaw — code fences")
print("=" * 60)

fenced = """[C]
```javascript
function test() {
    return true;
}
```

[H]
NEXT DIRECTIVE

[C]
```python
# What if [H] appears on its own line inside a fence?
data = {
    "tag": "[H]"
}
[A]
# This line is INSIDE a python code block but looks like a tag
print("oops")
```
"""

blocks = parse(fenced)
print(f"  Parsed {len(blocks)} blocks from fenced code test:")
for b in blocks:
    preview = b['content'][:60].replace('\n', ' ↵ ')
    print(f"    [{b['tag']}] {preview}")

# The [A] inside the python fence WILL be mis-parsed as a new block
has_false_split = any(b['tag'] == 'A' for b in blocks)
print(f"\n  False tag split inside code fence: {'YES — THIS IS THE FLAW' if has_false_split else 'no'}")
if has_false_split:
    print("  ⚠ A bare [A] on its own line inside a fenced code block")
    print("    was parsed as a role tag. This is the format's one")
    print("    structural weakness: the parser doesn't track fence state.")
    print("  FIX: track ``` open/close state in the parser (adds ~5 lines)")
