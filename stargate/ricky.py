from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable

try:
    from containment import ContainmentKernel, Phase
except Exception:
    ContainmentKernel = object  # type: ignore
    Phase = None  # type: ignore


RICKY_SOURCE = "{. . | | . . | . .}"


def _parse_brick(source: str) -> tuple[tuple[str, ...], ...]:
    cells = tuple(ch for ch in source if ch in ".|")
    if len(cells) != 9:
        raise ValueError("a star-gate brick must contain exactly 9 '.'/'|' cells")
    rows = tuple(tuple(cells[i:i + 3]) for i in range(0, 9, 3))
    if rows[1][1] != ".":
        raise ValueError("the center cell must remain open")
    return rows


@dataclass(frozen=True)
class RickyKey:
    """The first passive star-gate brick: a rollable 3x3 key stencil."""

    cells: tuple[tuple[str, ...], ...] = _parse_brick(RICKY_SOURCE)
    quarter_turns: int = 0
    name: str = "Ricky"

    def roll(self, turns: int = 1) -> "RickyKey":
        turns %= 4
        grid = self.cells
        for _ in range(turns):
            grid = tuple(tuple(grid[2 - r][c] for r in range(3)) for c in range(3))
        return RickyKey(grid, (self.quarter_turns + turns) % 4, self.name)

    @property
    def glyph(self) -> str:
        return "{" + " ".join(cell for row in self.cells for cell in row) + "}"

    @property
    def compact(self) -> str:
        return "".join(cell for row in self.cells for cell in row)

    @property
    def seal(self) -> str:
        body = f"{self.name}|{self.quarter_turns}|{self.compact}".encode("utf-8")
        return sha256(body).hexdigest()

    @property
    def walls(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (row - 1, col - 1)
            for row in range(3)
            for col in range(3)
            if self.cells[row][col] == "|"
        )

    @property
    def openings(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (row - 1, col - 1)
            for row in range(3)
            for col in range(3)
            if self.cells[row][col] == "." and (row, col) != (1, 1)
        )

    def admission_token(self, containment: ContainmentKernel) -> str:
        if Phase is None or getattr(containment, "phase", None) != Phase.CONTAINMENT_VERIFIED:
            raise RuntimeError("Ricky denied: containment must be verified before key admission")
        boundary_seal = getattr(containment, "boundary_seal", None)
        if not boundary_seal:
            raise RuntimeError("Ricky denied: containment seal missing")
        return sha256(f"RICKY|{self.seal}|{boundary_seal}".encode("utf-8")).hexdigest()


def mandelbrot_escape(c: complex, max_iter: int = 64) -> int:
    z = 0j
    for i in range(max_iter):
        z = z * z + c
        if (z.real * z.real + z.imag * z.imag) > 4.0:
            return i + 1
    return max_iter


@dataclass(frozen=True)
class WanderStep:
    index: int
    position: complex
    escape: int
    roll: int
    key: str


class MandelbrotWanderer:
    """Deterministic contour-seeking walker driven by Ricky's rolled stencil."""

    def __init__(
        self,
        start: complex = complex(-0.75, 0.10),
        step_size: float = 0.01,
        max_iter: int = 64,
        target_escape: int | None = None,
        key: RickyKey | None = None,
    ) -> None:
        if step_size <= 0:
            raise ValueError("step_size must be positive")
        if max_iter < 4:
            raise ValueError("max_iter must be >= 4")
        self.position = start
        self.step_size = float(step_size)
        self.max_iter = int(max_iter)
        self.target_escape = int(target_escape if target_escape is not None else max_iter * 3 // 4)
        self.key = key or RickyKey()
        self.index = 0
        self.visited: set[tuple[float, float]] = {self._stamp(start)}

    @staticmethod
    def _stamp(z: complex) -> tuple[float, float]:
        return (round(z.real, 12), round(z.imag, 12))

    def _candidates(self) -> Iterable[tuple[int, complex, int]]:
        for order, (dr, dc) in enumerate(self.key.openings):
            candidate = self.position + complex(dc * self.step_size, -dr * self.step_size)
            yield order, candidate, mandelbrot_escape(candidate, self.max_iter)

    def step(self) -> WanderStep:
        candidates = list(self._candidates())
        if not candidates:
            raise RuntimeError("Ricky has no open neighbor cells")

        def score(item: tuple[int, complex, int]) -> tuple[int, int, int, float, float]:
            order, candidate, escape = item
            revisit = 1 if self._stamp(candidate) in self.visited else 0
            boundary_distance = abs(escape - self.target_escape)
            return (revisit, boundary_distance, order, candidate.real, candidate.imag)

        _, chosen, escape = min(candidates, key=score)
        state = WanderStep(
            index=self.index,
            position=chosen,
            escape=escape,
            roll=self.key.quarter_turns,
            key=self.key.compact,
        )
        self.position = chosen
        self.visited.add(self._stamp(chosen))
        self.index += 1
        self.key = self.key.roll(1)
        return state

    def walk(self, steps: int) -> list[WanderStep]:
        if steps < 0:
            raise ValueError("steps cannot be negative")
        return [self.step() for _ in range(steps)]
