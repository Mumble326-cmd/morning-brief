# morning-brief

Daily automated news briefing for 6 clients (HNB, Hayleys, MAS, BYD, MIFL, Port City Colombo). Fetches from Google News RSS, filters by Sri Lanka relevance, classifies stories, detects duplicates, ranks sources, and generates an interactive HTML dashboard.

## Features

- **Morning-brief-first layout** — the default view answers "what happened since yesterday?": an executive summary strip of the top-ranked stories across all clients, then per-client sections showing NEW-since-last-run coverage (or an explicit "No new coverage" line). Older stories collapse into a "Previously reported" block per client.
- **Daily automation** via GitHub Actions (6:30 AM Sri Lanka time)
- **6 client briefings** with separate governance (keywords, exclusions, priority sources)
- **Story classification** into 5 categories: Direct Mention, Industry, Market Watch, Risk Watch, Low Relevance
- **Compound relevance scoring** (category weight × match strength × source rank × freshness decay) driving story order everywhere, including the executive summary
- **Noise suppression** — recurring time-series posts (daily CBSL exchange rate, market close) roll up to a single line; per-client caps on filler categories (max 5 industry / 3 market-watch cards a day); a global sports/junk exclude layer; low-relevance stories never render (kept in JSON for audit); outlet boilerplate stripped from headlines
- **Duplicate detection** using normalized title comparison + date proximity
- **Cluster grouping** showing "Also covered by" for stories from multiple sources
- **Source ranking** (1-5 scale) preferring local news authority outlets
- **Archive system** saving daily snapshots to `data/archive/YYYY-MM-DD.json`
- **Offline replay harness** — `python brief.py --replay [DATE]` regenerates any archived morning through the full pipeline with no network; `python replay_checks.py` asserts the product guarantees against the result
- **Privacy protection** ensuring no journalist contact information in output
- **Interactive filters** for time window, client, category, and full-text search
- **Minimal dependencies** — only `feedparser` (for robust RSS/Atom parsing; optional for replay); everything else is Python standard library

## Quick Start

### Prerequisites
- Python 3.11+
- Git

### Local Run
```bash
python brief.py
```
Generates `index.html` + `data/latest.json` + `data/archive/YYYY-MM-DD.json`

### Offline Replay (no network needed)
```bash
python brief.py --replay              # replay the newest archived morning
python brief.py --replay 2026-07-07   # replay a specific date
python replay_checks.py [DATE]        # replay + assertion suite (exit 1 on failure)
```
Rebuilds the raw story pool from `data/archive/DATE.json` and pushes it back
through the identical classification → scoring → dedup → rollup → render
pipeline the live run uses. Writes `index.html` + `data/latest.json`; dated
archives are never overwritten by a replay.

### Automated Run
GitHub Actions triggers daily at 6:30 AM (SL time). Workflow defined in `.github/workflows/daily-brief.yml`.

## Configuration

### Keywords (`keywords.json`)
Defines what stories to fetch for each client. Structure:
```json
{
  "hnb": {
    "label": "HNB",
    "sector": "Banking",
    "direct_mentions": ["HNB", "Hatton National Bank", ...],
    "industry_watch": ["CBSL", "monetary policy", ...],
    "market_watch": ["stock market", "CSE", ...],
    "risk_watch": ["HNB fraud", "banking scandal", ...],
    "exclude": ["horse racing", "sports", ...],
    "priority_sources": ["Daily FT", "EconomyNext", ...]
  }
}
```

**Categories:**
- `direct_mentions`: Exact company/brand names (highest relevance)
- `industry_watch`: Sector trends, competitors, regulations
- `market_watch`: Stock prices, indices, market data (lower relevance)
- `risk_watch`: Fraud, scandal, investigation stories (separate tracking)
- `exclude`: Noise patterns to filter (sports, cricket, etc.)

### Outlets (`outlets.json`)
Source ranking configuration. Tiers:
- **Rank 1** (priority): Daily FT, Mirror, Island, News, Sunday Times, EconomyNext, LBO, etc.
- **Rank 2** (accepted): Other local newspapers
- **Rank 3** (international): Reuters, BBC, Al Jazeera
- **Rank 4** (aggregators): Magzter, MSN, MarketScreener
- **Rank 5** (blocked): Spam/unusable

