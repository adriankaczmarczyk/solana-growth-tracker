"""Write snapshots out as JSON, CSV and an append-only history log."""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, List

from .growth import is_established, momentum_label, rank_by_momentum
from .models import Snapshot

CSV_COLUMNS = [
    "slug",
    "name",
    "category",
    "tvl",
    "tvl_change_1d",
    "tvl_change_7d",
    "tvl_change_30d",
    "tvl_change_90d",
    "volume_24h",
    "volume_7d",
    "volume_30d",
    "volume_change_7d",
    "volume_change_30d",
    "aggregator_volume_24h",
    "aggregator_volume_30d",
    "fees_24h",
    "fees_30d",
    "fees_change_30d",
    "revenue_24h",
    "revenue_30d",
    "mcap",
    "capital_turnover",
    "momentum",
]


def _ensure_parent(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)


def write_json(snapshot: Snapshot, path: str, include_history: bool = True) -> str:
    _ensure_parent(path)
    payload = snapshot.to_dict(include_history=include_history)
    for record, protocol in zip(snapshot.protocols, payload["protocols"]):
        protocol["trend"] = momentum_label(protocol.get("momentum"))
        protocol["established"] = is_established(record)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    return path


def write_csv(snapshot: Snapshot, path: str) -> str:
    _ensure_parent(path)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for protocol in snapshot.protocols:
            writer.writerow(protocol.to_dict(include_history=False))
    return path


def write_markdown(text: str, path: str) -> str:
    _ensure_parent(path)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def append_history(snapshot: Snapshot, path: str) -> str:
    """Append one line of chain-level metrics per run, deduped by day.

    This is what turns the repo itself into a longitudinal dataset: every CI
    run leaves a durable record that no API backfill can revise away.
    """
    _ensure_parent(path)
    entry: Dict[str, Any] = {
        "date": snapshot.generated_at[:10],
        "generated_at": snapshot.generated_at,
        "chain_tvl": snapshot.chain_tvl,
        "dex_volume_24h": snapshot.dex_volume_24h,
        "aggregator_volume_24h": snapshot.aggregator_volume_24h,
        "fees_24h": snapshot.fees_24h,
        "revenue_24h": snapshot.revenue_24h,
        "protocols_tracked": len(snapshot.protocols),
        "top_movers": [
            {"slug": p.slug, "name": p.name, "momentum": p.momentum}
            for p in rank_by_momentum(snapshot.protocols)[:10]
        ],
    }

    rows: List[Dict[str, Any]] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    rows = [row for row in rows if row.get("date") != entry["date"]]
    rows.append(entry)
    rows.sort(key=lambda row: row.get("date") or "")

    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    return path
