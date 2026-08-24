from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from containment import ContainmentError, ContainmentKernel, Phase

RICKY_NAME = "Ricky"
RICKY_PATTERN = (".", ".", "|", "|", ".", ".", "|", ".", ".")
RICKY_PATTERN_TEXT = "{. . | | . . | . .}"
_ALLOWED_PHASES = {Phase.CONTAINMENT_VERIFIED, Phase.PLASMA_ARMED, Phase.PLASMA_ACTIVE}


def roll_pattern(roll: int = 0) -> tuple[str, ...]:
    n = len(RICKY_PATTERN)
    shift = int(roll) % n
    if shift == 0:
        return RICKY_PATTERN
    return RICKY_PATTERN[-shift:] + RICKY_PATTERN[:-shift]


def _float_hex(value: float) -> str:
    return float(value).hex()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class WanderStep:
    hop: int
    symbol: str
    z_real: str
    z_imag: str
    checkpoint: bool
    escaped: bool

    @property
    def z(self) -> complex:
        return complex(float.fromhex(self.z_real), float.fromhex(self.z_imag))


@dataclass(frozen=True)
class RickyKey:
    name: str
    pattern: str
    rolled_pattern: tuple[str, ...]
    roll: int
    c_real: str
    c_imag: str
    containment_seal: str
    route: tuple[WanderStep, ...]
    escaped: bool
    key_sha256: str

    @property
    def c(self) -> complex:
        return complex(float.fromhex(self.c_real), float.fromhex(self.c_imag))

    @property
    def checkpoint_hops(self) -> tuple[int, ...]:
        return tuple(step.hop for step in self.route if step.checkpoint)

    def _payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "pattern": self.pattern,
            "rolled_pattern": list(self.rolled_pattern),
            "roll": self.roll,
            "c": [self.c_real, self.c_imag],
            "containment_seal": self.containment_seal,
            "route": [
                {
                    "hop": step.hop,
                    "symbol": step.symbol,
                    "z": [step.z_real, step.z_imag],
                    "checkpoint": step.checkpoint,
                    "escaped": step.escaped,
                }
                for step in self.route
            ],
            "escaped": self.escaped,
        }

    def verify(self) -> bool:
        return sha256(_canonical(self._payload())).hexdigest() == self.key_sha256

    def valid_for(self, kernel: ContainmentKernel) -> bool:
        return (
            self.verify()
            and kernel.phase in _ALLOWED_PHASES
            and bool(kernel.boundary_seal)
            and kernel.boundary_seal == self.containment_seal
        )


def _build_key(c: complex, containment_seal: str, roll: int = 0) -> RickyKey:
    mask = roll_pattern(roll)
    z = 0j
    route: list[WanderStep] = []
    escaped = False
    for index, symbol in enumerate(mask, start=1):
        z = z * z + c
        escaped = abs(z) > 2.0
        route.append(WanderStep(index, symbol, _float_hex(z.real), _float_hex(z.imag), symbol == "|", escaped))
        if escaped:
            break

    draft = RickyKey(
        name=RICKY_NAME,
        pattern=RICKY_PATTERN_TEXT,
        rolled_pattern=mask,
        roll=int(roll) % len(RICKY_PATTERN),
        c_real=_float_hex(c.real),
        c_imag=_float_hex(c.imag),
        containment_seal=containment_seal,
        route=tuple(route),
        escaped=escaped,
        key_sha256="",
    )
    digest = sha256(_canonical(draft._payload())).hexdigest()
    return RickyKey(**{**draft.__dict__, "key_sha256": digest})


def issue_ricky_key(kernel: ContainmentKernel, c: complex, *, roll: int = 0) -> RickyKey:
    """Issue Ricky only from verified containment, before plasma arm."""
    if kernel.phase != Phase.CONTAINMENT_VERIFIED:
        raise ContainmentError("Ricky denied: key issuance requires verified containment before plasma arm")
    if not kernel.boundary_seal or not kernel.guard():
        raise ContainmentError("Ricky denied: containment guard failed")
    return _build_key(complex(c), kernel.boundary_seal, roll=roll)
