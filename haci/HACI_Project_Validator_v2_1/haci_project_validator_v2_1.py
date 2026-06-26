#!/usr/bin/env python3
"""
HACI Project Validator v2.1 — Conversation Engine Patch

Language base:
- HACI v2.0 semantics are retained.
- lowercase = human-owned
- UPPERCASE = AI-owned
- Sentence Case = context/shared
- Syntax unchanged: ! ? >
- No new operators. No new punctuation.

v2.1 fixes:
1. Dual-edge lines are complete by default.
2. Body lines after dual-edge lines attach without making the event unresolved.
3. Declarations do not remain open unless body-attached, and even then they are not unresolved protocol asks.
4. Cross-file conversation pairing is two-pass and order-independent.
5. Warnings/errors are deduplicated.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, Iterable
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
    resolved_object: Optional[str]
    payload: str
    owner: str
    authority: Optional[str]

@dataclass
class Conversation:
    id: str
    kind: str
    object: Optional[str]
    files: List[str]
    start: dict
    body: List[dict]
    returns: List[dict]
    complete: bool
    unresolved: bool
    diagnostics: List[str]

@dataclass
class ProjectResult:
    ok: bool
    strict: bool
    root: str
    symbols: Dict[str, dict]
    aliases: Dict[str, List[str]]
    edges: List[dict]
    cycles: List[List[str]]
    conversations: List[dict]
    errors: List[str]
    warnings: List[str]
    nodes: List[dict]

def unique(items: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out

def strip_order_prefix(segment: str) -> str:
    return re.sub(r"^\d+[_-]?", "", segment).lower()

def classify_owner_v2(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "unknown"
    upper = sum(1 for c in letters if c.isupper())
    lower = sum(1 for c in letters if c.islower())
    if lower and not upper:
        return "human"
    if upper and not lower:
        return "ai"
    if text[:1].isupper():
        return "context"
    return "mixed"

def split_haci_line(line: str) -> Tuple[Optional[str], str, Optional[str]]:
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

def iter_haci_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for p in root.rglob("*.haci"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        files.append(p)
    return sorted(files, key=lambda x: str(x))

def canonical_for_file(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    parts = [strip_order_prefix(p) for p in rel.parts[:-1]]
    stem = strip_order_prefix(path.stem)
    parts.append(stem)
    return ".".join([p for p in parts if p])

def scope_for_file(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    parts = [strip_order_prefix(p) for p in rel.parts[:-1]]
    return ".".join([p for p in parts if p])

def parse_file_raw(path: Path) -> List[dict]:
    raw_nodes: List[dict] = []
    in_code = False
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.rstrip("\n")
        stripped = raw.strip()
        if not stripped:
            continue

        if stripped.startswith("```"):
            in_code = not in_code
            raw_nodes.append({
                "file": str(path), "line": line_no, "raw": raw,
                "outbound": None, "inbound": None, "object": None,
                "payload": stripped, "owner": "code",
            })
            continue

        if in_code:
            raw_nodes.append({
                "file": str(path), "line": line_no, "raw": raw,
                "outbound": None, "inbound": None, "object": None,
                "payload": raw, "owner": "code",
            })
            continue

        if stripped.startswith("#"):
            raw_nodes.append({
                "file": str(path), "line": line_no, "raw": raw,
                "outbound": None, "inbound": None, "object": None,
                "payload": stripped, "owner": "structure",
            })
            continue

        prefix, body, suffix = split_haci_line(raw)
        outbound = OPERATORS.get(prefix) if prefix else None
        inbound = OPERATORS.get(suffix) if suffix else None
        obj = None
        payload = body

        # HACI object slot:
        # only operator-bearing lines consume first token as object address.
        if outbound or inbound:
            parts = body.split(None, 1)
            if parts and is_symbol_token(parts[0]):
                obj = parts[0]
                payload = parts[1] if len(parts) > 1 else ""

        raw_nodes.append({
            "file": str(path), "line": line_no, "raw": raw,
            "outbound": outbound, "inbound": inbound, "object": obj,
            "payload": payload, "owner": classify_owner_v2(payload if payload else body),
        })
    return raw_nodes

def add_alias(aliases: Dict[str, List[str]], alias: str, canonical: str) -> None:
    aliases.setdefault(alias, [])
    if canonical not in aliases[alias]:
        aliases[alias].append(canonical)

def build_file_symbols(files: List[Path], root: Path, errors: List[str]) -> Tuple[Dict[str, dict], Dict[str, List[str]]]:
    symbols: Dict[str, dict] = {}
    aliases: Dict[str, List[str]] = {}

    for p in files:
        canonical = canonical_for_file(p, root)
        stem = strip_order_prefix(p.stem)

        if canonical in symbols:
            errors.append(f"DUPLICATE_CANONICAL_SYMBOL:{canonical}:{symbols[canonical]['file']}:{p}")
            continue

        symbols[canonical] = {
            "symbol": canonical,
            "alias": stem,
            "kind": "file",
            "file": str(p),
            "scope": scope_for_file(p, root),
        }
        add_alias(aliases, stem, canonical)
        add_alias(aliases, canonical, canonical)

    return symbols, aliases

def current_file_canonical_for_object(obj: str, current_file: Path, root: Path) -> Optional[str]:
    current = canonical_for_file(current_file, root)
    stem = strip_order_prefix(current_file.stem)
    if not obj:
        return None
    base = obj.split(".")[0]
    if base == stem:
        rest = obj.split(".")[1:]
        return ".".join([current] + rest) if rest else current
    return None

def resolve_object(
    obj: Optional[str],
    symbols: Dict[str, dict],
    aliases: Dict[str, List[str]],
    current_file: Optional[Path] = None,
    root: Optional[Path] = None,
) -> Tuple[Optional[str], Optional[str]]:
    if not obj:
        return None, None

    # Exact canonical path wins.
    if obj in symbols:
        return obj, None

    # Current file's own stem wins inside its own file, even if alias is globally ambiguous.
    if current_file and root:
        local = current_file_canonical_for_object(obj, current_file, root)
        if local:
            return local, None

    segments = obj.split(".")
    first = segments[0]
    candidates = aliases.get(first, [])

    if len(candidates) == 1:
        base = candidates[0]
        rest = segments[1:]
        return ".".join([base] + rest) if rest else base, None

    if len(candidates) > 1:
        return None, f"AMBIGUOUS_OBJECT:{first}:{','.join(candidates)}"

    return None, f"UNDECLARED_OBJECT:{first}"

def nearest_declared_prefix(path: str, symbols: Dict[str, dict]) -> Optional[str]:
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in symbols:
            return candidate
    return None

def create_line_symbol(
    obj: str,
    current_file: Path,
    root: Path,
    symbols: Dict[str, dict],
    aliases: Dict[str, List[str]],
    payload: str,
    line: int,
) -> str:
    local = current_file_canonical_for_object(obj, current_file, root)
    if local:
        canonical = local
    else:
        scope = scope_for_file(current_file, root)
        base = obj.split(".")[0]
        canonical = ".".join([scope, base]) if scope else base

    base = obj.split(".")[0]
    symbols.setdefault(canonical, {
        "symbol": canonical,
        "alias": base,
        "kind": "line",
        "file": str(current_file),
        "scope": scope_for_file(current_file, root),
    })
    symbols[canonical]["meaning"] = payload.strip()
    symbols[canonical]["declared_at"] = f"{current_file}:L{line}"
    add_alias(aliases, base, canonical)
    add_alias(aliases, canonical, canonical)
    return canonical

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
        key = "->".join(c)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out

def is_protocol_node(n: Node) -> bool:
    return bool(n.outbound or n.inbound)

def object_key(n: Node) -> Optional[str]:
    return n.resolved_object or n.object

def node_to_dict(n: Node) -> dict:
    return asdict(n)

def make_conversation(n: Node, kind: str, complete: bool, unresolved: bool) -> Conversation:
    key = object_key(n)
    return Conversation(
        id=f"{Path(n.file).name}:L{n.line}:{key or 'none'}",
        kind=kind,
        object=key,
        files=[n.file],
        start=node_to_dict(n),
        body=[],
        returns=[node_to_dict(n)] if n.inbound else [],
        complete=complete,
        unresolved=unresolved,
        diagnostics=[],
    )

def group_conversations(nodes: List[Node]) -> Tuple[List[Conversation], List[str]]:
    """
    v2.1 conversation engine:
    - Declarations are complete symbol events by default.
    - Ask/observe outbound with inbound is complete by default.
    - Ask/observe outbound without inbound is open until paired with a return.
    - Body after any protocol opener attaches to that event until the next protocol line in the same file.
    - Return-only nodes pair in a second pass by resolved object, independent of file order.
    """
    warnings: List[str] = []
    conversations: List[Conversation] = []
    return_only_nodes: List[Node] = []
    last_attachable_by_file: Dict[str, Optional[Conversation]] = {}

    for n in nodes:
        if n.owner in {"structure", "code"}:
            continue

        if is_protocol_node(n):
            key = object_key(n)

            # Return-only line; defer pairing to second pass.
            if n.inbound and not n.outbound:
                return_only_nodes.append(n)
                last_attachable_by_file[n.file] = None
                continue

            if n.outbound == "declare":
                # Declarations are not unresolved conversations.
                conv = make_conversation(n, "declaration", complete=True, unresolved=False)
                conversations.append(conv)
                last_attachable_by_file[n.file] = conv
                continue

            if n.outbound in {"ask", "observe"}:
                dual = bool(n.inbound)
                conv = make_conversation(n, "conversation", complete=dual, unresolved=not dual)
                conversations.append(conv)
                last_attachable_by_file[n.file] = conv
                continue

            # Defensive fallback.
            conv = make_conversation(n, "event", complete=bool(n.inbound), unresolved=not bool(n.inbound))
            conversations.append(conv)
            last_attachable_by_file[n.file] = conv
            continue

        # Plain body attaches to the most recent protocol event in the same file.
        conv = last_attachable_by_file.get(n.file)
        if conv:
            conv.body.append(node_to_dict(n))

    # Second pass: pair return-only nodes to unresolved matching conversations by object.
    unresolved_by_object: Dict[str, List[Conversation]] = {}
    for conv in conversations:
        if conv.unresolved and conv.object:
            unresolved_by_object.setdefault(conv.object, []).append(conv)

    for ret in return_only_nodes:
        key = object_key(ret)
        nd = node_to_dict(ret)

        if key and key in unresolved_by_object and unresolved_by_object[key]:
            conv = unresolved_by_object[key].pop(0)
            conv.returns.append(nd)
            conv.complete = True
            conv.unresolved = False
            if ret.file not in conv.files:
                conv.files.append(ret.file)
            continue

        # Unmatched return is its own complete return event with warning.
        conv = make_conversation(ret, "return", complete=True, unresolved=False)
        conv.diagnostics.append("RETURN_WITHOUT_OPEN_REQUEST")
        conversations.append(conv)
        warnings.append(f"{ret.file}:L{ret.line}:RETURN_WITHOUT_OPEN_REQUEST:{conv.id}")

    # Mark remaining unresolved after pairing.
    for convs in unresolved_by_object.values():
        for conv in convs:
            conv.diagnostics.append("OPEN_CONVERSATION")
            warnings.append(f"{conv.files[0]}:L{conv.start['line']}:OPEN_CONVERSATION:{conv.id}")

    return conversations, unique(warnings)

def validate_conversations(conversations: List[Conversation], strict: bool) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    for conv in conversations:
        start = conv.start

        if not start.get("payload"):
            errors.append(f"{conv.files[0]}:L{start['line']}:CONVERSATION_EMPTY_PAYLOAD:{conv.id}")

        if conv.unresolved:
            msg = f"{conv.files[0]}:L{start['line']}:OPEN_CONVERSATION:{conv.id}"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)

        if conv.kind == "conversation" and start.get("outbound") == "ask" and not conv.returns:
            msg = f"{conv.files[0]}:L{start['line']}:ASK_WITHOUT_RETURN:{conv.id}"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)

    return unique(errors), unique(warnings)

def validate_project(root: Path, strict: bool = False) -> ProjectResult:
    root = root.resolve()
    errors: List[str] = []
    warnings: List[str] = []

    files = iter_haci_files(root)
    raw_nodes: List[dict] = []
    for f in files:
        raw_nodes.extend(parse_file_raw(f))

    symbols, aliases = build_file_symbols(files, root, errors)
    immutable: Dict[str, str] = {}
    nodes: List[Node] = []
    edges: List[Tuple[str, str]] = []
    edge_records: List[dict] = []

    for rn in raw_nodes:
        owner = rn["owner"]
        if owner in {"structure", "code"}:
            nodes.append(Node(**rn, resolved_object=None, authority=None))
            continue

        current_file = Path(rn["file"])
        current_symbol = canonical_for_file(current_file, root)
        obj = rn["object"]
        resolved = None
        authority = owner if rn["outbound"] == "declare" else None

        if obj:
            resolved, err = resolve_object(obj, symbols, aliases, current_file, root)
            if err and rn["outbound"] == "declare":
                resolved = create_line_symbol(obj, current_file, root, symbols, aliases, rn["payload"], rn["line"])
                err = None
            elif err:
                errors.append(f"{rn['file']}:L{rn['line']}:{err}")

        node = Node(
            file=rn["file"], line=rn["line"], raw=rn["raw"],
            outbound=rn["outbound"], inbound=rn["inbound"],
            object=obj, resolved_object=resolved,
            payload=rn["payload"], owner=owner, authority=authority,
        )
        nodes.append(node)

        if (node.outbound or node.inbound) and not node.payload:
            errors.append(f"{node.file}:L{node.line}:EMPTY_PAYLOAD")

        if node.outbound == "declare" and resolved:
            meaning = node.payload.strip()
            existing = symbols.get(resolved, {})

            if resolved in immutable and immutable[resolved] != meaning:
                errors.append(f"{node.file}:L{node.line}:AUTHORITY_MUTATION:{resolved}")

            if existing.get("meaning") and existing["meaning"] != meaning:
                errors.append(f"{node.file}:L{node.line}:DUPLICATE_OR_CONFLICTING_SYMBOL:{resolved}")
            else:
                symbols.setdefault(resolved, {
                    "symbol": resolved,
                    "alias": obj.split(".")[0] if obj else None,
                    "kind": "line",
                    "file": node.file,
                    "scope": scope_for_file(current_file, root),
                })
                symbols[resolved]["meaning"] = meaning
                symbols[resolved]["declared_at"] = f"{node.file}:L{node.line}"
                symbols[resolved]["authority"] = authority

            if authority == "human":
                immutable[resolved] = meaning
            elif authority == "ai":
                warnings.append(f"{node.file}:L{node.line}:AI_DECLARATION_NOT_HUMAN_AUTHORITY:{resolved}")

        if resolved:
            target = nearest_declared_prefix(resolved, symbols) or resolved
            if current_symbol != target:
                edges.append((current_symbol, target))
                edge_records.append({
                    "from": current_symbol,
                    "to": target,
                    "file": node.file,
                    "line": node.line,
                    "raw": node.raw,
                })

        if owner == "mixed" and (node.outbound or node.inbound):
            warnings.append(f"{node.file}:L{node.line}:MIXED_CASE_OWNER")

    cycles = detect_cycles(edges)
    for c in cycles:
        errors.append("DEPENDENCY_CYCLE:" + "->".join(c))

    conversations, conv_warnings = group_conversations(nodes)
    warnings.extend(conv_warnings)
    conv_errors, conv_warnings_2 = validate_conversations(conversations, strict)
    errors.extend(conv_errors)
    warnings.extend(conv_warnings_2)

    errors = unique(errors)
    warnings = unique(warnings)

    return ProjectResult(
        ok=not errors,
        strict=strict,
        root=str(root),
        symbols=symbols,
        aliases=aliases,
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
    return unique(errors)

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="HACI Project Validator v2.1")
    parser.add_argument("root")
    parser.add_argument("--strict", action="store_true", help="open/unresolved conversations fail instead of warn")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    result = validate_project(Path(args.root), strict=args.strict)
    data = json.dumps(asdict(result), indent=2)
    if args.out:
        Path(args.out).write_text(data, encoding="utf-8")
    print(data)
    return 0 if result.ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
