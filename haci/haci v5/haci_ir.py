#!/usr/bin/env python3
"""
HACI AST/IR v0.1

Human Artfully Crafted Intelligence
.haci parser core

Core rule:
    prefix = intent
    suffix = status
    case   = ownership
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import json
import re
import sys
from pathlib import Path

INTENT_PREFIX = {
    "!": "declare",
    "?": "inquire",
    ">": "observe",
}

STATUS_SUFFIX = {
    "!": "committed",
    "?": "pending",
    ">": "verified",
}

MARKDOWN_PREFIXES = ("#", "-", "*", "+")
EDGE_OPERATORS = set("!?>")

@dataclass
class HaciNode:
    id: int
    type: str
    raw: str
    content: str
    intent: Optional[str] = None
    status: Optional[str] = None
    owner: Optional[str] = None
    diagnostics: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None

@dataclass
class HaciDocument:
    haci_version: str
    ir_version: str
    source_name: Optional[str]
    nodes: List[HaciNode]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "haci_document",
            "haci_version": self.haci_version,
            "ir_version": self.ir_version,
            "source_name": self.source_name,
            "nodes": [
                {k: v for k, v in asdict(node).items() if v not in (None, [], {})}
                for node in self.nodes
            ],
        }

def classify_owner(content: str) -> str:
    """
    Ownership by casing:
        UPPERCASE     -> human
        lowercase     -> machine
        Sentence Case -> shared
        mixed/other   -> shared
    """
    letters = [c for c in content if c.isalpha()]
    if not letters:
        return "neutral"

    upper = sum(1 for c in letters if c.isupper())
    lower = sum(1 for c in letters if c.islower())
    total = len(letters)

    # Mostly uppercase, allowing acronyms/numbers/spaces/punctuation.
    if upper / total >= 0.80 and lower == 0:
        return "human"

    # Mostly lowercase.
    if lower / total >= 0.80 and upper == 0:
        return "machine"

    # Sentence case or mixed prose belongs to shared documentation by default.
    return "shared"

def classify_markdown(content: str) -> Optional[Dict[str, Any]]:
    stripped = content.lstrip()
    if stripped.startswith("#"):
        level = len(stripped) - len(stripped.lstrip("#"))
        if level > 0 and len(stripped) > level and stripped[level] == " ":
            return {"type": "heading", "level": level, "text": stripped[level:].strip()}
    if re.match(r"^(\s*)([-*+])\s+", content):
        return {"type": "list_item"}
    if re.match(r"^(\s*)\d+\.\s+", content):
        return {"type": "ordered_list_item"}
    return None

def parse_line(line: str, node_id: int, in_code: bool) -> tuple[HaciNode, bool]:
    raw = line.rstrip("\n")
    stripped = raw.strip()
    diagnostics: List[str] = []

    # Blank line.
    if not stripped:
        return HaciNode(node_id, "blank", raw, ""), in_code

    # Code fence toggles parsing suspension.
    if stripped.startswith("```") or stripped.startswith("~~~"):
        fence = stripped[:3]
        if not in_code:
            language = stripped[3:].strip() or None
            return HaciNode(
                node_id,
                "code_fence_open",
                raw,
                stripped,
                owner="runtime",
                meta={"fence": fence, "language": language},
            ), True
        else:
            return HaciNode(
                node_id,
                "code_fence_close",
                raw,
                stripped,
                owner="runtime",
                meta={"fence": fence},
            ), False

    if in_code:
        return HaciNode(node_id, "code", raw, raw, owner="runtime"), in_code

    # Markdown structure has priority unless an intent prefix is present.
    first = stripped[0]
    prefix_symbol = None
    suffix_symbol = None

    if first in EDGE_OPERATORS:
        prefix_symbol = first
        stripped = stripped[1:].strip()

    # Suffix operator is only active at final edge after prefix removal.
    if stripped and stripped[-1] in EDGE_OPERATORS:
        suffix_symbol = stripped[-1]
        stripped = stripped[:-1].strip()

    content = stripped
    intent = INTENT_PREFIX.get(prefix_symbol) if prefix_symbol else None
    status = STATUS_SUFFIX.get(suffix_symbol) if suffix_symbol else None

    md = classify_markdown(content) if not prefix_symbol else None
    owner = classify_owner(content)

    if md:
        node_type = md["type"]
        meta = {k: v for k, v in md.items() if k != "type"}
    elif intent:
        node_type = "statement"
        meta = None
    elif status:
        node_type = "statement"
        meta = None
    else:
        if owner == "machine":
            node_type = "machine"
        elif owner == "human":
            node_type = "human"
        else:
            node_type = "documentation"
        meta = None

    # v0.1 validation hints.
    if intent == "declare" and owner == "machine":
        diagnostics.append("declare intent uses lowercase/machine-owned content")
    if status == "verified" and intent == "inquire":
        diagnostics.append("inquiry marked verified; check whether this should be observe or declare")
    if prefix_symbol and not content:
        diagnostics.append("intent operator without content")
    if suffix_symbol and not content:
        diagnostics.append("status operator without content")

    return HaciNode(
        node_id,
        node_type,
        raw,
        content,
        intent=intent,
        status=status,
        owner=owner,
        diagnostics=diagnostics or None,
        meta=meta,
    ), in_code

def parse_haci(text: str, source_name: Optional[str] = None) -> HaciDocument:
    nodes: List[HaciNode] = []
    in_code = False
    for idx, line in enumerate(text.splitlines(), start=1):
        node, in_code = parse_line(line, idx, in_code)
        nodes.append(node)

    if in_code:
        nodes.append(HaciNode(
            len(nodes) + 1,
            "diagnostic",
            "",
            "unclosed code fence",
            diagnostics=["unclosed code fence"],
        ))

    return HaciDocument(
        haci_version="0.1",
        ir_version="0.1",
        source_name=source_name,
        nodes=nodes,
    )

def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: haci_ir.py <file.haci>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    doc = parse_haci(path.read_text(encoding="utf-8"), source_name=path.name)
    print(json.dumps(doc.to_dict(), indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
