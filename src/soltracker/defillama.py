"""Typed access to the DefiLlama endpoints this tracker depends on."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .http import get_json, get_json_many

BASE = "https://api.llama.fi"
CHAIN = "Solana"

_OVERVIEW_QUERY = "excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true"


class DefiLlama:
    def __init__(self, cache_dir: Optional[str] = None, cache_ttl: int = 900, workers: int = 8):
        self.cache_dir = cache_dir
        self.cache_ttl = cache_ttl
        self.workers = workers

    def _get(self, path: str, ttl: Optional[int] = None) -> Any:
        return get_json(
            BASE + path,
            cache_dir=self.cache_dir,
            cache_ttl=self.cache_ttl if ttl is None else ttl,
        )

    # --- TVL -------------------------------------------------------------

    def protocols(self) -> List[Dict[str, Any]]:
        """Every protocol DefiLlama tracks, across all chains."""
        return self._get("/protocols")

    def chain_overview(self) -> Dict[str, Any]:
        for chain in self._get("/v2/chains"):
            if chain.get("name") == CHAIN:
                return chain
        return {}

    def chain_tvl_history(self) -> List[Dict[str, Any]]:
        """Daily [{date, tvl}] for the whole Solana chain."""
        return self._get("/v2/historicalChainTvl/" + CHAIN)

    def protocol_histories(self, slugs: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Solana-only daily TVL series per protocol slug, fetched concurrently.

        Protocol payloads are large and rarely change intraday, so they get a
        longer cache TTL than the overview endpoints.
        """
        urls = ["{}/protocol/{}".format(BASE, slug) for slug in slugs]
        results = get_json_many(
            urls,
            workers=self.workers,
            cache_dir=self.cache_dir,
            cache_ttl=max(self.cache_ttl, 6 * 3600),
        )
        histories: Dict[str, List[Dict[str, Any]]] = {}
        for url, payload, error in results:
            if error or not isinstance(payload, dict):
                continue
            slug = url.rsplit("/", 1)[-1]
            series = (payload.get("chainTvls") or {}).get(CHAIN, {}).get("tvl") or []
            histories[slug] = [
                {"date": int(point["date"]), "tvl": float(point["totalLiquidityUSD"])}
                for point in series
                if point.get("date") is not None and point.get("totalLiquidityUSD") is not None
            ]
        return histories

    # --- Volume / fees ---------------------------------------------------

    def dex_overview(self) -> Dict[str, Any]:
        return self._get("/overview/dexs/{}?{}".format(CHAIN.lower(), _OVERVIEW_QUERY))

    def aggregator_overview(self) -> Dict[str, Any]:
        """Swap aggregators (Jupiter et al). Volume here overlaps DEX volume by
        design — an aggregator routes into the same pools — so it is tracked as
        a separate metric rather than summed into chain volume."""
        return self._get("/overview/aggregators/{}?{}".format(CHAIN.lower(), _OVERVIEW_QUERY))

    def fees_overview(self) -> Dict[str, Any]:
        return self._get(
            "/overview/fees/{}?{}&dataType=dailyFees".format(CHAIN.lower(), _OVERVIEW_QUERY)
        )

    def revenue_overview(self) -> Dict[str, Any]:
        return self._get(
            "/overview/fees/{}?{}&dataType=dailyRevenue".format(CHAIN.lower(), _OVERVIEW_QUERY)
        )
