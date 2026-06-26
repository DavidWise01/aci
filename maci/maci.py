#!/usr/bin/env python3
"""
maci.py — MACI v0.1 proof-of-concept.

Machine Artfully Crafted Intelligence: a JSON message envelope
for role-attributed, decision-chained machine-to-machine communication.

Part of the ACI (Artfully Crafted Intelligence) family.
Author: David Lee Wise / Bridge-Burners LLC
"""

__version__ = "0.1.0"

import json, sys
from datetime import datetime, timezone
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════════════
# MESSAGE SCHEMA
# ═══════════════════════════════════════════════════════════════════════

VALID_ROLES = {
    'COMMAND', 'PROPOSAL', 'EVIDENCE', 'QUESTION',
    'CODE', 'DOCUMENT', 'DECISION', 'DELEGATE',
}

VALID_AUTHORITY = {'sovereign', 'delegated', 'advisory', 'observer'}
VALID_STATUS = {'pending', 'approved', 'rejected', 'executed', 'superseded', None}

# HACI ↔ MACI role mapping
HACI_TO_MACI = {
    'HUMAN': 'COMMAND',
    'HUMAN_QUESTION': 'QUESTION',
    'AI': 'PROPOSAL',
    'AI_QUESTION': 'QUESTION',
    'DOCUMENTATION': 'DOCUMENT',
    'EVIDENCE': 'EVIDENCE',
    'CODE': 'CODE',
}

MACI_TO_HACI = {
    'COMMAND': 'HUMAN',
    'PROPOSAL': 'AI',
    'EVIDENCE': 'EVIDENCE',
    'QUESTION': 'AI_QUESTION',
    'CODE': 'CODE',
    'DOCUMENT': 'DOCUMENTATION',
    'DECISION': 'HUMAN',       # decisions render as ! in HACI
    'DELEGATE': 'HUMAN',       # delegations render as ! in HACI
}


class Message:
    """A single MACI message."""

    _counter = 0

    def __init__(self, role, content, from_agent, refs=None,
                 authority=None, status=None, meta=None, msg_id=None):
        Message._counter += 1
        self.id = msg_id or f"m-{Message._counter:04d}"
        self.ts = datetime.now(timezone.utc).isoformat()
        self.role = role
        self.from_agent = from_agent
        self.content = content
        self.refs = refs or []
        self.authority = authority or ('sovereign' if role == 'COMMAND' else 'advisory')
        self.status = status
        self.meta = meta or {}

    def to_dict(self):
        d = {
            'maci': __version__,
            'id': self.id,
            'ts': self.ts,
            'from': self.from_agent,
            'role': self.role,
            'content': self.content,
        }
        if self.authority:
            d['authority'] = self.authority
        if self.refs:
            d['refs'] = self.refs
        if self.status:
            d['status'] = self.status
        if self.meta:
            d['meta'] = self.meta
        return d

    def __repr__(self):
        return f"<{self.role} {self.id} from={self.from_agent}>"


# ═══════════════════════════════════════════════════════════════════════
# CONVERSATION — ordered message stream with validation
# ═══════════════════════════════════════════════════════════════════════

