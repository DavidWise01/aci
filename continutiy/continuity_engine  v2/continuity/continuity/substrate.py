"""
THE SUBSTRATE — the one validated object that H and M are both exits of.

A substrate is an ordered list of typed messages forming a causal DAG. This is
the ACI Core made concrete, consistent with the duality-engine's MACI validator:
roles, authority lattice, explicit refs, no forward refs, no cycles.

Continuity's rule, stated once: H and M do not convert into *each other*; they are
two PROJECTIONS of this substrate. The bridge is only ever
    skin_a  ->  from_a  ->  SUBSTRATE  ->  to_b  ->  skin_b
so the substrate must be validated FIRST. Nothing crosses except through it.

The honest boundary (the recorded I5 asymmetry): two roles are machine-only.
A substrate is BRIDGEABLE iff it contains none of them; otherwise the bridge is
partial and the engine says exactly where — it never silently drops them (that
silent drop is the lossy seam, generalized).
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# Roles, taken from the duality-engine MACI validator (the substrate we validate against).
ROLES = {"COMMAND", "PROPOSAL", "QUESTION", "EVIDENCE", "DECISION", "DELEGATE", "CODE"}
AUTHORITY = {"sovereign", "delegated", "advisory", "observer"}

# The shared core both skins can carry losslessly (the bridgeable set) ...
BRIDGEABLE = {"COMMAND", "PROPOSAL", "QUESTION", "EVIDENCE", "CODE"}
# ... and the machine-only residue the bridge must DETECT, not drop.
MACHINE_ONLY = {"DECISION", "DELEGATE"}

ROLE_MIN_AUTHORITY = {
    "COMMAND":  {"sovereign", "delegated"},
    "DECISION": {"sovereign", "delegated"},
    "DELEGATE": {"sovereign", "delegated"},
    "PROPOSAL": {"sovereign", "delegated", "advisory"},
    "QUESTION": {"sovereign", "delegated", "advisory", "observer"},
    "EVIDENCE": {"sovereign", "delegated", "advisory", "observer"},
    "CODE":     {"sovereign", "delegated", "advisory"},
}


@dataclass
class Msg:
    id: str
    frm: str            # 'from' is a Python keyword
    role: str
    authority: str
    content: str
    refs: List[str] = field(default_factory=list)

    def key(self) -> dict:
        """Normalized identity used for exact substrate equality (refs order kept)."""
        return {"id": self.id, "from": self.frm, "role": self.role,
                "authority": self.authority, "content": self.content,
                "refs": list(self.refs)}


def substrate_key(S: List[Msg]) -> list:
    return [m.key() for m in S]


def equal(a: List[Msg], b: List[Msg]) -> bool:
    return substrate_key(a) == substrate_key(b)


def residue(S: List[Msg]) -> List[str]:
    """The machine-only message ids — the part no H skin can carry."""
    return [m.id for m in S if m.role in MACHINE_ONLY]


def is_bridgeable(S: List[Msg]) -> bool:
    return not residue(S)


def validate(S: List[Msg]) -> List[str]:
    """Substrate validity (the FIRST gate). Returns a list of error codes; empty = valid."""
    errors: List[str] = []
    seen = set()
    index = {m.id: i for i, m in enumerate(S)}
    for i, m in enumerate(S):
        if m.id in seen:
            errors.append(f"DUPLICATE_ID:{m.id}")
        seen.add(m.id)
        if m.role not in ROLES:
            errors.append(f"INVALID_ROLE:{m.role}")
        if m.authority not in AUTHORITY:
            errors.append(f"INVALID_AUTHORITY:{m.authority}")
        if not m.content:
            errors.append(f"EMPTY_CONTENT:{m.id}")
        if m.role in ROLE_MIN_AUTHORITY and m.authority not in ROLE_MIN_AUTHORITY[m.role]:
            errors.append(f"AUTHORITY_EXCEEDED:{m.id}:{m.role}/{m.authority}")
        for r in m.refs:
            if r not in index:
                errors.append(f"REF_NOT_FOUND:{m.id}->{r}")
            elif index[r] >= i:
                errors.append(f"FORWARD_REF:{m.id}->{r}")   # may not ref the future
    return errors
