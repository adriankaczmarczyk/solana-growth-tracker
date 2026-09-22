"""Collect Solana TVL, volume and fee data into a single ranked snapshot."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, Iterable, List, Optional

from .defillama import DefiLlama
from .growth import score_protocol
from .models import Protocol, Snapshot

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _key(value: str) -> str:
    return _NON_ALNUM.sub("", (value or "").lower())


def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None or previous <= 0:
        return None
    return (current - previous) / previous * 100.0


def _value_at(history: List[Dict[str, float]], days_ago: int) -> Optional[float]:
    """TVL closest to `days_ago` days before the last point in the series."""
    if not history:
        return None
    target = history[-1]["date"] - days_ago * 86400
    if history[0]["date"] > target:
        return None
    best = min(history, key=lambda point: abs(point["date"] - target))
    # Reject matches more than three days off; the series has a gap there.
    return best["tvl"] if abs(best["date"] - target) <= 3 * 86400 else None


class _Index:
    """Resolves overview-endpoint rows onto the protocol records built from TVL."""

    def __init__(self) -> None:
        self.by_slug: Dict[str, str] = {}
        self.by_id: Dict[str, str] = {}
        self.by_name: Dict[str, str] = {}

    def add(self, slug: str, llama_id: Any, name: str) -> None:
        self.by_slug[_key(slug)] = slug
        if llama_id is not None:
            self.by_id[str(llama_id)] = slug
        self.by_name.setdefault(_key(name), slug)

    def resolve(self, row: Dict[str, Any]) -> Optional[str]:
        for candidate in (
            self.by_slug.get(_key(row.get("slug") or "")),
            self.by_id.get(str(row.get("defillamaId"))),
            self.by_name.get(_key(row.get("displayName") or "")),
            self.by_name.get(_key(row.get("name") or "")),
        ):
            if candidate:
                return candidate
        return None


def _base_records(raw_protocols: Iterable[Dict[str, Any]], index: "_Index") -> Dict[str, Protocol]:
    records: Dict[str, Protocol] = {}
    for row in raw_protocols:
        chains = row.get("chains") or []
        if "Solana" not in chains:
            continue
        tvl = _num((row.get("chainTvls") or {}).get("Solana"))
        slug = row.get("slug") or _key(row.get("name") or "")
        if not slug:
            continue
        records[slug] = Protocol(
            slug=slug,
            name=row.get("name") or slug,
            category=row.get("category") or "Unknown",
            url=row.get("url") or "",
            logo=row.get("logo") or "",
            symbol=(row.get("symbol") or "").replace("-", ""),
            mcap=_num(row.get("mcap")),
            tvl=tvl,
            # change_* on /protocols are chain-agnostic, but for Solana-native
            # protocols (the vast majority here) they track the Solana series.
            tvl_change_1d=_num(row.get("change_1d")),
            tvl_change_7d=_num(row.get("change_7d")),
        )
        index.add(slug, row.get("id"), records[slug].name)
    return records


def _merge_overview(
    records: Dict[str, Protocol],
    index: _Index,
    overview: Dict[str, Any],
    assign: str,
) -> None:
    for row in (overview or {}).get("protocols") or []:
        slug = index.resolve(row)
        if slug is None:
            slug = row.get("slug") or _key(row.get("name") or "")
            if not slug:
                continue
            records[slug] = Protocol(
                slug=slug,
                name=row.get("displayName") or row.get("name") or slug,
                category=row.get("category") or "Unknown",
                logo=row.get("logo") or "",
            )
            index.add(slug, row.get("defillamaId"), records[slug].name)

        record = records[slug]
        if assign == "dex":
            record.volume_24h = _num(row.get("total24h"))
            record.volume_7d = _num(row.get("total7d"))
            record.volume_30d = _num(row.get("total30d"))
            record.volume_change_7d = _num(row.get("change_7dover7d"))
            record.volume_change_30d = _num(row.get("change_30dover30d"))
        elif assign == "aggregator":
            record.aggregator_volume_24h = _num(row.get("total24h"))
            record.aggregator_volume_30d = _num(row.get("total30d"))
            if record.volume_change_7d is None:
                record.volume_change_7d = _num(row.get("change_7dover7d"))
            if record.volume_change_30d is None:
                record.volume_change_30d = _num(row.get("change_30dover30d"))
        elif assign == "fees":
            record.fees_24h = _num(row.get("total24h"))
            record.fees_30d = _num(row.get("total30d"))
            record.fees_change_30d = _num(row.get("change_30dover30d"))
        elif assign == "revenue":
            record.revenue_24h = _num(row.get("total24h"))
            record.revenue_30d = _num(row.get("total30d"))


# Exchange wallet balances are reported against Solana but are not ecosystem
# DeFi: Binance alone books more "TVL" than the entire chain.
DEFAULT_EXCLUDED_CATEGORIES = ("CEX", "Chain")


def _is_relevant(record: Protocol, min_tvl: float, min_volume: float) -> bool:
    return (
        (record.tvl or 0) >= min_tvl
        or (record.volume_24h or 0) >= min_volume
        or (record.aggregator_volume_24h or 0) >= min_volume
        or (record.fees_30d or 0) >= min_volume / 30.0
    )


def collect(
    client: DefiLlama,
    history_limit: int = 60,
    min_tvl: float = 1_000_000.0,
    min_volume: float = 1_000_000.0,
    exclude_categories: Iterable[str] = DEFAULT_EXCLUDED_CATEGORIES,
) -> Snapshot:
    """Build a full snapshot. `history_limit` protocols get a TVL series fetched."""
    index = _Index()
    records = _base_records(client.protocols(), index)

    dex = client.dex_overview()
    aggregators = _safe(client.aggregator_overview) or {}
    fees = client.fees_overview()
    revenue = _safe(client.revenue_overview)

    _merge_overview(records, index, dex, "dex")
    _merge_overview(records, index, aggregators, "aggregator")
    _merge_overview(records, index, fees, "fees")
    _merge_overview(records, index, revenue, "revenue")

    blocked = {_key(name) for name in exclude_categories}
    relevant = [
        r
        for r in records.values()
        if _key(r.category) not in blocked and _is_relevant(r, min_tvl, min_volume)
    ]

    if history_limit > 0:
        ranked = sorted(
            relevant,
            key=lambda r: max(r.tvl or 0, r.volume_24h or 0, r.aggregator_volume_24h or 0),
            reverse=True,
        )[:history_limit]
        histories = client.protocol_histories([r.slug for r in ranked])
        for record in ranked:
            series = histories.get(record.slug) or []
            if not series:
                continue
            record.tvl_history = series[-400:]
            latest = series[-1]["tvl"]
            record.tvl_change_30d = _pct_change(latest, _value_at(series, 30))
            record.tvl_change_90d = _pct_change(latest, _value_at(series, 90))

    for record in relevant:
        if record.tvl and record.volume_30d:
            record.capital_turnover = record.volume_30d / record.tvl
        record.momentum, record.momentum_signals = score_protocol(record)

    relevant.sort(key=lambda r: (r.tvl or 0, r.volume_24h or 0), reverse=True)

    chain = client.chain_overview()
    chain_history_raw = _safe(client.chain_tvl_history) or []
    chain_history = [
        {"date": int(p["date"]), "tvl": float(p["tvl"])}
        for p in chain_history_raw
        if p.get("date") is not None and p.get("tvl") is not None
    ]
    chain_tvl = _num(chain.get("tvl"))
    if chain_tvl is None and chain_history:
        chain_tvl = chain_history[-1]["tvl"]

    return Snapshot(
        generated_at=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        chain_tvl=chain_tvl,
        chain_tvl_change_7d=_pct_change(chain_tvl, _value_at(chain_history, 7)),
        chain_tvl_change_30d=_pct_change(chain_tvl, _value_at(chain_history, 30)),
        dex_volume_24h=_num(dex.get("total24h")),
        dex_volume_7d=_num(dex.get("total7d")),
        dex_volume_change_7d=_num(dex.get("change_7dover7d")),
        aggregator_volume_24h=_num(aggregators.get("total24h")),
        aggregator_volume_change_7d=_num(aggregators.get("change_7dover7d")),
        fees_24h=_num(fees.get("total24h")),
        fees_30d=_num(fees.get("total30d")),
        revenue_24h=_num((revenue or {}).get("total24h")),
        chain_tvl_history=chain_history[-730:],
        protocols=relevant,
    )


def _safe(fn: Any) -> Any:
    """Optional endpoints should degrade to missing data, not kill the run."""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None
