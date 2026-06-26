#!/usr/bin/env python3
"""
HACI Project Validator v1.1

Target:
- HACI v1.0 frozen syntax.
- Project-level validation added without changing HACI syntax.

Adds:
- Folder scan
- Global symbol table from file stems + line declarations
- Cross-file object resolution
- Dependency edge extraction
- Cycle detection wired into project validation
- OG/FSS/BSS/OG' merge scenario validation
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
import argparse
import json
import re
import sys

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
class ProjectResult:
    ok: bool
    root: str
    symbols: Dict[str, dict]
    edges: List[dict]
    cycles: List[List[str]]
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

        # HACI v1 frozen rule:
        # first token becomes object only on operator-bearing protocol lines
        if outbound or inbound:
            parts = body.split(None, 1)
            if parts and is_symbol_token(parts[0]):
                obj = parts[0]
                payload = parts[1] if len(parts) > 1 else ""

        owner = classify_owner(payload if payload else body)
        nodes.append(Node(str(path), line_no, raw, outbound, inbound, obj, payload, owner))
    return nodes

def iter_haci_files(root: Path) -> List[Path]:
    files = []
    for p in root.rglob("*.haci"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        files.append(p)
    return sorted(files, key=lambda x: str(x))

def file_symbol(path: Path) -> Optional[str]:
    stem = path.stem
    if re.fullmatch(r"[a-z][a-z0-9]*", stem):
        return stem
    return None

def scope_order(path: Path, root: Path) -> Tuple:
    rel = path.relative_to(root)
    return tuple(str(part) for part in rel.parts)

def build_file_symbol_table(files: List[Path], root: Path, errors: List[str]) -> Dict[str, dict]:
    symbols: Dict[str, dict] = {}
    for p in files:
        sym = file_symbol(p)
        if not sym:
            continue
        if sym in symbols:
            prev = symbols[sym]["file"]
            # v1.1: duplicate file-stem symbols are an error unless exact same path impossible.
            errors.append(f"DUPLICATE_FILE_SYMBOL:{sym}:{prev}:{p}")
            continue
        symbols[sym] = {
            "symbol": sym,
            "kind": "file",
            "file": str(p),
            "scope": str(p.parent),
            "order": scope_order(p, root),
        }
    return symbols

def detect_cycles(edges: List[Tuple[str, str]]) -> List[List[str]]:
    graph: Dict[str, List[str]] = {}
    for a, b in edges:
        graph.setdefault(a, []).append(b)

    cycles: List[List[str]] = []
    visiting: List[str] = []
    visited: Set[str] = set()

    def dfs(node: str):
        if node in visiting:
            i = visiting.index(node)
            cycles.append(visiting[i:] + [node])
            return
        if node in visited:
            return
        visiting.append(node)
        for nxt in graph.get(node, []):
            dfs(nxt)
        visiting.pop()
        visited.add(node)

    for node in list(graph):
        dfs(node)
    # de-dupe simple cycle strings
    seen = set()
    unique = []
    for c in cycles:
        key = "->".join(c)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique

def validate_project(root: Path) -> ProjectResult:
    root = root.resolve()
    errors: List[str] = []
    warnings: List[str] = []
    files = iter_haci_files(root)
    nodes: List[Node] = []
    for f in files:
        nodes.extend(parse_file(f))

    symbols = build_file_symbol_table(files, root, errors)
    immutable: Dict[str, str] = {}
    edges: List[Tuple[str, str]] = []
    edge_records: List[dict] = []

    # line declarations and references
    for node in nodes:
        if node.owner in {"structure", "code"}:
            continue

        if (node.outbound or node.inbound) and not node.payload:
            errors.append(f"{node.file}:L{node.line}:EMPTY_PAYLOAD")

        current_file_sym = file_symbol(Path(node.file))
        current = current_file_sym or str(Path(node.file).relative_to(root))

        if node.outbound == "declare" and node.object:
            base = node.object.split(".")[0]
            meaning = node.payload.strip()

            if base in immutable and immutable[base] != meaning:
                errors.append(f"{node.file}:L{node.line}:AUTHORITY_MUTATION:{base}")

            if base in symbols and symbols[base].get("meaning") and symbols[base]["meaning"] != meaning:
                errors.append(f"{node.file}:L{node.line}:DUPLICATE_OR_CONFLICTING_SYMBOL:{base}")
            else:
                symbols.setdefault(base, {
                    "symbol": base,
                    "kind": "line",
                    "file": node.file,
                    "scope": str(Path(node.file).parent),
                })
                symbols[base]["meaning"] = meaning
                symbols[base]["declared_at"] = f"{node.file}:L{node.line}"

            if node.owner == "human":
                immutable[base] = meaning

        if node.object:
            base = node.object.split(".")[0]
            if base not in symbols:
                errors.append(f"{node.file}:L{node.line}:UNDECLARED_OBJECT:{base}")
            else:
                if current != base:
                    edges.append((current, base))
                    edge_records.append({
                        "from": current,
                        "to": base,
                        "file": node.file,
                        "line": node.line,
                        "raw": node.raw,
                    })

        if node.owner == "mixed" and (node.outbound or node.inbound):
            warnings.append(f"{node.file}:L{node.line}:MIXED_CASE_OWNER")

    cycles = detect_cycles(edges)
    for c in cycles:
        errors.append("DEPENDENCY_CYCLE:" + "->".join(c))

    return ProjectResult(
        ok=not errors,
        root=str(root),
        symbols={k: {kk: vv for kk, vv in v.items() if kk != "order"} for k, v in symbols.items()},
        edges=edge_records,
        cycles=cycles,
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
    parser = argparse.ArgumentParser(description="HACI Project Validator v1.1")
    parser.add_argument("root", help="project folder containing .haci files")
    parser.add_argument("--out", help="write JSON result to path")
    args = parser.parse_args(argv)

    result = validate_project(Path(args.root))
    data = json.dumps(asdict(result), indent=2)
    if args.out:
        Path(args.out).write_text(data, encoding="utf-8")
    print(data)
    return 0 if result.ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
