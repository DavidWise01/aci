#!/usr/bin/env python3
"""
haci2.py — HACI v0.2 reference parser.

Human Artfully Crafted Intelligence
Part of the ACI (Artfully Crafted Intelligence) family.

v0.2 spec (prefix/suffix duality):
  same symbol, different meaning by position.

  PREFIX (first non-space char):
    !  declare / command
    ?  inquire / explore
    >  observe / evidence

  SUFFIX (last non-space char):
    !  committed / decided
    ?  pending / unresolved
    >  verified / completed

  DUAL MODE: both ends used simultaneously.
    ! BUILD RUNTIME >
    → intent=declare, status=verified

  OWNERSHIP (casing of content after stripping operators):
    UPPERCASE       human-owned
    lowercase       machine-owned
    Sentence Case   shared documentation

  AMBIGUITY RULE: symbols inside the line are literal text.
    memory > cache ratio  → not evidence, just content.
    Only edge positions matter.

Author: David Lee Wise / Bridge-Burners LLC
"""

__version__ = "0.2.0"

import re, sys, json, argparse
from html import escape
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# LEXER — prefix/suffix/dual-mode parser
# ═══════════════════════════════════════════════════════════════════════

OPERATORS = {'!', '?', '>'}

INTENT_MAP = {
    '!': 'declare',
    '?': 'inquire',
    '>': 'observe',
}

STATUS_MAP = {
    '!': 'committed',
    '?': 'pending',
    '>': 'verified',
}

FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})')
HEAD_RE  = re.compile(r'^\s*#{1,6}\s')


def classify_owner(text):
    """Classify ownership by casing of content."""
    for ch in text:
        if ch.isalpha():
            # check if the whole visible text is uppercase
            alpha_chars = [c for c in text if c.isalpha()]
            if all(c.isupper() for c in alpha_chars):
                return 'human'
            elif alpha_chars[0].islower():
                return 'machine'
            else:
                return 'shared'
    return 'shared'  # no alpha chars


def parse_line(line):
    """
    Parse a single line per HACI v0.2 spec.
    Returns a node dict: {intent, status, owner, content, prefix, suffix, raw}

    Parser order:
      1. detect code fence → handled by parse()
      2. trim line
      3. detect prefix operator (first non-space char)
      4. detect suffix operator (last non-space char)
      5. remove operators from content
      6. classify casing → owner
      7. emit node
    """
    raw = line
    s = line.strip()

    if not s:
        return None  # blank line

    # heading detection (before operator stripping)
    if HEAD_RE.match(s):
        level = 0
        for ch in s:
            if ch == '#':
                level += 1
            else:
                break
        return {
            'type': 'heading',
            'level': level,
            'content': s.lstrip('#').strip(),
            'intent': None,
            'status': None,
            'owner': 'shared',
            'prefix': '#',
            'suffix': None,
            'raw': raw,
        }

    # HTML comment / metadata
    if s.startswith('<!--'):
        return {
            'type': 'meta',
            'content': s,
            'intent': None,
            'status': None,
            'owner': 'shared',
            'prefix': None,
            'suffix': None,
            'raw': raw,
        }

    # step 3: detect prefix
    prefix = None
    if s[0] in OPERATORS:
        prefix = s[0]

    # step 4: detect suffix
    suffix = None
    if s[-1] in OPERATORS:
        # only if it's not the SAME character as prefix on a single-char line
        if len(s) == 1:
            suffix = None  # single operator char = prefix only
        elif s[-1] != prefix or len(s.strip(''.join(OPERATORS)).strip()) > 0:
            suffix = s[-1]
        # edge case: `! !` — prefix and suffix are both !, content is empty
        # edge case: `! BUILD !` — prefix !, suffix !, content is BUILD
        # check if suffix char is truly at the edge (not part of content)
        # re-check: if prefix consumed the first char, suffix should check the last
        if prefix and len(s) > 1:
            suffix = s[-1] if s[-1] in OPERATORS else None

    # step 5: strip operators from content
    content = s
    if prefix:
        content = content[1:].strip()
    if suffix and len(content) > 0 and content[-1] == suffix:
        content = content[:-1].strip()

    # handle empty content after stripping
    if not content:
        content = ''

    # step 6: classify ownership
    intent = INTENT_MAP.get(prefix) if prefix else None
    status = STATUS_MAP.get(suffix) if suffix else None
    owner = classify_owner(content) if content else ('human' if prefix == '!' else 'shared')

    return {
        'type': 'line',
        'content': content,
        'intent': intent,
        'status': status,
        'owner': owner,
        'prefix': prefix,
        'suffix': suffix,
        'raw': raw,
    }


