#!/usr/bin/env python3
"""
HACI Project Validator v2.2 — Resolution + Pairing Patch

Language base:
- HACI v2.x semantics retained.
- lowercase = human-owned
- UPPERCASE = AI-owned
- Sentence Case = context/shared
- Syntax unchanged: ! ? >
- No new operators. No new punctuation.

v3.4 fixes:
1. Keeps multi commit return attachment from v3.3.
2. Adds missing parent scope gate.
3. Committed nested child symbols require their parent object chain to exist and be committed.
4. Flat namespace-root symbols remain allowed.
5. Missing or pending parents block child commits.
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
STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "in", "on", "and", "or", "is",
    "are", "was", "were", "be", "been", "ready", "result", "status",
    "previous", "parser", "please", "return", "answer", "response",
}

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

        # v2.2: blank lines become structure boundaries.
        if not stripped:
            raw_nodes.append({
                "file": str(path), "line": line_no, "raw": raw,
                "outbound": None, "inbound": None, "object": None,
                "payload": "", "owner": "boundary",
            })
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

def current_file_canonical_for_object(obj: str, current_file: Path, root: Path, symbols: Dict[str, dict]) -> Tuple[Optional[str], Optional[str]]:
    current = canonical_for_file(current_file, root)
    stem = strip_order_prefix(current_file.stem)
    if not obj:
        return None, None

    segments = obj.split(".")
    base = segments[0]
    if base != stem:
        return None, None

    if len(segments) == 1:
        return current, None

    full = ".".join([current] + segments[1:])
    if full in symbols:
        return full, None
    return None, f"DOT_PATH_NOT_FOUND:{full}"

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

    # Current file's own stem wins inside its file.
    if current_file and root:
        local, local_err = current_file_canonical_for_object(obj, current_file, root, symbols)
        if local or local_err:
            return local, local_err

    segments = obj.split(".")
    first = segments[0]
    candidates = aliases.get(first, [])

    if len(candidates) == 1:
        base = candidates[0]
        if len(segments) == 1:
            return base, None
        full = ".".join([base] + segments[1:])
        if full in symbols:
            return full, None
        return None, f"DOT_PATH_NOT_FOUND:{full}"

    if len(candidates) > 1:
        return None, f"AMBIGUOUS_OBJECT:{first}:{','.join(candidates)}"

    return None, f"UNDECLARED_OBJECT:{first}"

def create_line_symbol_if_allowed(
    obj: str,
    current_file: Path,
    root: Path,
    symbols: Dict[str, dict],
    aliases: Dict[str, List[str]],
    payload: str,
    line: int,
) -> Tuple[Optional[str], Optional[str]]:
    """
    v2.2: No virtual dotted path creation.
    Declarations may enrich the current file's own object, or an already-existing exact object.
    They may not create phantom dot paths.
    """
    if not obj:
        return None, "MISSING_DECLARATION_OBJECT"

    if "." in obj:
        resolved, err = resolve_object(obj, symbols, aliases, current_file, root)
        if err:
            return None, err
        return resolved, None

    stem = strip_order_prefix(current_file.stem)
    if obj == stem:
        canonical = canonical_for_file(current_file, root)
        return canonical, None

    # If a non-local base already resolves uniquely, allow enriching it.
    resolved, err = resolve_object(obj, symbols, aliases, current_file, root)
    if resolved:
        return resolved, None
    return None, err or f"UNDECLARED_OBJECT:{obj}"

def declared_edge_target(resolved: str, symbols: Dict[str, dict]) -> str:
    # resolved is guaranteed exact in v2.2; use it directly.
    return resolved

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

def tokens(text: str) -> Set[str]:
    raw = re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
    return {t for t in raw if t not in STOPWORDS and len(t) > 1}

def same_file_return_before_ask(conv: Conversation, ret: Node) -> bool:
    start = conv.start
    return (
        ret.file == start.get("file")
        and ret.line is not None
        and start.get("line") is not None
        and ret.line < start.get("line")
    )

def chronology_pair_allowed(conv: Conversation, ret: Node) -> bool:
    # Cross-file pairing stays order-independent.
    # Same-file return-side nodes may not answer/clarify/accept a later ask.
    return not same_file_return_before_ask(conv, ret)

def pairing_score(conv: Conversation, ret: Node) -> int:
    if not chronology_pair_allowed(conv, ret):
        return 0
    # Use payload/body token overlap; object is already matched outside.
    ask_text = " ".join([
        conv.start.get("payload", ""),
        " ".join(b.get("payload", "") for b in conv.body),
    ])
    ret_text = ret.payload
    a = tokens(ask_text)
    b = tokens(ret_text)
    if not a or not b:
        return 0
    return len(a & b)

def inbound_completes(inbound: Optional[str]) -> bool:
    # Suffix > maps to observe: told / evidence / result.
    # Suffix ! maps to declare: accepted / acknowledged / committed.
    # Suffix ? maps to ask: returned as question / still open.
    return inbound in {"observe", "declare"}

def inbound_is_question(inbound: Optional[str]) -> bool:
    return inbound == "ask"

def declaration_commits(inbound: Optional[str]) -> bool:
    # A declaration is committed only when the return side confirms it.
    # > = returned/told/verified; ! = accepted/committed.
    # ? or no suffix = pending/open, not committed.
    return inbound_completes(inbound)

def return_dict_completes(ret: dict) -> bool:
    return inbound_completes(ret.get("inbound"))

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

def group_conversations(nodes: List[Node]) -> Tuple[List[Conversation], List[str], List[str]]:
    """
    v2.4 conversation engine:
    - Declarations complete by default unless the inbound suffix is ?.
    - Suffix > and suffix ! are complete inbound returns.
    - Suffix ? is an inbound question and keeps the conversation unresolved.
    - Body attachment stops at headings, blank boundaries, code blocks, or next protocol line.
    - Return-only answer nodes are paired by mutual unique positive best match.
    - Return-only question nodes can attach to one unique open conversation but keep it unresolved.
    """
    errors: List[str] = []
    warnings: List[str] = []
    conversations: List[Conversation] = []
    return_only_nodes: List[Node] = []
    return_question_nodes: List[Node] = []
    last_attachable_by_file: Dict[str, Optional[Conversation]] = {}

    for n in nodes:
        if n.owner in {"structure", "boundary", "code"}:
            last_attachable_by_file[n.file] = None
            continue

        if is_protocol_node(n):
            if not n.object:
                errors.append(f"{n.file}:L{n.line}:OBJECT_REQUIRED_PROTOCOL_LINE")
                last_attachable_by_file[n.file] = None
                continue

            # Suffix-only return/question nodes are handled in the pairing pass.
            if n.inbound and not n.outbound:
                if inbound_is_question(n.inbound):
                    return_question_nodes.append(n)
                else:
                    return_only_nodes.append(n)
                last_attachable_by_file[n.file] = None
                continue

            if n.outbound == "declare":
                committed = declaration_commits(n.inbound)
                unresolved = not committed
                conv = make_conversation(n, "declaration", complete=committed, unresolved=unresolved)
                if inbound_is_question(n.inbound):
                    conv.diagnostics.append("INBOUND_QUESTION_UNRESOLVED")
                if not committed:
                    conv.diagnostics.append("DECLARATION_PENDING_NOT_COMMITTED")
                conversations.append(conv)
                last_attachable_by_file[n.file] = conv
                continue

            if n.outbound in {"ask", "observe"}:
                if n.inbound:
                    complete = inbound_completes(n.inbound)
                    unresolved = not complete
                else:
                    complete = False
                    unresolved = True
                conv = make_conversation(n, "conversation", complete=complete, unresolved=unresolved)
                if inbound_is_question(n.inbound):
                    conv.diagnostics.append("INBOUND_QUESTION_UNRESOLVED")
                conversations.append(conv)
                last_attachable_by_file[n.file] = conv
                continue

            complete = inbound_completes(n.inbound)
            unresolved = not complete
            conv = make_conversation(n, "event", complete=complete, unresolved=unresolved)
            if inbound_is_question(n.inbound):
                conv.diagnostics.append("INBOUND_QUESTION_UNRESOLVED")
            conversations.append(conv)
            last_attachable_by_file[n.file] = conv
            continue

        conv = last_attachable_by_file.get(n.file)
        if conv:
            conv.body.append(node_to_dict(n))

    unresolved_by_object: Dict[str, List[Conversation]] = {}
    for conv in conversations:
        if conv.unresolved and conv.object:
            unresolved_by_object.setdefault(conv.object, []).append(conv)

    # v3.1: Attach suffix-? return-question nodes independently.
    # Multiple return-questions may attach to the same open conversation.
    # Each return-question must still have exactly one positive best conversation match.
    # They never complete the target. They only preserve "returned as question / still open".
    return_questions_by_object: Dict[str, List[Node]] = {}
    for retq in return_question_nodes:
        key = object_key(retq)
        if key:
            return_questions_by_object.setdefault(key, []).append(retq)
        else:
            conv = make_conversation(retq, "return_question", complete=False, unresolved=True)
            conv.diagnostics.append("RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST")
            conversations.append(conv)
            warnings.append(f"{retq.file}:L{retq.line}:RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST:{conv.id}")

    for key, questions in return_questions_by_object.items():
        convs = unresolved_by_object.get(key, [])
        if not convs:
            for retq in questions:
                conv = make_conversation(retq, "return_question", complete=False, unresolved=True)
                conv.diagnostics.append("RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST")
                conversations.append(conv)
                warnings.append(f"{retq.file}:L{retq.line}:RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST:{conv.id}")
            continue

        for retq in questions:
            scored = [(pairing_score(conv, retq), ci) for ci, conv in enumerate(convs)]
            best_score = max((score for score, _ in scored), default=0)

            if best_score <= 0:
                conv = make_conversation(retq, "return_question", complete=False, unresolved=True)
                if any(same_file_return_before_ask(c, retq) for c in convs):
                    conv.diagnostics.append("SAME_FILE_RETURN_BEFORE_ASK")
                    warnings.append(f"{retq.file}:L{retq.line}:SAME_FILE_RETURN_BEFORE_ASK:{conv.id}")
                conv.diagnostics.append("RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST")
                conversations.append(conv)
                warnings.append(f"{retq.file}:L{retq.line}:RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST:{conv.id}")
                continue

            best_convs = [ci for score, ci in scored if score == best_score]
            if len(best_convs) != 1:
                for ci in best_convs:
                    convs[ci].diagnostics.append("AMBIGUOUS_RETURN_QUESTION_PAIR")
                conv = make_conversation(retq, "return_question", complete=False, unresolved=True)
                conv.diagnostics.append("AMBIGUOUS_RETURN_QUESTION_PAIR")
                conv.diagnostics.append("RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST")
                conversations.append(conv)
                warnings.append(f"{retq.file}:L{retq.line}:RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST:{conv.id}")
                continue

            conv = convs[best_convs[0]]
            conv.returns.append(node_to_dict(retq))
            conv.unresolved = True
            conv.complete = False
            conv.diagnostics.append("RETURNED_AS_QUESTION")
            if retq.file not in conv.files:
                conv.files.append(retq.file)
            warnings.append(f"{retq.file}:L{retq.line}:RETURNED_AS_QUESTION:{conv.id}")

    returns_by_object: Dict[str, List[Node]] = {}
    for ret in return_only_nodes:
        key = object_key(ret)
        if key:
            returns_by_object.setdefault(key, []).append(ret)
        else:
            warnings.append(f"{ret.file}:L{ret.line}:RETURN_WITHOUT_OBJECT")

    for key, returns in returns_by_object.items():
        convs = unresolved_by_object.get(key, [])
        if not convs:
            for ret in returns:
                conv = make_conversation(ret, "return", complete=True, unresolved=False)
                conv.diagnostics.append("RETURN_WITHOUT_OPEN_REQUEST")
                conversations.append(conv)
                warnings.append(f"{ret.file}:L{ret.line}:RETURN_WITHOUT_OPEN_REQUEST:{conv.id}")
            continue

        matched_returns: Set[int] = set()

        # v3.2/v3.3: completion returns with positive unique matches attach independently.
        # Suffix > evidence/result and suffix ! commit/ack returns may both attach multiple
        # times to the same conversation when each return has exactly one positive best match.
        # Zero-score ! returns are left for the old conservative accepted-return fallback.
        for ri, ret in enumerate(returns):
            if ret.inbound not in {"observe", "declare"}:
                continue

            scored = [(pairing_score(conv, ret), ci) for ci, conv in enumerate(convs)]
            best_score = max((score for score, _ in scored), default=0)

            if best_score <= 0:
                if ret.inbound == "declare":
                    # Preserve the v2.6 no-token accepted fallback for suffix !.
                    continue
                conv = make_conversation(ret, "return", complete=True, unresolved=False)
                if any(same_file_return_before_ask(c, ret) for c in convs):
                    conv.diagnostics.append("SAME_FILE_RETURN_BEFORE_ASK")
                    warnings.append(f"{ret.file}:L{ret.line}:SAME_FILE_RETURN_BEFORE_ASK:{conv.id}")
                conv.diagnostics.append("RETURN_WITHOUT_OPEN_REQUEST")
                conversations.append(conv)
                warnings.append(f"{ret.file}:L{ret.line}:RETURN_WITHOUT_OPEN_REQUEST:{conv.id}")
                matched_returns.add(ri)
                continue

            best_convs = [ci for score, ci in scored if score == best_score]
            if len(best_convs) != 1:
                for ci in best_convs:
                    convs[ci].diagnostics.append("AMBIGUOUS_RETURN_PAIR")
                conv = make_conversation(ret, "return", complete=True, unresolved=False)
                conv.diagnostics.append("AMBIGUOUS_RETURN_PAIR")
                conv.diagnostics.append("RETURN_WITHOUT_OPEN_REQUEST")
                conversations.append(conv)
                warnings.append(f"{ret.file}:L{ret.line}:RETURN_WITHOUT_OPEN_REQUEST:{conv.id}")
                matched_returns.add(ri)
                continue

            conv = convs[best_convs[0]]
            conv.returns.append(node_to_dict(ret))
            conv.complete = True
            conv.unresolved = False
            if ret.inbound == "declare":
                conv.diagnostics.append("COMMIT_RETURN_PAIR")
                warnings.append(f"{ret.file}:L{ret.line}:COMMIT_RETURN_PAIR:{conv.id}")
            if ret.file not in conv.files:
                conv.files.append(ret.file)
            matched_returns.add(ri)

        # v2.6 accepted-return fallback remains conservative:
        # Suffix ! means accepted / acknowledged / committed back.
        # It may close without token overlap only when there is exactly one still-open ask
        # and exactly one remaining same-object ! return.
        remaining_decl_returns = [
            i for i in range(len(returns))
            if i not in matched_returns and returns[i].inbound == "declare"
        ]
        remaining_open_convs = [
            i for i, conv in enumerate(convs)
            if conv.unresolved and conv.kind == "conversation" and conv.start.get("outbound") == "ask"
        ]

        if len(remaining_open_convs) == 1 and len(remaining_decl_returns) == 1:
            ci = remaining_open_convs[0]
            ri = remaining_decl_returns[0]
            conv = convs[ci]
            ret = returns[ri]
            if chronology_pair_allowed(conv, ret):
                conv.returns.append(node_to_dict(ret))
                conv.complete = True
                conv.unresolved = False
                conv.diagnostics.append("ACCEPTED_RETURN_PAIR")
                if ret.file not in conv.files:
                    conv.files.append(ret.file)
                matched_returns.add(ri)
                warnings.append(f"{ret.file}:L{ret.line}:ACCEPTED_RETURN_PAIR:{conv.id}")

        for ci in range(len(convs)):
            if convs[ci].unresolved:
                convs[ci].diagnostics.append("UNPAIRED_CONVERSATION")
                if "AMBIGUOUS_RETURN_PAIR" not in convs[ci].diagnostics:
                    convs[ci].diagnostics.append("NO_UNIQUE_RETURN_PAIR")

        for ri in range(len(returns)):
            if ri in matched_returns:
                continue
            ret = returns[ri]
            conv = make_conversation(ret, "return", complete=True, unresolved=False)
            if any(same_file_return_before_ask(c, ret) for c in convs):
                conv.diagnostics.append("SAME_FILE_RETURN_BEFORE_ASK")
                warnings.append(f"{ret.file}:L{ret.line}:SAME_FILE_RETURN_BEFORE_ASK:{conv.id}")
            conv.diagnostics.append("RETURN_WITHOUT_OPEN_REQUEST")
            conversations.append(conv)
            warnings.append(f"{ret.file}:L{ret.line}:RETURN_WITHOUT_OPEN_REQUEST:{conv.id}")

    for convs in unresolved_by_object.values():
        for conv in convs:
            if conv.unresolved:
                conv.diagnostics.append("OPEN_CONVERSATION")
                warnings.append(f"{conv.files[0]}:L{conv.start['line']}:OPEN_CONVERSATION:{conv.id}")

    return conversations, unique(errors), unique(warnings)

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

        if conv.kind == "conversation" and start.get("outbound") == "ask":
            has_complete_return = any(return_dict_completes(ret) for ret in conv.returns)
            if not has_complete_return:
                msg = f"{conv.files[0]}:L{start['line']}:ASK_WITHOUT_RETURN:{conv.id}"
                if strict:
                    errors.append(msg)
                else:
                    warnings.append(msg)

        if conv.kind == "return" and "RETURN_WITHOUT_OPEN_REQUEST" in conv.diagnostics:
            msg = f"{conv.files[0]}:L{start['line']}:RETURN_WITHOUT_OPEN_REQUEST:{conv.id}"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)

        if conv.kind == "return_question" or "RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST" in conv.diagnostics:
            msg = f"{conv.files[0]}:L{start['line']}:RETURN_QUESTION_WITHOUT_UNIQUE_REQUEST:{conv.id}"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)

        if "INBOUND_QUESTION_UNRESOLVED" in conv.diagnostics:
            msg = f"{conv.files[0]}:L{start['line']}:INBOUND_QUESTION_UNRESOLVED:{conv.id}"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)

        if "SAME_FILE_RETURN_BEFORE_ASK" in conv.diagnostics:
            msg = f"{conv.files[0]}:L{start['line']}:SAME_FILE_RETURN_BEFORE_ASK:{conv.id}"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)

        if "DECLARATION_PENDING_NOT_COMMITTED" in conv.diagnostics:
            msg = f"{conv.files[0]}:L{start['line']}:DECLARATION_PENDING_NOT_COMMITTED:{conv.id}"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)

        # A return-question after a complete same-file return is not a clarification of the open ask;
        # it is a new unresolved protocol event and must not be hidden inside a completed conversation.
        complete_returns = [ret for ret in conv.returns if return_dict_completes(ret)]
        question_returns = [ret for ret in conv.returns if ret.get("inbound") == "ask"]
        for qret in question_returns:
            q_file = qret.get("file")
            q_line = qret.get("line")
            for cret in complete_returns:
                if cret.get("file") == q_file and cret.get("line") is not None and q_line is not None and cret.get("line") < q_line:
                    msg = f"{q_file}:L{q_line}:LATE_RETURN_QUESTION_AFTER_COMPLETION:{conv.id}"
                    if strict:
                        errors.append(msg)
                    else:
                        warnings.append(msg)
                    break

    return unique(errors), unique(warnings)

def nearest_existing_parent_symbol(symbol: str, symbols: Dict[str, dict]) -> Optional[str]:
    parts = symbol.split(".")
    for i in range(len(parts) - 1, 0, -1):
        parent = ".".join(parts[:i])
        if parent in symbols:
            return parent
    return None

def is_symbol_committed(sym: dict) -> bool:
    return sym.get("commit_state") == "committed" and "meaning" in sym and "authority" in sym

def required_parent_symbols(symbol: str) -> List[str]:
    """
    Parent chain rule:
    - The first segment is a namespace/scope folder, not a committed object.
    - A flat object like memory.m is allowed without a memory symbol.
    - A nested object like memory.m.parser.last requires:
      memory.m and memory.m.parser.
    """
    parts = symbol.split(".")
    if len(parts) <= 2:
        return []
    return [".".join(parts[:i]) for i in range(2, len(parts))]

def block_committed_symbol(sym: dict, blocked_by: str, reason: str) -> None:
    blocked = {
        "meaning": sym.pop("meaning", None),
        "authority": sym.pop("authority", None),
        "declared_at": sym.pop("declared_at", None),
        "previous_commit_state": sym.pop("commit_state", None),
        "blocked_by": blocked_by,
        "reason": reason,
    }
    sym.setdefault("blocked_commits", []).append(blocked)
    if reason == "MISSING_PARENT_SCOPE":
        sym["commit_state"] = "blocked_missing_parent"
    else:
        sym["commit_state"] = "blocked_pending_parent"

def apply_pending_parent_scope_gate(symbols: Dict[str, dict]) -> List[str]:
    """
    Structural gate:
    A committed nested child symbol requires each object parent in its scope chain
    to exist and be committed.

    This is an error even outside strict mode because scope authority cannot invert.
    """
    errors: List[str] = []

    for symbol in sorted(list(symbols.keys())):
        sym = symbols[symbol]
        if not is_symbol_committed(sym):
            continue

        for parent in required_parent_symbols(symbol):
            parent_sym = symbols.get(parent)
            if parent_sym is None:
                block_committed_symbol(sym, parent, "MISSING_PARENT_SCOPE")
                errors.append(f"{sym.get('file', symbol)}:MISSING_PARENT_SCOPE:{parent}->{symbol}")
                break

            if not is_symbol_committed(parent_sym):
                block_committed_symbol(sym, parent, "PENDING_PARENT_SCOPE")
                errors.append(f"{sym.get('file', symbol)}:PENDING_PARENT_SCOPE:{parent}->{symbol}")
                break

    return errors

def dependency_edge_allowed(node: Node) -> bool:
    # Pending declarations must not mutate graph topology.
    # Committed declarations, asks, observes, and other resolved protocol references may still create edges.
    if node.outbound == "declare":
        return declaration_commits(node.inbound)
    return True

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
        if owner in {"structure", "boundary", "code"}:
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
                resolved, err = create_line_symbol_if_allowed(
                    obj, current_file, root, symbols, aliases, rn["payload"], rn["line"]
                )
            if err:
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

            symbols.setdefault(resolved, {
                "symbol": resolved,
                "alias": obj.split(".")[0] if obj else None,
                "kind": "line",
                "file": node.file,
                "scope": scope_for_file(current_file, root),
            })

            if declaration_commits(node.inbound):
                if resolved in immutable and immutable[resolved] != meaning:
                    errors.append(f"{node.file}:L{node.line}:AUTHORITY_MUTATION:{resolved}")

                if existing.get("meaning") and existing["meaning"] != meaning:
                    errors.append(f"{node.file}:L{node.line}:DUPLICATE_OR_CONFLICTING_SYMBOL:{resolved}")
                else:
                    symbols[resolved]["meaning"] = meaning
                    symbols[resolved]["declared_at"] = f"{node.file}:L{node.line}"
                    symbols[resolved]["authority"] = authority
                    symbols[resolved]["commit_state"] = "committed"

                if authority == "human":
                    immutable[resolved] = meaning
                elif authority == "ai":
                    warnings.append(f"{node.file}:L{node.line}:AI_DECLARATION_NOT_HUMAN_AUTHORITY:{resolved}")
            else:
                pending = symbols[resolved].setdefault("pending_declarations", [])
                pending.append({
                    "meaning": meaning,
                    "authority": authority,
                    "declared_at": f"{node.file}:L{node.line}",
                    "inbound": node.inbound,
                    "state": "pending",
                })
                warnings.append(f"{node.file}:L{node.line}:DECLARATION_PENDING_NOT_COMMITTED:{resolved}")

        if resolved and dependency_edge_allowed(node):
            target = declared_edge_target(resolved, symbols)
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

    errors.extend(apply_pending_parent_scope_gate(symbols))

    cycles = detect_cycles(edges)
    for c in cycles:
        errors.append("DEPENDENCY_CYCLE:" + "->".join(c))

    conversations, group_errors, group_warnings = group_conversations(nodes)
    errors.extend(group_errors)
    warnings.extend(group_warnings)
    conv_errors, conv_warnings = validate_conversations(conversations, strict)
    errors.extend(conv_errors)
    warnings.extend(conv_warnings)

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
    parser = argparse.ArgumentParser(description="HACI Project Validator v3.4")
    parser.add_argument("root")
    parser.add_argument("--strict", action="store_true", help="open/unresolved/unmatched returns fail instead of warn")
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
