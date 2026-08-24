from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
import time
from typing import Any, Iterable


class Phase(str, Enum):
    EMPTY = "empty"
    CONTAINMENT_DEFINED = "containment_defined"
    CONTAINMENT_VERIFIED = "containment_verified"
    PLASMA_ARMED = "plasma_armed"
    PLASMA_ACTIVE = "plasma_active"
    QUENCHED = "quenched"
    FAULT_LOCKED = "fault_locked"


class ContainmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    min_boundary_nodes: int
    witness_slots: int = 3
    approvals_required: int = 2


PROFILES = {
    "ACI": Profile("ACI", min_boundary_nodes=4),
    "CUBIS": Profile("CUBIS", min_boundary_nodes=6),
}


@dataclass
class LedgerEvent:
    seq: int
    ts_ns: int
    event: str
    payload: dict[str, Any]
    previous_hash: str
    event_hash: str


@dataclass
class ContainmentKernel:
    profile: Profile
    phase: Phase = Phase.EMPTY
    boundary: tuple[str, ...] = ()
    boundary_seal: str | None = None
    witnesses: dict[str, bool] = field(default_factory=dict)
    ledger: list[LedgerEvent] = field(default_factory=list)
    _armed_seal: str | None = None

    @classmethod
    def for_system(cls, system: str) -> "ContainmentKernel":
        key = system.strip().upper()
        if key not in PROFILES:
            raise ValueError(f"unknown containment profile: {system!r}")
        return cls(PROFILES[key])

    def _canonical(self, value: Any) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _append(self, event: str, payload: dict[str, Any]) -> LedgerEvent:
        previous = self.ledger[-1].event_hash if self.ledger else "0" * 64
        body = {
            "seq": len(self.ledger),
            "event": event,
            "payload": payload,
            "previous_hash": previous,
        }
        digest = sha256(self._canonical(body)).hexdigest()
        row = LedgerEvent(len(self.ledger), time.time_ns(), event, payload, previous, digest)
        self.ledger.append(row)
        return row

    def _seal_boundary(self) -> str:
        return sha256(self._canonical({"profile": self.profile.name, "boundary": self.boundary})).hexdigest()

    def define_containment(self, nodes: Iterable[str]) -> str:
        if self.phase in {Phase.PLASMA_ARMED, Phase.PLASMA_ACTIVE}:
            self._fault("containment mutation attempted after plasma arm")
        cleaned = tuple(dict.fromkeys(str(n).strip() for n in nodes if str(n).strip()))
        if len(cleaned) < self.profile.min_boundary_nodes:
            raise ContainmentError(
                f"{self.profile.name} requires at least {self.profile.min_boundary_nodes} boundary nodes"
            )
        self.boundary = cleaned
        self.boundary_seal = self._seal_boundary()
        self.witnesses.clear()
        self._armed_seal = None
        self.phase = Phase.CONTAINMENT_DEFINED
        self._append("CONTAINMENT_DEFINED", {"nodes": list(cleaned), "seal": self.boundary_seal})
        return self.boundary_seal

    def witness(self, witness_id: str, approve: bool) -> None:
        if self.phase not in {Phase.CONTAINMENT_DEFINED, Phase.CONTAINMENT_VERIFIED}:
            raise ContainmentError("witnessing is only valid before plasma arm")
        witness_id = witness_id.strip()
        if not witness_id:
            raise ValueError("witness_id cannot be empty")
        if witness_id not in self.witnesses and len(self.witnesses) >= self.profile.witness_slots:
            raise ContainmentError("witness slots are full")
        self.witnesses[witness_id] = bool(approve)
        self._append("WITNESS", {"id": witness_id, "approve": bool(approve)})
        self._recompute_verification()

    def _recompute_verification(self) -> None:
        if self.boundary_seal != self._seal_boundary():
            self._fault("boundary seal mismatch")
        approvals = sum(1 for approved in self.witnesses.values() if approved)
        full_quorum = len(self.witnesses) == self.profile.witness_slots
        if full_quorum and approvals >= self.profile.approvals_required:
            if self.phase != Phase.CONTAINMENT_VERIFIED:
                self.phase = Phase.CONTAINMENT_VERIFIED
                self._append(
                    "CONTAINMENT_VERIFIED",
                    {"witnesses": len(self.witnesses), "approvals": approvals, "seal": self.boundary_seal},
                )
        elif self.phase == Phase.CONTAINMENT_VERIFIED:
            self.phase = Phase.CONTAINMENT_DEFINED
            self._append("CONTAINMENT_REVOKED", {"witnesses": len(self.witnesses), "approvals": approvals})

    def arm_plasma(self) -> None:
        if self.phase != Phase.CONTAINMENT_VERIFIED:
            raise ContainmentError("plasma denied: containment is not verified")
        current = self._seal_boundary()
        if not self.boundary_seal or current != self.boundary_seal:
            self._fault("plasma denied: containment seal mismatch")
        self._armed_seal = current
        self.phase = Phase.PLASMA_ARMED
        self._append("PLASMA_ARMED", {"seal": current})

    def ignite_plasma(self) -> None:
        if self.phase != Phase.PLASMA_ARMED:
            raise ContainmentError("plasma denied: arm stage incomplete")
        if self._armed_seal != self._seal_boundary():
            self._fault("plasma denied: containment changed after arm")
        self.phase = Phase.PLASMA_ACTIVE
        self._append("PLASMA_ACTIVE", {"seal": self._armed_seal})

    def guard(self) -> bool:
        if self.phase not in {Phase.PLASMA_ARMED, Phase.PLASMA_ACTIVE}:
            return True
        current = self._seal_boundary()
        approvals = sum(1 for approved in self.witnesses.values() if approved)
        quorum_ok = (
            len(self.witnesses) == self.profile.witness_slots
            and approvals >= self.profile.approvals_required
        )
        seal_ok = current == self.boundary_seal == self._armed_seal
        if not (quorum_ok and seal_ok):
            self.quench("runtime containment guard failed")
            return False
        return True

    def quench(self, reason: str = "manual") -> None:
        previous = self.phase
        self.phase = Phase.QUENCHED
        self._append("QUENCH", {"reason": reason, "from": previous.value})

    def reset(self) -> None:
        if self.phase not in {Phase.QUENCHED, Phase.FAULT_LOCKED}:
            raise ContainmentError("reset is only allowed after quench/fault")
        self.boundary = ()
        self.boundary_seal = None
        self.witnesses.clear()
        self._armed_seal = None
        self.phase = Phase.EMPTY
        self._append("RESET", {})

    def _fault(self, reason: str) -> None:
        previous = self.phase
        self.phase = Phase.FAULT_LOCKED
        self._append("FAULT_LOCKED", {"reason": reason, "from": previous.value})
        raise ContainmentError(reason)

    def verify_ledger(self) -> bool:
        previous = "0" * 64
        for i, row in enumerate(self.ledger):
            body = {
                "seq": i,
                "event": row.event,
                "payload": row.payload,
                "previous_hash": previous,
            }
            expected = sha256(self._canonical(body)).hexdigest()
            if row.seq != i or row.previous_hash != previous or row.event_hash != expected:
                return False
            previous = row.event_hash
        return True

    def snapshot(self) -> dict[str, Any]:
        approvals = sum(1 for approved in self.witnesses.values() if approved)
        return {
            "system": self.profile.name,
            "phase": self.phase.value,
            "boundary_nodes": len(self.boundary),
            "witnesses": len(self.witnesses),
            "approvals": approvals,
            "seal": self.boundary_seal,
            "ledger_ok": self.verify_ledger(),
        }
