"""
THE TWO EXITS — faithful projections of the substrate.

Faithful = from_X(to_X(S)) recovers S exactly, graph and all. The base HACI of
eskimo-brothers was NOT faithful: it rebuilt refs as linear adjacency, so
M -> H -> M collapsed any non-linear graph (the proven seam). The fix is honest
and has a stated cost: to make the human skin a faithful exit, the provenance
(id, from, authority, role, refs) has to live somewhere visible. So HACI-C
keeps the human sentence on the left and carries the provenance in a tail:

    ! BUILD THE SCHEDULER⟦h-001|human|sovereign|COMMAND⟧
    use a min-heap⟦h-002|ai-agent|advisory|PROPOSAL|h-001⟧

The left is the readable line (the ! ? > sugar is decorative); the tail is the
machine truth. Role is read from the tail, never sniffed from casing — so there
is zero classification ambiguity, and the round-trip is exact.

Scope (stated, not hidden): content is single-line here; multi-line / CODE-fence
bodies are a declared extension, out of the faithfulness domain below.
"""
from typing import List
from .substrate import Msg
from .canonical import canon

SUGAR = {"COMMAND": "! ", "QUESTION": "? ", "EVIDENCE": "> "}  # decorative only
OPEN, CLOSE, SEP = "⟦", "⟧", "|"


# ---- Machine exit (canonical MACI, JSON Lines) --------------------------
def to_M(S: List[Msg]) -> str:
    lines = []
    for m in S:
        obj = {"maci": "0.1.0", "id": m.id, "from": m.frm, "role": m.role,
               "authority": m.authority, "content": m.content, "refs": list(m.refs)}
        lines.append(canon(obj).decode("utf-8").rstrip("\n"))
    return "\n".join(lines)


def from_M(text: str) -> List[Msg]:
    import json
    out = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        o = json.loads(line)
        out.append(Msg(id=o["id"], frm=o["from"], role=o["role"],
                       authority=o["authority"], content=o["content"],
                       refs=list(o.get("refs", []))))
    return out


# ---- Human exit (HACI-C, provenance-carrying) ---------------------------
def to_H(S: List[Msg]) -> str:
    lines = []
    for m in S:
        sugar = SUGAR.get(m.role, "")
        tail = OPEN + SEP.join([m.id, m.frm, m.authority, m.role]
                               + ([",".join(m.refs)] if m.refs else [])) + CLOSE
        lines.append(sugar + m.content + tail)
    return "\n".join(lines)


def from_H(text: str) -> List[Msg]:
    out = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        if not line.endswith(CLOSE) or OPEN not in line:
            raise ValueError(f"HACI-C line missing provenance tail: {line!r}")
        left, tail = line[:line.rindex(OPEN)], line[line.rindex(OPEN) + 1:-1]
        parts = tail.split(SEP)
        mid, frm, authority, role = parts[0], parts[1], parts[2], parts[3]
        refs = parts[4].split(",") if len(parts) > 4 and parts[4] else []
        sugar = SUGAR.get(role, "")
        content = left[len(sugar):] if left.startswith(sugar) else left
        out.append(Msg(id=mid, frm=frm, role=role, authority=authority,
                       content=content, refs=refs))
    return out
