#!/usr/bin/env python3
"""
HACI Project Validator v2.0

Breaking semantic change from v1.x:
- lowercase = human-owned
- UPPERCASE = AI-owned
- Sentence Case = context/shared

Syntax unchanged:
- Operators: ! ? >
- Prefix = outbound act
- Suffix = inbound return
- Dot = scope dive
- Folders = namespace/scope
- File stems = declared objects

v2.0 fixes from prejudice audit:
1. Swapped ownership rule.
2. Scoped canonical symbols instead of flat-only symbols.
3. Body lines after dual-edge protocol lines are preserved.
4. Project-level conversation pairing across files.
5. Strict mode for unresolved/open conversations.
6. Authority is explicit on declarations and no longer silently depends on payload case alone.
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
    resolved_object: Optional[str]
    payload: str
    owner: str
    authority: Optional[str]

@dataclass
class Conversation:
    id: str
    object: Optional[str]
    files: List[str]
    start: dict
    body: List[dict]
    returns: List[dict]
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
    files = []
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

        # HACI object slot remains v1-compatible:
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

def resolve_object(
    obj: str,
    symbols: Dict[str, dict],
    aliases: Dict[str, List[str]],
) -> Tuple[Optional[str], Optional[str]]:
    if not obj:
        return None, None

    segments = obj.split(".")
    first = segments[0]

    # Exact canonical path wins.
    if obj in symbols:
        return obj, None

    # Alias base resolution, preserving dot dive after the base.
    candidates = aliases.get(first, [])
    if len(candidates) == 1:
        base = candidates[0]
        rest = segments[1:]
        return ".".join([base] + rest) if rest else base, None

    if len(candidates) > 1:
        return None, f"AMBIGUOUS_OBJECT:{first}:{','.join(candidates)}"

    return None, f"UNDECLARED_OBJECT:{first}"

def create_line_symbol(
    obj: str,
    current_file: Path,
    root: Path,
    symbols: Dict[str, dict],
    aliases: Dict[str, List[str]],
    payload: str,
    line: int,
) -> str:
    # New declarations are scoped to the current file's folder.
    scope = scope_for_file(current_file, root)
    base = obj.split(".")[0]
    canonical = ".".join([scope, base]) if scope else base
    symbols[canonical] = {
        "symbol": canonical,
        "alias": base,
        "kind": "line",
        "file": str(current_file),
        "scope": scope,
        "meaning": payload.strip(),
        "declared_at": f"{current_file}:L{line}",
    }
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
        k = "->".join(c)
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out

def is_protocol_node(n: Node) -> bool:
    return bool(n.outbound or n.inbound)

def object_key(n: Node) -> Optional[str]:
    return n.resolved_object or n.object

def group_conversations(nodes: List[Node]) -> Tuple[List[Conversation], List[str]]:
    """
    v2 conversation grouping:
    - Protocol line starts/continues a conversation for its resolved object.
    - Body lines after a protocol line attach even if the opener had both outbound+inbound.
    - Project-level pairing: returns for the same resolved object attach across files.
    - A new outbound for the same object closes the previous open event and starts another.
    """
    warnings: List[str] = []
    conversations: List[Conversation] = []
    open_by_object: Dict[str, Conversation] = {}
    last_conversation_by_file: Dict[str, Optional[Conversation]] = {}

    def close(conv: Conversation):
        conversations.append(conv)

    for n in nodes:
        if n.owner in {"structure", "code"}:
            continue

        nd = asdict(n)
        key = object_key(n)

        if is_protocol_node(n):
            # Return-only line closes or attaches to matching open conversation.
            if n.inbound and not n.outbound and key and key in open_by_object:
                conv = open_by_object.pop(key)
                conv.returns.append(nd)
                if n.file not in conv.files:
                    conv.files.append(n.file)
                close(conv)
                last_conversation_by_file[n.file] = conv
                continue

            # New outbound line starts a new conversation.
            if n.outbound:
                if key and key in open_by_object:
                    old = open_by_object.pop(key)
                    old.diagnostics.append("OPEN_REPLACED_BY_NEW_OUTBOUND")
                    warnings.append(f"{old.files[0]}:L{old.start['line']}:OPEN_REPLACED_BY_NEW_OUTBOUND:{old.id}")
                    close(old)

                cid = f"{Path(n.file).name}:L{n.line}:{key or 'none'}"
                conv = Conversation(
                    id=cid,
                    object=key,
                    files=[n.file],
                    start=nd,
                    body=[],
                    returns=[],
                    diagnostics=[],
                )

                # A suffix on the opener is a return marker, but the conversation remains body-attachable.
                if n.inbound:
                    conv.returns.append(nd)

                if key:
                    open_by_object[key] = conv
                else:
                    # Objectless protocol event can still collect local body.
                    open_by_object[cid] = conv
                    key = cid

                last_conversation_by_file[n.file] = conv
                continue

            # Suffix-only return without open conversation becomes standalone return conversation.
            cid = f"{Path(n.file).name}:L{n.line}:{key or 'return'}"
            conv = Conversation(
                id=cid,
                object=key,
                files=[n.file],
                start=nd,
                body=[],
                returns=[nd],
                diagnostics=["RETURN_WITHOUT_OPEN_REQUEST"],
            )
            warnings.append(f"{n.file}:L{n.line}:RETURN_WITHOUT_OPEN_REQUEST:{cid}")
            conversations.append(conv)
            last_conversation_by_file[n.file] = conv
            continue

        # Plain line attaches to the last conversation in the same file if it is still open.
        conv = last_conversation_by_file.get(n.file)
        if conv and conv in open_by_object.values():
            conv.body.append(nd)
            if n.file not in conv.files:
                conv.files.append(n.file)

    # Close leftovers.
    for conv in list(open_by_object.values()):
        conv.diagnostics.append("OPEN_CONVERSATION")
        warnings.append(f"{conv.files[0]}:L{conv.start['line']}:OPEN_CONVERSATION:{conv.id}")
        conversations.append(conv)

    # De-duplicate possible duplicate objectless closures.
    seen_ids = set()
    unique = []
    for c in conversations:
        if c.id not in seen_ids:
            seen_ids.add(c.id)
            unique.append(c)
    return unique, warnings

def validate_conversations(conversations: List[Conversation], strict: bool) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    for c in conversations:
        start = c.start
        outbound = start.get("outbound")

        if not start.get("payload"):
            errors.append(f"{c.files[0]}:L{start['line']}:CONVERSATION_EMPTY_PAYLOAD:{c.id}")

        is_open = "OPEN_CONVERSATION" in c.diagnostics
        if is_open:
            msg = f"{c.files[0]}:L{start['line']}:OPEN_CONVERSATION:{c.id}"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)

        if outbound == "ask" and not c.returns and not c.body:
            msg = f"{c.files[0]}:L{start['line']}:ASK_WITHOUT_RETURN:{c.id}"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)

        if outbound == "declare" and not c.returns and not c.body:
            warnings.append(f"{c.files[0]}:L{start['line']}:DECLARE_WITHOUT_RETURN:{c.id}")

    return errors, warnings

def validate_project(root: Path, strict: bool = False) -> ProjectResult:
    root = root.resolve()
    errors: List[str] = []
    warnings: List[str] = []

    files = iter_haci_files(root)
    raw_nodes = []
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
        authority = None

        if rn["outbound"] == "declare":
            authority = owner

        if obj:
            resolved, err = resolve_object(obj, symbols, aliases)
            if err and rn["outbound"] == "declare":
                # Forward pass may add declared object without new syntax.
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
                    "kind": "line",
                    "file": node.file,
                    "scope": scope_for_file(current_file, root),
                })
                symbols[resolved]["meaning"] = meaning
                symbols[resolved]["declared_at"] = f"{node.file}:L{node.line}"
                symbols[resolved]["authority"] = authority

            # v2: declaration authority is explicit and reported.
            # Lowercase human declarations become immutable. AI declarations are not human authority anchors.
            if authority == "human":
                immutable[resolved] = meaning
            elif authority == "ai":
                warnings.append(f"{node.file}:L{node.line}:AI_DECLARATION_NOT_HUMAN_AUTHORITY:{resolved}")

        if resolved:
            dep_base = ".".join(resolved.split(".")[:2]) if len(resolved.split(".")) > 1 else resolved
            # edge to the resolved declared base, not every dotted dive leaf
            target = dep_base if dep_base in symbols else resolved.split(".")[0]
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
    return errors

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="HACI Project Validator v2.0")
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