def parse(text):
    """Parse a full HACI v0.2 document into AST nodes."""
    lines = text.split('\n')
    nodes = []
    in_fence = False
    fence_buf = []
    fence_start = 0
    fence_lang = None
    warnings = []

    for i, line in enumerate(lines, 1):
        s = line.strip()

        # fence tracking
        if FENCE_RE.match(s):
            if in_fence:
                fence_buf.append(line)
                nodes.append({
                    'type': 'code',
                    'content': '\n'.join(fence_buf),
                    'lang': fence_lang,
                    'line': fence_start,
                    'intent': None,
                    'status': None,
                    'owner': 'machine',
                    'prefix': None,
                    'suffix': None,
                })
                fence_buf = []
                in_fence = False
                fence_lang = None
                continue
            else:
                in_fence = True
                fence_buf = [line]
                fence_start = i
                m = re.match(r'^\s*`{3,}\s*(\w+)', s)
                fence_lang = m.group(1) if m else None
                continue

        if in_fence:
            fence_buf.append(line)
            continue

        node = parse_line(line)
        if node:
            node['line'] = i
            nodes.append(node)

    # unclosed fence
    if fence_buf:
        warnings.append(f"Unclosed code fence starting at line {fence_start}")
        nodes.append({
            'type': 'code',
            'content': '\n'.join(fence_buf),
            'lang': fence_lang,
            'line': fence_start,
            'intent': None,
            'status': None,
            'owner': 'machine',
            'prefix': None,
            'suffix': None,
        })

    return nodes, warnings


# ═══════════════════════════════════════════════════════════════════════
# OUTPUT: print mode
# ═══════════════════════════════════════════════════════════════════════

def fmt_node(n):
    """Format a node as a compact one-line summary."""
    pre = n.get('prefix') or ' '
    suf = n.get('suffix') or ' '
    intent = (n.get('intent') or '')[0:7].ljust(7) if n.get('intent') else '       '
    status = (n.get('status') or '')[0:9].ljust(9) if n.get('status') else '         '
    owner = (n.get('owner') or '')[0:7].ljust(7)
    content = n['content'][:52].replace('\n', ' \u21b5 ')
    if len(n['content']) > 52:
        content += '\u2026'
    return f"  {pre}{suf} {intent} {status} {owner} L{n.get('line',0):>3d}  {content}"


def cmd_print(nodes, warnings):
    for w in warnings:
        print(f"  \033[33m\u26a0 {w}\033[0m")
    print(f"\n  {len(nodes)} nodes parsed:")
    print(f"  {'':3s} {'INTENT':7s} {'STATUS':9s} {'OWNER':7s} {'LINE':>4s}  CONTENT")
    print(f"  {'─'*3} {'─'*7} {'─'*9} {'─'*7} {'─'*4}  {'─'*40}")
    for n in nodes:
        print(fmt_node(n))
    print()


# ═══════════════════════════════════════════════════════════════════════
# OUTPUT: stats
# ═══════════════════════════════════════════════════════════════════════

