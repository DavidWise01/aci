#!/usr/bin/env python3
"""
haci_git — the human skin for git-transported machine dialogue.

You write plain Markdown (.haci). Git supplies the MACI envelope for free:
    commit hash    -> message id
    commit time    -> ts
    author         -> from
    parent commits -> refs (the decision DAG, already acyclic & content-addressed)
    signature      -> authority TRIT   (+ sovereign / 0 delegated / - advisory)

Two ternary axes (Fiddler likes 3):
    SPEECH ACT  { ! command , ? question , > evidence }
    AUTHORITY   { + sovereign , 0 delegated , - advisory }
    => a 3x3 lattice of "who said what, with what weight".

Stdlib only. Fails loud. The parser half is faithful to DavidWise01/haci hmd.py.
"""
import re, sys, json, hashlib, subprocess, argparse

# ---- axis 1: the three speech acts (+ the markdown natives HACI keeps) --------
SPEECH = {'!': 'command', '?': 'question', '>': 'evidence'}

# ---- axis 2: the three authority trits ---------------------------------------
#   resolved from the git signature, NOT from the text -> unspoofable by content
TRIT = {+1: 'sovereign', 0: 'delegated', -1: 'advisory'}
GLYPH = {+1: '+', 0: '0', -1: '-'}


def classify_line(line):
    """Faithful port of hmd.classify_line (HMD v0.1 rules 1-7)."""
    s = line.strip()
    if not s:
        return ('BLANK', '', None)
    if s.startswith('!'):
        body = s[1:].strip()
        if body.startswith('?'):
            return ('HUMAN_QUESTION', body[1:].strip(), '!?')
        return ('HUMAN', body, '!')
    if s.startswith('?'):
        body = s[1:].strip()
        if body.startswith('!'):
            return ('HUMAN_QUESTION', body[1:].strip(), '?!')
        for ch in body:
            if ch.isalpha():
                return (('HUMAN_QUESTION' if ch.isupper() else 'AI_QUESTION'), body, '?')
        return ('AI_QUESTION', body, '?')
    if s.startswith('>'):
        return ('EVIDENCE', s[1:].strip(), '>')
    if re.match(r'^(`{3,}|~{3,})', s):
        return ('CODE_FENCE', s, None)
    if re.match(r'^#{1,6}\s', s):
        return ('HEADING', s.lstrip('#').strip(), '#')
    if s.startswith('<!--'):
        return ('META', s, None)
    for ch in s:
        if ch.isalpha():
            return (('DOCUMENTATION' if ch.isupper() else 'AI'), s, None)
    return ('DOCUMENTATION', s, None)


def parse(text):
    """Single-pass, fence-tracked. Returns (blocks, errors)."""
    blocks, errors = [], []
    in_fence, fence_buf, fence_open_line = False, [], 0
    for i, line in enumerate(text.split('\n'), 1):
        role, body, mark = classify_line(line)
        if role == 'CODE_FENCE':
            if not in_fence:
                in_fence, fence_buf, fence_open_line = True, [line], i
            else:
                fence_buf.append(line)
                blocks.append({'role': 'CODE', 'content': '\n'.join(fence_buf),
                               'line': fence_open_line, 'mark': '```'})
                in_fence, fence_buf = False, []
            continue
        if in_fence:
            fence_buf.append(line)     # <- fence-immunity: marks inside are content
            continue
        if role != 'BLANK':
            blocks.append({'role': role, 'content': body, 'line': i, 'mark': mark})
    # THE GUARD: an unterminated fence silently swallows every ! after it.
    # This is the one live vector the independent audit surfaced. Fail loud.
    if in_fence:
        errors.append(f"F001: unterminated code fence opened at line {fence_open_line} "
                      f"-> {len(fence_buf)} lines swallowed, including any '!' commands. "
                      f"Authority-availability breach; refuse to commit.")
        # still surface what got eaten, flagged
        blocks.append({'role': 'SWALLOWED', 'content': '\n'.join(fence_buf),
                       'line': fence_open_line, 'mark': None})
    return blocks, errors


# ---- git envelope ------------------------------------------------------------
def _git(args, cwd):
    return subprocess.run(['git', '-C', cwd] + args,
                          capture_output=True, text=True)


def resolve_authority(commit, cwd, governor_fpr=None, agent_fprs=()):
    """Signature -> authority trit. Unspoofable by file content.
       +1 sovereign : good sig by the governor key
        0 delegated : good sig by an authorized agent key
       -1 advisory  : unsigned or unverifiable
    """
    r = _git(['verify-commit', '--raw', commit], cwd)
    blob = (r.stdout + r.stderr)
    m = re.search(r'VALIDSIG\s+(\S+)', blob)
    if not m:
        return -1                       # unsigned / bad -> advisory
    key = m.group(1)
    if governor_fpr and key.endswith(governor_fpr[-16:]):
        return +1
    if any(key.endswith(a[-16:]) for a in agent_fprs):
        return 0
    return -1


