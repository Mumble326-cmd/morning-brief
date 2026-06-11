# morning-brief

Daily automated news briefing for 6 clients (HNB, Hayleys, MAS, BYD, MIFL, Port City Colombo). Fetches from Google News RSS, filters by Sri Lanka relevance, classifies stories, detects duplicates, ranks sources, and generates an interactive HTML dashboard.

## Features

- **Daily automation** via GitHub Actions (6:30 AM Sri Lanka time)
- **6 client briefings** with separate governance (keywords, exclusions, priority sources)
- **Story classification** into 5 categories: Direct Mention, Industry, Market Watch, Risk Watch, Low Relevance
- **Duplicate detection** using normalized title comparison + date proximity (2-hour window)
- **Cluster grouping** showing "Also covered by" for stories from multiple sources
- **Source ranking** (1-5 scale) preferring local news authority outlets
- **Archive system** saving daily snapshots to `data/archive/YYYY-MM-DD.json`
- **Privacy protection** ensuring no journalist contact information in output
- **Interactive filters** for time window, client, category, and full-text search
- **Zero external dependencies** (Python standard library only)

## Quick Start

### Prerequisites
- Python 3.11+
- Git

### Local Run
```bash
python brief.py
```
Generates `index.html` + `data/latest.json` + `data/archive/YYYY-MM-DD.json`

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
Static settings: client list, window (30 days), max stories, SL signals.

## Output

### `index.html`
Interactive dashboard with:
- Story cards showing headline, snippet, source, category, relevance score
- "Also covered by" links for duplicate clusters
- Filters: 7-day/14-day/30-day window, per-client view, category filter
- Full-text search
- Responsive design with print-friendly styling

### `data/latest.json`
Current briefing snapshot (stories, clusters, metadata). Used for archival + trend analysis.

### `data/archive/YYYY-MM-DD.json`
Daily snapshots for historical tracking (identify trends, measure coverage over time).

## Architecture

```
Fetch (Google News RSS per keyword query)
  ↓ (SL relevance gate + date cutoff)
Parse & Extract (headline, snippet, source, link)
  ↓
Classify (direct mention/industry/market_watch/risk_watch/low_relevance)
  ↓
Cluster (group duplicates by normalized title + date proximity)
  ↓
Rank Sources (prioritize local authority outlets)
  ↓
Archive (save to data/latest.json + dated archive)
  ↓
Render (build interactive HTML with category filters)
```

## Privacy & Safety

- **No contact storage**: Journalist names, emails, phone numbers excluded
- **No tracking**: Pure static HTML (no analytics, cookies, or beacons)
- **Validation**: Automated scan for leaked contact patterns
- **Open data**: Raw JSON archives available for manual review

## Development

### Testing
```bash
python brief.py                           # Full run
python -m json.tool keywords.json         # Validate config
python -c "import utils; print(dir(utils))" # Check functions
```

### Debugging
Enable diagnostic output in `brief.py`:
- Per-client story counts (kept/not-SL/too-old)
- Duplicate grouping summary
- Privacy validation warnings

### Key Functions (utils.py)
- `classify_story()`: Categorize story + relevance score
- `cluster_stories()`: Group duplicates
- `source_rank()`: Rank by outlet authority
- `save_archive()`: Persist to JSON
- `validate_no_private_contacts()`: Privacy check

## Files

```
brief.py              — Main generator (fetch → classify → cluster → render)
utils.py              — Helper functions (classification, clustering, ranking)
config.py             — Static settings (clients, window, SL signals)
keywords.json         — Client keyword governance
outlets.json          — Media source ranking tiers
index.html            — Generated interactive dashboard (daily)
data/
  latest.json         — Current briefing (stories + clusters)
  archive/
    2026-06-11.json   — Daily snapshot (historical tracking)
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