def cmd_stats(nodes):
    from collections import Counter

    intents = Counter(n.get('intent') or '(none)' for n in nodes)
    statuses = Counter(n.get('status') or '(none)' for n in nodes)
    owners = Counter(n.get('owner') or '(none)' for n in nodes)
    types = Counter(n.get('type') for n in nodes)

    print(f"\n  INTENT DISTRIBUTION:")
    for k, v in intents.most_common():
        bar = '\u2588' * int(30 * v / max(intents.values()))
        print(f"    {k:<12s} {v:>4d}  {bar}")

    print(f"\n  STATUS DISTRIBUTION:")
    for k, v in statuses.most_common():
        bar = '\u2588' * int(30 * v / max(statuses.values()))
        print(f"    {k:<12s} {v:>4d}  {bar}")

    print(f"\n  OWNERSHIP DISTRIBUTION:")
    for k, v in owners.most_common():
        bar = '\u2588' * int(30 * v / max(owners.values()))
        print(f"    {k:<12s} {v:>4d}  {bar}")

    print(f"\n  NODE TYPES:")
    for k, v in types.most_common():
        print(f"    {k:<12s} {v:>4d}")
    print()


# ═══════════════════════════════════════════════════════════════════════
# OUTPUT: JSON
# ═══════════════════════════════════════════════════════════════════════

def cmd_json(nodes, warnings):
    output = {
        'haci': __version__,
        'warnings': warnings,
        'node_count': len(nodes),
        'nodes': [{
            'type': n['type'],
            'content': n['content'],
            'line': n.get('line'),
            'intent': n.get('intent'),
            'status': n.get('status'),
            'owner': n.get('owner'),
            'prefix': n.get('prefix'),
            'suffix': n.get('suffix'),
        } for n in nodes],
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════════════════
# OUTPUT: HTML renderer (series aesthetic)
# ═══════════════════════════════════════════════════════════════════════

OWNER_COLORS = {
    'human':   '#8a2be2',
    'machine': '#1db954',
    'shared':  '#c8c0b0',
}

INTENT_BADGES = {
    'declare': ('\u25cf', '#8a2be2'),   # ●
    'inquire': ('\u25cb', '#d9a441'),   # ○
    'observe': ('\u25b6', '#73b3a3'),   # ▶
}

STATUS_BADGES = {
    'committed': ('\u2713', '#8a2be2'),  # ✓
    'pending':   ('\u25cb', '#d9a441'),  # ○
    'verified':  ('\u2713', '#73b3a3'),  # ✓
}

def cmd_html(nodes, path):
    title = Path(path).stem
    parts = [f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)} — HACI v0.2</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700&family=Spectral:wght@300;400&family=Cormorant+Garamond:wght@300;400&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#170d20;color:#c8c0b0;font-family:"Spectral",serif;line-height:1.6;display:flex;justify-content:center}}
.doc{{max-width:760px;width:100%;padding:32px 20px 60px}}
.hdr{{font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:rgba(168,127,51,.5);margin-bottom:18px}}
.nd{{display:flex;gap:8px;margin:2px 0;align-items:baseline;padding:3px 0 3px 8px;border-left:2px solid transparent}}
.nd:hover{{background:rgba(255,255,255,.015)}}
.badges{{display:flex;gap:3px;min-width:28px;justify-content:flex-end;flex-shrink:0;padding-top:2px}}
.badge{{font-size:10px;width:14px;text-align:center}}
.own{{font-family:"IBM Plex Mono",monospace;font-size:8px;letter-spacing:.06em;min-width:48px;text-align:right;opacity:.35;flex-shrink:0;padding-top:3px}}
.con{{flex:1;font-size:14.5px;word-wrap:break-word}}
.con.bold{{font-weight:bold}}
pre.code{{background:rgba(0,0,0,.25);border:1px solid rgba(154,152,166,.12);border-radius:6px;padding:12px 14px;
  font-family:"IBM Plex Mono",monospace;font-size:12px;overflow-x:auto;margin:0;white-space:pre-wrap;line-height:1.5}}
