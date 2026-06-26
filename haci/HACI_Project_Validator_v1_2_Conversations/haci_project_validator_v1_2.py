#!/usr/bin/env python3
"""
HACI Project Validator v1.2 — Conversation Rules

Frozen base:
- HACI v1.0 syntax remains unchanged.
- Operators remain: ! ? >
- Prefix = outbound act.
- Suffix = inbound return.
- File/folder scope rules remain.

v1.2 fix:
- Parser emits nodes.
- Validator groups nodes into conversation events.
- Dependency/cycle validation remains project-level.
- Conversation validation catches protocol failures that raw node validation cannot.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
import argparse
import json
import re

OPERATORS = {"!": "declare", "?": "ask", ">": "observe"}
SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules"}

@dataclass
class Node:
    file: str
    line: int
    raw: str
    outbound: Optional[str]
    inbound: Optional[str]
    object: Optional[str]
    payload: str
    owner: str

@dataclass
class Conversation:
    id: str
    file: str
    start_line: int
    object: Optional[str]
    opener: dict
    body: List[dict]
    closer: Optional[dict]
    diagnostics: List[str]

@dataclass
class ProjectResult:
    ok: bool
    root: str
    symbols: Dict[str, dict]
    edges: List[dict]
    cycles: List[List[str]]
    conversations: List[dict]
    errors: List[str]
    warnings: List[str]
    nodes: List[dict]

def classify_owner(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "unknown"
    upper = sum(1 for c in letters if c.isupper())
    lower = sum(1 for c in letters if c.islower())
    if upper and not lower:
        return "human"
    if lower and not upper:
        return "machine"
    if text[:1].isupper():
        return "context"
    return "mixed"

def split_haci_line(line: str):
    s = line.strip()
    if not s:
        return None, "", None
    prefix = s[0] if s[0] in OPERATORS else None
    if prefix:
        s = s[1:].strip()
    suffix = s[-1] if s and s[-1] in OPERATORS else None
    if suffix:
        s = s[:-1].strip()
    return prefix, s, suffix

def is_symbol_token(token: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*", token))

def file_symbol(path: Path) -> Optional[str]:
    stem = path.stem
    if re.fullmatch(r"[a-z][a-z0-9]*", stem):
        return stem
    return None

def parse_file(path: Path) -> List[Node]:
    nodes: List[Node] = []
    in_code = False
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        raw = line.rstrip("\n")
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("```"):
            in_code = not in_code
            nodes.append(Node(str(path), line_no, raw, None, None, None, stripped, "code"))
            continue
        if in_code:
            nodes.append(Node(str(path), line_no, raw, None, None, None, raw, "code"))
            continue
        if stripped.startswith("#"):
            nodes.append(Node(str(path), line_no, raw, None, None, None, stripped, "structure"))
            continue

        prefix, body, suffix = split_haci_line(raw)
        outbound = OPERATORS.get(prefix) if prefix else None
        inbound = OPERATORS.get(suffix) if suffix else None
        obj = None
        payload = body

        # v1 frozen object-slot rule.
        if outbound or inbound:
            parts = body.split(None, 1)
            if parts and is_symbol_token(parts[0]):
                obj = parts[0]
                payload = parts[1] if len(parts) > 1 else ""

        nodes.append(Node(
            file=str(path),
            line=line_no,
            raw=raw,
            outbound=outbound,
            inbound=inbound,
            object=obj,
            payload=payload,
            owner=classify_owner(payload if payload else body),
        ))
    return nodes

def iter_haci_files(root: Path) -> List[Path]:
    files = []
    for p in root.rglob("*.haci"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        files.append(p)
    return sorted(files, key=lambda x: str(x))

def build_file_symbols(files: List[Path], errors: List[str]) -> Dict[str, dict]:
    symbols: Dict[str, dict] = {}
    for p in files:
        sym = file_symbol(p)
        if not sym:
            continue
        if sym in symbols:
            errors.append(f"DUPLICATE_FILE_SYMBOL:{sym}:{symbols[sym]['file']}:{p}")
            continue
        symbols[sym] = {
            "symbol": sym,
            "kind": "file",
            "file": str(p),
            "scope": str(p.parent),
        }
    return symbols

def detect_cycles(edges: List[Tuple[str, str]]) -> List[List[str]]:
    graph: Dict[str, List[str]] = {}
    for a, b in edges:
        graph.setdefault(a, []).append(b)
    cycles: List[List[str]] = []
    visiting: List[str] = []
    visited: Set[str] = set()

    def dfs(n: str):
        if n in visiting:
            i = visiting.index(n)
            cycles.append(visiting[i:] + [n])
            return
        if n in visited:
            return
        visiting.append(n)
        for nxt in graph.get(n, []):
            dfs(nxt)
        visiting.pop()
        visited.add(n)

    for n in list(graph):
        dfs(n)

    seen = set()
    out = []
    for c in cycles:
        k = "->".join(c)
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out

def node_dict(n: Node) -> dict:
    return asdict(n)

def is_protocol_node(n: Node) -> bool:
    return bool(n.outbound or n.inbound)

def group_conversations(nodes: List[Node]) -> Tuple[List[Conversation], List[str]]:
    """
    Conversation grouping rule v1.2:
    - A protocol node opens a conversation event.
    - Immediately following non-protocol context/machine nodes attach as body.
    - A later protocol node with same file+object closes prior only if it has no outbound and has inbound.
    - Otherwise it starts a new conversation.
    - Single-line dual operator nodes are self-closed.
    """
    conversations: List[Conversation] = []
    warnings: List[str] = []

    by_file: Dict[str, List[Node]] = {}
    for n in nodes:
        by_file.setdefault(n.file, []).append(n)

    for file, file_nodes in by_file.items():
        current: Optional[Conversation] = None

        for n in file_nodes:
            if n.owner in {"structure", "code"}:
                continue

            nd = node_dict(n)

            if is_protocol_node(n):
                # Close-only return node: no outbound, inbound present.
                if current and n.inbound and not n.outbound and n.object == current.object:
                    current.closer = nd
                    conversations.append(current)
                    current = None
                    continue

                # New protocol node starts a new conversation.
                if current:
                    warnings.append(f"{current.file}:L{current.start_line}:OPEN_CONVERSATION")
                    conversations.append(current)

                cid = f"{Path(file).name}:{n.line}"
                current = Conversation(
                    id=cid,
                    file=file,
                    start_line=n.line,
                    object=n.object,
                    opener=nd,
                    body=[],
                    closer=None,
                    diagnostics=[],
                )

                # Dual-edge line is already a complete conversation.
                if n.outbound and n.inbound:
                    conversations.append(current)
                    current = None
                continue

            # Plain nodes attach to open conversation body.
            if current:
                current.body.append(nd)

        if current:
            warnings.append(f"{current.file}:L{current.start_line}:OPEN_CONVERSATION")
            conversations.append(current)

    return conversations, warnings

def validate_conversations(conversations: List[Conversation]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    for c in conversations:
        opener = c.opener
        outbound = opener.get("outbound")
        inbound = opener.get("inbound")

        # A protocol event must have payload unless it is an explicit closer.
        if not opener.get("payload"):
            errors.append(f"{c.file}:L{c.start_line}:CONVERSATION_EMPTY_PAYLOAD:{c.id}")

        # Ask conversations should either have inbound on same line, a closer, or body.
        if outbound == "ask" and not inbound and not c.closer and not c.body:
            warnings.append(f"{c.file}:L{c.start_line}:ASK_WITHOUT_RETURN:{c.id}")

        # Declare conversations without inbound/body are allowed but open.
        if outbound == "declare" and not inbound and not c.closer and not c.body:
            warnings.append(f"{c.file}:L{c.start_line}:DECLARE_WITHOUT_RETURN:{c.id}")

        # Observe as outbound should have evidence payload; empty checked above.
        if outbound == "observe" and opener.get("owner") == "unknown":
            warnings.append(f"{c.file}:L{c.start_line}:OBSERVE_UNKNOWN_OWNER:{c.id}")

    return errors, warnings

def validate_project(root: Path) -> ProjectResult:
    root = root.resolve()
    errors: List[str] = []
    warnings: List[str] = []

    files = iter_haci_files(root)
    nodes: List[Node] = []
    for f in files:
        nodes.extend(parse_file(f))

    symbols = build_file_symbols(files, errors)
    immutable: Dict[str, str] = {}
    edges: List[Tuple[str, str]] = []
    edge_records: List[dict] = []

    for n in nodes:
        if n.owner in {"structure", "code"}:
            continue

        if (n.outbound or n.inbound) and not n.payload:
            errors.append(f"{n.file}:L{n.line}:EMPTY_PAYLOAD")

        current = file_symbol(Path(n.file)) or str(Path(n.file).relative_to(root))

        if n.outbound == "declare" and n.object:
            base = n.object.split(".")[0]
            meaning = n.payload.strip()

            if base in immutable and immutable[base] != meaning:
                errors.append(f"{n.file}:L{n.line}:AUTHORITY_MUTATION:{base}")

            if base in symbols and symbols[base].get("meaning") and symbols[base]["meaning"] != meaning:
                errors.append(f"{n.file}:L{n.line}:DUPLICATE_OR_CONFLICTING_SYMBOL:{base}")
            else:
                symbols.setdefault(base, {
                    "symbol": base,
                    "kind": "line",
                    "file": n.file,
                    "scope": str(Path(n.file).parent),
                })
                symbols[base]["meaning"] = meaning
                symbols[base]["declared_at"] = f"{n.file}:L{n.line}"

            if n.owner == "human":
                immutable[base] = meaning

        if n.object:
            base = n.object.split(".")[0]
            if base not in symbols:
                errors.append(f"{n.file}:L{n.line}:UNDECLARED_OBJECT:{base}")
            elif current != base:
                edges.append((current, base))
                edge_records.append({
                    "from": current,
                    "to": base,
                    "file": n.file,
                    "line": n.line,
                    "raw": n.raw,
                })

        if n.owner == "mixed" and (n.outbound or n.inbound):
            warnings.append(f"{n.file}:L{n.line}:MIXED_CASE_OWNER")

    cycles = detect_cycles(edges)
    for c in cycles:
        errors.append("DEPENDENCY_CYCLE:" + "->".join(c))

    conversations, conv_warnings = group_conversations(nodes)
    warnings.extend(conv_warnings)
    conv_errors, conv_warnings_2 = validate_conversations(conversations)
    errors.extend(conv_errors)
    warnings.extend(conv_warnings_2)

    return ProjectResult(
        ok=not errors,
        root=str(root),
        symbols=symbols,
        edges=edge_records,
        cycles=cycles,
        conversations=[asdict(c) for c in conversations],
        errors=errors,
        warnings=warnings,
        nodes=[asdict(n) for n in nodes],
    )

def validate_merge(og: Dict[str, str], fss: Dict[str, str], bss_requires: List[str], protected: Optional[List[str]] = None) -> List[str]:
    protected = protected or ["ROOT"]
    errors: List[str] = []
    for k, v in fss.items():
        if k in og and og[k] != v:
            errors.append(f"FSS_CONFLICT:{k}")
        if k in protected and og.get(k) != v:
            errors.append(f"AUTHORITY_MUTATION:{k}")
    merged = dict(og)
    merged.update(fss)
    for req in bss_requires:
        if req not in merged:
            errors.append(f"BSS_MISSING:{req}")
    return errors

def main(argv=None):
    parser = argparse.ArgumentParser(description="HACI Project Validator v1.2 Conversation Rules")
    parser.add_argument("root")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    result = validate_project(Path(args.root))
    data = json.dumps(asdict(result), indent=2)
    if args.out:
        Path(args.out).write_text(data, encoding="utf-8")
    print(data)
    return 0 if result.ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
