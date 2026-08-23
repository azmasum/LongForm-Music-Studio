"""Random seed system.

Every composition carries a master seed. Sub-seeds for independent generator
subsystems are derived deterministically so that identical generator versions
and parameters reproduce identical results.
"""
from __future__ import annotations

import hashlib
import random

SEED_RANGE = 10_000_000


class SeedSystem:
    def __init__(self, seed: int | str | None = None) -> None:
        self.seed = self.normalize(seed) if seed is not None else self.random_seed()

    @staticmethod
    def random_seed() -> int:
        return random.SystemRandom().randrange(0, SEED_RANGE)

    @staticmethod
    def normalize(value: int | str) -> int:
        if isinstance(value, bool):
            raise TypeError("seed must be an integer or string")
        if isinstance(value, int):
            return value % SEED_RANGE
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text) % SEED_RANGE
        digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % SEED_RANGE

    def derive(self, namespace: str, index: int = 0) -> int:
        key = f"{namespace}:{index}:{self.seed}".encode()
        digest = hashlib.blake2b(key, digest_size=8).digest()
        return int.from_bytes(digest, "big") % SEED_RANGE

    def copy_with(self, new_seed: int | str) -> SeedSystem:
        return SeedSystem(new_seed)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"SeedSystem(seed={self.seed})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SeedSystem) and other.seed == self.seed

    def __hash__(self) -> int:
        return hash(self.seed)