.h1{{font-family:"Cormorant Garamond",serif;font-size:28px;font-weight:300;margin-top:20px;line-height:1.1;color:#e9e2d2}}
.h2{{font-family:"Cormorant Garamond",serif;font-size:22px;font-weight:300;margin-top:16px;line-height:1.15;color:#e9e2d2}}
.h3{{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.14em;text-transform:uppercase;margin-top:14px;font-weight:500;color:#d9a441}}
.foot{{font-family:"IBM Plex Mono",monospace;font-size:9px;color:rgba(154,152,166,.3);text-align:center;margin-top:36px;letter-spacing:.08em}}
</style></head><body><div class="doc">
<div class="hdr">HACI v0.2 &middot; {escape(title)}</div>
"""]

    for n in nodes:
        owner = n.get('owner', 'shared')
        color = OWNER_COLORS.get(owner, '#9a98a6')
        bold = ' bold' if owner == 'human' else ''

        if n['type'] == 'code':
            code_lines = n['content'].split('\n')
            if len(code_lines) >= 2 and (code_lines[-1].strip().startswith('`') or code_lines[-1].strip().startswith('~')):
                code_body = '\n'.join(code_lines[1:-1])
            else:
                code_body = '\n'.join(code_lines[1:]) if len(code_lines) > 1 else n['content']
            parts.append(f'<div class="nd"><span class="badges"></span><span class="own" style="color:#73b3a3">code</span>'
                        f'<pre class="code" style="color:#73b3a3">{escape(code_body)}</pre></div>')
            continue

        if n['type'] == 'heading':
            lv = n.get('level', 2)
            cls = {1:'h1',2:'h2'}.get(lv, 'h3')
            parts.append(f'<div class="nd"><span class="badges"></span><span class="own"></span>'
                        f'<div class="con {cls}">{escape(n["content"])}</div></div>')
            continue

        if n['type'] == 'meta':
            parts.append(f'<div class="nd"><span class="badges"></span><span class="own" style="color:#5b5868">meta</span>'
                        f'<div class="con" style="color:#5b5868">{escape(n["content"])}</div></div>')
            continue

        # build badge strip
        badges = ''
        if n.get('intent') and n['intent'] in INTENT_BADGES:
            glyph, bc = INTENT_BADGES[n['intent']]
            badges += f'<span class="badge" style="color:{bc}">{glyph}</span>'
        if n.get('status') and n['status'] in STATUS_BADGES:
            glyph, bc = STATUS_BADGES[n['status']]
            badges += f'<span class="badge" style="color:{bc}">{glyph}</span>'

        parts.append(
            f'<div class="nd" style="border-left-color:{color}22">'
            f'<span class="badges">{badges}</span>'
            f'<span class="own" style="color:{color}">{owner}</span>'
            f'<div class="con{bold}" style="color:{color}">{escape(n["content"])}</div></div>')

    parts.append('<div class="foot">HACI v0.2 &middot; Human-AI Collaborative Interchange &middot; ACI family</div>')
    parts.append('</div></body></html>')

    out_path = str(Path(path).with_suffix('.html'))
    with open(out_path, 'w') as f:
        f.write('\n'.join(parts))
    print(f"  rendered to {out_path}")
    return out_path


# ═══════════════════════════════════════════════════════════════════════
# TEST SUITE
# ═══════════════════════════════════════════════════════════════════════

def cmd_test():
    print(f"\n{'='*60}")
    print("HACI v0.2 PARSER TEST SUITE")
    print(f"{'='*60}")

    cases = [
        # (input_line, expected_intent, expected_status, expected_owner, description)

        # prefix only
        ("! BUILD RUNTIME",          "declare",  None,        "human",   "prefix ! → declare, UPPERCASE → human"),
        ("? should memory be pooled", "inquire", None,        "machine", "prefix ? → inquire, lowercase → machine"),
        ("> latency dropped 18%",    "observe",  None,        "machine", "prefix > → observe, lowercase → machine"),

        # suffix only
        ("BUILD RUNTIME !",          None,       "committed", "human",   "suffix ! → committed, UPPERCASE → human"),
        ("pool memory ?",            None,       "pending",   "machine", "suffix ? → pending, lowercase → machine"),
        ("runtime verified >",       None,       "verified",  "machine", "suffix > → verified, lowercase → machine"),

        # dual mode
        ("! BUILD RUNTIME >",        "declare",  "verified",  "human",   "prefix ! + suffix > → declare + verified"),
        ("? explore options !",      "inquire",  "committed", "machine", "prefix ? + suffix ! → inquire + committed"),
        ("! DEPLOY NOW !",           "declare",  "committed", "human",   "prefix ! + suffix ! → declare + committed"),
        ("> test passed !",          "observe",  "committed", "machine", "prefix > + suffix ! → observe + committed"),

        # no operators
        ("allocate workers",         None,       None,        "machine", "no operators, lowercase → machine"),
        ("DEPLOY IMMEDIATELY",       None,       None,        "human",   "no operators, UPPERCASE → human"),
        ("The runtime starts.",      None,       None,        "shared",  "no operators, Sentence case → shared"),

        # ambiguity rule: operators inside are literal
        ("memory > cache ratio",     None,       None,        "machine", "middle > is literal, not an operator"),
        ("is this ok?",              None,       "pending",   "machine", "trailing ? IS suffix (last char)"),
        ("what! is happening",       None,       None,        "machine", "middle ! is literal"),

        # edge cases
        ("!",                        "declare",  None,        "human",   "lone ! → declare, default human"),
        ("! >",                      "declare",  "verified",  "human",   "prefix ! suffix > empty content"),
        ("  ! PADDED  ",             "declare",  None,        "human",   "whitespace-padded prefix"),
    ]

    all_pass = True
    for line_in, exp_intent, exp_status, exp_owner, desc in cases:
        node = parse_line(line_in)
        if node is None:
            print(f"  \033[31m✗\033[0m NULL node: \"{line_in}\" — {desc}")
            all_pass = False
            continue

        ok_intent = node['intent'] == exp_intent
        ok_status = node['status'] == exp_status
        ok_owner = node['owner'] == exp_owner
        ok = ok_intent and ok_status and ok_owner

        if not ok:
            all_pass = False
            fails = []
            if not ok_intent:
                fails.append(f"intent: got {node['intent']}, expected {exp_intent}")
            if not ok_status:
                fails.append(f"status: got {node['status']}, expected {exp_status}")
            if not ok_owner:
                fails.append(f"owner: got {node['owner']}, expected {exp_owner}")
            print(f"  \033[31m✗\033[0m \"{line_in}\"")
            print(f"       {'; '.join(fails)}")
            print(f"       ({desc})")
        else:
            i = (node['intent'] or '-')[:3]
            s = (node['status'] or '-')[:3]
            o = (node['owner'] or '-')[:3]
            print(f"  \033[32m✓\033[0m {i}/{s}/{o}  \"{line_in}\"")

    print(f"\n  {'✓ ALL TESTS PASSED' if all_pass else '✗ SOME TESTS FAILED'}")
    print(f"  {len(cases)} cases tested\n")
    return all_pass


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        prog='haci2',
        description='HACI v0.2 parser — prefix/suffix duality',
        epilog='ACI family · David Lee Wise / Bridge-Burners LLC')
    p.add_argument('file', nargs='?', help='.haci document')
    p.add_argument('--html', action='store_true', help='render HTML')
    p.add_argument('--json', action='store_true', help='export JSON')
    p.add_argument('--stats', action='store_true', help='show distribution')
    p.add_argument('--test', action='store_true', help='run test suite')
    p.add_argument('--all', action='store_true', help='run everything')
    p.add_argument('--version', action='version', version=f'haci {__version__}')
    args = p.parse_args()

    if args.test:
        cmd_test()
        return

    if not args.file:
        p.print_help()
        return

    with open(args.file) as f:
        text = f.read()

    nodes, warnings = parse(text)
    ran = False

    if args.all or args.stats:
        cmd_stats(nodes); ran = True
    if args.all or args.html:
        cmd_html(nodes, args.file); ran = True
    if args.json:
        cmd_json(nodes, warnings); ran = True
    if not ran:
        cmd_print(nodes, warnings)


if __name__ == '__main__':
    main()