### Config (`config.py`)
Static settings: client list, window (30 days), max stories, SL signals, plus
the noise controls: `GLOBAL_EXCLUDE` (junk terms applied to every client),
`SERIES_PATTERNS` (recurring time-series detectors), and `CATEGORY_CAPS`
(per-client per-day card caps for filler-prone categories).

## Output

### `index.html`
Interactive dashboard with:
- Executive summary strip — the top stories across all clients, new-first,
  ranked by compound score
- Per-client sections: NEW-since-last-run cards (or an explicit "No new
  coverage" line), one-line rollups for recurring updates, and a collapsed
  "Previously reported" block for everything older
- "Also covered by" links for duplicate clusters
- Filters: 1/7/14/30-day window, per-client view, category filter
- Full-text search
- Responsive design with print-friendly styling

### `data/latest.json`
Current briefing snapshot (stories, clusters, metadata). Used for archival + trend analysis.

### `data/archive/YYYY-MM-DD.json`
Daily snapshots for historical tracking (identify trends, measure coverage over time).

## Architecture

```
Fetch (Google News RSS per keyword query)          ─┐ live run only —
  ↓ (SL relevance gate + date cutoff)               │ --replay rebuilds this
Parse & Extract (headline, snippet, source, link)  ─┘ pool from data/archive
  ↓
run_pipeline() — shared by live run and replay:
  Classify (mention/industry/market_watch/risk_watch/low_relevance,
            global + per-client excludes, boilerplate stripped)
  ↓
  Cluster (group duplicates by normalized title + date proximity)
  ↓
  Mark NEW (vs the previous archived run)
  ↓
  Roll up recurring series · compound scores · category caps
  ↓
  Archive (save to data/latest.json + dated archive)
  ↓
  Render (exec summary + new-first sections + collapsed history)
```

## Privacy & Safety

- **No contact storage**: Journalist names, emails, phone numbers excluded
- **No tracking**: Pure static HTML (no analytics, cookies, or beacons)
- **Validation**: Automated scan for leaked contact patterns
- **Open data**: Raw JSON archives available for manual review

## Development

### Testing
```bash
python replay_checks.py                   # Offline replay + assertion suite
python brief.py                           # Full live run (network)
python -m json.tool keywords.json         # Validate config
```

### Debugging
Enable diagnostic output in `brief.py`:
- Per-client story counts (kept/not-SL/too-old)
- Duplicate grouping summary
- Privacy validation warnings

### Key Functions (utils.py)
- `classify_story()`: Categorize story + relevance score
- `compound_score()`: Category × match × source × freshness ordering score
- `rollup_series()`: Collapse recurring time-series posts
- `apply_category_caps()`: Per-client filler caps
- `strip_headline_boilerplate()`: Remove aggregator branding from headlines
- `cluster_stories()`: Group duplicates
- `source_rank()`: Rank by outlet authority
- `save_archive()`: Persist to JSON
- `validate_no_private_contacts()`: Privacy check

## Files

```
brief.py              — Main generator (fetch → run_pipeline → render) + --replay harness
utils.py              — Helper functions (classification, scoring, rollup, clustering)
config.py             — Static settings (clients, window, SL signals, noise controls)
keywords.json         — Client keyword governance
outlets.json          — Media source ranking tiers
replay_checks.py      — Offline assertion suite (replays an archive, exit 1 on failure)
index.html            — Generated interactive dashboard (daily)
data/
  latest.json         — Current briefing (stories + clusters, incl. audit-only stories)
  archive/
    2026-06-11.json   — Daily snapshot (historical tracking, replay input)
.github/workflows/
  daily-brief.yml     — GitHub Actions automation (6:30 AM SL time)
```

## Future Enhancements

- Trend analysis dashboard (coverage by client/category over 30+ days)
- Sentiment analysis (positive/neutral/negative story tone)
- Entity extraction (people, companies, locations mentioned)
- API endpoint for programmatic access
- Slack/email integration for automated distribution
- Multi-language support (Tamil, Sinhala summaries)

## License

Internal tool for Adfactors PR.
