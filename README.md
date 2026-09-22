# Solana Growth Tracker

Tracks TVL, DEX volume and protocol fees across the Solana ecosystem, then ranks
protocols by how fast they are actually growing — not just how big they are.

Two surfaces, one data pipeline:

- **CLI** — tables in the terminal, plus JSON/CSV/Markdown export.
- **Dashboard** — a static page (no build step, no dependencies) you can host on
  GitHub Pages or GitLab Pages.

Data comes from the public [DefiLlama](https://defillama.com/chain/Solana) API.
No API key required.

## Install

Python 3.9+ and nothing else. The tracker uses only the standard library.

```bash
git clone <this repo>
cd solana-growth-tracker
pip install -e .          # optional, gives you the `soltracker` command
```

Without installing, run it as a module:

```bash
PYTHONPATH=src python3 -m soltracker overview
```

## Use

```bash
soltracker overview              # chain summary + the headline tables
soltracker tvl --limit 30        # largest protocols by Solana TVL
soltracker volume                # highest 24h volume
soltracker growth                # fastest growing, by momentum score
soltracker growth --category Lending --category Dexs
soltracker export                # writes dashboard data, CSV and REPORT.md
```

Useful flags (they work before or after the subcommand):

| Flag | What it does |
|---|---|
| `--limit N` | rows per table |
| `--history N` | fetch TVL history for the N largest protocols (enables 30d/90d changes) |
| `--min-tvl` / `--min-volume` | relevance floor for inclusion |
| `--category` / `--exclude-category` | filter by DefiLlama category |
| `--include-small` | let sub-threshold protocols onto the growth board |
| `--no-cache` | skip the on-disk response cache |
| `--json` | dump the whole snapshot as JSON |

## Dashboard

```bash
soltracker export        # refresh web/data/
node web/serve.js        # http://localhost:8777
```

The page reads `web/data/snapshot.json` and renders everything client-side, so
publishing it is just a matter of serving the `web/` directory.

## The momentum score

Size and growth are different questions. A $1.4B lending market growing 2% a
month and a $40M perps venue tripling its volume both matter, but only one of
them shows up in a TVL leaderboard.

The score blends five signals into one 0-100 number where **50 means flat**:

| Signal | Weight | Why |
|---|---|---|
| TVL 7d | 0.20 | short-term capital flow |
| TVL 30d | 0.22 | sticky capital, the slowest signal to fake |
| Volume 7d over 7d | 0.22 | fast, noisy, reacts first |
| Volume 30d over 30d | 0.16 | smooths out a single hot week |
| Fees 30d over 30d | 0.20 | revenue is the hardest signal to fake |

Each percentage change goes through `tanh` before it is weighted, so a 10x pump
ranks above a 2x but cannot drown out every other signal. Missing signals are
dropped and the remaining weights renormalise; below 35% coverage the protocol
gets no score at all rather than a misleading one.

Two guardrails keep the board honest:

- **CEX wallets are excluded.** DefiLlama reports exchange balances against
  Solana — Binance alone books more "TVL" than the entire chain's DeFi.
- **Size floors.** A protocol needs $5M TVL, $100M of 30d volume, or $250k of
  30d fees to be ranked. Otherwise a $20k protocol doubling overnight tops the
  list every single day. Pass `--include-small` to see them anyway.

## Automation

Both CI configs are wired up:

- `.github/workflows/update.yml` — refreshes the data daily, commits the new
  snapshot, and deploys the dashboard to GitHub Pages.
- `.gitlab-ci.yml` — runs the tests and publishes the dashboard to GitLab Pages
  with data generated at build time.

Every refresh appends one row to `web/data/history.jsonl`, so the repository
slowly becomes its own longitudinal dataset — a record of what the ecosystem
looked like on a given day that no API backfill can revise away.

## Tests

```bash
python3 -m unittest discover -s tests
```

All tests are offline; the DefiLlama client is replaced with an inline fixture.

## Caveats

- `tvl_change_1d` and `tvl_change_7d` come straight from DefiLlama and are
  chain-agnostic. For multi-chain protocols they reflect total TVL, not the
  Solana slice. The 30d/90d changes are computed from the Solana-only series.
- Aggregator volume overlaps DEX volume by design (an aggregator routes into the
  same pools), so the two are reported separately and never summed.
- Perps data needs a paid DefiLlama plan, so it is not included.

## Licence

MIT
