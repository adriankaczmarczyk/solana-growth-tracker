"""Terminal tables and Markdown reports."""

from __future__ import annotations

import os
import sys
from typing import Callable, List, Optional, Sequence

from .growth import momentum_label, rank_by_momentum
from .models import Protocol, Snapshot

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"


def use_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def paint(text: str, code: str) -> str:
    return code + text + RESET if use_color() else text


def fmt_usd(value: Optional[float], precision: int = 2) -> str:
    if value is None:
        return "-"
    magnitude = abs(value)
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if magnitude >= threshold:
            return "${:,.{}f}{}".format(value / threshold, precision, suffix)
    return "${:,.0f}".format(value)


def fmt_pct(value: Optional[float], colored: bool = True) -> str:
    if value is None:
        return "-"
    text = "{:+.1f}%".format(value)
    if not colored:
        return text
    return paint(text, GREEN if value >= 0 else RED)


def fmt_num(value: Optional[float], precision: int = 1) -> str:
    return "-" if value is None else "{:,.{}f}".format(value, precision)


def _visible_len(text: str) -> int:
    length, in_escape = 0, False
    for char in text:
        if in_escape:
            in_escape = char != "m"
        elif char == "\033":
            in_escape = True
        else:
            length += 1
    return length


def table(headers: Sequence[str], rows: Sequence[Sequence[str]], right_align: Sequence[int] = ()) -> str:
    if not rows:
        return paint("  (no matching protocols)", DIM)
    widths = [_visible_len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _visible_len(cell))

    def line(cells: Sequence[str], bold: bool = False) -> str:
        parts = []
        for i, cell in enumerate(cells):
            pad = " " * (widths[i] - _visible_len(cell))
            parts.append(pad + cell if i in right_align else cell + pad)
        text = "  ".join(parts).rstrip()
        return paint(text, BOLD) if bold else text

    out = [line(headers, bold=True), paint("─" * min(sum(widths) + 2 * (len(widths) - 1), 160), DIM)]
    out.extend(line(row) for row in rows)
    return "\n".join(out)


def _label_cell(protocol: Protocol) -> str:
    label = momentum_label(protocol.momentum)
    colors = {"breakout": GREEN, "growing": GREEN, "cooling": RED, "declining": RED}
    return paint(label, colors.get(label, DIM))


def render_overview(snapshot: Snapshot) -> str:
    lines = [
        paint("Solana ecosystem — {}".format(snapshot.generated_at), BOLD + CYAN),
        "",
        "  Chain TVL        {}   7d {}   30d {}".format(
            fmt_usd(snapshot.chain_tvl),
            fmt_pct(snapshot.chain_tvl_change_7d),
            fmt_pct(snapshot.chain_tvl_change_30d),
        ),
        "  DEX volume 24h   {}   7d {}   7d-over-7d {}".format(
            fmt_usd(snapshot.dex_volume_24h),
            fmt_usd(snapshot.dex_volume_7d),
            fmt_pct(snapshot.dex_volume_change_7d),
        ),
        "  Aggregator 24h   {}   7d-over-7d {}".format(
            fmt_usd(snapshot.aggregator_volume_24h), fmt_pct(snapshot.aggregator_volume_change_7d)
        ),
        "  Fees 24h         {}   30d {}   revenue 24h {}".format(
            fmt_usd(snapshot.fees_24h), fmt_usd(snapshot.fees_30d), fmt_usd(snapshot.revenue_24h)
        ),
        "  Protocols tracked {}".format(len(snapshot.protocols)),
    ]
    return "\n".join(lines)


def render_tvl(protocols: List[Protocol], limit: int) -> str:
    rows = []
    for i, p in enumerate(protocols[:limit], start=1):
        rows.append([
            str(i),
            p.name[:28],
            p.category[:18],
            fmt_usd(p.tvl),
            fmt_pct(p.tvl_change_1d),
            fmt_pct(p.tvl_change_7d),
            fmt_pct(p.tvl_change_30d),
        ])
    return table(
        ["#", "PROTOCOL", "CATEGORY", "TVL", "1D", "7D", "30D"],
        rows,
        right_align=(0, 3, 4, 5, 6),
    )


def volume_24h(protocol: Protocol) -> Optional[float]:
    """Aggregator flow overlaps DEX flow, so report the larger side, never the sum."""
    values = [v for v in (protocol.volume_24h, protocol.aggregator_volume_24h) if v is not None]
    return max(values) if values else None


def _volume_30d(protocol: Protocol) -> Optional[float]:
    values = [v for v in (protocol.volume_30d, protocol.aggregator_volume_30d) if v is not None]
    return max(values) if values else None


def render_volume(protocols: List[Protocol], limit: int) -> str:
    ranked = sorted(protocols, key=lambda p: volume_24h(p) or 0, reverse=True)
    rows = []
    for i, p in enumerate(ranked[:limit], start=1):
        rows.append([
            str(i),
            p.name[:28],
            fmt_usd(volume_24h(p)),
            fmt_usd(_volume_30d(p)),
            fmt_pct(p.volume_change_7d),
            fmt_usd(p.fees_24h),
            fmt_num(p.capital_turnover, 1) + "x" if p.capital_turnover else "-",
        ])
    return table(
        ["#", "PROTOCOL", "VOL 24H", "VOL 30D", "VOL 7D/7D", "FEES 24H", "TURNOVER"],
        rows,
        right_align=(0, 2, 3, 4, 5, 6),
    )


