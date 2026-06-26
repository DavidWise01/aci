#!/usr/bin/env python3
"""
haci.py — HACI v0.1 reference parser.

Human-AI Collaborative Interchange: a semantic Markdown profile
for deterministic role attribution in collaborative documents.

Usage:
    python3 haci.py <file>                 # parse and print blocks
    python3 haci.py <file> --html          # render role-attributed HTML
    python3 haci.py <file> --json          # export blocks as JSON
    python3 haci.py <file> --stats         # role distribution
    python3 haci.py <file> --lint          # check for common issues
    python3 haci.py <file> --test          # self-hosting verification
    python3 haci.py <file> --all           # run everything

Part of the ACI (Artfully Crafted Intelligence) family.
Author: David Lee Wise / Bridge-Burners LLC
"""

__version__ = "0.1.0"

import re, sys, json, argparse
from html import escape
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# LEXER — Rules 1-7 per HACI v0.1 specification
# ═══════════════════════════════════════════════════════════════════════

ROLES = {
    'HUMAN':          'Human command (authoritative)',
    'HUMAN_QUESTION': 'Human question (directive)',
    'AI':             'AI proposal / reasoning',
    'AI_QUESTION':    'AI question (exploratory)',
    'DOCUMENTATION':  'Documentation / explanation',
    'EVIDENCE':       'Evidence / observation / runtime output',
    'CODE':           'Executable code (fenced block)',
    'HEADING':        'Document structure',
    'META':           'Metadata (HTML comment, version header)',
}

FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})')
HEAD_RE  = re.compile(r'^\s*#{1,6}\s')


def classify_line(line):
    """
    Classify a single line per HACI v0.1 lexer rules.
    Returns (role, content, symbol).
    
    Priority order:
      1. ! prefix  → HUMAN (or HUMAN_QUESTION if !?)
      2. ? prefix  → QUESTION (subtyped by case of body)
      3. > prefix  → EVIDENCE
      4. ``` / ~~~ → CODE_FENCE (toggle; handled by parse())
      5. # prefix  → HEADING
      6. Case      → DOCUMENTATION (upper) or AI (lower)
      7. Fallback  → DOCUMENTATION (no alpha chars)
    """
    s = line.strip()
    if not s:
        return ('BLANK', '', None)

    # Rule 1: ! = human command
    if s.startswith('!'):
        body = s[1:].strip()
        # !? composite = human question
        if body.startswith('?'):
            return ('HUMAN_QUESTION', body[1:].strip(), '!?')
        return ('HUMAN', body, '!')

    # Rule 2 + 7: ? = question, subtyped by case
    if s.startswith('?'):
        body = s[1:].strip()
        # ?! composite = human question
        if body.startswith('!'):
            return ('HUMAN_QUESTION', body[1:].strip(), '?!')
        # case subtyping on body
        for ch in body:
            if ch.isalpha():
                if ch.isupper():
                    return ('HUMAN_QUESTION', body, '?')
                else:
                    return ('AI_QUESTION', body, '?')
        # no alpha in body
        return ('AI_QUESTION', body, '?')

    # Rule 3: > = evidence / runtime output
    if s.startswith('>'):
        return ('EVIDENCE', s[1:].strip(), '>')

    # Rule 4: code fence (open/close tracked by parse())
    if FENCE_RE.match(s):
        return ('CODE_FENCE', s, None)

    # Rule 5: heading
    if HEAD_RE.match(s):
        level = 0
        for ch in s:
            if ch == '#':
                level += 1
            else:
                break
        return ('HEADING', s.lstrip('#').strip(), f'h{level}')

    # META: HTML comment
    if s.startswith('<!--'):
        return ('META', s, None)

    # Rule 6: case convention — first alphabetic character
    for ch in s:
        if ch.isalpha():
            if ch.isupper():
                return ('DOCUMENTATION', s, None)
            else:
                return ('AI', s, None)

    # Rule 7: fallback — no alpha characters
    return ('DOCUMENTATION', s, None)