def envelope(cwd, governor_fpr=None, agent_fprs=(), max_commits=200):
    """Walk git log -> MACI-style message stream. Git IS the envelope."""
    fmt = '%H%x1f%an%x1f%aI%x1f%P%x1f%s'
    r = _git(['log', f'--pretty=format:{fmt}', f'-{max_commits}'], cwd)
    if r.returncode != 0:
        raise RuntimeError(f"not a git repo / no commits: {r.stderr.strip()}")
    stream = []
    for row in r.stdout.split('\n'):
        if not row.strip():
            continue
        h, an, ts, parents, subj = row.split('\x1f')
        trit = resolve_authority(h, cwd, governor_fpr, agent_fprs)
        stream.append({
            'id': h[:12], 'full': h, 'from': an, 'ts': ts,
            'refs': [p[:12] for p in parents.split()],   # parent commits = the DAG
            'subject': subj,
            'authority': TRIT[trit], 'trit': trit, 'glyph': GLYPH[trit],
        })
    return stream


# ---- validators (MACI V-rules, re-homed onto the git DAG) --------------------
def validate_stream(stream):
    errors = []
    ids = {m['id'] for m in stream}
    seen = set()
    for m in stream:
        if m['id'] in seen:
            errors.append(f"V001: duplicate id {m['id']}")
        seen.add(m['id'])
        for ref in m['refs']:
            # a ref may point outside the fetched window; only flag intra-window ghosts
            if ref not in ids and ref not in {x['id'] for x in stream}:
                pass
    # acyclicity is guaranteed by git's Merkle DAG; assert it anyway (Kahn)
    indeg = {m['id']: 0 for m in stream}
    adj = {m['id']: [] for m in stream}
    idset = set(indeg)
    for m in stream:
        for ref in m['refs']:
            if ref in idset:
                adj[ref].append(m['id']); indeg[m['id']] += 1
    q = [n for n, d in indeg.items() if d == 0]; done = 0
    while q:
        n = q.pop()
        done += 1
        for w in adj[n]:
            indeg[w] -= 1
            if indeg[w] == 0:
                q.append(w)
    if done != len(idset):
        errors.append("V-DAG: cycle detected in commit graph (should be impossible under git)")
    return errors


def seal(stream):
    """Portable fingerprint of the whole conversation's crossings."""
    h = hashlib.sha256()
    for m in stream:
        h.update(f"{m['id']}:{m['from']}:{m['trit']}:{','.join(m['refs'])}\n".encode())
    return 'haci-git:' + h.hexdigest()[:12]


# ---- cli ---------------------------------------------------------------------
def cmd_lint(args):
    text = open(args.file, encoding='utf-8').read()
    blocks, errors = parse(text)
    tally = {}
    for b in blocks:
        tally[b['role']] = tally.get(b['role'], 0) + 1
    print(f"lint {args.file}: {len(blocks)} blocks  {tally}")
    for e in errors:
        print("  ERROR:", e)
    if errors:
        print("REFUSE — fix before commit.")
        sys.exit(1)
    print("clean.")


def cmd_envelope(args):
    stream = envelope(args.repo, args.governor, args.agent)
    print(json.dumps(stream, indent=2))
    errs = validate_stream(stream)
    for e in errs:
        print("VALIDATION:", e, file=sys.stderr)
    print(seal(stream), file=sys.stderr)
    if errs:
        sys.exit(1)


def cmd_selftest(args):
    ok = True
    # fence-immunity
    b, e = parse("! REAL\n```\n! fake\n> fake\n```\n> real")
    cmds = [x for x in b if x['role'] == 'HUMAN']
    code = [x for x in b if x['role'] == 'CODE']
    assert len(cmds) == 1 and code and '! fake' in code[0]['content'], "fence-immunity broken"
    print("  [ok] fence-immunity: 1 command survives, fakes are CODE content")
    # fence-swallow guard fires
    b, e = parse("```\n! swallowed command")
    assert any(x.startswith('F001') for x in e), "swallow guard silent"
    print("  [ok] fence-swallow guard: F001 raised, commit would be refused")
    # trit mapping is total
    assert set(TRIT) == {+1, 0, -1}, "authority not ternary"
    print("  [ok] authority is ternary: {+ sovereign, 0 delegated, - advisory}")
    print("SELFTEST PASSED" if ok else "SELFTEST FAILED")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(prog='haci_git')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('lint'); p.add_argument('file'); p.set_defaults(fn=cmd_lint)
    p = sub.add_parser('envelope'); p.add_argument('repo')
    p.add_argument('--governor', default=None); p.add_argument('--agent', action='append', default=[])
    p.set_defaults(fn=cmd_envelope)
    p = sub.add_parser('selftest'); p.set_defaults(fn=cmd_selftest)
    args = ap.parse_args()
    args.fn(args)
