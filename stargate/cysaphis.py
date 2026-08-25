from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from containment import ContainmentError, ContainmentKernel, Phase
from .ricky import RickyKey, WanderStep, RICKY_PATTERN, roll_pattern

CYSAPHIS_NAME = "Cysaphis"
CYCLE_LENGTH = len(RICKY_PATTERN)
_ALLOWED_PHASES = {Phase.CONTAINMENT_VERIFIED, Phase.PLASMA_ARMED, Phase.PLASMA_ACTIVE}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _float_hex(value: float) -> str:
    return float(value).hex()


@dataclass(frozen=True)
class RollBrick:
    cycle: int
    roll: int
    rolled_pattern: tuple[str, ...]
    start_z_real: str
    start_z_imag: str
    route: tuple[WanderStep, ...]
    escaped: bool
    parent_sha256: str
    brick_sha256: str

    @property
    def start_z(self) -> complex:
        return complex(float.fromhex(self.start_z_real), float.fromhex(self.start_z_imag))

    @property
    def end_z(self) -> complex:
        return self.route[-1].z if self.route else self.start_z

    @property
    def checkpoint_hops(self) -> tuple[int, ...]:
        return tuple(step.hop for step in self.route if step.checkpoint)

    def payload(self) -> dict[str, object]:
        return {
            "cycle": self.cycle,
            "roll": self.roll,
            "rolled_pattern": list(self.rolled_pattern),
            "start_z": [self.start_z_real, self.start_z_imag],
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
            "parent_sha256": self.parent_sha256,
        }

    def verify(self) -> bool:
        return sha256(_canonical(self.payload())).hexdigest() == self.brick_sha256


@dataclass(frozen=True)
class CysaphisChain:
    name: str
    ricky_key_sha256: str
    containment_seal: str
    c_real: str
    c_imag: str
    origin_roll: int
    direction: int
    bricks: tuple[RollBrick, ...]
    escaped: bool
    home_returned: bool
    chain_sha256: str

    @property
    def c(self) -> complex:
        return complex(float.fromhex(self.c_real), float.fromhex(self.c_imag))

    @property
    def total_hops(self) -> int:
        return sum(len(brick.route) for brick in self.bricks)

    def payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ricky_key_sha256": self.ricky_key_sha256,
            "containment_seal": self.containment_seal,
            "c": [self.c_real, self.c_imag],
            "origin_roll": self.origin_roll,
            "direction": self.direction,
            "brick_hashes": [brick.brick_sha256 for brick in self.bricks],
            "escaped": self.escaped,
            "home_returned": self.home_returned,
        }

    def verify(self) -> bool:
        parent = self.ricky_key_sha256
        for index, brick in enumerate(self.bricks, start=1):
            if brick.cycle != index or brick.parent_sha256 != parent or not brick.verify():
                return False
            parent = brick.brick_sha256
        return sha256(_canonical(self.payload())).hexdigest() == self.chain_sha256

    def valid_for(self, kernel: ContainmentKernel) -> bool:
        return (
            self.verify()
            and kernel.phase in _ALLOWED_PHASES
            and bool(kernel.boundary_seal)
            and kernel.boundary_seal == self.containment_seal
        )


def _roll_once(c: complex, start_z: complex, roll: int, cycle: int, parent_sha256: str) -> RollBrick:
    mask = roll_pattern(roll)
    z = start_z
    route: list[WanderStep] = []
    escaped = False

    for hop, symbol in enumerate(mask, start=1):
        z = z * z + c
        escaped = abs(z) > 2.0
        route.append(
            WanderStep(
                hop=hop,
                symbol=symbol,
                z_real=_float_hex(z.real),
                z_imag=_float_hex(z.imag),
                checkpoint=symbol == "|",
                escaped=escaped,
            )
        )
        if escaped:
            break

    draft = RollBrick(
        cycle=cycle,
        roll=roll % CYCLE_LENGTH,
        rolled_pattern=mask,
        start_z_real=_float_hex(start_z.real),
        start_z_imag=_float_hex(start_z.imag),
        route=tuple(route),
        escaped=escaped,
        parent_sha256=parent_sha256,
        brick_sha256="",
    )
    digest = sha256(_canonical(draft.payload())).hexdigest()
    return RollBrick(**{**draft.__dict__, "brick_sha256": digest})


def issue_cysaphis(
    kernel: ContainmentKernel,
    ricky: RickyKey,
    *,
    rolls: int = CYCLE_LENGTH,
    direction: int = 1,
) -> CysaphisChain:
    """Continue Ricky's Mandelbrot orbit through hash-linked rolled bricks."""
    if kernel.phase != Phase.CONTAINMENT_VERIFIED:
        raise ContainmentError("Cysaphis denied: issuance requires verified containment before plasma arm")
    if not ricky.valid_for(kernel):
        raise ContainmentError("Cysaphis denied: Ricky key is invalid for this containment")
    if ricky.escaped:
        raise ContainmentError("Cysaphis denied: Ricky already escaped")
    if rolls < 1 or rolls > CYCLE_LENGTH:
        raise ValueError(f"rolls must be between 1 and {CYCLE_LENGTH}")
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or +1")

    z = ricky.route[-1].z if ricky.route else 0j
    parent = ricky.key_sha256
    bricks: list[RollBrick] = []
    escaped = False

    for cycle in range(1, rolls + 1):
        roll = (ricky.roll + direction * cycle) % CYCLE_LENGTH
        brick = _roll_once(ricky.c, z, roll, cycle, parent)
        bricks.append(brick)
        parent = brick.brick_sha256
        z = brick.end_z
        if brick.escaped:
            escaped = True
            break

    home_returned = (
        not escaped
        and len(bricks) == CYCLE_LENGTH
        and bricks[-1].roll == ricky.roll
    )

    draft = CysaphisChain(
        name=CYSAPHIS_NAME,
        ricky_key_sha256=ricky.key_sha256,
        containment_seal=ricky.containment_seal,
        c_real=_float_hex(ricky.c.real),
        c_imag=_float_hex(ricky.c.imag),
        origin_roll=ricky.roll,
        direction=direction,
        bricks=tuple(bricks),
        escaped=escaped,
        home_returned=home_returned,
        chain_sha256="",
    )
    digest = sha256(_canonical(draft.payload())).hexdigest()
    return CysaphisChain(**{**draft.__dict__, "chain_sha256": digest})