def parse(text):
    """
    Parse a HACI document into a list of blocks.
    Each block: {role, content, line, raw_lines}
    
    Handles code fence state tracking (Rule 4).
    """
    lines = text.split('\n')
    blocks = []
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
                # closing fence
                fence_buf.append(line)
                blocks.append({
                    'role': 'CODE',
                    'content': '\n'.join(fence_buf),
                    'line': fence_start,
                    'lang': fence_lang,
                    'raw_lines': len(fence_buf),
                })
                fence_buf = []
                in_fence = False
                fence_lang = None
                continue
            else:
                # opening fence — extract language hint
                in_fence = True
                fence_buf = [line]
                fence_start = i
                lang_match = re.match(r'^\s*`{3,}\s*(\w+)', s)
                fence_lang = lang_match.group(1) if lang_match else None
                continue

        if in_fence:
            fence_buf.append(line)
            continue

        role, content, sym = classify_line(line)
        if role == 'BLANK':
            continue

        blocks.append({
            'role': role,
            'content': content,
            'line': i,
            'symbol': sym,
            'raw_lines': 1,
        })

    # unclosed fence
    if fence_buf:
        warnings.append(f"Unclosed code fence starting at line {fence_start}")
        blocks.append({
            'role': 'CODE',
            'content': '\n'.join(fence_buf),
            'line': fence_start,
            'lang': fence_lang,
            'raw_lines': len(fence_buf),
        })

    return blocks, warnings


# ═══════════════════════════════════════════════════════════════════════
# OUTPUT MODES
# ═══════════════════════════════════════════════════════════════════════

# ── print mode ─────────────────────────────────────────────────────────

ROLE_GLYPHS = {
    'HUMAN': '!', 'HUMAN_QUESTION': '?!', 'AI': ' ', 'AI_QUESTION': '? ',
    'DOCUMENTATION': ' ', 'EVIDENCE': '>', 'CODE': '~', 'HEADING': '#', 'META': '·',
}

def cmd_print(blocks, warnings):
    for w in warnings:
        print(f"  \033[33m⚠ {w}\033[0m")
    print(f"\n  {len(blocks)} blocks parsed:\n")
    for b in blocks:
        glyph = ROLE_GLYPHS.get(b['role'], ' ')
        preview = b['content'][:68].replace('\n', ' \u21b5 ')
        if len(b['content']) > 68:
            preview += '\u2026'
        role_short = b['role'][:16]
        print(f"  {glyph:2s} {role_short:17s} L{b['line']:>3d}  {preview}")
    print()


# ── stats mode ─────────────────────────────────────────────────────────

def cmd_stats(blocks):
    counts = {}
    chars = {}
    lines = {}
    for b in blocks:
        r = b['role']
        counts[r] = counts.get(r, 0) + 1
        chars[r] = chars.get(r, 0) + len(b['content'])
        lines[r] = lines.get(r, 0) + b.get('raw_lines', 1)

    total_blocks = sum(counts.values())
    total_chars = sum(chars.values())

    print(f"\n  {'ROLE':<20s} {'BLOCKS':>7s} {'CHARS':>7s} {'LINES':>7s}  BAR")
    print(f"  {'─'*20} {'─'*7} {'─'*7} {'─'*7}  {'─'*20}")
    for role in sorted(counts.keys()):
        bar_len = int(30 * counts[role] / max(counts.values()))
        bar = '\u2588' * bar_len
        print(f"  {role:<20s} {counts[role]:>7d} {chars[role]:>7d} {lines[role]:>7d}  {bar}")
    print(f"  {'─'*20} {'─'*7} {'─'*7} {'─'*7}")
    print(f"  {'TOTAL':<20s} {total_blocks:>7d} {total_chars:>7d} {sum(lines.values()):>7d}")
    print()