class Conversation:
    """A MACI conversation: an ordered, validated message stream."""

    def __init__(self):
        self.messages = []
        self._ids = set()
        self._index = {}

    def add(self, msg):
        """Add a message, returns list of validation errors (empty = ok)."""
        errors = self._validate(msg)
        if not errors:
            self.messages.append(msg)
            self._ids.add(msg.id)
            self._index[msg.id] = msg
        return errors

    def _validate(self, msg):
        errors = []

        # V001: unique ID
        if msg.id in self._ids:
            errors.append(f"V001: duplicate message ID '{msg.id}'")

        # V002: valid role
        if msg.role not in VALID_ROLES:
            errors.append(f"V002: invalid role '{msg.role}'")

        # V003: valid authority
        if msg.authority and msg.authority not in VALID_AUTHORITY:
            errors.append(f"V003: invalid authority '{msg.authority}'")

        # V004: valid status
        if msg.status and msg.status not in VALID_STATUS:
            errors.append(f"V004: invalid status '{msg.status}'")

        # V005: DECISION must have refs
        if msg.role == 'DECISION' and not msg.refs:
            errors.append("V005: DECISION message must reference at least one prior message")

        # V006: DECISION must have status approved or rejected
        if msg.role == 'DECISION' and msg.status not in ('approved', 'rejected'):
            errors.append(f"V006: DECISION must have status 'approved' or 'rejected', got '{msg.status}'")

        # V007: refs must reference existing messages
        for ref in msg.refs:
            if ref not in self._ids:
                errors.append(f"V007: ref '{ref}' does not match any existing message ID")

        # V008: DELEGATE must specify scope
        if msg.role == 'DELEGATE' and not msg.content:
            errors.append("V008: DELEGATE message must specify scope in content")

        return errors

    def get_chain(self, msg_id):
        """Walk refs backwards to find the full decision chain for a message."""
        if msg_id not in self._index:
            return []
        chain = []
        visited = set()
        stack = [msg_id]
        while stack:
            mid = stack.pop()
            if mid in visited:
                continue
            visited.add(mid)
            if mid in self._index:
                msg = self._index[mid]
                chain.append(msg)
                stack.extend(msg.refs)
        # sort by position in conversation
        order = {m.id: i for i, m in enumerate(self.messages)}
        chain.sort(key=lambda m: order.get(m.id, 0))
        return chain

    def detect_cycles(self):
        """Check for cycles in the refs DAG."""
        # Kahn's algorithm for topological sort
        in_degree = defaultdict(int)
        graph = defaultdict(list)
        all_ids = set()
        for msg in self.messages:
            all_ids.add(msg.id)
            for ref in msg.refs:
                graph[ref].append(msg.id)
                in_degree[msg.id] += 1

        queue = [mid for mid in all_ids if in_degree[mid] == 0]
        count = 0
        while queue:
            mid = queue.pop(0)
            count += 1
            for child in graph[mid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        return count != len(all_ids)  # True = has cycles

    def to_json(self, indent=2):
        return json.dumps([m.to_dict() for m in self.messages],
                         indent=indent, ensure_ascii=False)

    def stats(self):
        counts = defaultdict(int)
        for m in self.messages:
            counts[m.role] += 1
        return dict(counts)

    def print_tree(self):
        """Print the conversation as a decision tree."""
        # find roots (messages with no refs)
        roots = [m for m in self.messages if not m.refs]
        printed = set()

        def print_node(msg, depth=0):
            if msg.id in printed:
                return
            printed.add(msg.id)
            indent = "  " * depth
            connector = "└─ " if depth > 0 else ""
            status_tag = f" [{msg.status}]" if msg.status else ""
            auth_tag = f" ({msg.authority})" if msg.authority != 'advisory' else ""
            print(f"  {indent}{connector}{msg.id} {msg.role}{status_tag}{auth_tag} "
                  f"from={msg.from_agent}: {msg.content[:55]}")

            # find children (messages that reference this one)
            children = [m for m in self.messages if msg.id in m.refs and m.id not in printed]
            for child in children:
                print_node(child, depth + 1)

        for root in roots:
            print_node(root)


# ═══════════════════════════════════════════════════════════════════════
# HACI ↔ MACI CONVERTER
# ═══════════════════════════════════════════════════════════════════════

def haci_blocks_to_maci(blocks, default_human="human", default_ai="ai-agent"):
    """Convert HACI parsed blocks to a MACI conversation."""
    conv = Conversation()
    prev_id = None

    for i, block in enumerate(blocks):
        haci_role = block['role']
        maci_role = HACI_TO_MACI.get(haci_role)
        if not maci_role:
            continue  # skip META, HEADING, etc.

        is_human = haci_role in ('HUMAN', 'HUMAN_QUESTION')
        agent = default_human if is_human else default_ai

        refs = [prev_id] if prev_id else []
        authority = 'sovereign' if is_human else 'advisory'
        status = None

        msg = Message(
            role=maci_role,
            content=block['content'],
            from_agent=agent,
            refs=refs,
            authority=authority,
            status=status,
            msg_id=f"h-{i+1:03d}",
        )
        conv.add(msg)
        prev_id = msg.id

    return conv


def maci_to_haci_text(conv):
    """Convert a MACI conversation to HACI-formatted text."""
    lines = ["<!-- HACI v0.1 -->", ""]
    for msg in conv.messages:
        haci_role = MACI_TO_HACI.get(msg.role, 'DOCUMENTATION')
        if msg.role == 'COMMAND':
            lines.append(f"! {msg.content.upper()}")
        elif msg.role == 'DECISION':
            ref_str = ', '.join(msg.refs) if msg.refs else ''
            lines.append(f"! {msg.status.upper()}: {msg.content} (refs: {ref_str})")
        elif msg.role == 'EVIDENCE':
            lines.append(f"> {msg.content}")
        elif msg.role == 'QUESTION':
            lines.append(f"? {msg.content}")
        elif msg.role == 'CODE':
            lines.append(f"```\n{msg.content}\n```")
        elif msg.role == 'PROPOSAL':
            lines.append(msg.content.lower() if msg.content[0:1].isupper() else msg.content)
        else:
            lines.append(msg.content)
        lines.append("")
    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════
# DEMO — a realistic multi-agent scenario
# ═══════════════════════════════════════════════════════════════════════

def run_demo():
    print("=" * 60)
    print("MACI v0.1 — Multi-Agent Decision Chain Demo")
    print("=" * 60)

    conv = Conversation()

    # Human commands the build
    m1 = Message("COMMAND", "build a task scheduler with priority and timeout",
                 "human", authority="sovereign")
    conv.add(m1)

    # Agent Alpha proposes architecture
    m2 = Message("PROPOSAL", "use a min-heap for O(log n) priority extraction",
                 "agent-alpha", refs=[m1.id])
    conv.add(m2)

    m3 = Message("PROPOSAL", "use work-stealing for thread distribution",
                 "agent-alpha", refs=[m1.id])
    conv.add(m3)

    # Agent Beta provides evidence
    m4 = Message("EVIDENCE", "benchmarks show work-stealing is 2.3x faster for uneven loads",
                 "agent-beta", refs=[m3.id])
    conv.add(m4)

    m5 = Message("EVIDENCE", "round-robin wastes 40% of idle core capacity",
                 "agent-beta", refs=[m3.id])
    conv.add(m5)

    # Agent Alpha asks a question
    m6 = Message("QUESTION", "should timeout be per-task or global?",
                 "agent-alpha", refs=[m1.id])
    conv.add(m6)

    # Human decides on both proposals
    m7 = Message("DECISION", "use work-stealing as proposed",
                 "human", refs=[m3.id, m4.id, m5.id],
                 authority="sovereign", status="approved")
    conv.add(m7)

    m8 = Message("DECISION", "use per-task timeout",
                 "human", refs=[m6.id],
                 authority="sovereign", status="approved")
    conv.add(m8)

    # Human delegates implementation authority to Alpha
    m9 = Message("DELEGATE", "implement scheduler per approved proposals m-0007 and m-0008",
                 "human", refs=[m7.id, m8.id],
                 authority="sovereign")
    conv.add(m9)

    # Agent Alpha writes code under delegated authority
    m10 = Message("CODE",
                  "class Scheduler:\n"
                  "    def __init__(self, n_workers):\n"
                  "        self.deques = [deque() for _ in range(n_workers)]",
                  "agent-alpha", refs=[m9.id],
                  authority="delegated")
    conv.add(m10)

    # Agent Beta verifies
    m11 = Message("EVIDENCE", "scheduler instantiated with 8 workers, all deques empty, ready",
                  "agent-beta", refs=[m10.id])
    conv.add(m11)

    m12 = Message("EVIDENCE", "all 47 tests passing, 0.3s total runtime",
                  "agent-beta", refs=[m10.id])
    conv.add(m12)

    # ── output ─────────────────────────────────────────────────────────
    print(f"\n  {len(conv.messages)} messages in conversation\n")

    # tree view
    print("  DECISION TREE:")
    conv.print_tree()

    # stats
    print(f"\n  ROLE DISTRIBUTION:")
    for role, count in sorted(conv.stats().items()):
        print(f"    {role:<12s} {count}")

    # cycle check
    has_cycles = conv.detect_cycles()
    print(f"\n  DAG cycle check: {'✗ CYCLES DETECTED' if has_cycles else '✓ acyclic'}")

    # chain trace: trace backwards from final evidence
    print(f"\n  CHAIN TRACE from {m12.id} (final evidence):")
    chain = conv.get_chain(m12.id)
    for msg in chain:
        refs_str = f" ← {msg.refs}" if msg.refs else " (root)"
        print(f"    {msg.id} {msg.role:<10s} {msg.from_agent:<14s}{refs_str}")

    # validation test: try to add a bad DECISION
    print(f"\n  VALIDATION TESTS:")
    bad1 = Message("DECISION", "approved without refs", "human", status="approved")
    errs = conv._validate(bad1)
    print(f"    DECISION without refs: {'✓ rejected' if errs else '✗ accepted'} → {errs}")

    bad2 = Message("DECISION", "missing status", "human", refs=[m1.id], status="maybe")
    errs = conv._validate(bad2)
    print(f"    DECISION bad status:   {'✓ rejected' if errs else '✗ accepted'} → {errs}")

    bad3 = Message("PROPOSAL", "refs ghost", "agent-x", refs=["m-9999"])
    errs = conv._validate(bad3)
    print(f"    PROPOSAL ghost ref:    {'✓ rejected' if errs else '✗ accepted'} → {errs}")

    bad4 = Message("DELEGATE", "", "human")
    errs = conv._validate(bad4)
    print(f"    DELEGATE empty scope:  {'✓ rejected' if errs else '✗ accepted'} → {errs}")

    # JSON export
    print(f"\n  JSON export: {len(conv.to_json())} bytes")

    # MACI → HACI conversion
    haci_text = maci_to_haci_text(conv)
    haci_lines = [l for l in haci_text.split('\n') if l.strip()]
    print(f"  HACI conversion: {len(haci_lines)} non-blank lines")

    print(f"\n  MACI → HACI preview:")
    for line in haci_text.split('\n')[:20]:
        if line.strip():
            print(f"    {line}")

    print(f"\n{'=' * 60}")
    print("  ✓ MACI v0.1 proof-of-concept complete")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    run_demo()
