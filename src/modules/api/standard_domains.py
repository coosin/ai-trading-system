from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List


STANDARD_DOMAINS: List[str] = [
    "system",
    "account",
    "market",
    "data",
    "strategy",
    "risk",
    "execution",
    "trades",
    "memory",
    "learning",
    "agents",
    "commander",
    "plugins",
]


@dataclass(frozen=True)
class CapabilityRoute:
    capability: str
    domain: str
    method: str
    path: str
    summary: str
    status: str = "canonical"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def assert_unique_capabilities(routes: Iterable[CapabilityRoute]) -> None:
    seen: Dict[str, str] = {}
    for route in routes:
        if route.status != "canonical":
            continue
        previous = seen.get(route.capability)
        if previous and previous != route.path:
            raise ValueError(f"duplicate canonical capability {route.capability}: {previous} vs {route.path}")
        seen[route.capability] = route.path