# ── json mode ──────────────────────────────────────────────────────────

def cmd_json(blocks, warnings):
    output = {
        'version': __version__,
        'dialect': 'HACI',
        'warnings': warnings,
        'block_count': len(blocks),
        'blocks': [{
            'role': b['role'],
            'content': b['content'],
            'line': b['line'],
            'lang': b.get('lang'),
        } for b in blocks],
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


# ── lint mode ──────────────────────────────────────────────────────────

def cmd_lint(blocks, warnings, text):
    issues = []

    # W001: missing version header
    if not text.strip().startswith('<!-- HACI'):
        issues.append(('W001', 1, 'Missing version header: document should start with <!-- HACI v0.1 -->'))

    # W002: unclosed fences
    for w in warnings:
        if 'Unclosed' in w:
            issues.append(('W002', 0, w))

    # W003: human speech without ! prefix (heuristic: first-person uppercase "I" starting a line)
    for b in blocks:
        if b['role'] == 'DOCUMENTATION' and b['content'].startswith('I '):
            issues.append(('W003', b['line'],
                f'Line starts with "I " — if this is a human directive, prefix with ! '
                f'(currently classified as DOCUMENTATION)'))

    # W004: evidence without > prefix (heuristic: lines starting with common runtime patterns)
    runtime_patterns = [
        r'^Error:', r'^Warning:', r'^OK\b', r'^\d+ (tests?|items?|rows?|tasks?) ',
        r'^PASS\b', r'^FAIL\b', r'^HTTP/\d', r'^\d{3}\s',
    ]
    for b in blocks:
        if b['role'] in ('DOCUMENTATION', 'AI'):
            for pat in runtime_patterns:
                if re.match(pat, b['content']):
                    issues.append(('W004', b['line'],
                        f'Line looks like runtime output but has no > prefix: "{b["content"][:50]}"'))
                    break

    # W005: brand-name case trap
    brand_lowers = ['macOS', 'iOS', 'iPhone', 'iPad', 'eBay', 'jQuery', 'npm', 'x86', 'x64']
    for b in blocks:
        if b['role'] == 'AI':
            for brand in brand_lowers:
                if b['content'].startswith(brand):
                    issues.append(('W005', b['line'],
                        f'Line starts with "{brand}" (lowercase-initial brand) — classified as AI. '
                        f'If this is documentation, rephrase: "The {brand} build..."'))
                    break

    # W006: consecutive HUMAN blocks (might want to merge or review)
    prev_role = None
    for b in blocks:
        if b['role'] == 'HUMAN' and prev_role == 'HUMAN':
            issues.append(('W006', b['line'],
                'Consecutive HUMAN commands — consider whether these should be a single directive'))
        prev_role = b['role']

    # W007: empty document
    if not blocks:
        issues.append(('W007', 0, 'Document contains no parseable blocks'))

    # print results
    if not issues:
        print(f"\n  \033[32m✓ No issues found\033[0m\n")
    else:
        errs = sum(1 for c, _, _ in issues if c.startswith('E'))
        warns = len(issues) - errs
        print(f"\n  {len(issues)} issue(s): {errs} error(s), {warns} warning(s)\n")
        for code, line, msg in issues:
            loc = f"L{line}" if line else "   "
            print(f"  {code} {loc:>4s}  {msg}")
        print()

    return issues


# ── HTML renderer ──────────────────────────────────────────────────────

ROLE_COLORS = {
    'HUMAN':          ('#8a2be2', True),
    'HUMAN_QUESTION': ('#8a2be2', True),
    'AI':             ('#1db954', False),
    'AI_QUESTION':    ('#1db954', False),
    'DOCUMENTATION':  ('#c8c0b0', False),
    'EVIDENCE':       ('#d9a441', False),
    'CODE':           ('#73b3a3', False),
    'HEADING':        ('#e9e2d2', True),
    'META':           ('#5b5868', False),
}

ROLE_LABELS = {
    'HUMAN': '!', 'HUMAN_QUESTION': '?!', 'AI': 'ai', 'AI_QUESTION': 'ai?',
    'DOCUMENTATION': 'doc', 'EVIDENCE': '>', 'CODE': 'code', 'HEADING': '#', 'META': '·',
}

def cmd_html(blocks, path):
    title = Path(path).stem
    parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)} — HACI</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700&family=Spectral:wght@300;400&family=Cormorant+Garamond:wght@300;400&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#170d20;color:#c8c0b0;font-family:"Spectral",serif;line-height:1.6;
  display:flex;justify-content:center;-webkit-font-smoothing:antialiased}}
