#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import re
import sys

OPERATORS = {"!": "declare", "?": "ask", ">": "observe"}

@dataclass
class Node:
    line: int
    raw: str
    outbound: Optional[str]
    inbound: Optional[str]
    object: Optional[str]
    payload: str
    owner: str
    diagnostics: List[str]

@dataclass
class ValidationResult:
    ok: bool
    file: str
    symbols: Dict[str, dict]
    nodes: List[dict]
    errors: List[str]
    warnings: List[str]

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

def parse_line(line: str, line_no: int) -> Optional[Node]:
    raw = line.rstrip("\n")
    stripped = raw.strip()
    if not stripped:
        return None
    if stripped.startswith("#"):
        return Node(line_no, raw, None, None, None, stripped, "structure", [])

    prefix, body, suffix = split_haci_line(raw)
    outbound = OPERATORS.get(prefix) if prefix else None
    inbound = OPERATORS.get(suffix) if suffix else None

    obj = None
    payload = body

    # HACI v1 frozen rule:
    # Only operator-bearing protocol lines may consume first token as object.
    if outbound or inbound:
        parts = body.split(None, 1)
        if parts:
            candidate = parts[0]
            if re.fullmatch(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*", candidate):
                obj = candidate
                payload = parts[1] if len(parts) > 1 else ""

    owner_basis = payload if payload else body
    return Node(
        line=line_no,
        raw=raw,
        outbound=outbound,
        inbound=inbound,
        object=obj,
        payload=payload,
        owner=classify_owner(owner_basis),
        diagnostics=[],
    )

def parse_haci(text: str) -> List[Node]:
    nodes = []
    in_code = False
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            nodes.append(Node(i, line, None, None, None, stripped, "code", []))
            continue
        if in_code:
            nodes.append(Node(i, line, None, None, None, line, "code", []))
            continue
        node = parse_line(line, i)
        if node:
            nodes.append(node)
    return nodes

def declared_symbol_from_file(path: Path) -> Optional[str]:
    stem = path.stem
    if re.fullmatch(r"[a-z][a-z0-9]*", stem):
        return stem
    return None

def validate_file(path: Path) -> ValidationResult:
    text = path.read_text(encoding="utf-8")
    nodes = parse_haci(text)
    symbols: Dict[str, dict] = {}
    errors: List[str] = []
    warnings: List[str] = []
    immutable: Dict[str, str] = {}

    file_symbol = declared_symbol_from_file(path)
    if file_symbol:
        symbols[file_symbol] = {
            "source": str(path),
            "scope": str(path.parent),
            "declared_by": "file",
        }

    for node in nodes:
        if node.owner in {"structure", "code"}:
            continue

        if (node.outbound or node.inbound) and not node.payload:
            errors.append(f"L{node.line}: EMPTY_PAYLOAD")

        if node.outbound == "declare" and node.object:
            symbol = node.object.split(".")[0]
            meaning = node.payload.strip()

            if symbol in immutable and meaning != immutable[symbol]:
                errors.append(f"L{node.line}: AUTHORITY_MUTATION:{symbol}")

            if symbol in symbols and symbols[symbol].get("meaning") and symbols[symbol]["meaning"] != meaning:
                errors.append(f"L{node.line}: DUPLICATE_OR_CONFLICTING_SYMBOL:{symbol}")
            else:
                symbols.setdefault(symbol, {
                    "source": str(path),
                    "scope": str(path.parent),
                    "declared_by": "line",
                })
                symbols[symbol]["meaning"] = meaning
                symbols[symbol]["line"] = node.line

            if node.owner == "human":
                immutable[symbol] = meaning

        if node.object:
            base = node.object.split(".")[0]
            if base not in symbols:
                errors.append(f"L{node.line}: UNDECLARED_OBJECT:{base}")

        if node.owner == "mixed" and (node.outbound or node.inbound):
            warnings.append(f"L{node.line}: MIXED_CASE_OWNER")

    return ValidationResult(
        ok=not errors,
        file=str(path),
        symbols=symbols,
        nodes=[asdict(n) for n in nodes],
        errors=errors,
        warnings=warnings,
    )

def detect_cycles(edges: List[Tuple[str, str]]) -> List[List[str]]:
    graph: Dict[str, List[str]] = {}
    for a, b in edges:
        graph.setdefault(a, []).append(b)

    cycles: List[List[str]] = []
    visiting: List[str] = []
    visited = set()

    def dfs(node: str):
        if node in visiting:
            idx = visiting.index(node)
            cycles.append(visiting[idx:] + [node])
            return
        if node in visited:
            return
        visiting.append(node)
        for nxt in graph.get(node, []):
            dfs(nxt)
        visiting.pop()
        visited.add(node)

    for n in list(graph):
        dfs(n)
    return cycles

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

def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print("usage: haci_validator.py validate <file.haci>")
        return 2
    if argv[1] == "validate":
        result = validate_file(Path(argv[2]))
        print(json.dumps(asdict(result), indent=2))
        return 0 if result.ok else 1
    print(f"unknown command: {argv[1]}")
    return 2

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
