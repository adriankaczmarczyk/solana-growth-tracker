"""Data shapes shared between collection, scoring and rendering."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Protocol:
    slug: str
    name: str
    category: str = "Unknown"
    url: str = ""
    logo: str = ""
    symbol: str = ""
    mcap: Optional[float] = None

    tvl: Optional[float] = None
    tvl_change_1d: Optional[float] = None
    tvl_change_7d: Optional[float] = None
    tvl_change_30d: Optional[float] = None
    tvl_change_90d: Optional[float] = None
    tvl_history: List[Dict[str, float]] = field(default_factory=list)

    volume_24h: Optional[float] = None
    volume_7d: Optional[float] = None
    volume_30d: Optional[float] = None
    volume_change_7d: Optional[float] = None
    volume_change_30d: Optional[float] = None

    aggregator_volume_24h: Optional[float] = None
    aggregator_volume_30d: Optional[float] = None

    fees_24h: Optional[float] = None
    fees_30d: Optional[float] = None
    fees_change_30d: Optional[float] = None
    revenue_24h: Optional[float] = None
    revenue_30d: Optional[float] = None

    momentum: Optional[float] = None
    momentum_signals: Dict[str, float] = field(default_factory=dict)
    capital_turnover: Optional[float] = None

    def to_dict(self, include_history: bool = True) -> Dict[str, Any]:
        data = asdict(self)
        if not include_history:
            data.pop("tvl_history", None)
        return data


@dataclass
class Snapshot:
    generated_at: str
    chain_tvl: Optional[float]
    chain_tvl_change_7d: Optional[float]
    chain_tvl_change_30d: Optional[float]
    dex_volume_24h: Optional[float]
    dex_volume_7d: Optional[float]
    dex_volume_change_7d: Optional[float]
    aggregator_volume_24h: Optional[float]
    aggregator_volume_change_7d: Optional[float]
    fees_24h: Optional[float]
    fees_30d: Optional[float]
    revenue_24h: Optional[float]
    chain_tvl_history: List[Dict[str, float]]
    protocols: List[Protocol]

    def to_dict(self, include_history: bool = True) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "chain": {
                "name": "Solana",
                "tvl": self.chain_tvl,
                "tvl_change_7d": self.chain_tvl_change_7d,
                "tvl_change_30d": self.chain_tvl_change_30d,
                "dex_volume_24h": self.dex_volume_24h,
                "dex_volume_7d": self.dex_volume_7d,
                "dex_volume_change_7d": self.dex_volume_change_7d,
                "aggregator_volume_24h": self.aggregator_volume_24h,
                "aggregator_volume_change_7d": self.aggregator_volume_change_7d,
                "fees_24h": self.fees_24h,
                "fees_30d": self.fees_30d,
                "revenue_24h": self.revenue_24h,
                "tvl_history": self.chain_tvl_history if include_history else [],
            },
            "protocols": [p.to_dict(include_history=include_history) for p in self.protocols],
        }