.doc{{max-width:740px;width:100%;padding:32px 20px 60px}}
.hdr{{font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase;
  color:rgba(168,127,51,.6);margin-bottom:18px}}
.blk{{display:flex;gap:10px;margin:2px 0;align-items:baseline;border-left:2px solid transparent;padding:2px 0 2px 8px}}
.blk:hover{{background:rgba(255,255,255,.02)}}
.tag{{font-family:"IBM Plex Mono",monospace;font-size:8.5px;letter-spacing:.06em;
  min-width:32px;text-align:right;opacity:.45;flex-shrink:0;padding-top:3px;user-select:none}}
.con{{flex:1;font-size:14.5px;word-wrap:break-word}}
.con.bold{{font-weight:bold}}
pre.code{{background:rgba(0,0,0,.25);border:1px solid rgba(154,152,166,.12);border-radius:6px;
  padding:12px 14px;font-family:"IBM Plex Mono",monospace;font-size:12px;
  overflow-x:auto;margin:0;white-space:pre-wrap;line-height:1.5}}
.lang{{font-family:"IBM Plex Mono",monospace;font-size:8px;letter-spacing:.1em;
  text-transform:uppercase;opacity:.35;margin-bottom:4px}}
.h1{{font-family:"Cormorant Garamond",serif;font-size:28px;font-weight:300;margin-top:20px;line-height:1.1}}
.h2{{font-family:"Cormorant Garamond",serif;font-size:22px;font-weight:300;margin-top:16px;line-height:1.15}}
.h3{{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.15em;text-transform:uppercase;
  margin-top:14px;font-weight:500}}
.foot{{font-family:"IBM Plex Mono",monospace;font-size:9px;color:rgba(154,152,166,.35);
  text-align:center;margin-top:36px;letter-spacing:.08em}}
