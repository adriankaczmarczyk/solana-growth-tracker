"""Momentum scoring: turns raw percentage changes into one comparable 0-100 number."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:  # pragma: no cover
    from .models import Protocol

# Each signal answers "is this protocol growing?" from a different angle.
# TVL is slow and sticky, volume is fast and noisy, fees prove real usage.
SIGNAL_WEIGHTS = {
    "tvl_7d": 0.20,
    "tvl_30d": 0.22,
    "volume_7d": 0.22,
    "volume_30d": 0.16,
    "fees_30d": 0.20,
}

# A signal needs this much weight covered before a score is meaningful.
MIN_COVERAGE = 0.35


def squash(pct_change: float) -> float:
    """Map a percentage change onto 0-100, with 0% change sitting at 50.

    tanh keeps a 10x pump from drowning out every other signal, while still
    ordering it above a 2x. Scale of 60 means +60% lands near 88.
    """
    return 50.0 * (1.0 + math.tanh(pct_change / 60.0))


def score_protocol(protocol: "Protocol") -> Tuple[Optional[float], Dict[str, float]]:
    raw = {
        "tvl_7d": protocol.tvl_change_7d,
        "tvl_30d": protocol.tvl_change_30d,
        "volume_7d": protocol.volume_change_7d,
        "volume_30d": protocol.volume_change_30d,
        "fees_30d": protocol.fees_change_30d,
    }

    signals: Dict[str, float] = {}
    total = 0.0
    covered = 0.0
    for name, weight in SIGNAL_WEIGHTS.items():
        value = raw.get(name)
        if value is None:
            continue
        # Clamp absurd readings: a protocol going from $12 to $120k of TVL is
        # a rounding artifact, not momentum.
        clamped = max(-95.0, min(1000.0, value))
        points = squash(clamped)
        signals[name] = round(points, 1)
        total += points * weight
        covered += weight

    if covered < MIN_COVERAGE:
        return None, signals
    return round(total / covered, 1), signals


# A protocol that went from $8k to $400k of fees is up 4900% and means nothing.
# The growth board only ranks protocols that clear one of these floors.
ESTABLISHED_TVL = 5_000_000.0
ESTABLISHED_VOLUME_30D = 100_000_000.0
ESTABLISHED_FEES_30D = 250_000.0


def is_established(protocol: "Protocol") -> bool:
    return (
        (protocol.tvl or 0) >= ESTABLISHED_TVL
        or (protocol.volume_30d or 0) >= ESTABLISHED_VOLUME_30D
        or (protocol.aggregator_volume_30d or 0) >= ESTABLISHED_VOLUME_30D
        or (protocol.fees_30d or 0) >= ESTABLISHED_FEES_30D
    )


def rank_by_momentum(protocols: List["Protocol"], include_small: bool = False) -> List["Protocol"]:
    candidates = [
        p
        for p in protocols
        if p.momentum is not None and (include_small or is_established(p))
    ]
    candidates.sort(key=lambda p: p.momentum or 0, reverse=True)
    return candidates


def momentum_label(score: Optional[float]) -> str:
    if score is None:
        return "no data"
    if score >= 70:
        return "breakout"
    if score >= 58:
        return "growing"
    if score >= 44:
        return "flat"
    if score >= 30:
        return "cooling"
    return "declining"
