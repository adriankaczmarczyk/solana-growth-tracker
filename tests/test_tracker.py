"""Offline tests: every fixture is inline, nothing here touches the network."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from soltracker import aggregate, export, growth, render  # noqa: E402
from soltracker.models import Protocol  # noqa: E402


def make_protocol(**kwargs):
    defaults = {"slug": "test", "name": "Test"}
    defaults.update(kwargs)
    return Protocol(**defaults)


class TestSquash(unittest.TestCase):
    def test_zero_change_is_neutral(self):
        self.assertAlmostEqual(growth.squash(0.0), 50.0)

    def test_monotonic_and_bounded(self):
        values = [growth.squash(x) for x in (-500, -100, -10, 0, 10, 100, 500)]
        self.assertEqual(values, sorted(values))
        self.assertGreater(values[0], 0.0)
        self.assertLess(values[-1], 100.0)

    def test_gain_and_loss_are_symmetric_around_fifty(self):
        self.assertAlmostEqual(growth.squash(60) - 50, 50 - growth.squash(-60), places=6)


class TestScoring(unittest.TestCase):
    def test_insufficient_signals_yield_no_score(self):
        score, signals = growth.score_protocol(make_protocol(tvl_change_7d=50.0))
        self.assertIsNone(score)
        self.assertEqual(set(signals), {"tvl_7d"})

    def test_growth_scores_above_fifty(self):
        score, _ = growth.score_protocol(
            make_protocol(tvl_change_7d=40.0, tvl_change_30d=90.0, fees_change_30d=120.0)
        )
        self.assertGreater(score, 50.0)

    def test_decline_scores_below_fifty(self):
        score, _ = growth.score_protocol(
            make_protocol(tvl_change_7d=-30.0, tvl_change_30d=-45.0, volume_change_7d=-20.0)
        )
        self.assertLess(score, 50.0)

    def test_extreme_outlier_is_clamped(self):
        wild, _ = growth.score_protocol(
            make_protocol(tvl_change_7d=50_000.0, tvl_change_30d=50_000.0, fees_change_30d=50_000.0)
        )
        strong, _ = growth.score_protocol(
            make_protocol(tvl_change_7d=1000.0, tvl_change_30d=1000.0, fees_change_30d=1000.0)
        )
        self.assertEqual(wild, strong)

    def test_labels_track_score_bands(self):
        self.assertEqual(growth.momentum_label(None), "no data")
        self.assertEqual(growth.momentum_label(85.0), "breakout")
        self.assertEqual(growth.momentum_label(50.0), "flat")
        self.assertEqual(growth.momentum_label(10.0), "declining")


class TestEstablished(unittest.TestCase):
    def test_tiny_protocol_is_excluded(self):
        self.assertFalse(growth.is_established(make_protocol(tvl=20_000.0, fees_30d=100.0)))

    def test_any_single_threshold_qualifies(self):
        self.assertTrue(growth.is_established(make_protocol(tvl=9_000_000.0)))
        self.assertTrue(growth.is_established(make_protocol(volume_30d=500_000_000.0)))
        self.assertTrue(growth.is_established(make_protocol(fees_30d=400_000.0)))

    def test_ranking_drops_unqualified_protocols(self):
        big = make_protocol(slug="big", tvl=50_000_000.0, momentum=60.0)
        tiny = make_protocol(slug="tiny", tvl=1000.0, momentum=99.0)
        self.assertEqual([p.slug for p in growth.rank_by_momentum([big, tiny])], ["big"])
        self.assertEqual(
            [p.slug for p in growth.rank_by_momentum([big, tiny], include_small=True)],
            ["tiny", "big"],
        )


class TestHelpers(unittest.TestCase):
    def test_pct_change_guards_against_zero_base(self):
        self.assertIsNone(aggregate._pct_change(100.0, 0.0))
        self.assertIsNone(aggregate._pct_change(None, 10.0))
        self.assertAlmostEqual(aggregate._pct_change(150.0, 100.0), 50.0)

    def test_value_at_finds_nearest_day(self):
        now = 1_700_000_000
        series = [{"date": now - day * 86400, "tvl": float(100 - day)} for day in range(60, -1, -1)]
        self.assertAlmostEqual(aggregate._value_at(series, 30), 70.0)

    def test_value_at_rejects_short_series(self):
        now = 1_700_000_000
        series = [{"date": now - day * 86400, "tvl": 1.0} for day in range(5, -1, -1)]
        self.assertIsNone(aggregate._value_at(series, 30))

    def test_num_rejects_nonsense(self):
        self.assertIsNone(aggregate._num("abc"))
        self.assertIsNone(aggregate._num(None))
        self.assertIsNone(aggregate._num(float("inf")))
        self.assertEqual(aggregate._num("12.5"), 12.5)

    def test_index_resolves_by_slug_id_and_name(self):
        index = aggregate._Index()
        index.add("kamino-lend", 3183, "Kamino Lend")
        self.assertEqual(index.resolve({"slug": "kamino-lend"}), "kamino-lend")
        self.assertEqual(index.resolve({"defillamaId": "3183"}), "kamino-lend")
        self.assertEqual(index.resolve({"displayName": "Kamino  Lend"}), "kamino-lend")
        self.assertIsNone(index.resolve({"name": "Something Else"}))


class TestFormatting(unittest.TestCase):
    def test_usd_scales_by_magnitude(self):
        self.assertEqual(render.fmt_usd(1_234_000_000), "$1.23B")
        self.assertEqual(render.fmt_usd(45_600_000), "$45.60M")
        self.assertEqual(render.fmt_usd(None), "-")

    def test_pct_is_signed(self):
        self.assertEqual(render.fmt_pct(12.34, colored=False), "+12.3%")
        self.assertEqual(render.fmt_pct(-1.0, colored=False), "-1.0%")

    def test_volume_takes_the_larger_side_never_the_sum(self):
        protocol = make_protocol(volume_24h=100.0, aggregator_volume_24h=400.0)
        self.assertEqual(render.volume_24h(protocol), 400.0)


class FakeClient:
    """Stands in for DefiLlama with a hand-built two-protocol ecosystem."""

    def protocols(self):
        return [
            {
                "id": "1",
                "slug": "kamino-lend",
                "name": "Kamino Lend",
                "category": "Lending",
                "chains": ["Solana"],
                "chainTvls": {"Solana": 1_400_000_000.0},
                "change_1d": 0.8,
                "change_7d": 7.3,
            },
            {
                "id": "2",
                "slug": "dust-protocol",
                "name": "Dust Protocol",
                "category": "Dexs",
                "chains": ["Solana"],
                "chainTvls": {"Solana": 4_000.0},
                "change_7d": 900.0,
            },
            {
                "id": "3",
                "slug": "binance-cex",
                "name": "Binance CEX",
                "category": "CEX",
                "chains": ["Solana"],
                "chainTvls": {"Solana": 7_000_000_000.0},
            },
            {
                "id": "4",
                "slug": "uniswap",
                "name": "Uniswap",
                "category": "Dexs",
                "chains": ["Ethereum"],
                "chainTvls": {"Ethereum": 3_000_000_000.0},
            },
        ]

    def dex_overview(self):
        return {
            "total24h": 3_000_000_000.0,
            "total7d": 20_000_000_000.0,
            "change_7dover7d": 13.9,
            "protocols": [
                {
                    "defillamaId": "1",
                    "name": "Kamino Lend",
                    "total24h": 250_000_000.0,
                    "total30d": 7_000_000_000.0,
                    "change_7dover7d": 22.0,
                    "change_30dover30d": 31.0,
                },
                {
                    "slug": "newcomer-dex",
                    "displayName": "Newcomer DEX",
                    "category": "Dexs",
                    "total24h": 40_000_000.0,
                    "total30d": 900_000_000.0,
                    "change_7dover7d": 88.0,
                    "change_30dover30d": 140.0,
                },
            ],
        }

    def aggregator_overview(self):
        return {"total24h": 1_200_000_000.0, "change_7dover7d": 6.8, "protocols": []}

    def fees_overview(self):
        return {
            "total24h": 18_000_000.0,
            "total30d": 420_000_000.0,
            "protocols": [
                {
                    "defillamaId": "1",
                    "name": "Kamino Lend",
                    "total24h": 500_000.0,
                    "total30d": 12_000_000.0,
                    "change_30dover30d": 40.0,
                }
            ],
        }

    def revenue_overview(self):
        return {"total24h": 7_000_000.0, "protocols": []}

    def chain_overview(self):
        return {"name": "Solana", "tvl": 6_500_000_000.0}

    def chain_tvl_history(self):
        now = int(time.time())
        return [{"date": now - day * 86400, "tvl": 5_000_000_000.0 + day * 1_000_000.0} for day in range(120, -1, -1)]

    def protocol_histories(self, slugs):
        now = int(time.time())
        return {
            slug: [
                {"date": now - day * 86400, "tvl": 1_000_000_000.0 + (120 - day) * 3_000_000.0}
                for day in range(120, -1, -1)
            ]
            for slug in slugs
        }


class TestCollect(unittest.TestCase):
    def setUp(self):
        self.snapshot = aggregate.collect(FakeClient(), history_limit=5)
        self.by_slug = {p.slug: p for p in self.snapshot.protocols}

    def test_only_solana_protocols_survive(self):
        self.assertNotIn("uniswap", self.by_slug)

    def test_cex_is_excluded_by_default(self):
        self.assertNotIn("binance-cex", self.by_slug)

    def test_cex_can_be_kept_explicitly(self):
        kept = aggregate.collect(FakeClient(), history_limit=0, exclude_categories=[])
        self.assertIn("binance-cex", {p.slug for p in kept.protocols})

    def test_sub_threshold_protocols_are_dropped(self):
        self.assertNotIn("dust-protocol", self.by_slug)

    def test_volume_only_protocol_gets_a_record(self):
        newcomer = self.by_slug["newcomer-dex"]
        self.assertEqual(newcomer.name, "Newcomer DEX")
        self.assertIsNone(newcomer.tvl)
        self.assertEqual(newcomer.volume_24h, 40_000_000.0)

    def test_overview_rows_merge_onto_tvl_records_by_id(self):
        kamino = self.by_slug["kamino-lend"]
        self.assertEqual(kamino.volume_24h, 250_000_000.0)
        self.assertEqual(kamino.fees_30d, 12_000_000.0)
        self.assertEqual(kamino.fees_change_30d, 40.0)

    def test_history_backfills_thirty_day_change(self):
        kamino = self.by_slug["kamino-lend"]
        self.assertIsNotNone(kamino.tvl_change_30d)
        self.assertGreater(kamino.tvl_change_30d, 0)

    def test_capital_turnover_is_volume_over_tvl(self):
        kamino = self.by_slug["kamino-lend"]
        self.assertAlmostEqual(kamino.capital_turnover, 5.0)

    def test_chain_metrics_are_populated(self):
        self.assertEqual(self.snapshot.chain_tvl, 6_500_000_000.0)
        self.assertIsNotNone(self.snapshot.chain_tvl_change_30d)
        self.assertEqual(self.snapshot.aggregator_volume_24h, 1_200_000_000.0)

    def test_protocols_are_sorted_by_tvl(self):
        tvls = [p.tvl or 0 for p in self.snapshot.protocols]
        self.assertEqual(tvls, sorted(tvls, reverse=True))


class TestExport(unittest.TestCase):
    def setUp(self):
        self.snapshot = aggregate.collect(FakeClient(), history_limit=5)

    def test_json_carries_trend_and_established_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = export.write_json(self.snapshot, os.path.join(tmp, "snapshot.json"))
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
        self.assertIn("chain", payload)
        self.assertTrue(all("trend" in p and "established" in p for p in payload["protocols"]))

    def test_csv_has_one_row_per_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = export.write_csv(self.snapshot, os.path.join(tmp, "protocols.csv"))
            with open(path, encoding="utf-8") as fh:
                lines = [line for line in fh.read().splitlines() if line]
        self.assertEqual(len(lines), len(self.snapshot.protocols) + 1)

    def test_history_log_keeps_one_entry_per_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "history.jsonl")
            export.append_history(self.snapshot, path)
            export.append_history(self.snapshot, path)
            with open(path, encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh if line.strip()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["chain_tvl"], 6_500_000_000.0)

    def test_markdown_report_renders_all_sections(self):
        text = render.markdown_report(self.snapshot)
        for heading in ("# Solana Growth Tracker", "## Chain overview", "## Fastest growing"):
            self.assertIn(heading, text)
        self.assertIn("Kamino Lend", text)


if __name__ == "__main__":
    unittest.main()