</style>
</head>
<body>
<div class="doc">
<div class="hdr">HACI v0.1 &middot; {escape(title)}</div>
"""]

    for b in blocks:
        role = b['role']
        color, bold = ROLE_COLORS.get(role, ('#9a98a6', False))
        label = ROLE_LABELS.get(role, role[:3])

        if role == 'CODE':
            code_lines = b['content'].split('\n')
            # strip fence markers
            if len(code_lines) >= 2:
                code_body = '\n'.join(code_lines[1:-1]) if code_lines[-1].strip().startswith('`') or code_lines[-1].strip().startswith('~') else '\n'.join(code_lines[1:])
            else:
                code_body = b['content']
            lang_tag = f'<div class="lang">{escape(b.get("lang") or "")}</div>' if b.get('lang') else ''
            parts.append(
                f'<div class="blk"><span class="tag" style="color:{color}">{label}</span>'
                f'<div class="con">{lang_tag}<pre class="code" style="color:{color}">{escape(code_body)}</pre></div></div>')
        elif role == 'HEADING':
            level = b.get('symbol', 'h2')
            css_class = {'h1': 'h1', 'h2': 'h2'}.get(level, 'h3')
            parts.append(
                f'<div class="blk"><span class="tag" style="color:{color}">{label}</span>'
                f'<div class="con {css_class}" style="color:{color}">{escape(b["content"])}</div></div>')
        else:
            bold_class = ' bold' if bold else ''
            parts.append(
                f'<div class="blk" style="border-left-color:{color}22"><span class="tag" style="color:{color}">{label}</span>'
                f'<div class="con{bold_class}" style="color:{color}">{escape(b["content"])}</div></div>')

    parts.append('<div class="foot">HACI &middot; Human-AI Collaborative Interchange &middot; ACI family</div>')
    parts.append('</div>\n</body>\n</html>')

    out_path = str(Path(path).with_suffix('.html'))
    with open(out_path, 'w') as f:
        f.write('\n'.join(parts))
    print(f"  rendered to {out_path}")
    return out_path


# ── self-hosting test ──────────────────────────────────────────────────

def cmd_test(blocks, warnings):
    from collections import Counter
    counts = Counter(b['role'] for b in blocks)

    required = {'HUMAN', 'AI', 'DOCUMENTATION', 'EVIDENCE', 'CODE', 'HEADING'}
    present = set(counts.keys())
    missing = required - present

    checks = [
        (not missing,       f"all required roles present" if not missing else f"missing: {missing}"),
        (counts['HUMAN'] >= 2,      f"HUMAN commands: {counts['HUMAN']}"),
        (counts['AI'] >= 2,         f"AI proposals: {counts['AI']}"),
        (counts.get('EVIDENCE', 0) >= 1, f"EVIDENCE blocks: {counts.get('EVIDENCE', 0)}"),
        (counts.get('CODE', 0) >= 1,     f"CODE blocks: {counts.get('CODE', 0)}"),
        (counts['DOCUMENTATION'] >= 3,   f"DOCUMENTATION blocks: {counts['DOCUMENTATION']}"),
        (not warnings,      f"no parser warnings" if not warnings else f"warnings: {warnings}"),
    ]

    print(f"\n  Self-hosting verification ({len(blocks)} blocks):\n")
    all_pass = True
    for ok, desc in checks:
        mark = '\033[32m✓\033[0m' if ok else '\033[31m✗\033[0m'
        if not ok:
            all_pass = False
        print(f"    {mark} {desc}")

    result = '\033[32m✓ SELF-HOSTING PASSED\033[0m' if all_pass else '\033[31m✗ SELF-HOSTING FAILED\033[0m'
    print(f"\n  {result}\n")
    return all_pass


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        prog='haci',
        description='HACI v0.1 reference parser — Human-AI Collaborative Interchange',
        epilog='Part of the ACI (Artfully Crafted Intelligence) family. '
               'David Lee Wise / Bridge-Burners LLC.',
    )
    p.add_argument('file', help='path to .haci document')
    p.add_argument('--html',  action='store_true', help='render role-attributed HTML')
    p.add_argument('--json',  action='store_true', help='export blocks as JSON')
    p.add_argument('--stats', action='store_true', help='show role distribution')
    p.add_argument('--lint',  action='store_true', help='check for common issues')
    p.add_argument('--test',  action='store_true', help='run self-hosting verification')
    p.add_argument('--all',   action='store_true', help='run all modes')
    p.add_argument('--version', action='version', version=f'haci {__version__}')

    args = p.parse_args()

    path = args.file
    with open(path) as f:
        text = f.read()

    blocks, warnings = parse(text)

    # default: print mode
    ran_something = False

    if args.all or args.stats:
        cmd_stats(blocks)
        ran_something = True

    if args.all or args.lint:
        cmd_lint(blocks, warnings, text)
        ran_something = True

    if args.all or args.test:
        cmd_test(blocks, warnings)
        ran_something = True

    if args.all or args.html:
        cmd_html(blocks, path)
        ran_something = True

    if args.json:
        cmd_json(blocks, warnings)
        ran_something = True

    if not ran_something:
        cmd_print(blocks, warnings)


if __name__ == '__main__':
    main()