def render_growth(protocols: List[Protocol], limit: int, include_small: bool = False) -> str:
    scored = rank_by_momentum(protocols, include_small=include_small)
    rows = []
    for i, p in enumerate(scored[:limit], start=1):
        rows.append([
            str(i),
            p.name[:26],
            p.category[:16],
            "{:.1f}".format(p.momentum or 0),
            _label_cell(p),
            fmt_usd(p.tvl),
            fmt_usd(_volume_30d(p)),
            fmt_pct(p.tvl_change_30d),
            fmt_pct(p.volume_change_7d),
            fmt_pct(p.fees_change_30d),
        ])
    return table(
        ["#", "PROTOCOL", "CATEGORY", "SCORE", "TREND", "TVL", "VOL 30D", "TVL 30D", "VOL 7D/7D", "FEES 30D"],
        rows,
        right_align=(0, 3, 5, 6, 7, 8, 9),
    )


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(out)


def markdown_report(snapshot: Snapshot, limit: int = 25) -> str:
    plain: Callable[[Optional[float]], str] = lambda v: fmt_pct(v, colored=False)
    protocols = snapshot.protocols

    sections = [
        "# Solana Growth Tracker",
        "",
        "Snapshot: `{}` · source: [DefiLlama](https://defillama.com/chain/Solana)".format(
            snapshot.generated_at
        ),
        "",
        "## Chain overview",
        "",
        _md_table(
            ["Metric", "Value", "Change"],
            [
                ["Chain TVL", fmt_usd(snapshot.chain_tvl), "7d " + plain(snapshot.chain_tvl_change_7d)],
                ["Chain TVL (30d)", fmt_usd(snapshot.chain_tvl), "30d " + plain(snapshot.chain_tvl_change_30d)],
                ["DEX volume 24h", fmt_usd(snapshot.dex_volume_24h), "7d/7d " + plain(snapshot.dex_volume_change_7d)],
                ["DEX volume 7d", fmt_usd(snapshot.dex_volume_7d), ""],
                [
                    "Aggregator volume 24h",
                    fmt_usd(snapshot.aggregator_volume_24h),
                    "7d/7d " + plain(snapshot.aggregator_volume_change_7d),
                ],
                ["Fees 24h", fmt_usd(snapshot.fees_24h), ""],
                ["Fees 30d", fmt_usd(snapshot.fees_30d), ""],
            ],
        ),
        "",
        "## Fastest growing protocols",
        "",
        "Momentum blends TVL, volume and fee growth into a single 0-100 score "
        "(50 = flat). Protocols below the size floors in "
        "[`growth.py`](src/soltracker/growth.py) are excluded, so a $20k protocol "
        "doubling overnight cannot top the board.",
        "",
    ]

    scored = rank_by_momentum(protocols)
    sections.append(
        _md_table(
            ["#", "Protocol", "Category", "Score", "Trend", "TVL", "Vol 30d", "TVL 30d", "Vol 7d/7d", "Fees 30d"],
            [
                [
                    str(i),
                    p.name,
                    p.category,
                    "{:.1f}".format(p.momentum or 0),
                    momentum_label(p.momentum),
                    fmt_usd(p.tvl),
                    fmt_usd(_volume_30d(p)),
                    plain(p.tvl_change_30d),
                    plain(p.volume_change_7d),
                    plain(p.fees_change_30d),
                ]
                for i, p in enumerate(scored[:limit], start=1)
            ],
        )
    )

    sections += ["", "## Largest protocols by TVL", ""]
    sections.append(
        _md_table(
            ["#", "Protocol", "Category", "TVL", "1d", "7d", "30d"],
            [
                [
                    str(i),
                    p.name,
                    p.category,
                    fmt_usd(p.tvl),
                    plain(p.tvl_change_1d),
                    plain(p.tvl_change_7d),
                    plain(p.tvl_change_30d),
                ]
                for i, p in enumerate(protocols[:limit], start=1)
            ],
        )
    )

    by_volume = sorted(protocols, key=lambda p: volume_24h(p) or 0, reverse=True)
    sections += ["", "## Highest volume protocols", ""]
    sections.append(
        _md_table(
            ["#", "Protocol", "Volume 24h", "Volume 30d", "Vol 7d/7d", "Fees 24h"],
            [
                [
                    str(i),
                    p.name,
                    fmt_usd(volume_24h(p)),
                    fmt_usd(_volume_30d(p)),
                    plain(p.volume_change_7d),
                    fmt_usd(p.fees_24h),
                ]
                for i, p in enumerate(by_volume[:limit], start=1)
            ],
        )
    )

    sections += ["", "---", "", "_Generated by [solana-growth-tracker](README.md)._", ""]
    return "\n".join(sections)
